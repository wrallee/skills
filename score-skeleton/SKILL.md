---
name: score-skeleton
description: >-
  Source score PDF → MusicXML (.mxl) with chord symbols.
  OpenCV detects structure → PaddleOCR reads chord symbols from per-measure crops → music21 generates .mxl. Vision LLM used as fallback only when OCR fails or confidence is low.
---

# Score Skeleton Transcription

**Input gate:** `STAVES_PER_SYSTEM` and `EXPECTED_MEASURE_COUNT` are required. Check `session_search` for the current thread first; if either value is missing, ask the user and stop. Do not infer stave count, count measures by eye, or start PDF conversion/detection/OCR/generation before both values are known.

**Pipeline:** PDF → PNG → OpenCV structure detection → PaddleOCR chord reading → vision fallback only when needed → `.mxl` generation → MusicXML post-process. Run each phase across all pages before moving to the next.

## Pitfalls

- **Don't over-verify with full vision.** Use vision only for conf < 0.8 (low/borderline OCR) and targeted sharp-key checks. For conf >= 0.8, keep the OCR text and let the custom MusicXML parser validate — do not vision-check every measure.
- **Borderline must use vision.** Do NOT auto-accept 0.5-0.8 conf chords even if they pass the whitelist and custom parser — the OCR text may be plausible-looking but wrong. Send to vision_analyze for confirmation.
- **No answer key.** Never use prior session data, reference files, or memory of "what should be there" to correct OCR output before presenting it to the user. The user explicitly considers this cheating and will reset the pipeline. Corrections come from vision_analyze or user input, not from prior knowledge.
- **When stuck, show the crop.** If a chord fails all automation (parse failure, slash-bass without context, ambiguous OCR), present the actual crop image to the user with MEDIA: — one item per message. Do not batch them or guess the intended chord.
- **OCR misses # on sharp keys.** PaddleOCR can miss the `#` glyph in 4+ sharp keys (E major, B major, etc.), reading `F` instead of `F#`, `C` instead of `C#`. After OCR, flag single-letter chords that are diatonic sharps in the key signature — verify with vision only for those, or note them for user review.
- **`(add9)` parentheses.** Normalize `A(add9)` → `Aadd9` before the custom MusicXML parser; do not leave this to music21's string parser.
- **Crop = first staff area only.** Crops run from system start (`y0`) to first staff bottom (`staves[0].bot`). This captures chord symbols above the staff while excluding lower staffs that add OCR noise. Use PAD_X=16 and do not add top/bottom margins by default. If you modify crop parameters, re-verify OCR output on a representative sample.
- **PaddleOCR scope = chord symbols only.** PaddleOCR reads printed chord text (`DM7`, `G/B`, `F#m`), not notation symbols. Full notation needs OMR; do not expand this pipeline beyond chords.
- **`key` name shadowing (4A/4C).** The break-map loop in section 4A uses a loop variable named `key`. When `from music21 import key` is used in section 4C, the loop variable shadows the import — later calls to `key.KeySignature()` fail with `AttributeError: 'tuple' object has no attribute 'KeySignature'`. Always name the loop variable `sys_key` or `k` to avoid the collision.
- **OCR digit confusion 7↔9.** PaddleOCR can misread `7` as `9`, but `9sus4` is also a legitimate printed chord. Do **not** auto-correct `9sus4` → `7sus4`. If confidence is <0.8 or the crop is visually ambiguous, verify via vision/user; otherwise parse `9sus4` as MusicXML `suspended-fourth` + added b7 + added 9.
- **OCR trailing characters on chord roots.** PaddleOCR occasionally appends stray characters to chord text (`F#m7I`, `C#m7/`). The chord-candidate whitelist/regex may accept these (they start with a valid root), but the custom parser must reject them. Log and flag such failures for review rather than silently trimming.
- **Standalone slash-bass at sequence start.** When the first chord(s) in a piece are standalone slash symbols (`/G#`, `/B`) without a preceding full chord, `prev_full = ''` and the `/`→ full-chord resolution cannot construct a complete chord. This usually means OCR missed the preceding full chord. Flag it for user review rather than guessing the root.

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
STAVES_PER_SYSTEM=2
EXPECTED_MEASURE_COUNT=57

