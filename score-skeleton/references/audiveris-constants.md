# Audiveris CLI Constants

Audiveris `-constant "key=value"` overrides application constants at runtime.
Paths use `omr.` prefix (strips `org.audiveris.` package prefix).

## Discovered Constants

| Constant Path | Type | Default | Effect |
|---|---|---|---|
| `omr.text.Language.defaultSpecification` | String | `eng` | OCR language code(s), `+`-separated (e.g. `eng+kor+deu`) |
| `omr.text.tesseract.TesseractOCR.useOCR` | Boolean | `true` | Set `false` to disable ALL OCR (chords, dynamics, lyrics, text) |
| `omr.text.tesseract.TesseractOCR.minConfidence` | Double | `0.65` | Minimum confidence threshold for OCR validity |
| `omr.text.tesseract.TesseractOCR.forceSingleBlock` | Boolean | `false` | Force PSM_SINGLE_BLOCK instead of PSM_AUTO |
| `omr.text.tesseract.TesseractOCR.saveImages` | Boolean | `false` | Save OCR input images to disk for debugging |

## CLI Usage

```bash
audiveris -batch \
  -constant "omr.text.Language.defaultSpecification=eng+kor" \
  -constant "omr.text.tesseract.TesseractOCR.useOCR=true" \
  -step LINKS -export "score.pdf" -output _scratch/
```

Multiple `-constant` flags can be chained.
Values can use `=` or `:` as separator (`key=value` or `key : value`).

## Important: No Step-Skip Mechanism

Audiveris has **no way to skip individual steps**. The pipeline is strictly sequential:
`LOAD → BINARY → SCALE → GRID → HEADERS → STEM_SEEDS → BEAMS → LEDGERS → HEADS → STEMS → REDUCTION → CUE_BEAMS → TEXTS → MEASURES → CHORDS → CURVES → SYMBOLS → LINKS → RHYTHMS → PAGE`

`-step X` means "run up to and including X" — all intermediate steps execute.
`getNeededSteps()` in SheetStub.java iterates from first to target with no skip logic.

To avoid garbage lyrics without losing chord symbols:
- **Cannot skip TEXTS alone** (no mechanism exists)
- Option A: `useOCR=false` → disables ALL text (fast, loses chords/dynamics)
- Option B: Post-process .mxl to strip `<lyric>` elements (keeps chords/dynamics)

## Korean OCR Notes

With `tesseract-ocr-kor` installed and `-constant "omr.text.Language.defaultSpecification=eng+kor"`:
- Korean lyric recognition **works on WSL** (tested: 163 Korean lyrics, 89 English, 0 garbage on Finale PDF)
- The constant MUST be set explicitly — Tesseract having `kor` installed is not enough; Audiveris defaults to `eng` only
- If `defaultSpecification` is not set, Korean lyrics come out garbled (`°1ﬂ1°l`, `HErEEZdQ'DPE`)
- Windows Tesseract also works, but WSL is sufficient with the correct constant

## Boolean Constant Caveat

`useOCR=false` **may not take effect** in some Audiveris versions — we observed identical lyric counts with both `true` and `false` settings (both produced 106 lyrics). If OCR disable is critical, verify by checking `<lyric>` element count in the output `.mxl` before proceeding.
