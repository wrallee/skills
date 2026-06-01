---
name: score-skeleton
description: >-
  Convert a source score PDF into a MusicXML skeleton using LLM vision
  extraction + music21. Audiveris OMR is optional (only needed for
  future melody-merge). Use before any downstream arrangement (bass TAB,
  practice material, chord analysis).
---

# Score Skeleton Transcription

Convert a source score PDF into a complete MusicXML (.mxl) using
**LLM vision extraction + music21**. Audiveris OMR is optional —
only needed if you later want melody notes merged into the skeleton.

## ⚠️ ZERO-TOLERANCE RULES (violation = unreliable output)

These rules were hard-earned from real failures. Breaking any of them means
the resulting skeleton WILL have shifted/wrong chords. Do not skip.

1. **SEQUENTIAL ASSIGNMENT IS FORBIDDEN** — "Chord 1 → M13, chord 2 → M14, ..." is
   FORBIDDEN. One measure can (and often does) have 2-6 chord events. Chords must
   be GROUPED by measure in the chord_map, not laid out as a flat sequence.

2. **PER-LINE EXTRACTION IS MANDATORY** — Per-page vision extraction causes
   measure-drift. You MUST extract chords one line at a time with a KNOWN starting
   measure number (from the Step 2 line map). Per-page is FORBIDDEN.

3. **2-INPUT RECONCILIATION IS MANDATORY** — The chord_map must be built by cross-
   checking vision output + PDF image, not from vision alone.

4. **1 chord ≠ 1 measure** — If the chord_map has every measure with exactly 1 chord
   (or a uniform 1-2 pattern across the whole score), you have a sequential-assignment
   bug. STOP and regroup chords by their actual measure.

5. **Audiveris is for melody-merge only** — Do not run Audiveris for a chord-only
   skeleton. The primary pipeline (Steps 1-7, no Audiveris) is complete for that
   use case. Running Audiveris unnecessarily wastes time and introduces no useful
   information (chord identity is ~62% accurate, layout is less reliable than vision).

## Pipeline (primary — no Audiveris)

```
Step 1: PDF Page Images → pdftoppm -png images
Step 2: PDF Line/Page Structure Mapping → master map (the foundation)
Step 3: Measure Count Confirmation → clarify with user
Step 4: Create Code Skeleton → blank .mxl with correct layout
Step 5: Vision Per-Line Chord Extraction → chord identities + beat position (PER-LINE ONLY — never per-page)
Step 6: LLM Reconciliation → final chord_map (2-input: vision + PDF image)
Step 7: Chord Injection (music21) → deliverable .mxl

Watchlist: Melody Merge (deferred — bar accuracy must be verified first)
```

**Audiveris note-stream** is only needed for future melody-merge (see Optional: Audiveris section below).
For a chord-only skeleton, the pipeline above is complete. Do NOT run Audiveris unless the user explicitly asks for note/lyric extraction too.

## Pipeline (with Audiveris — melody merge use case)

```
Step 1: Audiveris LINKS → raw .mxl (note durations, optional)
Step 2: PDF Page Images → pdftoppm -png images
Step 3: PDF Line/Page Structure Mapping → master map (the foundation)
Step 4: Measure Count Confirmation → clarify with user
Step 5: Create Code Skeleton → blank .mxl with correct layout
Step 6: Vision Per-Line Chord Extraction → chord identities + beat position
Step 7: LLM Reconciliation → final chord_map
Step 8: Chord Injection (music21) → deliverable .mxl
```

---

## Step 0: Pre-flight

```bash
python3 -c "import music21; print('music21:', music21.__version__)" || echo "music21: MISSING"
```

music21 missing → `pip install music21`.

**Beware: `python3` and `pip` may resolve to different interpreters.**
If pip installs music21 into a venv but `python3` is system brew Python, the import will fail.
Either use the venv python explicitly (`./.venv/bin/python3`) or install for both.

