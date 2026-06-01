---
name: score-skeleton
description: >-
  Source score PDF → MusicXML (.mxl) with chord symbols.
  OpenCV detects staff systems and barline x-boundaries without fixed stave count,
  then LLM vision reads per-measure crops with explicit numeric barline boundaries.
  Output preserves the source PDF's system/page layout and forces chord display text via chordKindStr.
---

# Score Skeleton Transcription

```
Pipeline:
  1. PDF → PNG                    (pdftoppm -r 300, all pages first)
  2. OpenCV structure detection    (staffs → dynamic systems → barline x-boundaries)
  3. Per-measure crop → LLM Vision (crop by detected barlines; pass x-boundaries)
  4. .mxl generation               (metadata + breaks + ChordSymbol + chordKindStr)
```

**Run by phase across all pages. Do not do page 1 phase 1→4, then page 2 phase 1→4.**

Do not assume a fixed number of staves per system. Detect staff candidates first, group them into systems by vertical gaps, and record `stave_count` per system. Use system-start measure numbers as a verification/correction signal when visible.

---

## 1. PDF → PNG

```bash
cp "원본파일.pdf" source.pdf
mkdir -p _scratch
pdftoppm -png -r 300 source.pdf _scratch/page
```

---

## 2. OpenCV structure detection

`detect_structure.py` is a bundled script in this skill directory's `scripts/`. **Do not copy it by default.** Run it directly from the score workdir so `_scratch` input/output remains relative to the workdir.

```bash
# Run from the score workdir. Substitute <skill_dir> with skill_view('score-skeleton').skill_dir.
for pn in $(seq 1 $N); do
    .venv/bin/python3 <skill_dir>/scripts/detect_structure.py $pn
done
```

Copy the script into the workdir only when modifying/experimenting with the detector. Do not hard-code user/profile absolute paths in SKILL.md.

### System-start measure-number verification

If measure numbers appear at the beginning of each system, use the page image as a verification pass before chord reading:

```text
Find system-start measure numbers on this page. Return JSON only:
[{"measure": 1, "y": 310}, {"measure": 5, "y": 780}]
Use approximate y center of the measure number/start of system.
```

Compare those y-positions with `systems[*].first_staff_top` / `y0_page`. They should increase in the same order. If a visible measure-number anchor falls inside the wrong detected system band, fix the system grouping before producing measure crops.

### Detection model

- Staff detection: horizontal projection → staff-line clustering, spacing 13-21px, ±4 tolerance.
- System grouping: sort detected staves by y-position, compute adjacent vertical gaps, split systems at the large between-system gaps. `stave_count` is an output, not an input assumption.
- Measure-number anchors: when system-start measure numbers are visible, read their approximate y-positions from page vision and compare with detected system starts. If a measure-number y lies between two grouped systems or a detected system lacks the expected start number, inspect/correct grouping before chord reading.
- Barline detection: vertical morphological open, kernel height = `system_height * 0.4`.
- Compound grouping: nearby vertical lines within 20px merge into one boundary.
- Repeat dots: search ±35px around compound center; connected components with area 20-120px² and circularity ≥ 0.5.

Output:

```json
{
  "page": 1,
  "systems": [
    {
      "system_idx": 0,
      "y0_page": 123,
      "y1_page": 456,
      "first_staff_top": 210,
      "stave_count": 2,
      "staves": [
        {"top": 210, "bot": 278, "line_count": 5},
        {"top": 318, "bot": 386, "line_count": 5}
      ],
      "num_measures": 4,
      "barlines": [
        {"type": "system_start", "x": 120, "num_lines": 1, "dots_left": 0, "dots_right": 0},
        {"type": "thin", "x": 520, "num_lines": 1, "dots_left": 0, "dots_right": 0}
      ],
      "measure_gaps": [
        {"gap_idx": 0, "x0": 120, "x1": 520, "left_type": "system_start", "right_type": "thin", "width": 400}
      ]
    }
  ]
}
```

`measure_gaps` are consecutive barline gaps. They are the source for per-measure crops and measure numbering.

---

## 3. Per-measure crop → LLM Vision

### 3A. Build measure gap list from structure.json

