---
name: score-skeleton
description: >-
  Source score PDF → MusicXML (.mxl) with chord symbols.
  OpenCV detects systems/barlines with type classification
  (thin, start_repeat, end_repeat, double, final),
  LLM vision reads chords from per-measure crops.
  Use before downstream arrangement (bass TAB, practice material).
---

# Score Skeleton Transcription

```
Pipeline:
  1. PDF → PNG                  (pdftoppm -r 300)
  2. OpenCV 구조 검출           (staff → systems → barlines with type)
  3. Per-measure crop → LLM     (barline-bounded crops → chord text)
  4. Post-process               (clef area before system-start repeat → drop)
  5. .mxl 생성                  (music21 ChordSymbol)
```

---

## 1. PDF → PNG

```bash
mkdir -p _scratch
pdftoppm -png -r 300 "source.pdf" _scratch/page
# → _scratch/page-{1..N}.png
```

## 2. OpenCV 구조 검출 (`scripts/detect_structure.py <page_n>`)

### 2A. Staff 검출
Horizontal projection → 5-line clustering (19px 간격 ±3 tolerance) → **3-stave grouping** (piano = vocal + RH + LH).

### 2B. Barline 검출 → 분류

**Vertical line:** Morphological open (tall kernel, height=system_height×0.4) → column projection.

**Compound grouping:** `< 20px` 간격 line들을 merge.

**Dot detection:** 각 compound 중심 ±35px에서 connectedComponents로 검은 원형 blob(면적 20-120, circularity≥0.5) 검출. 3-stave 악보는 6 dot 검출 시 repeat 확정.

**분류 순서 (dot 우선):**
| type | 조건 |
|------|------|
| `system_start` | system 첫 줄 |
| `system_end` | system 마지막 줄 |
| `thin` | single line |
| `start_repeat` | compound + dots 우측 |
| `end_repeat` | compound + dots 좌측 |
| `end_start_repeat` | compound + dots 양측 |
| `double` | compound + dots 없음 |
| `final` | compound + 마지막 줄 두꺼움 (>6px) |

---

## 3. Per-Measure Crop → LLM Vision

### 3A. Crop (`scripts/crop_measures.py <page_n>`)
```python
meas_x = [b['x'] for b in barlines if b['type'] not in ('system_start','system_end')]
all_x = [start_x] + meas_x + [end_x]
for mi in range(len(all_x) - 1):
    crop = img[y0:y1, all_x[mi]+3 : all_x[mi+1]-3]
```
→ `_scratch/pN_measures/M{mm}.png` (~500×95px)

### 3B. LLM Prompt
```
Single measure crop. Read chord symbol(s) printed above the staff.
Exact text only. If empty, say "empty".
```
간단할수록 좋다. barline 좌표, beat, system 번호 전달 불필요.

### 3C. Lead-In Measure 제거
시스템 첫 measure가 `start_repeat` 오른쪽 barline이고 LLM이 "empty"라고 응답하면 → 폐기, 이후 measure 번호 -1 shift.

---

## 4. .mxl 생성

```python
from music21 import *

score = stream.Score()
part = stream.Part()
part.partName = 'Voice'
part.append([clef.TrebleClef(), key.KeySignature(3), meter.TimeSignature('4/4')])

for n in range(MEASURE_COUNT):
    m = stream.Measure(number=n+1)
    m.append(note.Rest(quarterLength=4.0))
    part.append(m)
score.insert(0, part)

score2 = converter.parse(score.write('musicxml', 'skeleton.mxl'))
for measure_num, chords in chord_map.items():
    m = score2.parts[0].measure(measure_num)
    for chord_name, offset in chords:
        cs = harmony.ChordSymbol(chord_name)
        cs.offset = offset
        m.insert(offset, cs)
score2.write('musicxml', 'final.mxl')
```

- `ChordSymbol("DM7")` 직접 사용. `.text` 수동 설정 금지.

## Notes

- **300dpi 필수.**
- **Compound merge: < 20px.** Repeat sign 두 줄(8-16px) 병합.
- **Dot detection 먼저, 두께 검사 나중.**
- **File 전달:** 요청 시에만, 요청 온 채널로 전달.
- **`.venv/` 보존.** `pip install opencv-python-headless`