for pn in $(seq 1 $N); do
    .venv/bin/python3 <skill_dir>/scripts/detect_structure.py \
        $pn --staves-per-system "$STAVES_PER_SYSTEM"
done
```

Copy the script into the workdir only when modifying/experimenting with the detector. Do not hard-code user/profile absolute paths in SKILL.md.

### System grouping sanity check

Primary grouping uses the provided `STAVES_PER_SYSTEM`; this avoids unnecessary inference. If visible system-start measure numbers exist, use them only as a sanity check: their y-positions should align with detected system starts and their sequence should agree with accumulated measure counts. If mismatch appears, fix the input stave count or inspect the detector output before chord reading.

### Detection model

- Staff detection: horizontal projection → staff-line clustering, spacing 13-21px, ±4 tolerance.
- System grouping: group sorted staves by user-provided `STAVES_PER_SYSTEM`; there is no automatic fallback in production workflow. If the count is missing, stop and ask the user.
- Measure-number anchors: optional verification/correction signal, not the primary grouping method.
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

## 3. Chord reading — PaddleOCR (default) → vision LLM (fallback)

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
                'first_staff_top': sys['first_staff_top'],
                'first_staff_bot': sys['staves'][0]['bot'] if sys.get('staves') else sys['first_staff_top'] + 77,
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
assert MEASURE_COUNT == EXPECTED_MEASURE_COUNT, (MEASURE_COUNT, EXPECTED_MEASURE_COUNT)
```

### 3C. Crop generation

**First-staff per-measure crops (primary):** crop each measure from system start (`y0`) to first staff bottom (`first_staff_bot`), with `PAD_X = 16` and no vertical margins. This captures chord text while excluding lower-staff/lyrics noise.

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
    y0 = e['y0']
    y1 = min(h, e['first_staff_bot'])
    crop = img[y0:y1, x0:x1]
    out = f"_scratch/measures/p{e['page']}_s{e['system_idx']}_g{e['gap_idx']}_M{e['measure']}.png"
    cv2.imwrite(out, crop)
    e['crop_path'] = out
