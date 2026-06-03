---
name: score-skeleton
description: >-
  Source score PDF → plain MusicXML (`target.musicxml`) with chord symbols.
  OpenCV detects structure → PaddleOCR reads chord symbols from per-measure crops → music21 generates uncompressed MusicXML. Vision LLM used as fallback only when OCR fails or confidence is low.
---

# Score Skeleton Transcription

**Input gate:** `STAVES_PER_SYSTEM` and `EXPECTED_MEASURE_COUNT` are required. Check `session_search` for the current thread first; if either value is missing, ask the user and stop. Do not infer stave count, count measures by eye, or start PDF conversion/detection/OCR/generation before both values are known.

**Pipeline:** PDF → PNG → OpenCV structure detection → PaddleOCR chord reading → vision fallback only when needed → custom MusicXML-spec validation → plain `target.musicxml` generation → MusicXML post-process. Run each phase across all pages before moving to the next.

**Feedback discipline:** When the user reports an output error, treat it as a possible pipeline/skill defect first, not as a one-song patch. Classify the feedback before editing output:

1. **Source-data correction** — a specific printed chord/beat/barline was read wrong. Apply only that explicit correction to the current manifest/output, with the crop/vision/user input as evidence.
2. **Algorithmic rule defect** — the pipeline used a bad general rule (example: forcing system-first chords to beat 1). Update this SKILL.md and/or reusable scripts first, then regenerate affected outputs from raw OCR/validated manifests. Do not hide the fix in `fix_<song>.py`.
3. **Tool/API pitfall** — music21/PaddleOCR/OpenCV behavior caused a reusable failure. Add a pitfall plus the exact safe pattern and verification.