_If_ running Audiveris (melody-merge use case only), Korean lyrics need:
```bash
sudo apt install tesseract-ocr-kor
audiveris -batch -constant "omr.text.Language.defaultSpecification=eng+kor" -step LINKS ...
```
Without the constant, Hangul output is garbled. With it, verified 163 lyrics / 0 garbage
on a Korean Finale PDF.

---

## Step 1: Extract PDF Page Images

```bash
mkdir -p _scratch/pages
pdftoppm -png -r 150 "source.pdf" _scratch/pages/page
```

This produces `page-1.png` through `page-N.png` at 150 DPI.
Images are needed for line structure mapping (Step 2) and vision chord extraction (Step 5/6).

**Why 150 DPI?** Enough for vision to read chord symbols and measure numbers,
small enough to keep tool output manageable. Higher DPI adds size without quality gains
for LLM vision models.

---

## Step 2: PDF Line/Page Structure Mapping ← THE FOUNDATION

**Do this before any chord extraction.** The line structure is the skeleton
that everything else hangs on.

For each page image, ask vision:

```
"각 라인(줄)의 시작 마디 번호를 알려줘. 형식: Line 1: M1~M4, Line 2: M5~M8, ..."
```

This produces the master map:

```
Page 1: Line 1 M1-4 | Line 2 M5-8 | Line 3 M9-12
Page 2: Line 1 M13-16 | Line 2 M17-20 | Line 3 M21-24 | Line 4 M25-28
...
```

This map serves as:
- Line grouping for vision chord extraction (Step 5)
- Break attribute reference for skeleton creation (Step 5)
- Measure count verification for Step 3

---

## Step 3: Measure Count Confirmation

**After Step 2 line map is built, confirm total measure count with the user
before proceeding.**

From the line map, compute the inferred total by looking at the last page's
last line end measure number. Then use `clarify` to ask:

```
"총 N마디 맞아?"
```

PDF 마지막 줄 마디번호로 유추 가능하지만, 1st/2nd ending, D.S., coda 구조에서
추정이 틀릴 수 있으므로 반드시 사용자 확인을 거칠 것.

Options: confirm (N마디 맞음), correct (다른 숫자 제시).

Only proceed to Step 4 after receiving confirmation.

---

## Step 4: Create Code Skeleton

**Goal**: a blank `.mxl` with only the structural frame — measures, system/page
breaks, key, time, clef, and whole rests. No notes, lyrics, or harmonies.
Built independently from Audiveris using music21.

```python
from music21 import stream, note, meter, key, clef

# Read key from PDF key signature (vision: "몇 개의 샵/플랫이 붙어있는가")
# If Audiveris mxl is available, also check <fifths> in the XML.
# Example: 3 sharps = A Major / F# minor
KEY_SHARPS = 3   # ← adjust per song
TIME_SIG = '4/4'  # ← adjust per song
MEASURE_COUNT = 82  # ← from Step 3 user confirmation, not inference

skeleton = stream.Score()
part = stream.Part()
part.partName = 'Voice'
part.append(clef.TrebleClef())
part.append(key.KeySignature(KEY_SHARPS))
part.append(meter.TimeSignature(TIME_SIG))

for n in range(1, MEASURE_COUNT + 1):
    m = stream.Measure(number=n)
    m.append(note.Rest(quarterLength=4.0))
    part.append(m)

skeleton.insert(0, part)
skeleton.write('musicxml', 'skeleton.mxl')
```

After building, post-process the XML to inject break attributes.
**Do NOT try to find-and-replace existing `<print />`** — music21 adds empty
`<print />` tags inconsistently, and regex substitution can produce issues
(literal `\n`, missing matches). Instead, **delete all existing `<print />`**
first, then inject fresh attributes:

