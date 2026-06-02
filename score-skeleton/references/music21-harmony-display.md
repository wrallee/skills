# music21 Harmony Display Internals + Chord Parsing

## The core problem

music21's built-in `ChordSymbol(cn)` parser is more capable than a simple kind dictionary: it parses root/bass, one `chordKind`, and extra `ChordStepModification` degree elements (`C7b9`, `C7 add b9`, `G7subtract5addb9add#9add#11addb13`, `Aadd9`, slash chords, etc.). Use it first after light normalization. Exception: `7sus4` needs MusicXML-kind normalization because music21's internal `suspended-fourth-seventh` kind is not a valid MusicXML `kind-value`.

Known spelling hazards should be handled as semantic normalization problems, not display overrides:

| Input | Expected | Handling |
|---|---|---|
| `BbM7` | root B-flat + `major-seventh` | normalize flat root spelling to music21's `B-` form before parse |
| `Bbm7` | root B-flat + `minor-seventh` | same flat-root normalization |
| `Cm7b5` | usually displayed as half-diminished | pitches are correct as `minor-seventh` + flat-5 degree; canonicalize display only after semantic verification |
| `Cmaj9` | `major-ninth` | normalize suffix case/alias to a music21-supported abbreviation such as `CM9` |
| `C+maj7` | `augmented-major-seventh` | parse as compound quality, e.g. normalize to `C+M7` / `Caugmaj7` |
| `CmMaj7` | `minor-major-seventh` | normalize suffix alias to `CmM7` / `Cminmaj7` |

Do not feed raw OCR/vision text blindly. First normalize common score/PDF artifacts (`F #m` → `F#m`, `D M7` → `DM7`, unicode accidentals, flat-root spelling, suffix case/alias variants, etc.), then call `ChordSymbol`. If parsing still fails, log measure/beat/original chord/error and fail fast; add the smallest semantic normalization rule only after the failure is visible.

For generated/default figures, prefer `M7` over music21's default `maj7` when desired:

```python
from music21 import harmony
harmony.changeAbbreviationFor('major-seventh', 'M7')
```

This mutates the in-process global abbreviation list. A fresh `python gen_mxl.py` process starts from the original list again, so one call per script run is safe. Repeated calls in the same long-lived Python process accumulate duplicate entries; use an idempotent helper only for notebooks/servers/repeated setup calls.

## The two approaches: old vs new

### OLD (don't use): `chordKindStr` as cosmetic band-aid

```python
cs = harmony.ChordSymbol('Eb7')  # kind='major' (WRONG!)
cs.chordKindStr = 'Eb7'          # forces display text, but pitches are wrong
```

