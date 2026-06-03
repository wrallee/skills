---
name: score-skeleton
description: >-
  Source score PDF → MusicXML (.mxl) with chord symbols.
  OpenCV detects structure → PaddleOCR reads chord symbols from per-measure crops → music21 generates .mxl. Vision LLM used as fallback only when OCR fails.
---

# Score Skeleton

## Prerequisites (HARD STOP if missing)
- `STAVES_PER_SYSTEM` — user-provided, do not infer
- `EXPECTED_MEASURE_COUNT` — user-provided, do not count by eye

Use `session_search` to check if the user already gave these in the current thread.

## Pitfalls
- **Don't over-verify with vision.** OCR + reasonable regex filtering catches ~95%+ of chords. If a handful of chords look wrong, generate the `.mxl` and let the user review — they'll tell you what to fix. Spending 10+ vision calls on per-chord verification frustrates the user ("답안지 없이 못할거같네").
- **OCR misses # on sharp keys.** PaddleOCR can miss the `#` glyph in 4+ sharp keys (E major, B major, etc.), reading `F` instead of `F#`, `C` instead of `C#`. After OCR, flag single-letter chords that are diatonic sharps in the key signature — verify with vision only for those, or note them for user review.
- **`(add9)` parentheses.** music21 rejects `A(add9)` — strip parens to `Aadd9` before `ChordSymbol()`.

## Pipeline (run by phase across ALL pages)

### 1. PDF → PNG
```bash
cp "원본파일.pdf" source.pdf && mkdir -p _scratch
pdftoppm -png -r 300 source.pdf _scratch/page
```

### 2. OpenCV structure detection
Script: `<skill_dir>/scripts/detect_structure.py`. Run from workdir:
```bash
for pn in $(seq 1 $N); do
    .venv/bin/python3 <skill_dir>/scripts/detect_structure.py $pn --staves-per-system "$STAVES_PER_SYSTEM"
done
```
Output per page: JSON `systems[]` with `y0_page`, `y1_page`, `first_staff_top`, `barlines[]`, `measure_gaps[]`.

### 3. Build measure entries & crops

```python
import json, re, cv2
from glob import glob

# Parse structure JSONs
struct_files = sorted(glob('_scratch/p*_struct/structure.json'))
entries = []
for fpath in struct_files:
    pn = int(re.search(r'p(\d+)_struct', fpath).group(1))
    data = json.load(open(fpath))
    for sys in data['systems']:
        for gap in sys.get('measure_gaps', []):
            entries.append(dict(page=pn, system_idx=sys['system_idx'], gap_idx=gap['gap_idx'],
                y0=sys['y0_page'], y1=sys['y1_page'], first_staff_top=sys['first_staff_top'],
                x0=gap['x0'], x1=gap['x1'], left_type=gap['left_type'], right_type=gap['right_type'],
                width=gap['width'], skip=False))

# Pseudo-gap: clef/key/time setup before start_repeat
for e in entries:
    if e['gap_idx']==0 and e['left_type']=='system_start' and e['right_type']=='start_repeat':
        e['skip'] = True

mn = 1
for e in entries:
    if e.get('skip'): continue
    e['measure'] = mn; mn += 1
assert mn-1 == EXPECTED_MEASURE_COUNT, (mn-1, EXPECTED_MEASURE_COUNT)

# Crop: PAD_X=30 (16 can truncate chord text), TOP_MARGIN=50, bottom=first_staff_top+127
import cv2, os
os.makedirs('_scratch/measures', exist_ok=True)
PAD_X, TOP, BOT = 30, 50, 127
for e in entries:
    if e.get('skip'): continue
    img = cv2.imread(f"_scratch/page-{e['page']}.png")
    h,w = img.shape[:2]
    y1 = min(h, e['first_staff_top'] + BOT)
    crop = img[max(0,e['y0']-TOP):y1, max(0,e['x0']-PAD_X):min(w,e['x1']+PAD_X)]
    e['crop_path'] = f"_scratch/measures/p{e['page']}_s{e['system_idx']}_g{e['gap_idx']}_M{e['measure']}.png"
    cv2.imwrite(e['crop_path'], crop)
```

### 4. Chord reading: PaddleOCR → vision fallback

PaddleOCR requires Python 3.11. Separate venv:
```bash
python3.11 -m venv /path/to/paddle_venv && /path/to/paddle_venv/bin/pip install "paddlepaddle<3.0" "paddleocr<3.0"
```

