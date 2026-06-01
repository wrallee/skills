---
name: score-skeleton
description: >-
  Source score PDF → MusicXML (.mxl) with chord symbols.
  OpenCV detects systems/barlines with type classification,
  LLM vision reads chords from system composites with text measure ranges.
  Output preserves source PDF's system/page layout.
---

# Score Skeleton Transcription

```
Pipeline:
  1. PDF → PNG                  (pdftoppm -r 300, 모든 페이지 한 phase에)
  2. OpenCV 구조 검출           (staff → systems → barlines, 모든 페이지)
  3. System composite → LLM     (measure 범위 텍스트로, 모든 페이지 parallel batch)
  4. .mxl 생성                  (ChordSymbol + chordKindStr + metadata + breaks)
```

**실행 순서: 모든 페이지를 Phase 단위로 처리. 페이지별로 Phase 1→4 돌리지 말 것.**

---

## 1. PDF → PNG

```bash
cp "원본파일.pdf" source.pdf
mkdir -p _scratch
pdftoppm -png -r 300 source.pdf _scratch/page
```

---

## 2. OpenCV 구조 검출

`detect_structure.py`는 이 스킬 디렉토리의 `scripts/`에 들어있는 linked script다. **복사할 필요 없이 bundled script를 그대로 실행한다.** 작업 디렉토리에서 실행하면 `_scratch` 입출력은 작업 디렉토리 기준으로 잡힌다. **사용자 홈/프로파일 절대경로를 SKILL.md에 박지 말 것.**

```bash
# Run from the score workdir. Use this skill's bundled script path.
for pn in $(seq 1 $N); do
    .venv/bin/python3 <skill_dir>/scripts/detect_structure.py $pn
done
```

Hermes agent는 `skill_view('score-skeleton')` 결과의 `skill_dir` 값을 `<skill_dir>`에 대입한다. 스크립트를 수정해야 할 때만 작업 디렉토리로 복사한다.

### Staff 검출
Horizontal projection → 5-line clustering (13-21px, ±4 tolerance) → 3-stave grouping (vocal+guitar+TAB, 또는 piano RH+LH). TAB(6-line) 포함.

### Barline 검출 → 분류
Vertical line: Morphological open (kernel = system_height × 0.4).
Compound grouping: < 20px merge.
Dot detection: compound 중심 ±35px, connectedComponents 원형 blob, area 20-120px², circularity ≥ 0.5.

| type | 조건 |
|------|------|
| `system_start` | system 첫 줄 |
| `system_end` | system 마지막 줄 |
| `thin` | single line |
| `start_repeat` | compound + dots 우측 |
| `end_repeat` | compound + dots 좌측 |
| `end_start_repeat` | compound + dots 양측 |
| `double` | compound + dots 없음 |
| `final` | compound + 마지막 줄 두꺼움 |

### output: `_scratch/p{N}_struct/structure.json`
```
{
  page: N,
  systems: [
    { y0_page, y1_page, vocal_staff_top,
      barlines: [{ type, x, num_lines, dots_left, dots_right }],
      num_measures
    }
  ]
}
```

---

## 3. System Composite → LLM Vision

### 3A. Crop + measure 범위 명시

각 system을 페이지에서 crop. **프롬프트에 measure 범위를 텍스트로 박는 게 barline 마커다.**

```python
for pn in pages:
    for si, sys in enumerate(page_data[pn]['systems']):
        crop = page_img[sys.y0:sys.y1, :]
        cv2.imwrite(f'_scratch/clean/p{pn}_s{si}.png', crop)
```

### 3B. LLM Vision (모든 시스템 parallel batch)

같은 응답에서 vision_analyze를 모든 시스템에 대해 한 번에 전송. 시스템별 반복 금지.

Prompt:
```
This system contains M{X}~M{Y}. Read chord symbols above the staff per measure
with beat position. Return JSON: [[["chord", beat], ...], ...].
"empty" if blank. Exact text.
```

응답 예시:
```json
[[["A", 1], ["C#m7", 3]], [["F#m7", 1], ["E", 3]], [["D", 1], ["Esus4", 3.5]], [["A", 1]]]
```

**M{X}~M{Y} 범위를 LLM에 전달하는 것이 곧 barline 마커다.** LLM은 이 범위를 보고 measure 수를 정확히 알며 hallucination하지 않는다.

### 3C. Lead-In 제거 (조건부)
시스템 첫 measure가 `start_repeat` 오른쪽 barline이고 LLM 응답에서 chord 없음 → 해당 measure 폐기, 이후 번호 -1 shift.

---

## 4. .mxl 생성

### 4A. 구조 데이터 → break map (자연스러운 귀결)

structure.json에서 직접 break 정보 추출. 별도 STRUCTURE dict 계산 불필요.

