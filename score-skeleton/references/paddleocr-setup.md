# PaddleOCR Setup for Chord Symbol Reading

## Version Pairing

Tested working combination:
- **paddleocr==2.10.0** (PP-OCRv3 detection + PP-OCRv4 recognition)
- **paddlepaddle==2.6.2** (CPU/GPU)
- **Python 3.11** (brew: `/home/linuxbrew/.linuxbrew/bin/python3.11`, system: `/usr/bin/python3.11`)

PaddlePaddle does NOT support Python 3.12+ on Linux (no wheels). Python 3.11 is required.

## Installation

```bash
python3.11 -m venv /tmp/paddle_venv
/tmp/paddle_venv/bin/pip install "paddlepaddle<3.0" "paddleocr<3.0"
```

This downloads ~2GB of model files on first run. Models cached at `~/.paddleocr/whl/` and `~/.paddlex/official_models/`.

## Observed behavior (first-staff tight crops, PAD_X=16)

Per-measure crop from system start (`y0`) to first staff bottom (`staves[0].bot`), PAD_X=16. Current SKILL.md uses this crop shape because it keeps chord symbols + first staff while excluding lower staffs/lyrics noise.

| Input | OCR Output | Confidence | Correct? |
|-------|-----------|------------|----------|
| F#m | F#m | 1.00 | ✅ |
| F#m7 | F#m7 | 1.00 | ✅ |
| D(add9) | D(add9) | 0.96 | ✅ |
| D M7 | D M7 | 0.81 | ⚠️ space |
| Dm | D m | 1.00 | ⚠️ space |
| /E | /E | 0.93 | ✅ |
| /G# | /G# | 0.90 | ✅ |
| /B | /B | 0.92 | ✅ |
| /F | /F | 0.95 | ✅ |
| /A | IA | 0.84 | ❌ I-for-/ |
| E7sus4 | E 7sus4 | 0.99 | ⚠️ space |
| E7 | E7 | 1.00 | ✅ |
| C#7 | C#7 | 0.90 | ✅ |
| A(add9) | A(add9) | 1.00 | ✅ |
| D | D | 0.99 | ✅ |
| E | E | 0.96 | ✅ |

## Normalization After PaddleOCR

```python
import re
def normalize_paddleocr(cn):
    # Spaces inside chord: D M7 -> DM7, D m -> Dm, E 7sus4 -> E7sus4
    cn = re.sub(r'\s+', '', cn)
    # IA -> /A (I-for-/ edge case)
    cn = re.sub(r'^I([A-G][#b]?)$', r'/\1', cn)
    return cn
```

## Performance

- Cold start (loading models): ~15s (download + init on first run)
- Per image: ~0.25-0.6s (first-staff tight measure crop)
- 57 measures total: ~5-12s (sequential)

## OCR Engine Comparison (measure crops, 3 scores × 5 measures = 15 test images)

| Engine | Sharp/slash handling | Speed/image | Notes |
|--------|----------------------|-------------|-------|
| Tesseract 5 | unreliable on `#` and slash-bass samples | ~0.3-0.9s | noisy on measure crops |
| EasyOCR | unreliable on `#`; often reads slash as `I` | ~0.1-0.4s | lyrics/noise mix in more often |
| **PaddleOCR 2.10** | best empirical result on the sample set | ~0.25-0.6s | confidence values available for filtering |
| vision LLM | useful fallback when OCR fails | ~8-12s | slower; use selectively |

Tested on: Sing Street "To Find You", G-Dragon "Untitled 2014", 청하 "Roller Coaster". Current production crop is first-staff tight (`y0` → `staves[0].bot`, PAD_X=16). If crop parameters change, rerun a representative sample before updating SKILL.md.