```

### 3D. Chord reading: PaddleOCR (default) → vision LLM (fallback)

**Decision flow:**

1. Generate **first-staff per-measure crops** (section 3C)
2. Run **PaddleOCR** on each crop. Parse `ocr.ocr(path, cls=False)`.
3. **Normalize** via `normalize_chord_text(cn)` — handles spaces (`D M7`→`DM7`), Unicode accidentals, and parenthesized adds (`A(add9)`→`Aadd9`). Do not do semantic rewrites like `7sus4`→`sus4addb7` in the OCR phase; semantic decomposition belongs in the custom MusicXML parser.
4. **Filter non-chords**: normalize first, then apply a case-insensitive chord-candidate whitelist/regex. Use it only to reject non-chords, not to auto-correct to the nearest chord.
5. **Confidence triage**:
   - `conf < 0.5` → **vision_analyze fallback** immediately (see prompt below). Do not keep the OCR text.
   - `0.5 <= conf < 0.8` → **borderline** → flag for vision_analyze verification. Do NOT auto-accept even if whitelist+custom parser pass — the OCR text may be wrong even when it looks parseable.
   - `conf >= 0.8` → **accepted** → keep as candidate. Still subject to custom MusicXML parser validation in Phase 3E.
6. After PaddleOCR + vision fallback for low/borderline conf, run **custom MusicXML parser validation** on all accepted candidates (section 3E). Chords that pass confidence but fail our parser are NOT automatically correct — they may be OCR artifacts or unsupported spellings that need user review.
7. **Beat assignment from PaddleOCR bbox x-coordinates** (not hardcoded spacing). Each OCR result includes a bounding box — normalize its center-x within the measure width, then map to the nearest valid beat grid for the time signature:

   ```python
   measure_px = e['x1'] - e['x0']
   beats_map = {
       '4/4': [1.0, 2.0, 3.0, 4.0],
       '3/4': [1.0, 2.0, 3.0],
       '6/8': [1.0, 4.0],
   }
   valid_beats = beats_map.get(TIME_SIG, [1.0])
   crop_x0 = max(0, e['x0'] - PAD_X)
   chords = []
   ocr_debug = []

   CHORD_CANDIDATE_RE = re.compile(
       r'^(?:[A-G][#b]?(?:[A-Za-z0-9+#b()/-]*)|/[A-G][#b]?)$',
       re.IGNORECASE,
   )

   def is_chord_candidate(cn: str) -> bool:
       return bool(CHORD_CANDIDATE_RE.match(cn))

   for line in result[0] or []:
       bbox = line[0]  # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] in crop coordinates
       raw, conf = line[1][0], line[1][1]
       chord = normalize_chord_text(raw)
       if conf < 0.5 or not is_chord_candidate(chord):
           continue
       chord_x_page = (bbox[0][0] + bbox[2][0]) / 2 + crop_x0
       rel_x = max(0.0, min(1.0, (chord_x_page - e['x0']) / measure_px))
       target = valid_beats[0] + rel_x * (valid_beats[-1] - valid_beats[0])
       beat = min(valid_beats, key=lambda b: abs(b - target))
       chords.append((chord, beat))          # chord_map stores 2-tuples only
       ocr_debug.append((chord, beat, conf)) # keep confidence only for logging/debugging
   ```

   Fallback (no valid bbox): space chords evenly by count. Vision fallback always returns explicit beats.

**Vision fallback prompt:**

When PaddleOCR fails on a per-measure crop, use vision_analyze:

```text
This image is one measure crop from page {page}, system {system_idx}, gap {gap_idx}.
Global measure: M{measure}.
The original system barline boundaries are x={x0}..x1={x1}; left boundary type={left_type}, right boundary type={right_type}.
Read chord symbols inside this one measure only. Do not split or merge measures.
Return JSON only: [{"chord": "A", "beat": 1.0}, {"chord": "C#m7", "beat": 3.0}]
If there are no chord symbols in this measure, return []. Exact chord text.
```

**Collect results from both OCR and fallback into:**

```python
chord_map = {
    1: [('A', 1.0), ('C#m7', 3.0)],
    2: [],
}
```

**PaddleOCR setup:** use Python 3.11 in a separate venv; paddlepaddle does not support 3.14+.

```bash
python3.11 -m venv /path/to/paddle_venv
/path/to/paddle_venv/bin/pip install "paddlepaddle<3.0" "paddleocr<3.0"
```

```python
from paddleocr import PaddleOCR
ocr = PaddleOCR(use_angle_cls=False, lang='en', show_log=False)
result = ocr.ocr(e['crop_path'], cls=False)
```

Normalize before filtering/parsing; `normalize_chord_text()` removes OCR spaces such as `D M7`, `D m`, `E 7sus4`. OCR engine comparison is in `references/paddleocr-setup.md`.

### 3E. Compile unresolved items → user cross-check

**Before generating .mxl**, run custom MusicXML parser validation on all accepted+vision-confirmed candidates and collect every chord that cannot be automatically resolved:

1. **Custom parser failures** — chords that pass the whitelist/regex but fail `parse_chord()` or `make_music21_chord()`. These may be OCR artifacts (`F#m7I`, `C#m7/`) or unsupported legitimate spellings. Do NOT silently correct them based on prior knowledge or answer keys — the user must see them.

2. **Standalone slash-bass resolution failures** — `/F`, `/E`, `/G#`, etc. that cannot attach to a previous full chord because `prev_full` is empty (first chord(s) of the piece, or OCR missed the full chord in a prior measure). These need user input.

