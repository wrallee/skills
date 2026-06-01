# Detection Parameters (300dpi)

## Page characteristics
- Size: ~2481×3509px (A4 at 300dpi)
- Staff line spacing: 17-21px (5 lines per staff; varies by engraver/PDF generation)
- Staff height: ~64-84px (top line to bottom line)
- System height: ~400-700px (3 staves + inter-staff gaps)
- Chord area y-range: vocal staff top - 105px to vocal staff top + 5px (adjust if chords clipped)
- Vocal+guitar+TAB scores: 3 staves per system (5 + 5 + 6 lines respectively)

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
- At system start: area before ||: is clef/key/time only — not a real measure
  → LLM reads "empty" + post-process discards it

## Known failure modes

| Issue | Symptom | Fix |
|-------|---------|------|
| TAB staff (6 lines) | Extra peaks break rigid 5-line search | Variable spacing + 3-stave grouping |
| Repeat sign as barline | Extra measure at system start | 20px merge + post-process discard |
| 1st/2nd ending bracket | Extra barline(s) at system end | LLM per-measure crop ignores them |
| Score watermark | False vertical/dot detection | Area/circularity filters on dots |