**Normalize BEFORE regex.** PaddleOCR outputs spaces (`D M7`), unicode accidentals (`♯`), lowercase roots (`c#`), and parenthesized add chords (`A(add9)`):
```python
def norm(s):
    s = re.sub(r'\s+', '', s).replace('♭','b').replace('♯','#')
    s = re.sub(r'\(add(\d+)\)', r'add\1', s)  # A(add9) -> Aadd9
    s = s.replace('(', '').replace(')', '')    # stray parens
    if s and s[0].isalpha(): s = s[0].upper() + s[1:]  # c#→C#
    return s
```

**Regex must accept `a-g`** (lowercase roots on small crops):
```python
import re
C_RE = re.compile(r'^[A-Ga-g][#b]?(m|M|dim|aug|sus|add)?[0-9]?(sus|add|dim|aug|M|m)?[0-9]*(#[0-9]+|b[0-9]+)*(/[A-Ga-g][#b]?)?$')
S_RE = re.compile(r'^/[A-Ga-g][#b]?$')
def is_chord(raw):
    n = norm(raw)
    return bool(n and (C_RE.match(n) or S_RE.match(n) or re.match(r'^[A-Ga-g][#b]?$', n)))
```

**Main loop:**
```python
from paddleocr import PaddleOCR
ocr = PaddleOCR(use_angle_cls=False, lang='en', show_log=False)
chord_map = {}
for e in entries:
    if e.get('skip'): continue
    r = ocr.ocr(e['crop_path'], cls=False)
    chords = []
    if r and r[0]:
        for line in r[0]:
            t = line[1][0].strip()
            if is_chord(t): chords.append((norm(t), line[1][1]))
    if not chords:
        # vision_analyze fallback on same crop
        # see "Vision fallback" below
        chords = []
    chord_map[e['measure']] = chords
```

**Beat assignment** (PaddleOCR provides no timing):

| Time sig | 1 chord | 2 chords |
|----------|---------|----------|
| 4/4 | 1.0 | 1.0, 3.0 |
| 3/4 | 1.0 | 1.0, 3.0 |
| 6/8 | 1.0 | 1.0, 4.0 |
| other | 1.0 | even division |

Deduplicate: same normalized text within 50px vertical → keep higher conf.

**Vision fallback** — call `vision_analyze` on same crop when:
- PaddleOCR returned text but zero chord candidates (chord likely missed)
- All candidates < 0.5 confidence
- Lone single-letter result near crop top (section marker, not chord)

```text
This image is one measure crop. Global measure: M{measure}.
Read chord symbols only. Return JSON: [{"chord":"","beat":1.0}] or [].
```

### 5. .mxl generation

**Breaks:**
```python
sys_br, pg_br = set(), set()
seen_sys, seen_pg = set(), set()
for e in entries:
    if e.get('skip'): continue
    k = (e['page'], e['system_idx'])
    if k not in seen_sys:
        if e['measure'] > 1: sys_br.add(e['measure'])
        seen_sys.add(k)
    if e['page'] not in seen_pg:
        if e['measure'] > 1: pg_br.add(e['measure'])
        seen_pg.add(e['page'])
```

**Metadata + skeleton:**
```python
from music21 import *
from music21.harmony import ChordStepModification
score = stream.Score()
score.metadata = metadata.Metadata(); score.metadata.title = TITLE or ''; score.metadata.composer = COMPOSER or ''
part = stream.Part(); part.partName = 'Voice'
part.append([clef.TrebleClef(), key.KeySignature(KEY_SHARPS), meter.TimeSignature(TIME_SIG)])
for n in range(1, MEASURE_COUNT + 1):
    m = stream.Measure(number=n)
    if n in pg_br: m.insert(0, layout.PageLayout(isNew=True)); m.insert(0, layout.SystemLayout(isNew=True))
    elif n in sys_br: m.insert(0, layout.SystemLayout(isNew=True))
    m.append(note.Rest(quarterLength=4.0))
    part.append(m)
score.insert(0, part)
score2 = converter.parse(score.write('musicxml', '_base.mxl'))
```

