# Sing Street OST — To Find You score notes

Use this only when the user is working in the `to-find-you-skeleton` workdir or with the source PDF titled similar to `Finale 2008 - [Sing Street OST-To Find You(ar).MUS].pdf`.

Verified structure facts from clean reruns:

```text
Source pages: 4
Expected real measures: 57
STAVES_PER_SYSTEM: 3

page totals:
  p1: 13 measures
  p2: 16 measures
  p3: 16 measures
  p4: 12 measures
  total: 57
```

A later full rerun produced a verified skeleton with:

```text
final.mxl parse verification:
  measures: 57
  chord symbols: 117
  double/final barlines present
  major-seventh kind present
```

Chord-reading workflow that worked best for this source:

```text
1. Run OpenCV detection with staves-per-system=3.
2. Generate measure_entries.json and per-measure crops.
3. Also generate padded annotated system crops:
   - include extra vertical padding above the top vocal staff
   - draw red measure boundaries
   - put measure labels in a top white strip so labels do not cover chord text
4. Prompt vision to read only printed chord symbols above the top vocal staff.
   Ignore accompaniment notation, TAB, fret numbers, lyrics, and inferred harmony.
```

Normalization examples from the verified run:

```text
A(add9)  -> Aadd9
D(add9)  -> Dadd9
E sus4   -> Esus4
E 7      -> E7
D M7     -> DM7
/F       -> C#7/F    # previous full chord C#7
/E       -> F#m/E or F#m7/E depending on previous full chord
/G#      -> F#m7/G#
/A       -> F#m7/A
/B       -> F#m7/B
```

Pitfall:

```text
STAVES_PER_SYSTEM=2 is wrong for this source.
It over-splits systems/barlines and produces a bogus measure count around 156 raw gaps.
```

Clean-slate convention for this workdir:

```text
Preserve:
- original PDF
- .venv, if still present and the user has not explicitly asked to remove it

Delete before rerun:
- _scratch/
- source.pdf
- final*.mxl
- final*.zip
- generated scripts / temporary XML outputs
```

`_scratch/` contents are temporary only: page PNGs, structure JSON, system crops, measure crops, and measure-entry JSON. Do not present `_scratch` as a deliverable; remove it when the user asks to clear the directory or after final delivery if no longer needed.
