# MusicXML custom chord parser notes

Use this reference when updating or implementing the score-skeleton chord injection phase.

## Why this exists

music21's string constructor can accept or create internal chord kinds that are not valid MusicXML `kind-value`s. The observed bad case is `suspended-fourth-seventh`: music21 may use it for `7sus4`, but MusicXML expects `suspended-fourth` plus a degree modification/display text. Therefore the pipeline must not use `harmony.ChordSymbol(cn)` as the parser/validator.

## Required architecture

1. Normalize OCR/source artifacts only: spaces, Unicode accidentals, parenthesized add chords.
2. Parse chord text with our own MusicXML-spec rules into:
   - root
   - MusicXML `kind-value`
   - degree modifications
   - optional bass
   - display suffix
3. Construct music21 using `harmony.ChordSymbol(root=root, kind=kind)`.
4. Add modifications with `ChordStepModification`.
5. Set `chordKindStr` for display.
6. Collect unresolved parser failures for user crop review; do not silently trim or answer-key-correct.

## Required special cases

### `9sus4`

Treat as a legitimate printed chord, not as automatic OCR confusion:

- kind: `suspended-fourth`
- add degree 7 with alter `-1`
- add degree 9 with alter `0`
- display: `9sus4`

Do not auto-correct `9sus4` to `7sus4`; only vision/user review can change the OCR text.

### `7sus4`

Represent as:

- kind: `suspended-fourth`
- add degree 7 with alter `-1`
- display: `7sus4`

Never export music21's non-MusicXML `suspended-fourth-seventh` kind.

### Degree modifications

Use MusicXML degree-type `alter` only when the target degree belongs to the chosen kind. If the degree is not in the kind, use `add`, even when altered. Example: `C7b9` is dominant-seventh plus added altered 9, so music21 reports the modification as `('add', 9, -1)`, not `('alter', 9, -1)`.

## Verification checklist

- The SKILL.md text does not contain old guidance to validate via `ChordSymbol(cn)` or `ChordSymbol(chord_str)`.
- `9sus4` and `7sus4` are represented via `suspended-fourth` plus degree modifications.
- Trailing OCR artifacts like `F#m7I` and malformed slashes like `C#m7/` are rejected and routed to crop review.
- A temporary music21 probe can instantiate representative chords using root/kind construction: `B9sus4`, `E7sus4`, `AM7`, `C7b9`, `F#m7`, `A6`.