```python
import zipfile, re, os

path = 'skeleton.mxl'
with zipfile.ZipFile(path, 'r') as z:
    # music21 names the XML inside the mxl after the input filename
    xml_name = [n for n in z.namelist() if '.musicxml' in n or '.xml' in n][0]
    xml = z.read(xml_name).decode('utf-8')

# Step 1: delete any existing <print .../> that music21 may have written
xml = re.sub(r'<print[^>]*/>', '', xml)

# Step 2: inject fresh break attributes after each measure opening tag
for mn in sorted(system_breaks | page_breaks):
    attrs = []
    if mn in system_breaks: attrs.append('new-system="yes"')
    if mn in page_breaks: attrs.append('new-page="yes"')
    attr_str = ' '.join(attrs)
    pat = r'(<measure[^>]*number="' + str(mn) + r'"[^>]*>)'
    xml = re.sub(pat, r'\1<print ' + attr_str + r'/>', xml, count=1)

tmp = os.path.join('/tmp', xml_name)
with open(tmp, 'w') as f: f.write(xml)
with zipfile.ZipFile(path, 'r') as zin:
    with zipfile.ZipFile(path + '.tmp', 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == xml_name: zout.write(tmp, xml_name)
            else: zout.writestr(item, zin.read(item.filename))
os.remove(tmp); os.replace(path + '.tmp', path)
```

The regex `<measure[^>]*number="N"[^>]*>` handles attributes like
`implicit="no"` that appear before `number`.

**music21 XML naming**: `score.write('musicxml', 'skeleton.mxl')` generates
`skeleton.musicxml` inside the mxl archive (matching the stem of the output
path). When inspecting raw XML, use `.namelist()` to discover the actual
filename — do not hardcode it.

---

## Step 5: Vision Chord Extraction

페이지 이미지를 보고 각 마디의 코드 심볼을 읽는다:

1. 페이지 이미지에서 각 라인의 **마디번호**(줄 왼쪽 숫자) 확인
2. **barline(세로줄)** 사이의 코드 심볼을 전부 읽음
3. 한 마디에 여러 코드 있으면 전부 기록, 추론 금지

형식: `M17: F#m, D` (여러 코드는 쉼표 구분)

**중요:** 균등 분할 crop 금지. 시스템 너비를 마디 수로 나눈 x좌표는 실제 barline 위치와 다르다. 페이지 전체 이미지에서 barline 기준으로 읽으면 됨.

**4마디에 6개 코드는 정상.** 한 마디에 여러 코드 있는 걸 의심하면 밀집 마디의 코드를 누락하게 됨.

---

## Step 6: LLM Reconciliation

**⚠️ 2-INPUT CROSS-CHECK IS MANDATORY. VISION-ONLY IS FORBIDDEN.**

