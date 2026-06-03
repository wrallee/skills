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

- **Don't over-verify with vision.** Use vision only for OCR failure, low-confidence output, or targeted sharp-key checks. Otherwise generate the `.mxl` and let the user review.
- **OCR misses # on sharp keys.** PaddleOCR can miss the `#` glyph in 4+ sharp keys (E major, B major, etc.), reading `F` instead of `F#`, `C` instead of `C#`. After OCR, flag single-letter chords that are diatonic sharps in the key signature — verify with vision only for those, or note them for user review.
- **`(add9)` parentheses.** music21 rejects `A(add9)` — strip parens to `Aadd9` before `ChordSymbol()`.
- **Crop = first staff area only.** Crops run from system start (`y0`) to first staff bottom (`staves[0].bot`). This captures chord symbols above the staff while excluding lower staffs that add OCR noise. Use PAD_X=16 and do not add top/bottom margins by default. If you modify crop parameters, re-verify OCR output on a representative sample.
- **PaddleOCR scope = chord symbols only.** PaddleOCR reads printed chord text (`DM7`, `G/B`, `F#m`), not notation symbols. Full notation needs OMR; do not expand this pipeline beyond chords.

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
3. **Normalize** via `normalize_chord_text(cn)` — handles spaces (`D M7`→`DM7`), `E7sus4`→`Esus4addb7`, etc.
4. **Filter non-chords**: normalize first, then keep only lines matching chord/root/slash patterns (regex must accept `[A-Ga-g]`, because PaddleOCR can output lowercase roots on small crops).
5. For any measure with **confidence < 0.5** or **unparseable output**, fall back to vision_analyze on the same crop (see prompt below). For borderline accepted candidates (`0.5 <= conf < 0.8`), keep the chord but log/flag it for review instead of silently treating it as fully verified.
6. **Beat assignment from PaddleOCR bbox x-coordinates** (not hardcoded spacing). Each OCR result includes a bounding box — normalize its center-x within the measure width, then map to the nearest valid beat grid for the time signature:

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

   for line in result[0] or []:
       bbox = line[0]  # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] in crop coordinates
       txt, conf = line[1][0], line[1][1]
       if conf < 0.5 or not is_chord(txt):
           continue
       chord_x_page = (bbox[0][0] + bbox[2][0]) / 2 + crop_x0
       rel_x = max(0.0, min(1.0, (chord_x_page - e['x0']) / measure_px))
       target = valid_beats[0] + rel_x * (valid_beats[-1] - valid_beats[0])
       beat = min(valid_beats, key=lambda b: abs(b - target))
       chord = normalize_chord_text(txt)
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

### 4D. Chord injection: normalize → music21 parser → fail fast

Normalize OCR/PDF artifacts, then use music21's built-in `harmony.ChordSymbol(cn)`. Fail fast on parser errors. Apply display policy only after semantic parsing succeeds; do not use `chordKindStr` or abbreviation changes as parser substitutes.

The parser decomposes chord figures into:

```text
root + one chordKind + zero/more ChordStepModification + optional bass
```

Known covered examples include `C7b9`, `Aadd9`, `DM7`, `F#m/E`, and slash chords. Important exception: music21 parses `E7sus4` as `chordKind='suspended-fourth-seventh'`, which is not a MusicXML `kind-value`. Normalize `E7sus4`/`E7sus` to `Esus4addb7`, then export as `<kind text="7sus4">suspended-fourth</kind>` plus hidden added seventh degree in MusicXML post-process.

Normalize common source-score/OCR artifacts before parsing:

- remove spacing inside chord glyphs: `F #m` → `F#m`, `D M7` → `DM7`, `B m7` → `Bm7`
- unicode accidentals: `♭` → `b`, `♯` → `#`
- Finale/PDF spaced suffixes: `C #7` → `C#7`
- parenthesized add chords when semantically identical: `A(add9)` → `Aadd9`, `D(add9)` → `Dadd9`
- spaced suffixes from vision/PDF text: `E sus4` → `Esus4`, `E 7` → `E7`
- **7sus4 normalization:** `E7sus4`/`E7sus` → `Esus4addb7` before feeding to `ChordSymbol`. This produces valid MusicXML (`suspended-fourth` kind + hidden minor-7 degree) instead of the invalid `suspended-fourth-seventh` kind. Implementation:
  ```python
  m_sus = re.match(r'^([A-G][#b]?)(.*)7sus4?$', cn)
  if m_sus:
      cn = f'{m_sus.group(1)}sus4addb7'
  ```