Creates `<kind text="Eb7">major</kind>` — MuseScore shows "Eb7" ✓, but
pitches are E major triad + D (E G# B D), not E dominant 7th (E G Bb Db) ✗.

**This is a fake chord. Don't do it.**

### NEW (correct): normalize lightly → `ChordSymbol` → fail fast

```python
from music21 import harmony

harmony.changeAbbreviationFor('major-seventh', 'M7')  # optional output preference

def normalize_chord_text(cn: str) -> str:
    return (
        cn.strip()
          .replace('♭', 'b')
          .replace('♯', '#')
          .replace(' ', '')
    )

try:
    cs = harmony.ChordSymbol(normalize_chord_text(cn))
except Exception as e:
    print(f'[CHORD_PARSE_ERROR] measure={mn} beat={beat} chord={cn!r} '
          f'error={type(e).__name__}: {e}')
    raise
```

Do not maintain a parallel kind dictionary unless a real unsupported score spelling forces it and the user explicitly approves the normalization rule.

## MusicXML output comparison

| Chord | Old approach (`ChordSymbol(cn)` + `chordKindStr`) | New approach (light normalize → built-in `ChordSymbol`) |
|---|---|---|
| `Eb7` | `<kind text="Eb7">major</kind>` (pitches wrong) | `<kind>dominant</kind>` (pitches correct) |
| `Cm7b5` | `<kind text="Cm7b5">minor-seventh</kind>` (pitches wrong) | `<kind>half-diminished</kind>` (pitches correct) |
| `C7b9` | `<kind text="C7b9">dominant-seventh</kind>` (missing b9) | `<kind>dominant</kind> <degree>...b9</degree>` (correct) |
| `C7sus4` | `<kind text="C7sus4">suspended-fourth-seventh</kind>` (invalid MusicXML kind; MuseScore may render literal enum) | `<kind text="7sus4">suspended-fourth</kind>` + hidden added minor-7 `<degree>` (correct display + valid MusicXML) |

## Built-in alteration parsing

music21's `ChordSymbol` parser already handles common alterations and exports them as MusicXML `<degree>` elements:

- `bN` / `#N` suffixes such as `C7b9`, `C7#11`
- explicit `addN`, `subtractN`, `alterN` text, including dense strings like `G7subtract5addb9add#9add#11addb13`
- slash basses such as `F#m/E`

A chord figure is a semantic union of units, not an opaque suffix string. music21's model is:

```text
root + one chordKind + zero/more ChordStepModification + optional bass
```

So do **not** try to store two `kind` values. For compound qualities (`augM7`, `mM7`, `7sus4`) use the single compound kind that music21 already defines when it exists (`augmented-major-seventh`, `minor-major-seventh`, `suspended-fourth-seventh`) or a valid MusicXML base kind plus degree modifications when the compound kind is not valid in MusicXML (`7sus4` → `suspended-fourth` + hidden added seventh).

If `ChordSymbol(raw)` fails or chooses the wrong prefix (`aug` before `augM7`, `m` before `mM7`), do not jump to a hand-written display dictionary. Inspect `music21.harmony.CHORD_TYPES` / `CHORD_ALIASES` and normalize the suffix as semantic units:

1. Split root and optional slash bass.
2. Match the longest known quality abbreviation from `CHORD_TYPES`/aliases first, including compound qualities.
3. Parse the remaining suffix as degree operations (`add`, `subtract`, `alter`, `b9`, `#11`, `omit3`, etc.).
4. Construct `ChordSymbol(root=..., kind=...)` and apply `ChordStepModification`s, or normalize to an equivalent string that music21 parses.
5. Only after pitch/kind/degrees are verified, set `chordKindStr` for display.

For unsupported spellings, fail visibly first; then add the smallest semantic normalization rule only after confirming music21's current source behavior. Prefer rules that map to existing music21 kinds/degree operations over one-off string-to-display mappings.

## Why `chordKindStr` is harmful

1. **Hides bugs.** If kind is wrong, `chordKindStr` only fixes display, not pitches.
2. **Breaks roundtrip.** Converting the MusicXML back to music21 loses `@text`.
3. **No improvement over degree elements.** Degree elements produce correct display
   *and* correct data.

## When to use `chordKindStr`

Use `chordKindStr` **only after semantic parsing succeeds**. It is the supported music21 path for MusicXML `<kind text="...">` display overrides, but it must not be used as a parser substitute.

Good use:

```python
cs = harmony.ChordSymbol('DM7')
assert cs.chordKind == 'major-seventh'
cs.chordKindStr = 'M7'  # display override only
```

Bad use:

```python
cs = harmony.ChordSymbol('D')
cs.chordKindStr = 'DM7'  # fake display; wrong semantics/pitches
```

For truly non-standard symbols that don't fit any MusicXML `<kind>` value, use `kind='other'` with degree elements to spell out the voicing explicitly. Only if the renderer still misrenders should `chordKindStr` be considered — and even then, only together with a correct `chordKind`.

## The `7sus4` MusicXML trap

`music21.harmony.CHORD_TYPES` includes `suspended-fourth-seventh` and parses `E7sus4` to that kind, but MusicXML's `kind-value` enum does **not** include `suspended-fourth-seventh`; it only includes `suspended-fourth`. MuseScore can therefore render the invalid kind literally as `Esuspended-fourth-seventh7` even when `<kind text="7sus4">...` is present.

Correct export for `E7sus4`:

```xml
<harmony>
  <root><root-step>E</root-step></root>
  <kind text="7sus4">suspended-fourth</kind>
  <degree print-object="no">
    <degree-value>7</degree-value>
    <degree-alter>0</degree-alter>
    <degree-type>add</degree-type>
  </degree>
</harmony>
```

Implementation pattern:

1. Normalize `E7sus4` / `E7sus` to `Esus4addb7` before parsing so music21's in-memory pitches stay correct.
2. After parse, detect `suspended-fourth` with degree mod `add b7`.
3. Set `cs.chordKindStr = harmony.getCurrentAbbreviationFor('suspended-fourth-seventh')` (usually `7sus4`).
4. Post-process MusicXML because music21 exporter has TODO for degree `print-object`: add `print-object="no"` to the added seventh degree element so MuseScore displays only `E7sus4`, not an extra degree suffix. In the exported MusicXML, set that added seventh's `degree-alter` to `0`: MusicXML defines added degrees relative to a dominant chord, i.e. major/perfect intervals except for a minor seventh.

## The `suspended-fourth-seventh` / `major-seventh` display trap

If `chordKind='suspended-fourth-seventh'` with no display text, MusicXML output is:

```xml
<kind>suspended-fourth-seventh</kind>
```

MuseScore can render this literally as `Esuspended-fourth-seventh7`. Similarly, `<kind>major-seventh</kind>` may render as `Dmaj7` even when the source score uses `DM7`.

Correct workflow:

1. First parse semantically with `harmony.ChordSymbol(cn)`.
2. Verify the resulting `chordKind`/pitches are correct.
3. Configure preferred suffix spellings by reordering music21's own `CHORD_TYPES[kind][1]` abbreviation list.
4. Set `cs.chordKindStr = harmony.getCurrentAbbreviationFor(kind)` for the parsed base kind.

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

This writes e.g. `<kind text="7sus4">suspended-fourth</kind>` plus a hidden added seventh degree after MusicXML post-process, while major-seventh/extended major qualities display as `M7`, `M9`, `M11`, `M13`. For altered chords such as `C7b9`, the base kind text remains `7`; `b9` belongs in MusicXML `<degree>` children.

## Debugging recipe

When a chord symbol renders wrong in MuseScore:

1. Check the `<kind>` element and any `<degree>` children in raw MusicXML.
2. Verify `kind` string maps to a valid MusicXML kind value.
3. If using the parser, inspect the original normalized input and verify whether music21 accepts that spelling in the current version.
4. For altered chords, verify degree elements have correct degree-value and
   degree-alter.
5. MuseScore renders each degree as a suffix (e.g., `<degree-value>9
   degree-alter>-1` → "♭9").