The chord_map must be produced by comparing BOTH sources together.
Vision alone is unreliable — it misses chords, misreads qualities (F#→F#m),
and misplaces beat positions. Reconciliation catches these errors.

**Inputs (BOTH required, never fewer):**
1. **Vision per-measure chord data** (Step 5): `M1: F#m(beat 1), DM7(beat 3)  M2: E(beat 1)...`
2. **PDF page image** — the line image that vision read from

**LLM task (execute this exact prompt for each line):**
```
"이 라인(M{X}~M{Y})의 작업: 아래 2개 입력을 비교해서 chord_map을 작성해.
1. Vision 추출 코드 리스트 (beat position 포함): {LIST}
2. PDF 이미지: {IMAGE_REF}

알고리즘:
- 이미지의 barline 위치를 기준으로 코드의 실제 measure/beat 위치를 확정
- vision의 measure grouping이 의심스러우면 (특히 thin barline 근처), PDF 이미지 보고 수동 보정
- vision이 misread한 코드(예: D→Dm, F#→F#m, E→Em) 보정
- vision이 누락한 코드는 이미지 보고 추가
- 한 마디에 여러 코드가 있으면 전부 같은 measure에 그루핑 (sequential spread 금지)
- 각 코드의 offset = (beat - 1) × 1.0 (예: beat 3 → offset 2.0)
- confidence < 70%인 코드는 NOT SURE로 표시
"
```

**Output:** `chord_map` dict:

```python
chord_map = {
    1:  [('F#m', 0.0), ('DM7', 2.0)],   # (chord_name, offset_in_quarter_lengths)
    2:  [('DM7', 0.0)],
    ...
}
```

**Validation after building chord_map:**
- Check that each measure has a REASONABLE number of chords
  (1 chord/measure in simple sections, 4-6 in dense sections)
- If every measure has ≤2 chords → possible sequential assignment bug
- If any measure in a consistently-dense section has 0 chords → flag for review

### Key-Constrained Validation

If the song's key is known (from `<key>` in the mxl), flag chords outside the
diatonic set. Example for A Major: `{A, Bm, C#m, D, E, F#m, G#dim}`.

A chord outside this set is not automatically wrong — secondary dominants,
modal interchange, and chromatic passing chords exist. But it should trigger
extra scrutiny during LLM reconciliation.

### Offset Units

Offset in `chord_map` is in **quarter-lengths** (music21 convention).
To convert from beat position: `beat_index × 1.0`. In 4/4:
- Beat 1 = offset 0.0
- Beat 2 = offset 1.0
- Beat 3 = offset 2.0
- Beat 4 = offset 3.0

Read `<divisions>` from the raw mxl if you need the XML-level offset:
`xml_offset = quarter_offset × divisions`. Do not hardcode — different
scores use different values.

---

## Step 7: Chord Injection

Use `music21.harmony.ChordSymbol`. Offset is in **quarter-lengths** (see Step 6).
**Do NOT manually set `.text`** — it causes duplicate display.

```python
from music21 import converter, harmony

score = converter.parse('skeleton.mxl')
part = score.parts[0]

# Inject from chord_map
for measure_num, chords in chord_map.items():
    m = part.measure(measure_num)
    for chord_name, offset in chords:
        cs = harmony.ChordSymbol(chord_name)
        cs.offset = offset
        m.insert(offset, cs)

score.write('musicxml', 'output.mxl')
```

music21 normalises "DM7" → "Dmaj7" internally. Same chord, different spelling.
MuseScore renders `<kind>major-seventh</kind>` as "Dmaj7". This is fine —
the user does not require exact original spelling.

---

## Step 8: Deliver & Verify

Deliver the completed `.mxl`. **Confirm with the user that the file actually
arrived** — platform delivery may silently fail (Discord gateway may not
attach MEDIA: files even when the tool returns `success: true`). Do not
declare delivery complete based solely on the tool return value.

**File delivery rules:**
- Never upload the file to external file-sharing services (tmpfiles.org,
  file.io, 0x0.st, etc.) without explicit user permission.
- Never change the file extension (.mxl → .txt) without asking.
- Prefer delivery channels that natively support the file type (Telegram
  is more reliable for MusicXML files than Discord).
- If gateway attachment fails, copy the file to a shared filesystem path
  the user can access directly (e.g. `/mnt/c/Users/.../Desktop/`).
- Always verify with the user that the file was received before moving on.

User opens in MuseScore for final verification.

The skeleton must contain:
- Correct measure count and layout (matches original PDF line/page breaks)
- Chord symbols at correct positions
- Key/time/clef metadata
- Empty measures with whole rests (no notes, no lyrics)

---

## Watchlist: Melody Merge

**Deferred until bar accuracy is verified.**

Audiveris barline misdetection can merge 5-6 measures into one, making
melody→measure mapping unreliable. When bars are correct:

1. From Audiveris mxl, extract melody notes in measures where harmonies exist
2. Map: "harmony at M14 offset 0 → melody notes also in M14"
3. After chord skeleton is verified, merge melodies to correct positions

If overflow detected: flat sequence dump → cumulative duration boundary detection →
user confirmation → split.

---

## Reference: Divisions

`<divisions>` is a MusicXML value defining how many ticks per quarter note.
It sets the resolution for all duration and offset values. Common values:

```
divisions=4  → quarter=4 ticks, whole=16, eighth=2
divisions=12 → quarter=12 ticks, whole=48, eighth=6
```

Read from the mxl by grepping the raw XML:
```python
import zipfile, re
with zipfile.ZipFile('source.mxl') as z:
    for n in z.namelist():
        if '.musicxml' in n or '.xml' in n:
            xml = z.read(n).decode()
            break
div = int(re.search(r'<divisions>(\d+)</divisions>', xml).group(1))
```
Never hardcode or ask the user.

---

## Pitfalls

### ⛔ ZERO-TOLERANCE VIOLATIONS (documented failures — do not repeat)

These mistakes were actually made during production. Each entry includes
the real failure mode and the enforced fix.

1. **VISION-ONLY CHORD_MAP** → ENFORCED: vision results must be cross-
   checked against the PDF image (Step 6 reconciliation).
   Vision alone misreads chord qualities (F#→F#m) and misses positions.

2. **SEQUENTIAL CHORD ASSIGNMENT** → ENFORCED: chords must be grouped by
   measure. Flat assignment (chord 1→M13, chord 2→M14, chord 3→M15...)
   scatters multi-chord measures across subsequent measures and produces
   an average density of ~1 chord/measure everywhere. This is the #1 cause
   of shifted chords. If the chord_map's per-measure density is suspiciously
   uniform, STOP and regroup.

3. **PER-PAGE VISION EXTRACTION (full page, one query)** → ENFORCED: showing
   the entire page and asking "각 라인별 코드 진행을 알려줘" causes vision
   to simplify/summarize. In dense measures with multiple chords (3+ changes),
   vision drops chords or compresses them. Individual measure symptoms:
   M20 had 3 chords → vision saw 1; M50-53 had 2 per measure → vision shifted
   them by one measure. **Per-line crop (각 system을 이미지로 crop) + per-measure
   query가 유일하게 허용된 방법.** crop은 마진 없이 system 전체 높이로 하되,
   개별 마디 crop (620×147px at 300dpi)이 가장 신뢰할 수 있음.

4. **IGNORING "1 chord ≠ 1 measure"** → ENFORCED: if the total chord count
   divided by measure count is ≤1.4 across the entire score, flag this for
   review. Pop/K-pop scores commonly have 3-6 chord changes per measure in
   chorus sections.

### Structure & Layout
- **Line structure map is THE foundation** (Step 2): Do this before any chord
  extraction. Without it, all downstream chord assignments drift.
- **music21 Layout objects don't produce XML break attributes**: `SystemLayout()`
  and `PageLayout()` write empty `<print />`. After building the skeleton with
  music21, post-process the XML to inject `new-system="yes"` / `new-page="yes"`
  attributes (see Step 4 code).

### Audiveris
- **Chord detection is unreliable**: Audiveris omits chords with `#` accidentals
  (F#m, C#m, C#7) completely, and identity accuracy on detected chords is ~62%.
  Never use Audiveris harmonies for chord identity. Use vision extraction only.
- **Offset is inferable from XML stream**: music21 parses temporal offsets from the
  harmony's position in the measure (~90% correct when it works). But since identity
  is unreliable, offset alone is only useful as a reconciliation hint.
- **Measure mapping is reliable**: When Audiveris does detect a chord, its measure
  assignment (~83%) is trustworthy.
- **No step skipping**: Audiveris pipeline is strictly sequential. To suppress
  garbage lyrics: `omr.text.tesseract.TesseractOCR.useOCR=false` (all OCR off)
  or post-process to strip `<lyric>`.
- **Barline→arpeggio misID**: Thin Finale barlines → arpeggios → merged
  measures. Flag, don't auto-fix.
- **X11 on WSL**: `/tmp/.X11-unix` is read-only. Run Audiveris directly
  against DISPLAY.

### Vision
- **Vision can hallucinate extra systems on the last page**: The last page
  often has fewer systems than earlier pages (e.g. 1 system instead of 4).
  Vision routinely invents non-existent 2nd/3rd lines. Always verify the
  last page's actual line count by looking at the image yourself, and confirm
  with the user in Step 3.
- **Chord follow-up verification**: When vision gives conflicting chord
  positions between "per-page" and "per-line" queries, re-ask with a
  focused question targeting the specific line. The per-line approach with
  known start measure is more reliable but still needs cross-checking when
  chord density is ambiguous.

### Chord Work
- **Vision per-line, not per-page**: Per-line extraction with known starting
  measure eliminates measure-drift.
- **Key-constrained validation**: Flag chords outside the diatonic set for
  extra scrutiny. Don't auto-reject — secondary dominants exist.
- **Never manually set `.text` on ChordSymbol**: Causes duplicate display
  (`<kind>` rendering + `<text>` both appear). Just use `ChordSymbol(name)`.
- **Don't strip `<kind>`/`<root>`/`<bass>` from harmony XML**: These ARE the
  chord. Stripping them produces garbage display ("Dpedal", "F#pedal").
  Only remove entire `<harmony>` blocks; never dissect them.
- **DM7 vs Dmaj7 doesn't matter**: music21 normalises internally. Display
  difference is cosmetic; the user does not require exact original spelling.
- **1 chord ≠ 1 measure**: Many pop scores have 2-3 chord changes per measure.

### Workflow
- **절대 기존 .mxl에 패치하지 말 것**: `converter.parse('existing.mxl')` + `measure(n).insert()`는
  이전 데이터가 남아서 중복 코드(D가 M17과 M18에 동시에 존재)가 생긴다. 수정이 필요하면
  **처음부터 다시 build** (Step 4 skeleton 생성 → Step 7 injection)하라.
- **"4마디에 6개 코드"를 의심하지 말 것**: M1의 F#m+DM7, M13의 F#m+DM7+E가 증명하듯
  한 마디에 여러 코드가 있는 게 정상이다. 의심하면 밀집 마디에서 코드를 누락하게 된다.
- **방법을 over-engineering하지 말 것**: 사용자가 "페이지 보고 마디번호 읽고 코드 위치 파악해서 기록"
  이라고 말했으면 그대로만 하면 된다. barline x좌표 공식, fallback 절차, 해상도 가이드라인 등을
  스스로 만들어내지 말 것. 단순함이 정확하다.
- **Chords above staff → Audiveris linking is irrelevant**: In pop/K-pop scores,
  chord symbols sit above the staff. Audiveris's "no chord below" linking failure
  is not a layout problem — it's an architectural limitation. Vertical position of
  chords contains no useful information; only the horizontal (x-coordinate) offset
  matters for measure/beat assignment. This is why vision extraction is superior:
  it reads chord symbols and barline positions independently, without needing
  vertical linking.
- **Verify file delivery actually happened**: When sending the .mxl via
  MEDIA: syntax in gateway messages, the tool may return `success: true`
  even when the file was not attached (Discord). After sending, ask the
  user to confirm the file arrived, or pre-emptively deliver via Telegram
  (more reliable for file attachments) or copy to a shared filesystem path.
  Never upload to external file hosts without explicit permission.
- **Never change file extensions without asking**: Renaming `.mxl` to `.txt`
  or other extensions to bypass gateway restrictions confuses the user.
  Instead, use a channel that supports the native format, or explain the
  limitation and offer a path-based alternative.
- **Clean up intermediate files**: Always write analysis/debug scripts into
  the project workspace (e.g., `~/Workspace/<project>/_investigate/`), never
  in `/tmp/`. After the investigation session, remove the `_investigate/`
  directory or individual scripts. Leaving temp files in `/tmp/` is noise
  that no one will clean up.
- **Question user contradictions against musical context**: If DM7 appears
  consistently and the user types "DM" for one measure, ask before applying.
- **Read `<divisions>` from the mxl**: Never hardcode or ask the user.
- **No mechanical loops**: If the approach isn't working after 2 attempts,
  stop and re-evaluate.
- **Unfamiliar song = can't verify**: Ask the user early if they can
  provide barline/pitch feedback. Without it, iteration is wasted.
- **User prefers code blocks over markdown tables**: Present data in plain
  text format, never markdown tables.

### Technical
- **MusicXML 4.0.3 is namespace-less**: Audiveris outputs no `xmlns`.
  music21 `parse()` works; namespace-aware XPath does not.
- **Multi-part Audiveris output**: An mxl can have 3+ parts (Voice, Piano×2).
  Always extract hints from the Voice part only (typically `score.parts[0]`).
