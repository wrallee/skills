---
name: score-skeleton
description: >-
  Source score PDF → MusicXML (.mxl) with chord symbols.
  OpenCV detects structure → PaddleOCR reads chord symbols from per-measure crops → music21 generates .mxl. Vision LLM used as fallback only when OCR fails or confidence is low.
---

# Score Skeleton Transcription

```
Required inputs before starting — HARD STOP if missing:
  STAVES_PER_SYSTEM       # user-provided only; do not infer/guess from the page
  EXPECTED_MEASURE_COUNT  # user-provided total real measures; do not count by eye

If either value is missing, ask the user for it and do no PDF conversion, detection, vision reading, or generation yet.

Before asking, use session_search to check whether the user already provided
these values in the current session's thread. Re-asking for values the user
just stated is a significant frustration signal — they will say "I already told you."
Check first, ask only if session_search returns nothing relevant.

**CRITICAL PITFALL — reference files are not a substitute for asking:**
Even if a skill reference file (e.g. `references/to-find-you.md`) records the
verified values from a prior session, do NOT skip the input gate and proceed
without asking. The user may want to start completely fresh ("다 새로시작하려고한건데").
Reference files document past work for future reference, NOT as pre-authorization
to skip asking. The only valid bypass is when the user explicitly provides or
confirms the values in the current session's conversation.
```

Pipeline:
  1. PDF → PNG                    (pdftoppm -r 300, all pages first)
  2. OpenCV structure detection    (given stave count → systems → barline x-boundaries)
  3. Chord reading                 (PaddleOCR on per-measure crops → vision LLM fallback)
  4. .mxl generation               (metadata + breaks + ChordSymbol)
  5. MusicXML post-process          (exact chord display + barlines/repeats)
```

**Run by phase across all pages.**

**Input gate:** `STAVES_PER_SYSTEM` and `EXPECTED_MEASURE_COUNT` are prerequisites. Do not infer stave count, do not count measures by eye, and do not skip asking based on reference files from past sessions. Use session_search to check the current thread first, then ask the user if missing.

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

**Full-height per-measure crops (primary):** crop each detected measure gap at full system height. All OCR comparison tests were done on these. PAD_X = 16. These give PaddleOCR the full chord area + staff context needed for beat positioning.

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

**Annotated system crops (batch alternative for vision LLM):** crop each detected system, draw red barline markers, label measures in a top white strip. Useful when vision LLM is the primary reader (3-5 measures per crop, fewer API calls). Pitfall: system crops can misplace chord beat positions — prefer per-measure crops when accuracy matters.

### 3D. LLM Vision prompt

Process all systems in one phase. Prefer **parallel/bulk system-crop reading** over sequential per-measure requests: send multiple independent system crop vision calls in the same assistant turn when possible, or use the provider's batch/multi-image API when available. Each request should cover exactly one annotated system, not a full page.

For dense vocal+guitar+TAB scores, the system crop must include extra space above the top vocal staff, red measure-boundary lines, and measure labels in a top white strip so they do not cover chord symbols. Ask vision to read **only printed chord symbols above the top vocal staff** and ignore accompaniment/TAB/fret numbers. This avoids two recurring errors: mistaking accompaniment/TAB data for chords, and missing chord symbols that sit above the original system crop.

Prompt template for annotated system crops:

```text
This image is one detected system from page {page}, system {system_idx}.
Red vertical lines mark detector-owned measure boundaries. Measure labels M{first_measure}..M{last_measure} are shown in the top strip.
Read only printed chord symbols above the top vocal staff. Ignore lyrics, notes, TAB, fret numbers, and accompaniment figures.
Do not split, merge, add, or remove measures. Return exactly these measure keys, even if empty.
Return JSON only:
{
  "M12": [{"chord": "A", "beat": 1.0}, {"chord": "C#m7", "beat": 3.0}],
  "M13": []
}
If there are no chord symbols in a measure, use an empty list. Exact chord text.
```

Fallback prompt for a single measure crop:

```text
This image is one measure crop from page {page}, system {system_idx}, gap {gap_idx}.
Global measure: M{measure}.
The original system barline boundaries are x={x0}..x1={x1}; left boundary type={left_type}, right boundary type={right_type}.
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

### 3E. Chord reading: PaddleOCR (default) → vision LLM (fallback)

**Decision flow:**