**Chord injection + barlines → write → zip → 7sus4 post-process → verify:**
```python
from music21 import harmony
harmony.changeAbbreviationFor('major-seventh', 'M7')
harmony.changeAbbreviationFor('suspended-fourth', 'sus4')
harmony.changeAbbreviationFor('suspended-fourth-seventh', '7sus4')

def kind_display(cs):
    mods = {(m.modType, m.degree, m.interval.semitones) for m in cs.chordStepModifications}
    if cs.chordKind == 'suspended-fourth' and ('add', 7, -1) in mods:
        cs.chordKindStr = harmony.getCurrentAbbreviationFor('suspended-fourth-seventh'); return
    kind = harmony.CHORD_ALIASES.get(cs.chordKind, cs.chordKind)
    abbr = harmony.getCurrentAbbreviationFor(kind) if kind in harmony.CHORD_TYPES else None
    if abbr: cs.chordKindStr = abbr

prev_full = ''
for mn_str in sorted(chord_map.keys(), key=int):
    m = score2.parts[0].measure(int(mn_str))
    if m is None: continue
    for cn, beat in chord_map[mn_str]:
        cn = norm(str(cn))
        if cn.startswith('/') and len(cn) > 1 and prev_full:
            cn = f'{prev_full}{cn}'
        m_sus = re.match(r'^([A-G][#b]?)(.*)7sus4?$', cn)
        if m_sus: cn = f'{m_sus.group(1)}sus4addb7'
        m_9sus = re.match(r'^([A-G][#b]?)9sus4$', cn)
        if m_9sus:
            cs = harmony.ChordSymbol(f'{m_9sus.group(1)}sus4')
            cs.addChordStepModification(ChordStepModification('add', 7, -1))
            cs.addChordStepModification(ChordStepModification('add', 9, 0))
            cs.chordKindStr = '9sus4'
            m.insert((float(beat)-1.0)*1.0, cs); prev_full = m_9sus.group(1); continue
        cs = harmony.ChordSymbol(cn); kind_display(cs)
        m.insert((float(beat)-1.0)*1.0, cs)
        if not cn.startswith('/'): prev_full = cn.split('/')[0] if '/' in cn else cn

for e in entries:
    if e.get('skip'): continue
    m = score2.parts[0].measure(e['measure'])
    if m is None: continue
    nxt = [e2 for e2 in entries if not e2.get('skip') and e2['page']==e['page'] and e2['system_idx']==e['system_idx'] and e2['measure']>e['measure']]
    if not nxt:
        if e['right_type'] == 'final': m.rightBarline = bar.Barline('light-heavy')
        elif e['right_type'] == 'end_repeat': m.rightBarline = bar.Repeat(direction='end')
        elif e['right_type'] == 'double': m.rightBarline = bar.Barline('light-light')
for e in entries:
    if e.get('skip') and e['right_type'] == 'start_repeat':
        nxt = [e2 for e2 in entries if not e2.get('skip') and e2['page']==e['page'] and e2['system_idx']==e['system_idx'] and e2['gap_idx']>e['gap_idx']]
        if nxt:
            nm = score2.parts[0].measure(nxt[0]['measure'])
            if nm: nm.leftBarline = bar.Repeat(direction='start')

score2.write('musicxml', '_raw.musicxml')

import xml.etree.ElementTree as ET
import zipfile

# 7sus4 post-process
tree = ET.parse('_raw.musicxml')
for he in tree.iter('harmony'):
    k = he.find('kind')
    if k is not None and k.text == 'suspended-fourth' and k.get('text') == '7sus4':
        has7 = any(d.find('degree-value') is not None and d.find('degree-value').text == '7' for d in he.findall('degree'))
        if not has7:
            d = ET.SubElement(he, 'degree')
            ET.SubElement(d, 'degree-value').text = '7'; ET.SubElement(d, 'degree-alter').text = '0'; ET.SubElement(d, 'degree-type').text = 'add'
tree.write('_out.musicxml', encoding='UTF-8', xml_declaration=True)

# Zip as .mxl (.mxl = compressed MusicXML, opens natively in MuseScore/Finale/Sibelius)
with zipfile.ZipFile('final.mxl', 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.write('_out.musicxml', 'Score.musicxml')
    zf.writestr('META-INF/container.xml', '<?xml version="1.0"?><container><rootfiles><rootfile full-path="Score.musicxml"/></rootfiles></container>')

# Verify
s3 = converter.parse('final.mxl')
ac = sum(1 for m in s3.parts[0].getElementsByClass(stream.Measure) for e in m.recurse() if isinstance(e, harmony.ChordSymbol))
assert len(s3.parts[0].getElementsByClass(stream.Measure)) == EXPECTED_MEASURE_COUNT
assert ac == sum(len(v) for v in chord_map.values()), ac
print(f'{ac} chords in final.mxl')
```

## Notes
- **300dpi** required unless detector recalibrated.
- **music21 offset:** Negative `<offset sound="yes">` values are relative to rest END, not measure start. Not a bug.
- **References:** `references/paddleocr-setup.md`, `references/music21-harmony-display.md`, `references/musicxml-7sus4.md`, `references/detection-params-300dpi.md`, `references/repeat-sign-notation.md`.
- **Clean-slate:** On user request, remove `_scratch/`, `final.mxl`, `source.pdf`, local scripts. Preserve `.venv` & original PDF.