Do not generalize from one song into a blanket musical rule unless it is backed by structure/OCR geometry, MusicXML spec, or explicit user instruction. Conversely, do not leave a discovered bad rule as a local workaround; encode the corrected procedure here so the next score run benefits.

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
- **OCR digit confusion 7↔9.** PaddleOCR can misread `7` as `9`, but `9sus4` is also a legitimate printed chord. Do **not** auto-correct `9sus4` → `7sus4`. If confidence is <0.8 or the crop is visually ambiguous, verify via vision/user; otherwise parse `9sus4` using the custom `make_chord()` path (dominant-ninth, subtract 3, add 4).
- **OCR trailing characters on chord roots.** PaddleOCR occasionally appends stray characters to chord text (`F#m7I`, `C#m7/`). The chord-candidate whitelist/regex may accept these (they start with a valid root), but the custom parser must reject them. Log and flag such failures for review rather than silently trimming.
- **Standalone slash-bass at sequence start.** When the first chord(s) in a piece are standalone slash symbols (`/G#`, `/B`) without a preceding full chord, `prev_full = ''` and the `/`→ full-chord resolution cannot construct a complete chord. This usually means OCR missed the preceding full chord. Flag it for user review rather than guessing the root.
- **Do not force first-measure/first-system chords to beat 1.** A chord in the first measure of a system is **not** automatically on beat 1. System-start gaps include clef/key/time setup space, and chord symbols may legitimately appear at beat 2/3. Use the OCR bbox-derived beat, vision/user correction, or explicit musical evidence. Never apply a blanket rule like “first chord in each system-first measure = beat 1.”
- **Padded crop leakage must not become a chord.** Measure crops may include `PAD_X` pixels outside the original barline bounds so OCR can read edge glyphs, but chord membership is still determined by the **unpadded** measure gap. If an OCR bbox center falls outside `e['x0']..e['x1']`, reject/flag it as neighbor-measure leakage. Never clamp outside centers back into `[0, 1]`; clamping hides leakage and creates extra chords at beat 1/4.
- **Beat positions are continuous decimals, not integer grid snaps.** Store chord positions as 1-based decimal beat labels (`1.00`, `2.37`, `3.50`, etc.) in the manifest. For music21 insertion, convert with `offset = beat - 1.0`. Do not quantize OCR bbox positions to integer beats by default; integer snapping collapses adjacent chords, loses offbeat placements, and destroys useful geometry for later melody/notation alignment. If quantization is ever needed, keep it as a separate reviewed post-process, not the source data.
- **Default output is plain `target.musicxml`; do not create compressed `.mxl`.** Generate the final deliverable as an uncompressed MusicXML file named `target.musicxml` so it can be opened in a text editor/Notepad and diffed directly. MuseScore can import/open standard uncompressed MusicXML (`.musicxml` / `.xml`). The score-skeleton workflow must not zip/package the output into `.mxl`.
- **MusicXML semantics and MuseScore display are separate.** The custom parser may correctly encode `M7`, `7sus4`, or `9sus4` semantically, but music21/MusicXML export and MuseScore import can still display expanded/default names (`Amaj7`, `Bsus4b7add9`). `kind@text` alone is not a reliable MuseScore display contract: MuseScore import (`importmusicxmlpass2.cpp` + `chordlist.cpp`) reads `kind@text`, but then matches parseable chords against its chord list and canonicalizes recognized names. Direct XML checks must be paired with a MuseScore import/export or source-backed import-path check. For `7sus4`/`9sus4`, prefer dominant 7/9 + `subtract 3` + `add 4` over `suspended-fourth + add7/add9`: it avoids music21's invalid string-parser kind (`suspended-fourth-seventh`) and avoids MuseScore-visible `b7add9`.
- **System-start beat origin is not the detected left barline.** The first measure of each system often includes clef/key/time/ending-label setup before the playable region. Keep raw `x0..x1` for chord membership/leakage checks, but compute beat positions from a separate `beat_x0`: for a widened system-first gap, set `beat_x0 = x1 - median(non-first gap widths in that system)` and `beat_width = x1 - beat_x0`. This removes setup width without forcing the chord to beat 1. Flag the measure for targeted vision/user review if OCR misses a chord or the first accepted chord still lands implausibly far right.
- **System-start OCR misses are targeted review items.** In setup-heavy first measures, PaddleOCR can miss a left chord entirely while reading the later chord correctly. If a system-first gap has setup width (`raw_width > median_nonfirst_width * 1.15`) and OCR output looks incomplete, do not silently accept the measure just because all returned chords parse. Send that crop to vision/user review as a targeted anomaly.
- **`cs.bass(non_chord_tone_pitch)` raises exception.** `harmony.ChordSymbol(root=root, kind=kind)` followed by `cs.bass(bass)` will crash with `"Pitch X not found in chord"` when the bass note is not a member of the chord (e.g. `F#m/E`, `C#7/F`). music21 verifies bass is a chord tone. **Fix:** use string-based construction (`ChordSymbol(f"{root}{display}/{bass}")`) for slash chords, or add the bass pitch as a chord step before calling `cs.bass()`. The `make_chord()` function in section 4D implements the string-based fallback.
- **`bar.Repeat(direction)` uses `'start'`/`'end'` not `'forward'`/`'backward'`.** In music21 v8+, `bar.Repeat(direction='forward')` raises `BarException`. Use `direction='start'` for forward repeats and `direction='end'` for backward repeats. The XML notation uses `forward`/`backward` but the Python API uses `start`/`end`.
- **`ChordSymbol(normed)` string parser cannot handle `9sus4` or `7sus4`.** music21's string-based `ChordSymbol('B9sus4')` raises `ValueError: Invalid chord abbreviation '9sus4'`. These must use the custom root+kind+add construction shown in `make_chord()`. The same applies to `7sus4` — `ChordSymbol('E7sus4')` produces the invalid internal kind `suspended-fourth-seventh`. Always use the custom construction for these two display classes.

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

### 2A. Dependencies

`detect_structure.py` requires OpenCV, which is **not** a dependency of music21. Install it in the music21 venv separately:

```bash
# Assuming .venv/ exists from an earlier music21 install step:
.venv/bin/pip install opencv-python-headless
```

If a `.venv` doesn't exist yet, create one and install both dependencies:

```bash
python3.11 -m venv .venv
.venv/bin/pip install "music21<10" opencv-python-headless
```