Do not ask the LLM to decide where measures begin/end. The structure detector owns measure boundaries. The LLM only reads chord text inside a known gap.

```python
import json, os, re
from glob import glob
import cv2

struct_files = sorted(glob('_scratch/p*_struct/structure.json'))
measure_entries = []

for fpath in struct_files:
    pn = int(re.search(r'p(\d+)_struct', fpath).group(1))
    data = json.load(open(fpath, encoding='utf-8'))
    for sys in data['systems']:
        for gap in sys.get('measure_gaps', []):
            entry = {
                'page': pn,
                'system_idx': sys['system_idx'],
                'gap_idx': gap['gap_idx'],
                'y0': sys['y0_page'],
                'y1': sys['y1_page'],
                'x0': gap['x0'],
                'x1': gap['x1'],
                'left_type': gap['left_type'],
                'right_type': gap['right_type'],
                'width': gap['width'],
                'skip': False,
            }
            measure_entries.append(entry)
```

### 3B. Repeat-start pseudo gap handling

Never discard a gap only because it has no chord symbols. Chordless real measures exist.

Only skip a gap when it is structurally/visually the setup area before a repeat start, i.e. the gap is between the system start and an immediate start-repeat sign and contains clef/key/time setup rather than a real measure:

```text
system_start | clef/key/time setup pseudo-gap | start_repeat | first real measure ...
```

Safe rule:

- Candidate only when `gap_idx == 0`, `left_type == 'system_start'`, and `right_type == 'start_repeat'`.
- Verify visually/geometrically that this is the narrow clef/key/time setup gap.
- Do **not** skip a full-width first measure just because it has no chord.

After deciding skips, assign global measure numbers only to non-skipped entries:

```python
mn = 1
for e in measure_entries:
    if e['skip']:
        continue
    e['measure'] = mn
    mn += 1
MEASURE_COUNT = mn - 1
```

### 3C. Crop each measure from the full system image

Crop by the detected barline x-boundaries. Include a small horizontal pad so chord symbols near the barline are not clipped, but keep the prompt explicit that the real measure is `x0..x1`.

```python
os.makedirs('_scratch/measures', exist_ok=True)
PAD_X = 16

for e in measure_entries:
    if e.get('skip'):
        continue
    img = cv2.imread(f"_scratch/page-{e['page']}.png")
    h, w = img.shape[:2]
    x0 = max(0, e['x0'] - PAD_X)
    x1 = min(w, e['x1'] + PAD_X)
    crop = img[e['y0']:e['y1'], x0:x1]
    out = f"_scratch/measures/p{e['page']}_s{e['system_idx']}_g{e['gap_idx']}_M{e['measure']}.png"
    cv2.imwrite(out, crop)
    e['crop_path'] = out
```

### 3D. LLM Vision prompt

Process all measure crops in one phase. Multiple `vision_analyze` calls may be sent in the same assistant turn when possible. Each crop is independent.

Prompt template:

```text
This image is one measure crop from page {page}, system {system_idx}, gap {gap_idx}.
Global measure: M{measure}.
The original system barline boundaries are x={x0}..{x1}; left boundary type={left_type}, right boundary type={right_type}.
Read chord symbols inside this one measure only. Do not split or merge measures.
Return JSON only: [{"chord": "A", "beat": 1.0}, {"chord": "C#m7", "beat": 3.0}]
If there are no chord symbols in this measure, return []. Exact chord text.
```

Collect results into:

```python
chord_map = {
    1: [('A', 1.0), ('C#m7', 3.0)],
    2: [],
}
```

---

## 4. .mxl generation

### 4A. Break map from measure entries

Derive system/page breaks from the first non-skipped measure of each detected system. Do not maintain a separate manual STRUCTURE dict.

```python
sys_breaks = set()
pg_breaks = set()
seen_systems = set()
seen_pages = set()

for e in measure_entries:
    if e.get('skip'):
        continue
    key = (e['page'], e['system_idx'])
    if key not in seen_systems:
        if e['measure'] > 1:
            sys_breaks.add(e['measure'])
        seen_systems.add(key)
    if e['page'] not in seen_pages:
        if e['measure'] > 1:
            pg_breaks.add(e['measure'])
        seen_pages.add(e['page'])
```

