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

## Tested Accuracy (full-height measure crops, PAD_X=16)

Per-measure, full system height. 57 measures across 3 scores.

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
- Per image: ~0.25-0.6s (full-height measure crop, ~40-65KB)
- 57 measures total: ~5-12s (sequential)

## OCR Engine Comparison (measure crops, 3 scores × 5 measures = 15 test images)

| Engine | # (sharp) | / (slash) | 7 (seven) | Speed/image | Noise |
|--------|-----------|-----------|-----------|-------------|-------|
| Tesseract 5 | ⚠️ ~50% (F#m/Fim) | ⚠️ /E 읽힘, /A 실패 | ⚠️ variable | ~0.3-0.9s | ❌ 매우 심함 |
| EasyOCR | ❌ 0% (Fim/FHm) | ❌ I로 읽음 | ⚠️ Z for 7 | ~0.1-0.4s | ⚠️ lyrics 섞임 |
| **PaddleOCR 2.10** | ✅ 100% (15/15) | ✅ 90% | ✅ 100% | **~0.25-0.6s** | ✅ conf 필터링 가능 |
| vision LLM | ✅ | ✅ (full crop) | ✅ | ~8-12s | ✅ context 이해 |

Tested on: Sing Street "To Find You", G-Dragon "Untitled 2014", 청하 "Roller Coaster". All tests used the same full-height measure crops, not chord-only crops (which would favor OCR engines further).

## Deployment / Integration Options (beyond Python pip)

PaddleOCR is a **Python package**, but Paddle Inference models (det+rec) can be deployed outside Python:

| Approach | Language | Effort | Notes |
|----------|----------|--------|-------|
| **Paddle Inference Java API** (JNI) | Java | 중간 | `com.baidu.paddle.inference` — Config, Predictor, Tensor classes. GitHub: `PaddlePaddle/Paddle` → `paddle/fluid/inference/experimental/javaapi/`. **실험적(experimental)**. Low-level — OCR pipeline logic (detection post-processing → recognition decoding → result assembly) must be reimplemented in Java. |
| **Paddle Inference C API** | C (→ any JNI) | 중간 | 기반 C API로 다른 언어 바인딩 가능. JavaCPP로 wrapping도 가능 (bytedeco 스타일). |
| **Paddle Lite / Paddle2ONNX** | Android Java / any | 중간 | Mobile deployment via Android Java SDK. ONNX export → ONNX Runtime from any language. |
| **Python subprocess** | Java → Python | 낮음 | `Runtime.exec("python3 -c '...'")` — simplest, but Python dependency + IPC overhead. |
| **HTTP server** | Java → Python REST | 낮음 | FastAPI/Flask wrapper, Java calls HTTP. Clean separation, no JNI complexity. |

**Key takeaway:** Paddle Inference does have an official Java JNI API (experimental), so writing JavaCPP bindings from scratch is NOT required. However, PaddleOCR's high-level pipeline (detection → recognition → result assembly) is Python-only — porting that pipeline logic to Java is the real work, not the JNI layer itself.