- standalone slash-bass symbols printed in the chart: `/F`, `/E`, `/G#`, `/A`, `/B` → attach to the most recent full chord root/kind before parsing, e.g. previous `C#7` + `/F` → `C#7/F`; previous `F#m7` + `/G#` → `F#m7/G#`

Do not treat standalone slash-bass symbols as independent chord roots; they are contextual shorthand and must resolve against the last full printed chord before passing to `harmony.ChordSymbol`.

```python
from music21 import harmony

prev_full = ''
for mn, chords in sorted(chord_map.items()):
    m = score2.parts[0].measure(mn)
    for cn, beat in chords:
        cn = normalize_chord_text(cn)
        if cn.startswith('/') and len(cn) > 1 and prev_full:
            cn = f'{prev_full}{cn}'
        offset = (float(beat) - 1.0) * 1.0  # beat 1 -> offset 0.0 in 4/4
        cs = harmony.ChordSymbol(cn)
        m.insert(offset, cs)
        # Track FULL chord text (before any /), not just root note
        if not cn.startswith('/'):
            prev_full = cn.split('/')[0] if '/' in cn else cn

score2.write('musicxml', '_raw.musicxml')
```

Do **not** silently fallback or guess on parser failure. If music21 rejects a chord spelling, log the exact measure/chord/error and let the exception fail the generation so the user can see and correct the source spelling or decide on an explicit normalization rule.

Known examples that need semantic normalization before `ChordSymbol`: flat roots with `b` spelling (`BbM7`, `Bbm7` → music21 `B-` root), suffix case/alias variants (`Cmaj9` → `CM9`/`CMaj9`), and compound-quality variants (`C+maj7` → `C+M7`/`Caugmaj7`, `CmMaj7` → `CmM7`/`Cminmaj7`). Treat these as root/quality/degree parsing issues, not display fixes.

After semantic parsing succeeds, set renderer-facing suffix text from music21's own `CHORD_TYPES` abbreviation data. This is safe only **after** `ChordSymbol(cn)` produced the correct pitches/kind; do not use it as a parser substitute:

```python
from music21 import harmony

def prefer_abbreviation(chord_type: str, abbr: str) -> None:
    abbrs = harmony.CHORD_TYPES[chord_type][1]
    if abbr in abbrs:
        abbrs.remove(abbr)
    abbrs.insert(0, abbr)

def configure_chord_display_policy() -> None:
    # Keep plain major triads bare (C, D, ...), but prefer M spellings
    # for major seventh/extended qualities instead of maj/Maj spellings.
    prefer_abbreviation('major-seventh', 'M7')
    prefer_abbreviation('major-ninth', 'M9')
    prefer_abbreviation('major-11th', 'M11')
    prefer_abbreviation('major-13th', 'M13')
    prefer_abbreviation('suspended-fourth', 'sus4')
    prefer_abbreviation('suspended-fourth-seventh', '7sus4')

def apply_kind_display_from_chord_types(cs: harmony.ChordSymbol) -> None:
    mods = {(m.modType, m.degree, m.interval.semitones) for m in cs.chordStepModifications}
    if cs.chordKind == 'suspended-fourth' and ('add', 7, -1) in mods:
        cs.chordKindStr = harmony.getCurrentAbbreviationFor('suspended-fourth-seventh')
        return

    kind = harmony.CHORD_ALIASES.get(cs.chordKind, cs.chordKind)
    if kind not in harmony.CHORD_TYPES:
        return
    abbr = harmony.getCurrentAbbreviationFor(kind)
    if abbr:
        cs.chordKindStr = abbr
```

This keeps semantic parsing separate from display text: e.g. `C7b9` remains `kindStr='7'` plus a MusicXML `<degree>` for `b9`. For `7sus4`, export valid `suspended-fourth` + hidden added minor-7 degree with `kindStr='7sus4'`; never export music21's non-MusicXML `suspended-fourth-seventh` kind.

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
- **References:** `references/paddleocr-setup.md` (OCR setup & comparison), `references/beat-assignment-from-bbox.md` (x-position beat logic), `references/music21-harmony-display.md` (display internals), `references/musicxml-7sus4.md` (7sus4 XML basis), `references/detection-params-300dpi.md` (detector params), `references/repeat-sign-notation.md` (repeat XML).