### 2B. Run detection

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
                # Beat-origin fields are filled after pseudo-gap handling.
                # Raw x0/x1 remain the membership/leakage bounds.
                'beat_x0': gap['x0'],
                'beat_x1': gap['x1'],
            }
            measure_entries.append(entry)

# After pseudo-gap handling, compute a playable beat span for setup-heavy
# first measures of each system. Do not change raw x0/x1 membership bounds.
from statistics import median
by_system = {}
for e in measure_entries:
    if e.get('skip'):
        continue
    by_system.setdefault((e['page'], e['system_idx']), []).append(e)

for entries in by_system.values():
    entries.sort(key=lambda e: e['gap_idx'])
    if len(entries) < 2:
        continue
    first = entries[0]
    nonfirst_widths = [e['width'] for e in entries[1:] if e['width'] > 0]
    if not nonfirst_widths:
        continue
    regular_width = median(nonfirst_widths)
    if first['left_type'] == 'system_start' and first['width'] > regular_width * 1.15:
        first['beat_x0'] = first['x1'] - regular_width
        first['beat_x1'] = first['x1']
        first['setup_width'] = round(first['beat_x0'] - first['x0'], 1)
        first['system_start_setup'] = True
    else:
        first['system_start_setup'] = False
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
7. **Beat assignment from PaddleOCR bbox x-coordinates** (continuous decimal, not integer snapping). Each OCR result includes a bounding box — normalize its center-x within the measure width, then map to a 1-based decimal beat label:

   - manifest/user-facing beat: `1.00` is the start of the measure; `2.00`, `3.00`, `4.00` are later beat starts; `3.50` is halfway from beat 3 to beat 4.
   - music21/MusicXML offset: 0-based quarterLength offset, so `offset = beat - 1.0`.
   - in 4/4, valid beat labels are normally `1.00 <= beat < 5.00`; beat `5.00` is the next measure's beat `1.00` / current measure offset `4.00` and should be treated as a boundary/leakage candidate, not inserted into the current measure.

   ```python
   beat_x0 = e.get('beat_x0', e['x0'])
   beat_x1 = e.get('beat_x1', e['x1'])
   measure_px = beat_x1 - beat_x0
   BAR_QL_BY_TIME_SIG = {
       '4/4': 4.0,
       '3/4': 3.0,
       '6/8': 3.0,  # music21 quarterLength duration of the bar
   }
   bar_ql = BAR_QL_BY_TIME_SIG.get(TIME_SIG, BAR_QL)
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
       if chord_x_page < e['x0'] or chord_x_page > e['x1']:
           # The padded crop caught a neighboring measure's chord.
           # Do not clamp it into this measure; log/flag for review.
           ocr_debug.append((chord, None, conf, 'outside_measure_bounds', chord_x_page))
           continue
       if chord_x_page < beat_x0:
           # Inside the raw measure, but inside the clef/key/time setup span.
           # Treat as a system-start anomaly, not a normal chord position.
           ocr_debug.append((chord, None, conf, 'before_playable_beat_origin', chord_x_page, beat_x0))
           continue
       rel_x = (chord_x_page - beat_x0) / measure_px
       beat = 1.0 + rel_x * bar_ql
       # Store decimal beat position as source data. Do not snap to integers.
       beat = round(beat, 2)
       if beat >= 1.0 + bar_ql:
           ocr_debug.append((chord, beat, conf, 'at_or_after_bar_end', chord_x_page, rel_x))
           continue
       chords.append((chord, beat))          # chord_map stores 2-tuples only
       ocr_debug.append((chord, beat, conf, chord_x_page, rel_x)) # keep geometry/confidence for debugging
   ```

   After beat assignment, scan for geometry anomalies and flag them before generation:

   - duplicate or near-duplicate decimal beat positions within one measure unless the crop clearly has stacked chord text;
   - candidates very close to bar start/end boundaries (`<1.00`, `>= 1.00 + bar_ql`, or visually crossing a barline);
   - system-start measures whose accepted chord positions look shifted because the raw gap includes clef/key/time/ending-label setup space;
   - any `outside_measure_bounds` candidate from the padded crop.

   These are pipeline uncertainty signals, not proof of a correction. Use vision/user review or an explicitly verified beat-area adjustment; do not force all system-first chords to beat 1 and do not snap to integer beats.

   Fallback (no valid bbox): space chords evenly by count using decimal beat positions. Vision fallback always returns explicit decimal beats.

