---
name: score-skeleton-transcriber
description: >-
  Use this skill when converting a source score PDF into a faithful LilyPond
  score skeleton before arranging for bass or any other instrument. It covers
  intake, source inspection, full measure mapping, vocal/instrument staff
  extraction, chords, lyrics, repeats, original system breaks, PDF rendering,
  MIDI generation, and uncertainty reporting.
---

# Score Skeleton Transcription Workflow

Goal: turn a source score PDF into a faithful, buildable LilyPond skeleton that
can later support bass, guitar, keys, melody, or other instrument-specific
arrangements. The source PDF is the authority. OCR and OMR output are helper
candidates only.

## Non-Negotiable Order

1. Identify the requested score scope and outputs.
2. Inspect the original PDF pages directly.
3. Create a full measure map before writing notation.
4. Write the LilyPond skeleton from the map and source PDF.
5. Render PDF and MIDI if possible.
6. Compare against the PDF and list uncertain measures for user approval.

Do not begin any instrument-specific arrangement until the skeleton is approved.

## Hard Failure Gates

Do not call a skeleton complete or ask for approval if any of these are true:

- The visible melody/voice is missing or replaced by placeholder full-measure
  rests where the PDF has notes.
- Lyrics visible in the requested scope are missing, OCR-garbled, or not aligned
  to the melody syllables.
- Chord names are missing, rhythmically misplaced, or changed from the visible
  source text.
- Repeats, endings, pickups, bar numbers, key, time, or tempo do not match the
  PDF.
- The deliverable includes unrequested staves such as piano accompaniment, OCR
  debris, arranger parts, or hidden helper material that changes the visible
  score.
- LilyPond fails to produce a normal PDF. SVG is only diagnostic, not the
  deliverable.
- Warnings indicate bar-check failures, overfull/underfull measures, negative
  skips, page overflow, or bar-number drift in deliverable notation.
- Multiple stale renders make it unclear which `.ly`, PDF, or MIDI is current.

If a hard gate fails, keep working or report the result as a partial draft with
specific blockers.

## Phase 0: Intake And Tool Check

Record these facts before editing notation:

- Source files: PDF, images, audio/video, existing `.ly` drafts.
- Requested scope: for example vocal staff only, vocal + piano left hand, lead
  sheet, or a specific instrument staff. Copy only the requested visible scope.
- Desired outputs: skeleton PDF, MIDI, later bass root/full/easy versions, or a
  different instrument arrangement.
- Metadata: title, artist, source notes, lyricist/composer, key, time, tempo.
- ASCII filenames: use slugs such as `[song]_skeleton.ly`; keep Korean and other
  non-ASCII text inside LilyPond metadata and lyrics.

Check available tools when relevant:

```bash
command -v lilypond
command -v pdftotext
command -v pdftoppm
command -v audiveris
command -v xvfb-run
```

If a tool is missing, continue with the parts that do not need it and state the
limitation. Do not install packages without user approval. Never overwrite the
source PDF.

## Phase 1: Faithful Skeleton From The PDF

### 1. Inspect The Source

Render PDF pages to images or screenshots when useful, then inspect the original
visual score. Use the PDF as authority for:

- total written measures and bar numbers
- requested staves and which staves to exclude
- system line breaks for the requested staff
- repeats, volta brackets, codas, segnos, endings
- key, time, tempo, pickups, final barlines
- chord symbols and their beat positions
- melody pitches, rhythm, rests, ties, slurs
- lyrics and syllable placement

Page count is not a rule. It is only a result of the requested staff scope and
LilyPond layout. Preserve the original measure/system line breaks for the
requested staff with `\break`, but do not force the source page count with
`\pageBreak`, `page-count`, custom page-breaking policy, staff-size changes, or
spacing tweaks unless solving a real overflow after the musical content is
correct.

### 2. Make The Measure Map First

Before writing LilyPond, create a full measure map covering the visible score.
Minimum columns:

```text
measure | page/system | form/repeat | chords | melody/rhythm | lyrics | uncertainty
```

For repeated sections, map written measures and playback form separately. Record
the exact measures covered by first/second endings. Do not proceed to LilyPond
until the map covers the whole requested scope or the user explicitly approves a
partial range.

### 3. Use OCR/OMR Only As Candidates

Audiveris, MusicXML, text extraction, and OCR can speed up entry, but they never
override the PDF.

- Use OMR for candidate pitches/durations only after checking bar counts and
  rhythms against the map.
- Expect errors in Korean lyrics, chord qualities, repeats, ties, tuplets, and
  syncopation.
- Discard unrequested accompaniment staves from deliverables. Keep OCR output in
  scratch folders only.
- If Audiveris fails on Linux/WSL with an X11/AWT display error, retry through
  `xvfb-run -a audiveris ...`; if sandboxed display sockets are blocked, request
  permission to run it outside the sandbox.
- If conversion logs contain negative skips, bar-check failures, overfull
  measures, or bar-number drift, normalize manually measure by measure.

For Korean lyrics, prefer the PDF text layer or visual transcription over OCR.
Classify suspicious strings as watermark/publisher noise, meaningful text to
recover, or unreadable OCR; never render unrecovered garbage as lyrics.

### 4. Write The LilyPond Skeleton

Create `[song]_skeleton.ly` with:

- `\header` metadata matching the source
- global key, time, tempo, pickup, and final barline
- visible chord names at the source rhythm and quality
- requested staff notes/rests matching the PDF
- lyrics aligned syllable by syllable
- repeats and `\alternative` endings matching the source
- original system breaks for the requested staff
- a `\midi` block unless the user asks not to generate MIDI

Use actual melody/voice notation for the requested range. A structure-only file
with rests, chords, and lyrics is not a completed skeleton unless the user asked
for that explicitly.

Do not make bass-specific range, fingering, tab, or simplification decisions in
this skeleton. Those belong to downstream arrangement skills such as
`score-bass-tab-transcriber`.

### 5. Render And Verify

Compile with LilyPond and keep the current artifacts unambiguous:

```bash
lilypond [song]_skeleton.ly
```

If the environment writes temporary files to an incompatible path, set a safe
temporary directory such as `TMPDIR=/tmp` and rerun. Do not claim warning-free
status unless the compile log is actually warning-free.

Compare the render against the source PDF:

- written measure count and bar numbers match
- requested system line breaks match
- repeat brackets and endings cover the same measures
- chord names and beat positions match
- melody rhythm and lyric alignment are coherent
- no unrequested staff, watermark, OCR debris, or stale helper text is visible
- notation stays inside printable margins
- PDF and MIDI are generated when requested/possible

Let LilyPond handle page breaking automatically by default. If the result is
layout-valid, do not brute-force compression or page count. Only adjust spacing
after identifying a concrete engraving problem such as overflow or collisions.

### 6. Stop For Approval

Before any downstream arrangement, report:

- current `.ly`, PDF, and MIDI paths
- source measure range covered
- whether LilyPond compiled cleanly
- uncertain measures and why they are uncertain
- confirmation that no bass or other instrument version has been started
