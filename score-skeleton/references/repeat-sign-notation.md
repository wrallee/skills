# Repeat Signs in Music Notation (Reference)

Sources: Wikipedia "Repeat sign", Wikipedia "Bar (music)", MuseScore Handbook

## Standard Notation

- **||:** (start repeat) = thin barline + thick/thin barline + 2 dots (right side)
  - Functions as ONE measure boundary, not two
  - "If appearing at the beginning of a staff, does not act as a bar line because no bar
    is before it; its only function is to indicate the beginning of the passage to be
    repeated." (Wikipedia)

- **:||** (end repeat) = 2 dots (left side) + thin barline + thick/thin barline
  - Also ONE measure boundary
  - Marks end of repeated section

- **:||:** = end repeat + start repeat (section boundary between two repeated sections)

## Visual Appearance in Scores

- Two vertical lines 8-16px apart at 300dpi
- Both lines extend full staff/system height
- Two small filled circles (dots) visible in middle staff space(s)
- Dots are always on the repeat side: ||: dots on right, :|| dots on left

## OpenCV Detection

- Compound grouping threshold: **20px** (safe for all common repeat sign spacing 8-16px)
  - 15px misses some (16px gap measured on Roller Coaster score)
- After grouping: classify by dot presence + dot direction
- **Dot detection**: crop ±35px around group center, connectedComponents, filter by:
  - Area 20-120px
  - Width 4-20px, height 4-20px
  - Circularity ≥ 0.5
  - Within staff y-range (between staff top and bottom)
- Multi-stave systems: expect 2 repeat dots per staff, but ≥2 dots on a side suffices for classification
- After merge + dot detection, classify:
  - `start_repeat` = compound + right-side dots
  - `end_repeat` = compound + left-side dots
  - `end_start_repeat` = compound + both-side dots
  - `double` = compound + no dots
  - `final` = compound + last line thick (>6px) + no dots

## Post-Processing

A `system_start → start_repeat` first gap can be a non-measure setup area:

`system_start | clef/key/time setup pseudo-gap | start_repeat | first real measure ...`

Do **not** discard it merely because no chord symbols are present. Chordless real measures exist.

Safe handling:

- Treat only the first gap as a candidate: `gap_idx == 0`, `left_type == system_start`, `right_type == start_repeat`.
- Verify visually/geometrically that the gap is the narrow setup area before the repeat sign.
- If it is a full-width musical measure, preserve it even when chordless.
- If verified as setup-only, mark that gap `skip=True` before global measure numbers are assigned.

Width-only heuristics are not fully safe; clef/key sharps/brackets and engraving differences can mislead. Use structure + visual confirmation, never chord emptiness alone.

## Exception

If the measure before a repeat sign has actual chord symbols, it IS a real
measure — the repeat sign just happens to align with it. Do not discard.