```python
import re, json, glob
from music21 import *

struct_files = sorted(glob('_scratch/p*_struct/structure.json'))
struct = {}
for fpath in struct_files:
    pn = int(re.search(r'p(\d+)_struct', fpath).group(1))
    struct[pn] = [s['num_measures'] for s in json.load(open(fpath))['systems']]

sys_breaks = set()
pg_breaks = set()
running = 0
for pn in sorted(struct.keys()):
    for si, n_meas in enumerate(struct[pn]):
        sys_first = running + 1
        if sys_first > 1:
            sys_breaks.add(sys_first)
            if si == 0:
                pg_breaks.add(sys_first)
        running += n_meas
```

### 4B. Metadata + skeleton

```python
score = stream.Score()
score.metadata = metadata.Metadata()
score.metadata.title = '곡 제목'       # PDF 페이지 1에서 vision으로 추출
score.metadata.composer = '작곡가'      # 또는 source PDF 파일명에서 유추

part = stream.Part()
part.partName = 'Voice'
part.append([clef.TrebleClef(), key.KeySignature(KEY_SHARPS), meter.TimeSignature(TIME_SIG)])
for n in range(1, MEASURE_COUNT + 1):
    m = stream.Measure(number=n)
    if n in pg_breaks:
        m.insert(0, layout.PageLayout(isNew=True))
        m.insert(0, layout.SystemLayout(isNew=True))
    elif n in sys_breaks:
        m.insert(0, layout.SystemLayout(isNew=True))
    m.append(note.Rest(quarterLength=BAR_QL))
    part.append(m)
score.insert(0, part)
score2 = converter.parse(score.write('musicxml', '_base.mxl'))
```

### 4C. Chord injection

```python
def norm(cn):
    cn = re.sub(r'\s+', '', cn)
    cn = re.sub(r'[()]', '', cn)
    return cn

prev_root = ''
for mn, chords in sorted(chord_map.items()):
    m = score2.parts[0].measure(mn)
    for cn, beat in chords:
        cn = norm(cn)
        # Slash chord: prev_root + /E → prev_root/E
        if cn.startswith('/') and len(cn) > 1 and prev_root:
            cn = f'{prev_root}{cn}'
        offset = (beat - 1) * 1.0  # beat 1 = offset 0.0
        cs = harmony.ChordSymbol(cn)
        cs.chordKindStr = cn        # ★ 필수: display text 강제
        cs.offset = offset
        m.insert(offset, cs)
        prev_root = cn.split('/')[0]
```

`cs.chordKindStr = cn` ★ 필수. 이거 없으면 E7sus4가 "suspended-fourth-seventh"로 표시됨.
ChordSymbol에 입력한 문자열이 그대로 `<kind text="E7sus4">` 속성이 된다.

- DM7, F#m7, Bm7 등 표준 코드는 자동 text 설정되지만 통일을 위해 항상 지정.
- 괄호 `(add9)` 등은 `re.sub(r'[()]', '', cn)`로 사전 제거.
- `DM7` → `ChordSymbol("DM7")` 후 `chordKindStr="DM7"`.

### 4D. Verify

```python
s3 = converter.parse('final.mxl')
total = sum(1 for me in s3.parts[0].getElementsByClass(stream.Measure)
            for e in me.recurse() if isinstance(e, harmony.ChordSymbol))
print(f'{total} chords in final.mxl')
```

---

## Notes

- **Phase 단위 실행:** 모든 페이지를 한 phase에서 다 처리한 후 다음 phase로.
- **300dpi 필수.**
- **Compound merge < 20px.**
- **프롬프트 measure 범위 필수** — "M{X}~M{Y}"로 barline hallucination 방지.
- **Parallel batch** — vision_analyze 여러 개는 같은 응답에서 한 번에 전송.
- **chordKindStr** — display text 강제. E7sus4 → "suspended-fourth-seventh" 방지.
- **Generator script** — `gen_mxl.py`/`gen_xml.py` 같은 생성 스크립트는 작업별 임시 파일이다. 스킬 요건은 스크립트 파일 자체가 아니라 `metadata`, `structure.json → breaks`, `ChordSymbol(cn)`, `cs.chordKindStr = cn` 패턴이다.
- **괄호 정규식 제거** — `re.sub(r'[()]', '', cn)`.
- **Layout natural flow** — structure.json → break map 직접 파생. 별도 계산 불필요.
- **File 전달:** 요청 시, 해당 채널로.
- **`.venv/` 보존.**
- **땜빵 금지** — 임시 STRUCTURE dict, 이미지 오버레이, 수동 break map 등 불필요한 우회 금지.
- **`chordKindStr = cn` 바로 다음에 `cs.offset = offset` 할 것.** 순서 바뀌면 offset이 무시됨.
