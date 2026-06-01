# Barline Recovery Techniques

When Audiveris misses thin barlines (common with Finale-generated PDFs), the `.mxl` has merged measures (e.g. 33 measures instead of the original 57).

## Root Cause

- GRID step detects all staves correctly but thin barlines have "serif normalized weight too small" (< 0.2 threshold)
- Barline→arpeggio misclassification: Audiveris classifies thin vertical lines as arpeggios instead of barlines
- Affected staves flagged in log: `Staff#N serif normalized weight too small X vs 0.2`
- The MEASURES step can only create measures from detected barlines → missing 15‑24 barlines

## Step Choice Matters

| Step | Measures | Notes |
|------|----------|-------|
| full pipeline | 33 | RHYTHMS + LINKS merge aggressively |
| `-step LINKS` | 33 | Same as full |
| `-step SYMBOLS` | 37 | Best yield, stops before LINKS reduction |
| GRID manual fix | full (57) | Requires GUI — takes long |

Always prefer `-step SYMBOLS -export` for problematic PDFs.

## LLM-Based Barline Inference

1. Get SYMBOLS-step .mxl (37 measures)
2. For each overflow measure (8‑10 ql = 2 merged measures), inspect:
   - Note pitch sequence (sequential note pattern reveals a natural break)
   - Beam group boundaries (beams rarely cross measure boundaries)
   - Voice structure (backup/forward elements suggest voice resets at measure boundaries)
   - Time signature (split at multiples of 4 ql for 4/4)
3. Insert `<barline location="right"><bar-style>regular</bar-style></barline>` at the split point
4. Assign sequential measure numbers, mark second half as `implicit="yes"`

## Arpeggio → Barline Detection

Signatures:
- `<arpeggiate>` inside `<notations>` of a note at measure boundary
- Duration mismatch (8‑10 ql vs expected 4 ql)
- Voice excess in Audiveris log for the same measure
- In overflow measure XML, arpeggiate present but no barline at measure start

## MusicXML Format Note

Audiveris 5.10.2 outputs MusicXML 4.0.3 **without xmlns namespace** on root element. Use bare tag names with `ET.fromstring()`. music21 handles both formats, but its `.duration.quarterLength` can be wrong for multi-voice measures with `<backup>` elements.

## To Find You Reference

57 measures original (4/4, A major, 3 sharps), 3 parts: Voice + AG. 1 + Voice(backing). 4 pages. SYMBOLS step gave 37 measures → 20 LLM barline insertions needed.
