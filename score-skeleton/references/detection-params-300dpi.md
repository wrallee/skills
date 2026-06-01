# Detection Parameters (300dpi)

## Page characteristics
- Size: ~2481×3509px (A4 at 300dpi)
- Staff line spacing: 17-21px (5 lines per staff; varies by engraver/PDF generation)
- Staff height: ~64-84px (top line to bottom line)
- System height: varies by stave count and spacing; detect from grouped staves, do not assume 3 staves
- Chord area y-range: vocal staff top - 105px to vocal staff top + 5px (adjust if chords clipped)
- Scores may have 1, 2, 3, or more staves per system; `stave_count` is detected per system

## Horizontal projection
- Threshold: w * 0.25 (staff lines are dense black)
- Minimum consecutive rows: 2
- Peak count varies: 5-line staves × N, plus TAB lines (6 per guitar staff)

## 5-line clustering
- Algorithm tries spacings 13-21px (±4 tolerance) to accommodate varied layouts
- Not all peaks belong to staves — lyrics underlines, system brackets, TAB strings create noise
- The while-loop skips used peaks and advances independently

## Barline detection
- Vertical kernel height: system_height * 0.4
- Column projection threshold: 5 (binary pixels per column)
- Minimum barline width: 2px
- Double barline/repeat sign merge threshold: **20px**
- After merge, typical barlines per 4-measure system: 5

## Repeat sign (||:) characteristics
- Two vertical lines 8-16px apart
- 20px merge treats them as one compound
- Dots on right = start_repeat, left = end_repeat
- At system start: the area before `||:` can be clef/key/time setup rather than a real measure
  → candidate only when the first gap is `system_start → start_repeat`; verify visually/geometrically before skipping

## Known failure modes

| Issue | Symptom | Fix |
|-------|---------|------|
| TAB staff / non-5-line staff | Extra or missed staff-line peaks | Verify detected `staves`/`stave_count`; adjust staff detector if TAB is not captured |
| Repeat sign as barline | Possible setup pseudo-gap at system start | 20px merge + verify `system_start → start_repeat` candidate before skipping |
| 1st/2nd ending bracket | Extra vertical marks near system end | Keep barline-derived measure gaps; verify suspect crops visually |
| Score watermark | False vertical/dot detection | Area/circularity filters on dots |
