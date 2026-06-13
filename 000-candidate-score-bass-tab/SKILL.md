---
name: 000-candidate-score-bass-tab
description: >-
  Use this skill after an approved LilyPond score skeleton exists to create or
  correct bass tab arrangements from that skeleton, source score, reference
  audio, or performance video. It covers bass context, root, full/performance,
  and easy versions. If the score skeleton is not approved yet, use the
  score-skeleton-transcriber skill first.
---

# Bass Tab Arrangement Workflow

Goal: produce bass-tab LilyPond files from an approved score skeleton and
optional source score, audio, or performance video. The skeleton provides the
measure map, form, chords, melody, lyrics, repeats, and system structure. The
source PDF remains the authority when a downstream bass decision depends on the
written score.

## Prerequisite Gate

Do not start bass tab work until there is an approved skeleton from the
`score-skeleton-transcriber` workflow or an equivalent user-approved score data
file.

A usable skeleton must have:

- complete measure map and form/repeat structure
- verified chord timing and qualities
- rendered PDF artifact
- MIDI artifact when possible
- unresolved uncertainties listed by measure
- user approval to proceed beyond the skeleton

If this gate is not met, stop bass work and build or repair the skeleton first.

## Non-Negotiable Order

1. Confirm the approved skeleton and unresolved uncertainties.
2. Establish bass context and tuning.
3. Create a root version if requested or useful.
4. Align video/audio only after the written form is known.
5. Build full tab in small verified measure ranges.
6. Derive easy versions only from an approved root or full version.

Do not invent notes, fingerings, or performance details. Mark uncertain spots by
measure and ask the user or inspect the source again.

## Hard Failure Gates

Do not call a bass file complete if any of these are true:

- Bar count, repeats, or endings drift from the approved skeleton.
- Bass notes contradict verified chord roots without a musical reason.
- Tablature string/fret positions are unplayable or inconsistent with the
  stated tuning.
- Video-derived fingerings are used without timestamp/confidence notes.
- LilyPond fails to render a PDF, or warnings indicate broken measures or
  structural drift.
- Multiple stale PDFs/MIDIs make the current deliverable ambiguous.

## Phase 2: Bass Context

Use standard 4-string bass tuning unless the source or user says otherwise:

- tab lines from top to bottom: G, D, A, E
- video observer view may appear vertically reversed relative to tab
- common position markers are at frets 3, 5, 7, 9, and 12
- prefer playable positions over excessive open strings when matching video

Before writing notes, record:

```text
tuning | target difficulty | source of bass part | unresolved skeleton measures
```

If the skeleton has unresolved chord/form issues, do not hide them with bass
choices. Resolve or flag them first.

## Phase 3: Root Version

Create `[song]_root.ly` from the approved skeleton.

- Use the skeleton's chord timing and repeat structure.
- Add one root note at each chord change or musically necessary sustained
  harmonic point.
- Keep rhythm simple and beginner-readable.
- Preserve measure numbers and bar checks.
- Render with LilyPond and verify against the skeleton.

The root version is a practice scaffold, not a claim about the original recorded
bass line unless the source explicitly shows that part.

## Phase 4: Video Or Audio Alignment

Use video/audio only after the score form is locked.

For each inspected range, record:

```text
measure range | timestamp | observed string/fret/position | heard rhythm | confidence
```

Cross-check the performance against the skeleton. If the performance differs
from the written score, preserve both facts and ask which version the user wants
reflected.

## Phase 5: Full Tab

Do not transcribe the whole song in one pass.

1. Write 4-8 measures.
2. Render.
3. Compare rhythm and harmony to the skeleton.
4. Compare fingerings to video/audio if available.
5. Correct before expanding the next range.

Use `[song]_full.ly` for the original/performance version. Keep scratch notes
separate from deliverables.

## Phase 6: Easy Version

Only derive `[song]_easy.ly` from an approved full or root version.

- Preserve the harmonic skeleton.
- Remove ornamental notes before changing core rhythm.
- Keep positions reasonably related to the full version so practice transfers.
- Render and verify bar checks.

## Artifact Hygiene

Keep deliverables obvious:

- main LilyPond sources at the workspace root with ASCII filenames
- current PDF/MIDI next to the source or in one predictable output directory
- OCR, video notes, and experiments in scratch folders
- no stale failed renders presented as current output

Before stopping, report exactly which `.ly`, PDF, and MIDI files are current.

## Completion Report

When stopping, report:

- files created or changed
- root/full/easy measure ranges completed
- render status, including PDF and MIDI
- unresolved uncertainties by measure
- whether user approval is needed before the next phase
