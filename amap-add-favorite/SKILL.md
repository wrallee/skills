---
name: amap-add-favorite
description: AMap 즐겨찾기 단건 추가. Playwright MCP 사용. 교통 거점(공항, 역, 케이블카/페리매표소 등) 최우선, 먹거리/맛집도 반드시 포함. 절대 루프 금지. 한 건 처리 후 검증 → 다음 한 건. LLM이 페이지 상황에 맞게 유연하게 대응 가능.
---

# AMap 즐겨찾기 단건 추가 (Playwright MCP)

## 절대 규칙 (반드시 준수)
1. **교통 거점 최우선**: 원본 데이터에 교통 거점(공항, 기차역, 버스 터미널, 지하철역, 케이블카매표소, 페리매표소 등) 항목이 있다면 **절대 누락 금지, 반드시 가장 먼저 처리한다**. 이 규칙이 가장 중요하다.
2. **먹거리/맛집 필수 추가**: 원본 데이터에 먹거리, 맛집, 식당, 카페, 간식, 레스토랑 등 식음료 관련 항목이 있다면 **절대 누락 금지, 반드시 모두 추가한다**. 사용자에게 먹거리 항목은 관광지만큼 중요하다.
3. **절대 코드 루프 금지**: `for`, `while`, `forEach` 등 반복문을 사용한 일괄 처리를 절대 사용하지 않는다.
4. **단건 처리 → 검증 → 다음 한 건**: 정확히 한 항목을 처리하고 DOM 상태를 검증한 후, 다음 항목으로 **자동으로 진행한다**. 사용자 확인을 받지 않는다.
5. **실패 시 기록 후 다음 항목**: 실패한 항목은 기록하고 다음 항목으로 진행한다.
6. **Playwright MCP 도구만 사용**: 모든 브라우저 조작은 `playwright_browser_run_code_unsafe`, `playwright_browser_navigate`, `playwright_browser_snapshot`, `playwright_browser_evaluate`, `playwright_browser_click` 만 사용한다.
7. **LLM 유연성 허용**: 이 스킬의 워크플로우는 권장 패턴이다. 페이지 상황에 따라 LLM이 플레이라이트 도구를 임기응변으로 사용하여 클릭/대체 전략을 구사할 수 있다. 페이지 구조가 달라졌다면 스냅샷 기반으로 유연하게 대응한다.
8. **여행지와 무관한 곳 추가 금지**: 검색 시 반드시 `${장소명}+${도시명}` 형식으로 검색한다. 검색 결과의 주소가 여행 도시와 무관하면 추가하지 않고 Skip한다. Skip된 항목은 마지막에 목록으로 사용자에게 알림.
9. **CSS 해시 클래스 사용 금지**: AMap은 CSS Modules를 사용하므로 클래스명(`__1UHoa` 등)은 빌드마다 변경된다. CSS 클래스 대신 `alt`, `src`, 구조적 셀렉터를 사용한다.

## 사전 요구사항: Playwright MCP 연결 확인

`playwright_browser_snapshot` 호출로 MCP 연결을 테스트한다. 실패 시 사용자에게 알림 후 스킬 중단.

## 실행 도구

모든 JavaScript 코드는 **`playwright_browser_run_code_unsafe`** 의 `code` 파라미터로 실행한다.

```javascript
// 코드 템플릿
async (page) => {
  // 여기에 스크립트 파일 코드 삽입
}
```

## AMap 두 가지 버전

AMap은 **구버전**과 **SSR 버전** 두 가지가 혼용된다. URL로 버전을 판단한다:

| 버전 | URL 패턴 | 스크립트 파일 |
|------|----------|---------------|
| 구버전 | `https://www.amap.com` (`/ssr/` 없음) | `scripts/old-version.js` |
| SSR 버전 | URL에 `/ssr/` 포함 | `scripts/ssr-version.js` |

### 버전 감지 코드

```javascript
async (page) => {
  const isSSR = page.url().includes('/ssr/');
  return isSSR ? 'ssr' : 'old';
}
```

LLM은 URL 확인 후 해당 버전의 스크립트 파일을 사용한다. 스크립트 파일에 포함된 Step 코드를 그대로 복사하여 실행한다.

## 워크플로우 (반드시 이 순서로 한 항목씩 처리)

### 1. 검색
- 검색 시 반드시 `${장소명}+${도시명}` 형식 사용
- 대기 시간: `await page.waitForTimeout(5000)`
- 실행: 구버전 스크립트 Step 1 또는 SSR 스크립트 Step 1

### 2. 검색결과 분석 (버전별 분기)
- **구버전** (URL `/ssr/` 없음):
  - `data-poiinfo-name` 이 검색어와 일치/startsWith 인 항목 필터
  - 매칭 ≥ 4 개 → `haversine` 으로 중심부 최단거리 지점 선택
  - 매칭 1~3 개 → 첫 매칭 선택 / 없으면 첫번째 폴백
  - `<CITY_LNG>`, `<CITY_LAT>` 는 LLM 이 도시 중심 좌표로 주입
  - 실행: 구버전 Step 2
- **SSR 버전** (URL `/ssr/` 포함):
  - SSR DOM 에 좌표 데이터가 없어 거리 계산 불가
  - 첫 `.poi-card` 클릭으로 진행
  - 실행: SSR Step 2

### 3. 상세페이지 주소 검증 ⭐ 중요
- 상세패널/상세페이지의 `.feedaddr`(구버전) 또는 `img[alt="位置"]` 인근 span(SSR)으로 주소 확인
- **schedule 도시 목록과 비교하여 일치하지 않으면 Skip**
- `skip` 반환 시 → 즐겨찾기 클릭 금지. Step 6으로 건너뛰어 다음 항목
- 실행: Step 3

### 4. 즐겨찾기 클릭 (Step 3 검증 통과 시에만 실행)
- `ok` 반환 후에만 실행
- 이미 저장됨(`faved`/filled star) 체크 → 재클릭 금지
- 실행: Step 4

### 5. 최종 검증
- 즐겨찾기 성공 확인
- 실행: Step 5

### 6. 다음 항목 준비
- 구버전: 상세패널 닫기(`#placereturnfixed i.icon-angleleft`), 검색창 초기화
- SSR: 검색바 초기화
- 실행: Step 6

### 7. 검토 필요 항목 기록
prefix match가 4개 이상인 경우, 자동으로 판단하지 말고 `add-favorite-log.md`에 기록한다.

- **파일명**: `add-favorite-log.md` (작업 디렉토리에 누적 기록)
- **실행일**: `YYYY-MM-DD HH:mm:ss`
- **양식**:
```
실행일: {date}

| 검색어 | 결과 |
|--------|--------|
| {query} | {count}개 |

---
```
- **기록 내용**: 검색어와 prefix match 개수만 기록

## 오류 대응
- 각 Step 실패 시 → 동일 코드를 개별적으로 최대 3회 재실행 (for/while 루프 아님)
- 3회 재시도 후 실패 → `playwright_browser_navigate` 로 페이지 재진입
- **"抱歉！未能获取到该地点信息" 표시 시 → 로딩 실패. 즉시 `page.reload()` 후 재진입**
- 여전히 실패 → 해당 항목 기록 → 다음 항목으로 자동 진행