3. **vision_analyze borderline corrections** — when borderlines were verified with vision and the vision result differs from or adds to the OCR output, note the correction for user awareness.

Present each unresolved item to the user with the actual crop image (MEDIA: path). Wait for user input on each before proceeding. Only after all items are resolved should you proceed to Phase 4 (.mxl generation).

**Never consult answer keys, prior session data, or reference files to correct unresolved chords before showing the user what the raw pipeline produced.** The user explicitly flags this as cheating. The pipeline output (including all errors) must be presented faithfully; corrections come from the user or from vision, not from memory of what "should" be there.

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
    sys_key = (e['page'], e['system_idx'])
    if sys_key not in seen_systems:
        if e['measure'] > 1:
            sys_breaks.add(e['measure'])
        seen_systems.add(sys_key)
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
from music21 import stream, metadata, clef, key, meter, layout, note, bar, converter, harmony

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

### 4D. Chord injection: MusicXML-spec custom parser → music21 compatible form

**Don't rely on music21's `ChordSymbol(cn)` string parser alone** — music21 has internal `chordKind` values (e.g. `suspended-fourth-seventh`) that don't exist in the MusicXML `kind-value` enum, causing broken `.mxl` output. Instead, define our own parser based on the MusicXML spec, then feed music21 a form it can render correctly.

**Architecture:** chord text → normalize → `parse_chord()` → `make_music21_chord()` → insert into measure.

Normalize common source-score/OCR artifacts before parsing:

```python
def norm(cn):
    cn = re.sub(r'\s+', '', str(cn)).replace('♭','b').replace('♯','#')
    cn = re.sub(r'\(add(\d+)\)', r'add\1', cn)
    cn = cn.replace('(','').replace(')','')
    if cn and cn[0].isalpha(): cn = cn[0].upper() + cn[1:]
    return cn
```

**Custom chord parser** — decomposes chord text into MusicXML-compatible components:

```python
def parse_chord(cn):
    """
    Returns dict {root, kind (MusicXML kind-value), alterations, bass, display}
    or None if unparsable. Slash-bass returns {bass, needs_prev: True}.
    """
    cn = norm(cn)
    
    # Standalone slash-bass
    m = re.match(r'^/([A-G][#b]?)$', cn)
    if m:
        return {'bass': m.group(1), 'needs_prev': True}
    
    # Split off slash bass
    bass = None
    if '/' in cn:
        parts = cn.split('/')
        if len(parts) == 2 and re.match(r'^[A-G][#b]?$', parts[1]):
            bass = parts[1]; cn = parts[0]
        else:
            return None
    
    # Extract root
    m = re.match(r'^([A-G][#b]?)', cn)
    if not m: return None
    root = m.group(1); rest = cn[len(root):]
    
    # Quality patterns (MusicXML kind-value, longest match first)
    # Format: (regex, music21_kind, display_text)
    Q = [
        (r'^mMaj7','minor-major-seventh','mMaj7'), (r'^mM7','minor-major-seventh','mM7'),
        (r'^maj7','major-seventh','maj7'), (r'^M13','major-13th','M13'),
        (r'^M11','major-11th','M11'), (r'^M9','major-ninth','M9'),
        (r'^M7','major-seventh','M7'), (r'^m13','minor-13th','m13'),
        (r'^m11','minor-11th','m11'), (r'^m9','minor-ninth','m9'),
        (r'^m7','minor-seventh','m7'), (r'^m6','minor-sixth','m6'),
        (r'^m','minor','m'), (r'^dim7','diminished-seventh','dim7'),
        (r'^dim','diminished','dim'), (r'^aug7','augmented-seventh','aug7'),
        (r'^aug','augmented','aug'),
        (r'^sus4','suspended-fourth','sus4'), (r'^sus2','suspended-second','sus2'),
        (r'^7sus4','suspended-fourth','7sus4'),
        (r'^9sus4','suspended-fourth','9sus4'),
        (r'^13','dominant-13th','13'), (r'^11','dominant-11th','11'),
        (r'^9','dominant-ninth','9'), (r'^7','dominant-seventh','7'),
        (r'^6','major-sixth','6'), (r'^$','major',''),  # plain triad
    ]
    
    def degree_mod_type(kind, degree):
        # MusicXML degree-type is "alter" only when changing a degree that
        # already belongs to the chosen kind; otherwise it is an added tone.
        core = {
            'major': {1,3,5}, 'minor': {1,3,5},
            'augmented': {1,3,5}, 'diminished': {1,3,5},
            'suspended-fourth': {1,4,5}, 'suspended-second': {1,2,5},
            'major-sixth': {1,3,5,6}, 'minor-sixth': {1,3,5,6},
            'dominant-seventh': {1,3,5,7}, 'major-seventh': {1,3,5,7},
            'minor-seventh': {1,3,5,7}, 'diminished-seventh': {1,3,5,7},
            'augmented-seventh': {1,3,5,7}, 'minor-major-seventh': {1,3,5,7},
            'dominant-ninth': {1,3,5,7,9}, 'major-ninth': {1,3,5,7,9},
            'minor-ninth': {1,3,5,7,9},
            'dominant-11th': {1,3,5,7,9,11}, 'major-11th': {1,3,5,7,9,11},
            'minor-11th': {1,3,5,7,9,11},
            'dominant-13th': {1,3,5,7,9,11,13}, 'major-13th': {1,3,5,7,9,11,13},
            'minor-13th': {1,3,5,7,9,11,13},
        }
        return 'alter' if degree in core.get(kind, set()) else 'add'
    
    for pat, kind, display in Q:
        m = re.match(pat, rest)
        if not m: continue
        tail = rest[len(m.group(0)):]
        alts = []
        while tail:
            am = re.match(r'([b#])(\d+)', tail)  # b9, #11
            if am:
                degree = int(am.group(2))
                alts.append((degree_mod_type(kind, degree), degree, -1 if am.group(1)=='b' else 1))
                tail = tail[am.end():]
                continue
            am = re.match(r'add(\d+)', tail)       # add9
            if am: alts.append(('add', int(am.group(1)), 0)); tail = tail[am.end():]; continue
            am = re.match(r'omit(\d+)', tail)      # omit5
            if am: alts.append(('subtract', int(am.group(1)), 0)); tail = tail[am.end():]; continue
            break
        if tail:
            continue
        return {'root': root, 'kind': kind, 'display': display, 'alterations': alts, 'bass': bass}
    
    return None
```

**Construct music21 ChordSymbol from parsed dict:**

Use `ChordSymbol(root=root, kind=...)` + `addChordStepModification()` for degree alterations. Set `chordKindStr` for the display suffix. **Never use music21's string-based `ChordSymbol(cn)` constructor as the parser/validator** — it may produce non-MusicXML kinds.

```python
from music21 import harmony
from music21.harmony import ChordStepModification

def make_chord(parsed, prev_full=''):
    """parsed dict → music21 ChordSymbol. Returns None on failure."""
    
    # Standalone slash-bass: attach to prev_full
    if parsed.get('needs_prev'):
        if not prev_full: return None
        return make_chord(parse_chord(f'{prev_full}/{parsed["bass"]}'), prev_full)
    
    root, kind, display = parsed['root'], parsed['kind'], parsed['display']
    alts = parsed.get('alterations', [])
    bass = parsed.get('bass')
    
    # --- Known edge cases that need custom construction ---
    
    # 9sus4: music21 has no built-in. suspended-fourth + add b7 + add 9
    if display == '9sus4':
        cs = harmony.ChordSymbol(root=root, kind='suspended-fourth')
        cs.addChordStepModification(ChordStepModification('add', 7, -1))
        cs.addChordStepModification(ChordStepModification('add', 9, 0))
        cs.chordKindStr = '9sus4'
        if bass: cs.bass(bass)
        return cs
    
    # 7sus4: suspended-fourth + add b7
    if display == '7sus4':
        cs = harmony.ChordSymbol(root=root, kind='suspended-fourth')
        cs.addChordStepModification(ChordStepModification('add', 7, -1))
        cs.chordKindStr = '7sus4'
        if bass: cs.bass(bass)
        return cs
    
    # --- Standard chords: construct from our parsed MusicXML kind ---
    # This avoids music21's string parser entirely for validation.
    try:
        cs = harmony.ChordSymbol(root=root, kind=kind)
        for atype, degree, alter in alts:
            cs.addChordStepModification(ChordStepModification(atype, degree, alter))
        if display is not None:
            cs.chordKindStr = display
        if bass:
            cs.bass(bass)
        return cs
    except Exception:
        return None
```