**Vision fallback prompt:**

When PaddleOCR fails on a per-measure crop, use vision_analyze:

```text
This image is one measure crop from page {page}, system {system_idx}, gap {gap_idx}.
Global measure: M{measure}.
The original system barline boundaries are x={x0}..x1={x1}; left boundary type={left_type}, right boundary type={right_type}.
Read chord symbols inside this one measure only. Do not split or merge measures.
Return JSON only with 1-based decimal beat positions: [{"chord": "A", "beat": 1.00}, {"chord": "C#m7", "beat": 3.50}]
If there are no chord symbols in this measure, return []. Exact chord text.
```

**Collect results from both OCR and fallback into:**

```python
chord_map = {
    1: [('A', 1.00), ('C#m7', 3.50)],
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

**Before generating `target.musicxml`**, run custom MusicXML parser validation on all accepted+vision-confirmed candidates and collect every chord that cannot be automatically resolved:

1. **Custom parser failures** — chords that pass the whitelist/regex but fail `parse_chord()` or `make_music21_chord()`. These may be OCR artifacts (`F#m7I`, `C#m7/`) or unsupported legitimate spellings. Do NOT silently correct them based on prior knowledge or answer keys — the user must see them.

2. **Standalone slash-bass resolution failures** — `/F`, `/E`, `/G#`, etc. that cannot attach to a previous full chord because `prev_full` is empty (first chord(s) of the piece, or OCR missed the full chord in a prior measure). These need user input.

3. **vision_analyze borderline corrections** — when borderlines were verified with vision and the vision result differs from or adds to the OCR output, note the correction for user awareness.

**Applying vision corrections structurally:** Maintain a `VISION_CORRECTIONS` dict keyed by `song_name → measure_number → [(chord_text, beat)]` that replaces the OCR chord_map entries for those measures before custom parser validation. This keeps corrections explicit and traceable rather than mixed into inline script logic.

```python
VISION_CORRECTIONS = {
    'roller-coaster': {
        30: [('E', 1.00)],  # OCR had 'A' @ 2.21, vision confirmed 'E' @ 1.00
    },
}
```

Present each unresolved item to the user with the actual crop image (MEDIA: path). Wait for user input on each before proceeding. Only after all items are resolved should you proceed to Phase 4 (`target.musicxml` generation).

**Never consult answer keys, prior session data, or reference files to correct unresolved chords before showing the user what the raw pipeline produced.** The user explicitly flags this as cheating. The pipeline output (including all errors) must be presented faithfully; corrections come from the user or from vision, not from memory of what "should" be there.

---

