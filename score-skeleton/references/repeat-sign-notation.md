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
- Piano 3-stave scores: expect 6 dots (2 per staff), but ≥2 on a side suffices for classification
- After merge + dot detection, classify:
  - `start_repeat` = compound + right-side dots
  - `end_repeat` = compound + left-side dots
  - `end_start_repeat` = compound + both-side dots
  - `double` = compound + no dots
  - `final` = compound + last line thick (>6px) + no dots

## Post-Processing (Step 3B)

When the first barline in a system is `start_repeat` AND the measure before it
(the clef/key setup area) was read by LLM as "empty" (no chord symbol),
that measure is NOT a real measure — discard it from the sequence and shift
all subsequent numbers by -1.

**Width heuristic is not needed and not safe** — clef key sharps/brackets
create false-positive dark pixels in the chord zone. Use LLM confirmation only.

## Exception

If the measure before a repeat sign has actual chord symbols, it IS a real
measure — the repeat sign just happens to align with it. Do not discard.
