# To Find You — Audiveris Post-Mortem

Song: "To Find You" (Sing Street OST)
PDF: Finale 2008 export
Audiveris: 5.10.2 on WSL + Windows GUI

## Step-by-step results

| Stop step | Measures | Notes (P1 V1) | Notes (P1 all) | Notes (P2) |
|-----------|----------|---------------|----------------|------------|
| `-step SYMBOLS` | 37 | 174 | 186 | 31 |
| `-step LINKS` | 33 | 174 | 186 | 31 |
| `-step GRID` only | (no .mxl) | — | — | — |

## Root cause

GRID detected 9 staves correctly (3 systems × 3 parts) but barline serifs were too thin:

```
BarsRetriever: Staff#2 serif normalized weight too small 0.02 vs 0.2
```

Finale-generated barlines are thinner than the Audiveris classifier expects. This causes ~20 undetected barlines → MEASURES step produces 33 instead of 57.

## Key diagnostics

- `m.duration.quarterLength` vs `m.barDuration.quarterLength` identifies overflow
- 8.00 ql = exactly 2 merged 4/4 measures (most common)
- `<arpeggiate>` elements inside `<note>` → `<notations>` = genuine arpeggios (keep)
- `<arpeggiate>` at measure boundary with no preceding `<note>` = barline misID (remove)

## LLM-driven rebuild approach

1. Flatten V1 notes sequentially across all measures
2. Use 4/4 → 48-duration-unit boundaries
3. Present the note stream (pitch, beam, tie, offset) to the LLM
4. LLM proposes barline positions based on musical context
5. Split measures, remove arpeggios at newly-created boundaries, output .mxl

## Naming

- `split_fixed.mxl` — first raw-XML split attempt (43 measures, had duplicates)
- `rebuild.mxl` — attempted flat-to-measure rebuild (had voice-offset bugs)
- `_scratch/Finale 2008 - [Sing Street OST-To Find You(ar).MUS].mxl` — cleanest starting point (LINKS, 33 measures)