## 4. `target.musicxml` generation

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
score2 = converter.parse(score.write('musicxml', '_base.musicxml'))
```

### 4D. Chord injection: MusicXML-spec custom parser → music21 compatible form

**Don't rely on music21's `ChordSymbol(cn)` string parser alone** — music21 has internal `chordKind` values (e.g. `suspended-fourth-seventh`) that don't exist in the MusicXML `kind-value` enum, causing broken MusicXML output. Instead, define our own parser based on the MusicXML spec, then feed music21 a form it can render correctly.

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

    # No quality matched — try as plain major triad + degree alterations
    # Handles chords like Aadd9, Dadd9, Eadd9/G#, C#b5 where the chord
    # text has no quality suffix (m, M, dim, sus, etc.) but has add/alter/omit.
    if rest:
        alts = []
        tail = rest[:]
        while tail:
            am = re.match(r'([b#])(\d+)', tail)
            if am:
                degree = int(am.group(2))
                alts.append((degree_mod_type('major', degree), degree, -1 if am.group(1)=='b' else 1))
                tail = tail[am.end():]
                continue
            am = re.match(r'add(\d+)', tail)
            if am: alts.append(('add', int(am.group(1)), 0)); tail = tail[am.end():]; continue
            am = re.match(r'omit(\d+)', tail)
            if am: alts.append(('subtract', int(am.group(1)), 0)); tail = tail[am.end():]; continue
            break
        if not tail:
            return {'root': root, 'kind': 'major', 'display': '', 'alterations': alts, 'bass': bass}

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

    # 9sus4: do NOT use ChordSymbol('B9sus4') and do NOT build as
    # suspended-fourth + add b7/add9. Build as dominant-ninth with the
    # third removed and fourth added; this matches MuseScore's import path
    # and avoids visible `b7add9` expansion.
    if display == '9sus4':
        cs = harmony.ChordSymbol(root=root, kind='dominant-ninth')
        cs.addChordStepModification(ChordStepModification('subtract', 3, 0))
        cs.addChordStepModification(ChordStepModification('add', 4, 0))
        cs.chordKindStr = '9sus4'
        if bass: cs.bass(bass)
        return cs

    # 7sus4: dominant seventh with third removed and fourth added.
    if display == '7sus4':
        cs = harmony.ChordSymbol(root=root, kind='dominant-seventh')
        cs.addChordStepModification(ChordStepModification('subtract', 3, 0))
        cs.addChordStepModification(ChordStepModification('add', 4, 0))
        cs.chordKindStr = '7sus4'
        if bass: cs.bass(bass)
        return cs

    # --- Standard chords: construct from normalized string ---
    # IMPORTANT: Do NOT use only root+kind+bass construction for slashed
    # chords. `cs.bass(non_chord_tone)` — e.g. `F#m/E`, `C#7/F` — raises
    # "Pitch X not found in chord" because music21 verifies the bass is
    # a chord tone. The custom parser validated the components; string
    # construction is safe here and handles slash chords correctly.
    try:
        if alts:
            # Degree alterations: construct from root+kind, then add alts.
            # Fall back to full string form if bass fails.
            cs = harmony.ChordSymbol(root=root, kind=kind)
            for atype, degree, alter in alts:
                cs.addChordStepModification(ChordStepModification(atype, degree, alter))
            if display is not None:
                cs.chordKindStr = display
            if bass:
                try:
                    cs.bass(bass)
                except Exception:
                    # Non-chord-tone bass: reconstruct from normalized string
                    normed = f"{root}{display}/{bass}"
                    cs = harmony.ChordSymbol(normed)
                    for atype, degree, alter in alts:
                        cs.addChordStepModification(
                            ChordStepModification(atype, degree, alter))
        else:
            # No alterations — plain chord or plain slash chord
            normed = f"{root}{display}"
            if bass:
                normed = f"{normed}/{bass}"
            cs = harmony.ChordSymbol(normed)
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

**Fail strategy:** Do not silently guess on parser failure. Log the exact measure/chord/error. For the final `target.musicxml` generation, collect all failures into a review list and present to the user. Only fail the run entirely if the user explicitly requested fail-fast. The chord-level output is partial — chords that parsed correctly are included, failures are skipped. The verification assertion only checks measure count, not chord count, when failures exist.

### 4E. Barlines and repeats

Before writing the final `target.musicxml`, insert barlines from `measure_entries` / detected structure:

- `right_type == 'double'` → right barline `light-light`.
- `right_type == 'final'` → right barline `light-heavy`.
- `right_type == 'end_repeat'` → right barline `light-heavy` + `<repeat direction="backward"/>`.
- `left_type == 'start_repeat'` → left barline `heavy-light` + `<repeat direction="forward"/>`.

Do not assume all barlines are thin. The detector's `left_type`/`right_type` are part of the score structure and must be rendered in the output.

### 4F. MusicXML display post-process