**Injection loop with prev_full tracking:**

```python
prev_full = ''
for mn, chords in sorted(chord_map.items()):
    m = score2.parts[0].measure(mn)
    for cn, beat in chords:
        parsed = parse_chord(norm(cn))
        if parsed is None:
            print(f'WARNING M{mn}: unparseable "{cn}"')
            continue
        cs = make_chord(parsed, prev_full)
        if cs is None:
            print(f'WARNING M{mn}: cannot construct chord from parsed "{cn}" (parsed={parsed})')
            continue
        offset = (float(beat) - 1.0) * 1.0
        m.insert(offset, cs)
        if not cn.startswith('/'):
            prev_full = cn.split('/')[0] if '/' in cn else cn
```

**Fail strategy:** Do not silently guess on parser failure. Log the exact measure/chord/error. For the final `.mxl` generation, collect all failures into a review list and present to the user. Only fail the run entirely if the user explicitly requested fail-fast. The chord-level output is partial — chords that parsed correctly are included, failures are skipped. The verification assertion only checks measure count, not chord count, when failures exist.

### 4E. Barlines and repeats

Before zipping the final `.mxl`, insert barlines from `measure_entries` / detected structure:

- `right_type == 'double'` → right barline `light-light`.
- `right_type == 'final'` → right barline `light-heavy`.
- `right_type == 'end_repeat'` → right barline `light-heavy` + `<repeat direction="backward"/>`.
- `left_type == 'start_repeat'` → left barline `heavy-light` + `<repeat direction="forward"/>`.

Do not assume all barlines are thin. The detector's `left_type`/`right_type` are part of the score structure and must be rendered in the output.

### 4F. Verify

```python
s3 = converter.parse('final.mxl')
actual = sum(
    1
    for me in s3.parts[0].getElementsByClass(stream.Measure)
    for e in me.recurse()
    if isinstance(e, harmony.ChordSymbol)
)
expected = sum(len(v) for v in chord_map.values())
assert len(s3.parts[0].getElementsByClass(stream.Measure)) == EXPECTED_MEASURE_COUNT
assert actual == expected, (actual, expected)
print(f'{actual} chords in final.mxl')

# Also inspect the zipped MusicXML text directly:
# - assert detected double/final/repeat barlines appear as <barline> tags
# - spot-check in MuseScore/PDF when barline or repeat signs are present in the source.
```

---

## Notes

- **300dpi required** unless detector parameters are recalibrated.
- **music21 offset behavior:** Negative `<offset sound="yes">` values in MusicXML (e.g., -20160 at beat 3) are correct — they are relative to the rest's END, not the measure start. Do not treat as a bug.
- **References:** `references/paddleocr-setup.md` (OCR setup & comparison), `references/ocr-confidence-and-chord-filtering.md` (confidence thresholds + case-insensitive reject-only chord filtering), `references/beat-assignment-from-bbox.md` (x-position beat logic), `references/music21-harmony-display.md` (display internals), `references/musicxml-7sus4.md` (7sus4 XML basis), `references/musicxml-custom-chord-parser.md` (MusicXML-spec parser architecture and verification), `references/detection-params-300dpi.md` (detector params), `references/repeat-sign-notation.md` (repeat XML).
