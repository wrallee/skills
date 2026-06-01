# Detection Parameters (300dpi, verified on Roller Coaster score)

## Page characteristics
- Size: ~2481×3509px (A4 at 300dpi)
- Staff line spacing: 19-20px (5 lines per staff)
- Staff height: ~76-80px (top line to bottom line)
- System height: ~600-700px (3 staves + inter-staff gaps)
- Inter-staff gaps: vocal→RH ≈ 216px, RH→LH ≈ 156px
- Chord area y-range: vocal staff top - 105px to vocal staff top + 5px

## Horizontal projection
- Threshold: w * 0.25 (staff lines are dense black, ~2500×0.25=625)
- Minimum consecutive rows: 2
- Typical peak count: 45 (3 sys × 3 staves × 5 lines) per page

## Robust 5-line clustering
- Expected line interval: 19px (tolerance ±3px)
- Algorithm: for each peak as potential top, check if next 4 exist at expected positions
- Skip misaligned windows (noise peaks between staff lines)

## Barline detection
- Vertical kernel height: system_height * 0.4
- Column projection threshold: 5 (binary pixels per column)
- Minimum barline width: 2px
- Double barline/repeat sign merge threshold: **20px** (15px는 16px 간격 repeat sign 누락)
- After merge, typical barlines per 4-measure system: 5

## Repeat sign (||:) characteristics
- Two vertical lines 8-16px apart
- First line = thin barline, second = repeat barline (slightly thicker or same thickness)
- Sometimes preceded by another thin barline (16px gap before the pair)
- Both lines span full system height (all 3 staves)
- Dots (two small filled circles) on the right side of the pair, staff-height range
- **At system start:** the area before ||: (between system edge and barline) is NOT a measure
  — it contains only clef(s), key signature, time signature.
  - Width of this area: ~170-180px (vs normal measure ~500px)
  - LLM will read it as "empty" (no chord symbol)
  - Fix: Step 3B post-processing (was_pair + empty check -> discard)
- **In middle of system:** ||: is a normal measure boundary. Merge handles it correctly.

## Known failure modes

| Issue | Symptom | Fix |
|-------|---------|-----|
| Gap-based system grouping | 1 system with 12 staves (P2) | Fixed 3-stave grouping |
| Repeat sign as barline | Extra measure at system start | 20px merge + Step 3B post-processing |
| Measure number as chord | '5', '9' at ratio ~0.25 | Not needed (LLM reads full crop) |
| Staff line noise | Extra peaks (lyrics underline) | Robust 5-line clustering skips them |
| 1st/2nd ending bracket | Extra barline(s) at system end | LLM per-measure crop ignores them |