### 4B. Metadata

Extract title/composer/arranger/etc. from the visible top area of page 1 when possible. Use only facts visible in the source score. Do not invent metadata from filename guesses.

```python
score = stream.Score()
score.metadata = metadata.Metadata()
score.metadata.title = TITLE or ''
score.metadata.composer = COMPOSER or ''
```

### 4C. Skeleton

```python
from music21 import *

part = stream.Part()
part.partName = 'Voice'
part.append([
    clef.TrebleClef(),
    key.KeySignature(KEY_SHARPS),
    meter.TimeSignature(TIME_SIG),
])

for n in range(1, MEASURE_COUNT + 1):
    m = stream.Measure(number=n)
    if n in pg_breaks:
        m.insert(0, layout.PageLayout(isNew=True))
        m.insert(0, layout.SystemLayout(isNew=True))
    elif n in sys_breaks:
        m.insert(0, layout.SystemLayout(isNew=True))
    m.append(note.Rest(quarterLength=BAR_QL))
    part.append(m)

score.insert(0, part)
score2 = converter.parse(score.write('musicxml', '_base.mxl'))
```

### 4D. Chord injection

```python
import re

def norm(cn):
    cn = re.sub(r'\s+', '', cn)
    cn = re.sub(r'[()]', '', cn)
    return cn

prev_root = ''
for mn, chords in sorted(chord_map.items()):
    m = score2.parts[0].measure(mn)
    for cn, beat in chords:
        cn = norm(cn)
        if cn.startswith('/') and len(cn) > 1 and prev_root:
            cn = f'{prev_root}{cn}'
        offset = (float(beat) - 1.0) * 1.0  # beat 1 -> offset 0.0 in 4/4 quarter-note beat units
        cs = harmony.ChordSymbol(cn)
        cs.chordKindStr = cn  # required: force display text, e.g. E7sus4 stays E7sus4
        m.insert(offset, cs)  # insertion offset is the source of truth
        prev_root = cn.split('/')[0]

score2.write('musicxml', 'final.mxl')
```

`cs.chordKindStr = cn` is required. Without it, music21 may serialize readable chord kinds such as `suspended-fourth-seventh` instead of the desired display text `E7sus4`.

- Always set `chordKindStr`, even for standard codes like `DM7`, `F#m7`, `Bm7`.
- `DM7` → `ChordSymbol('DM7')` + `chordKindStr = 'DM7'`.
- Remove parentheses before constructing `ChordSymbol`: `(add9)` → `add9`.

### 4E. Verify

```python
s3 = converter.parse('final.mxl')
actual = sum(
    1
    for me in s3.parts[0].getElementsByClass(stream.Measure)
    for e in me.recurse()
    if isinstance(e, harmony.ChordSymbol)
)
expected = sum(len(v) for v in chord_map.values())
assert actual == expected, (actual, expected)
print(f'{actual} chords in final.mxl')
```

---

## Notes

- **Phase order:** finish all pages in each phase before moving to the next phase.
- **300dpi required** unless detector parameters are recalibrated.
- **Measure ownership:** OpenCV/barline x-boundaries define measures; LLM reads chord text only.
- **Per-measure crop:** preferred for chord accuracy. Do not let the LLM hallucinate measure grouping from a full system.
- **No chord ≠ not a measure.** Preserve chordless measures unless the gap is structurally verified as a setup pseudo-gap.
- **Parallel vision:** batch independent measure crops in the same assistant turn when possible.
- **Generator script:** `gen_mxl.py`/`gen_xml.py` is a workdir-local temporary artifact. The skill requirement is the pattern: metadata, `measure_entries → breaks`, `ChordSymbol(cn)`, `cs.chordKindStr = cn`, final write, verification.
- **Layout natural flow:** derive system/page breaks from structure-derived measure entries. No manual break map.
- **No personal absolute paths** in reusable skill text.
- **File delivery:** deliver the final `.mxl` through the requested channel when possible; if Discord fails to attach unusual extensions, share the workdir path or use Telegram.