1. Generate **full-height per-measure crops** (section 3C)
2. Run **PaddleOCR** on each crop. Parse `ocr.ocr(path, cls=False)`, collect text with conf ≥ 0.5.
3. **Normalize** via `normalize_chord_text(cn)` — handles spaces (`D M7`→`DM7`), `E7sus4`→`Esus4addb7`, etc.
4. **Filter non-chords**: keep only lines matching `^[A-G][#b]?` or `^/[A-G][#b]?$` (chord roots + standalone slashes)
5. For any measure with **confidence < 0.5** or **unparseable output**, fall back to `vision_analyze` on the same full-height crop.
6. Assign beat positions: if PaddleOCR gives chord texts but no beats, space chords evenly across the measure. Vision fallback gives explicit beats.

**PaddleOCR** (v2.10.0 with paddlepaddle 2.6.2) reads chord symbols with high accuracy including sharp (#) and slash (/) glyphs. Speed: ~0.25-0.6s per image.

**Requirements:** Python 3.11 (paddlepaddle does not support 3.14+). Use a separate venv.

```bash
python3.11 -m venv /path/to/paddle_venv
/path/to/paddle_venv/bin/pip install "paddlepaddle<3.0" "paddleocr<3.0"
```

**Usage:**

```python
from paddleocr import PaddleOCR
ocr = PaddleOCR(use_angle_cls=False, lang='en', show_log=False)
result = ocr.ocr(e['crop_path'], cls=False)
if result and result[0]:
    for line in result[0]:
        txt = line[1][0]
        conf = line[1][1]
        # txt = 'F#m', conf = 0.99
```

**Post-processing for PaddleOCR output:**

PaddleOCR sometimes introduces spaces in chord text. Normalize before music21 parsing:
- `D M7` → `DM7`, `D m` → `Dm` (spaces inside chord glyphs)
- `E 7sus4` → `E7sus4` (space before number)
The standard `normalize_chord_text()` function already handles space removal via `re.sub(r'\s+', '', cn)`, so these are automatically fixed for chord parsing.

**Fallback:** If a per-measure crop's PaddleOCR output is low confidence (<0.5) or returns nonsense, fall back to vision_analyze on the same crop. PaddleOCR processes the entire image in one pass and returns all detected text lines — filter to chord-pattern matching (`^[A-G][#b]?`) to isolate chord symbols from lyrics.

OCR engine comparison is in `references/paddleocr-setup.md`. In practice: always use PaddleOCR first via full-height per-measure crops. Fall back to vision_analyze only if PaddleOCR returns low confidence (<0.5) or unparseable text.

### 3F. Speed optimization: subagent-based parallel per-measure reading

When per-measure crop reading is needed (fallback from system crops or user requests better offset accuracy) and the user expresses concern about speed, use `delegate_task` to process measures in parallel batches via subagents with `toolsets=["vision"]`.

Strategy:
- Generate all per-measure crops first (section 3C)
- Split into N batches (3 subagents × ~19 measures for a 57-measure score is a good default)
- Each subagent independently reads its batch via vision_analyze and returns the chord_map chunk as JSON
- Compile results from all subagent summaries

```python
# After per-measure crops are generated, batch them:
import json
entries = json.load(open('_scratch/measure_entries.json'))
active = [e for e in entries if not e.get('skip')]
active.sort(key=lambda e: (e['page'], e['system_idx'], e['gap_idx']))
n = len(active)
batch_size = (n + 2) // 3  # split into 3 batches
batches = [active[i:i + batch_size] for i in range(0, n, batch_size)]

# Build crop listing for each batch and delegate via delegate_task(tasks=...)
# Each task gets toolsets=["vision"]. The subagent uses vision_analyze on each
# crop file path, extracts chord text + beat, returns JSON.
# The parent parses the returned JSON from each subagent's summary.
```

Pitfall: subagents cannot use `clarify`, `memory`, or `execute_code`. They produce text summaries, not file outputs — the parent must parse the returned JSON from the summary text. Do NOT write results to shared files from subagents; return them in the summary.

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

Use music21's built-in `harmony.ChordSymbol(cn)` first after light OCR/PDF normalization. `changeAbbreviationFor()` changes generated/default `figure` abbreviations, but it does **not** add MusicXML `<kind text="...">` by itself:

```python
from music21 import harmony
harmony.changeAbbreviationFor('major-seventh', 'M7')                 # optional: generated figure DM7
harmony.changeAbbreviationFor('suspended-fourth-seventh', '7sus4')  # optional: generated figure E7sus4
```

For the normal one-shot `python gen_mxl.py` workflow, one call per script run is safe: each fresh Python process starts from music21's original abbreviation list, so duplicates do **not** accumulate across runs. Only use an idempotent helper in long-lived Python processes such as notebooks, servers, REPL sessions, or repeated setup calls inside one process.

The parser already decomposes chord figures into:

```text
root + one chordKind + zero/more ChordStepModification + optional bass
```

Confirmed covered examples include `C7b9`, `C7 add b9`, `G7subtract5addb9add#9add#11addb13`, `F7 add 4 subtract 3`, `Aadd9`, `Dadd9`, `DM7`, `F#m/E`, and slash chords. Important exception: music21 parses `E7sus4` as `chordKind='suspended-fourth-seventh'`, but that value is **not** in the MusicXML `kind-value` enum and can render literally in MuseScore. Normalize `E7sus4`/`E7sus` to `Esus4addb7` for music21 pitch correctness, then export as `<kind text="7sus4">suspended-fourth</kind>` plus hidden added seventh degree (`degree-alter=0` per MusicXML's add-degree rule) in MusicXML post-process.

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

This keeps `C7b9` split correctly as `kindStr='7'` plus MusicXML `<degree>` for `b9`, instead of stuffing the whole chord suffix into `<kind text>`. For `7sus4`, do **not** export music21's `suspended-fourth-seventh` kind: MusicXML does not define it. Encode it as valid `suspended-fourth` + hidden added minor-7 degree, with `kindStr='7sus4'`. **Do not set `chordKindStr` as a semantic fix.** It is a display-text override and can mask incorrect kind/pitches if used before/without correct parsing. If a display override is needed after correct semantic parsing, derive it from `CHORD_TYPES` and keep it separate from semantic validation.

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

- **Inputs first:** obtain user-provided `STAVES_PER_SYSTEM` and `EXPECTED_MEASURE_COUNT` before any tool work. Use session_search to check the current thread first; ask only if missing. Reference files from past sessions are NOT a substitute — the user may want a clean start.
- **Phase order:** finish all pages in each phase before moving to the next phase.
- **300dpi required** unless detector parameters are recalibrated.
- **Chord reading priority:** PaddleOCR on full-height per-measure crops (section 3E) → vision_analyze as fallback. Annotated system crops (section 3C) are a batch option for vision-only but can misplace beat positions. See `references/paddleocr-setup.md` for comparison data.
- **Chord injection:** after light normalization (spaces, unicode, parentheses), use `harmony.ChordSymbol(cn)`. Normalize `E7sus4` → `Esus4addb7` before parsing. Track `prev_full` (full chord text) for standalone slash-bass resolution. Do not use `chordKindStr` as a semantic fix. See section 4D for full rules.
- **Chord display:** configure abbreviation preferences via `changeAbbreviationFor` / `CHORD_TYPES` reordering (M7, 7sus4, sus4, M9). Set `chordKindStr` from `getCurrentAbbreviationFor` only after successful semantic parse. See section 4D for the `apply_kind_display` helper.
- **Barlines:** preserve `double`, `final`, `start_repeat`, and `end_repeat` from detected structure.
- **System grouping:** use the user-provided stave count only. Do not infer it.
- **Clean-slate reruns:** remove `_scratch/`, generated `.mxl`/`.musicxml`/`.zip`, `source.pdf`, and workdir-local scripts. Preserve original PDF and `.venv` (user preference).
- **Subagent parallelism:** for per-measure vision fallback, delegate 3 batches with `toolsets=["vision"]` (section 3F).
- **Generator script:** `gen_mxl.py` is a workdir-local temporary artifact.
- **File delivery:** share workdir path or zip if Discord fails to attach `.mxl`.
- **music21 offset behavior:** Negative `<offset sound="yes">` values in MusicXML (e.g., -20160 at beat 3) are correct — they are relative to the rest's END, not the measure start. Do not treat as a bug.
- **References:** `references/paddleocr-setup.md` (OCR setup & comparison), `references/to-find-you.md` (known score facts), `references/music21-harmony-display.md` (display internals), `references/musicxml-7sus4.md` (7sus4 XML basis), `references/detection-params-300dpi.md` (detector params), `references/repeat-sign-notation.md` (repeat XML).
