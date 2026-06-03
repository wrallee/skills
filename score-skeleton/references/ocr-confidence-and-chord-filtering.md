# OCR confidence and chord filtering

Use this when tuning PaddleOCR chord-symbol acceptance.

## Confidence policy

- `conf < 0.5`: treat as failed; use vision fallback or manual review.
- `0.5 <= conf < 0.8`: keep only if chord-candidate filtering and `music21.harmony.ChordSymbol()` validation both pass; log/flag for review.
- `conf >= 0.8`: accept if filtering and parser validation pass.

Rationale: a real Roller Coaster run had a valid `A` at confidence `0.519`, so `0.8` is too high as a hard reject threshold. Below `0.5`, fallback is safer.

## Whitelist/regex role

Use a chord-candidate whitelist/regex only to reject non-chord OCR output. Do not auto-correct to the nearest chord spelling; that can silently change musical meaning (`D` vs `Dm`, `F` vs `F#`, `/A` vs `IA`).

Recommended order:

1. normalize OCR text first (`D M7` → `DM7`, unicode accidentals, slash-bass edge cases);
2. apply a case-insensitive chord-candidate regex/whitelist;
3. validate semantically with `music21.harmony.ChordSymbol()`;
4. only then insert into `chord_map`.

Example candidate filter:

```python
CHORD_CANDIDATE_RE = re.compile(
    r'^(?:[A-G][#b]?(?:[A-Za-z0-9+#b()/-]*)|/[A-G][#b]?)$',
    re.IGNORECASE,
)

def is_chord_candidate(cn: str) -> bool:
    return bool(CHORD_CANDIDATE_RE.match(cn))
```

Keep confidence/bbox data in debug output only. Production `chord_map` entries stay `(chord, beat)`.