After generating the score, write and post-process **plain `target.musicxml`** directly. Do not create compressed `.mxl` output in this workflow. music21 can encode chord semantics correctly while still exporting display text that notation software expands (`major-seventh` → `maj7`, `suspended-fourth` + degrees → `sus4b7add9`).

Required display/import patches:

- Source suffix `7sus4` / `9sus4` → encode as **dominant 7/9 with suspended fourth**: MusicXML `dominant` / `dominant-ninth` plus implementation-only degrees `subtract 3` and `add 4`. Set visible `<kind text="7sus4">` / `<kind text="9sus4">`, and hide the implementation-only degrees with `print-object="no"`. Do **not** encode these as `suspended-fourth + add b7/add9`; MuseScore can import that as visible `b7add9`.
- Source suffix `M7` → `<kind text="M7">major-seventh</kind>` is semantically correct MusicXML, but MuseScore may still canonicalize it to the default chord-list name (`maj7`) during import. This is an accepted trade-off — `maj7` is a standard notation for major seventh and does not change the chord meaning.

Patch by measure and harmony order from `chord_map`; then save `target.musicxml`. Verify both layers:

1. Read `target.musicxml` directly for semantic tags/degrees.
2. For MuseScore display claims, inspect the MuseScore import path or run a MuseScore import/export probe. Do **not** rely only on music21 re-parse or chord counts, because those verify semantics, not MuseScore-visible display text.

### 4G. Verify

```python
s3 = converter.parse('target.musicxml')
actual = sum(
    1
    for me in s3.parts[0].getElementsByClass(stream.Measure)
    for e in me.recurse()
    if isinstance(e, harmony.ChordSymbol)
)
expected = sum(len(v) for v in chord_map.values())
assert len(s3.parts[0].getElementsByClass(stream.Measure)) == EXPECTED_MEASURE_COUNT
assert actual == expected, (actual, expected)
print(f'{actual} chords in target.musicxml')

# Also inspect target.musicxml text directly:
# - assert detected double/final/repeat barlines appear as <barline> tags
# - spot-check in MuseScore/PDF when barline or repeat signs are present in the source.
```

### 4H. Applying review corrections without creating song-only hacks

When the user reviews the generated `target.musicxml` and reports mistakes, keep two layers separate:

- **Explicit per-score overrides:** exact user/vision-confirmed corrections such as `M37 C#m7 beat1, A beat4`. Store/apply these to the current run manifest only. They are not new global rules.
- **Reusable pipeline fixes:** incorrect assumptions, parsing rules, beat mapping logic, crop parameters, MusicXML post-processing, API pitfalls. These must be reflected in this SKILL.md and reusable scripts before or alongside regenerating the score.

Safe correction workflow:

1. Start from the raw OCR/vision/custom-parser manifest, not from a previously patched `target.musicxml`.
2. Apply only explicit per-score overrides for that score.
3. Remove any rejected blanket rule completely; verify negative examples where the old rule would have changed data incorrectly.
4. Regenerate `target.musicxml` and verify measure count, chord count, chord offsets for corrected measures, and MusicXML display text.
5. Patch this skill whenever the correction changes the general procedure. Do not bury reusable learning inside `fix_<title>.py`.

---

## Notes

- **300dpi required** unless detector parameters are recalibrated.
- **music21 offset behavior:** Negative `<offset sound="yes">` values in MusicXML (e.g., -20160 at beat 3) are correct — they are relative to the rest's END, not the measure start. Do not treat as a bug.
- **References:** `references/paddleocr-setup.md` (OCR setup & comparison), `references/ocr-confidence-and-chord-filtering.md` (confidence thresholds + case-insensitive reject-only chord filtering), `references/beat-assignment-from-bbox.md` (x-position beat logic), `references/music21-harmony-display.md` (display internals), `references/musicxml-7sus4.md` (7sus4 XML basis), `references/musicxml-custom-chord-parser.md` (MusicXML-spec parser architecture and verification), `references/target-musicxml-output-and-display.md` (plain target.musicxml-only output and direct display postprocess), `references/detection-params-300dpi.md` (detector params), `references/repeat-sign-notation.md` (repeat XML).
