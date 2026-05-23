---
name: amap-update-memo
description: AMap 즐겨찾기 메모 단건 수정. Playwright MCP 사용. /ssr/favorite → 항목 찾기 → 3점 메뉴 →备注 → 메모 입력 → 저장. 최대 3회 재시도(코드 루프 아님). 루프 금지.
---

# AMap 즐겨찾기 메모 단건 수정 (Playwright MCP — 구버전 + SSR버전 동시 지원)

## 사전 요구사항: Playwright MCP 연결 확인

`playwright_browser_snapshot` 호출로 MCP 연결을 테스트한다. 실패 시 사용자에게 알림 후 스킬 중단.

## 절대 규칙 (반드시 준수)
1. **절대 코드 루프 금지**: `for`, `while`, `forEach` 등 반복문을 사용한 일괄 처리를 절대 사용하지 않는다.
2. **단건 처리 → 검증 → 다음 한 건**: 정확히 한 항목을 처리하고 저장 완료 검증 후, 다음 항목으로 **자동으로 진행한다**. 사용자 확인을 받지 않는다.
3. **강제 클릭**: 모든 조작은 `page.evaluate()` 를 통해 DOM 요소에 직접 수행한다.
4. **3회 재시도 (코드 루프 아님)**: 각 Step 실패 시 **동일한 코드를 최대 3번 개별 실행**한다. `for`/`while` 루프로 감싸지 않는다. 3회 실패 시 `page.reload()` 수행.
5. **CSS 해시 클래스 사용 금지**: AMap CSS Modules(`__uGD7f`, `__v4gk1` 등) 빌드마다 변경. `alt`/`placeholder`/텍스트 콘텐츠 기반 셀렉터만 사용.
6. **"抱歉！未能获取到该地点信息" 표시 시 → 로딩 실패. 즉시 `page.reload()` 후 재진입**

## 실행 도구

모든 JavaScript 코드(`page.evaluate`, `querySelector` 등)는 **`playwright_browser_run_code_unsafe`** 의 `code` 파라미터로 실행한다.

```javascript
// 코드 템플릿
async (page) => {
  // 여기에 스크립트 파일 코드 삽입
}
```

## AMap 두 가지 버전

URL로 버전을 판단한다:

| 버전 | URL 패턴 | 즐겨찾기 URL | 스크립트 파일 |
|------|----------|--------------|---------------|
| 구버전 | `https://www.amap.com` (`/ssr/` 없음) | `https://www.amap.com/faves` | `scripts/old-version.js` |
| SSR 버전 | URL에 `/ssr/` 포함 | `https://www.amap.com/ssr/favorite` | `scripts/ssr-version.js` |

### 버전 감지 코드

```javascript
async (page) => {
  const isSSR = page.url().includes('/ssr/');
  return isSSR ? 'ssr' : 'old';
}
```

LLM은 URL 확인 후 해당 버전의 스크립트 파일을 사용한다.

---

## 구버전 DOM 구조

- **즐겨찾기 URL**: `https://www.amap.com/faves`
- **즐겨찾기 항목**: `li.favitem`
  - **제목**: `.favtitle` (또는 `input.fav-edit-input` 수정 모드일 때)
  - **주소**: `.favaddr`
  - **收藏时间**: `.favtime`
- **컨트롤 버튼**: `.favctrl` (호버 시 표시)
  - 置顶: `.favtop`
  - 备注: `.favedit` (수정 진입)
  - 删除: `.favdel`
- **수정 컨트롤**: `.favctrl-edit` (수정 모드일 때 표시)
  - 取消: `.fav-edit-cancel`
  - 保存: `.fav-edit-save`

### 구버전 워크플로우

| Step | 설명 | old-version.js 함수 |
|------|------|---------------------|
| 1 | `.faves-panel` 진입, 항목 찾고 `.favedit` 클릭 | Step 1 |
| 2 | `input.fav-edit-input` 존재 확인 | Step 2 |
| 3 | 메모 입력 (네이티브 setter 사용) | Step 3 |
| 4 | `.fav-edit-save` 클릭, `.favtitle` 내용으로 검증 | Step 4 |

---

## SSR DOM 구조 (아래는 SSR 전용 정보)

- **URL**: `https://www.amap.com/ssr/favorite`
- **즐겨찾기 항목**: `div` 요소 (항목을 감싸는 컨테이너)
  - **제목**: 항목 div 내부의 제목 div (`.FavoriteItem_listItemTitle__kM3ot` 또는 유사)
  - **설명**: 항목 div 내부의 설명 div (`.FavoriteItem_listItemDesc__rlTtO` 또는 유사)
  - **3점 메뉴 아이콘**: 항목 div 내부의 SVG (`viewBox="0 0 16 16"` + 3개의 동그라미 path)
- **메뉴 팝업**: 3점 클릭 시 Ant Design Popover
  - 메뉴 항목들: `div` with "置顶" / "备注" / "删除" 텍스트
- **수정 모드**: "备注" 클릭 시
  - 항목에 editing 클래스 추가 (`FavoriteItem_listItemEditing__Zz9Yh` 또는 유사)
  - **입력 필드**: `input[placeholder="请输入备注"]`
  - **저장 버튼**: `button` with "保存" 텍스트
  - **취소 버튼**: `button` with "取消" 텍스트

## 워크플로우 (반드시 이 순서로 한 항목씩 처리)

### Step 0: 페이지 진입 (아직 접속하지 않은 경우)

```
playwright_browser_navigate: https://www.amap.com/ssr/favorite
```

### Step 1: 항목 찾기 및 3점 메뉴 클릭

```javascript
async (page) => {
  const zh = '중국명';
  const triggered = await page.evaluate((name) => {
    const items = Array.from(document.querySelectorAll('[class*="FavoriteItem_listItem"]'));
    const targetItem = items.find(el => {
      const titleEl = el.querySelector('[class*="FavoriteItem_listItemTitle"]');
      return titleEl && titleEl.textContent.includes(name);
    });
    if (!targetItem) return false;

    const menuWrapper = targetItem.querySelector('[class*="FavoriteItemMenu_moreIconWrapper"]');
    const svgIcon = menuWrapper?.querySelector('svg[viewBox="0 0 16 16"]');
    if (svgIcon) {
      svgIcon.click();
      return true;
    }

    const allSvgs = targetItem.querySelectorAll('svg');
    const threeDotSvg = Array.from(allSvgs).find(svg => {
      const paths = svg.querySelectorAll('path');
      return paths.length === 3;
    });
    if (threeDotSvg) {
      threeDotSvg.click();
      return true;
    }

    return false;
  }, zh);
  await page.waitForTimeout(1000);
  return { status: triggered ? 'menu_opened' : 'not_found' };
}
```

### Step 2: "备注" 메뉴 항목 클릭하여 수정 모드 진입

```javascript
async (page) => {
  const zh = '중국명';
  const triggered = await page.evaluate((name) => {
    const memoItems = Array.from(document.querySelectorAll('[class*="FavoriteItemMenu_menuItem"]'));
    const memoBtn = memoItems.find(el => el.textContent.trim() === '备注');
    if (!memoBtn) return false;
    memoBtn.click();
    return true;
  }, zh);
  await page.waitForTimeout(1000);

  const editing = await page.evaluate(() => {
    const editingItem = document.querySelector('[class*="FavoriteItem_listItemEditing"]');
    const input = document.querySelector('input[placeholder="请输入备注"]');
    return !!(editingItem && input);
  });

  return { status: editing ? 'edit_mode' : 'failed', detail: editing ? '수정 모드 진입 성공' : '수정 모드 진입 실패' };
}
```

### Step 3: 메모 입력 (React/Ant Design 호환)

```javascript
async (page) => {
  const zh = '중국명';
  const ko = '한글명';
  const memo = `${zh} (${ko}) 5/14`;

  const filled = await page.evaluate((m) => {
    const inp = document.querySelector('input[placeholder="请输入备注"]');
    if (!inp) return false;

    // React controlled input: 네이티브 디스크립터로 값 설정
    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
    if (nativeSetter) {
      nativeSetter.call(inp, m);
    } else {
      inp.value = m;
    }

    // 완전한 이벤트 시퀀스
    inp.dispatchEvent(new Event('focus', { bubbles: true }));
    inp.dispatchEvent(new Event('select', { bubbles: true }));
    inp.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, cancelable: true, inputType: 'insertText' }));
    inp.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true, inputType: 'insertText', data: m }));
    inp.dispatchEvent(new Event('change', { bubbles: true }));

    return inp.value === m;
  }, memo);

  return { status: filled ? 'input_filled' : 'failed' };
}
```

### Step 4: 저장 및 결과 검증

```javascript
async (page) => {
  const zh = '중국명';
  const ko = '한글명';
  const memo = `${zh} (${ko}) 5/14`;

  const saveClicked = await page.evaluate(() => {
    const editing = document.querySelector('[class*="FavoriteItem_listItemEditing"]');
    if (!editing) return 'not_editing';
    const btn = editing.querySelector('[class*="FavoriteItem_saveButton"]');
    if (btn) { btn.click(); return 'clicked'; }
    return 'no_save_btn';
  });
  await page.waitForTimeout(3000);

  const isSaved = await page.evaluate((expect) => {
    const inp = document.querySelector('input[placeholder="请输入备注"]');
    if (inp) return false;

    const items = Array.from(document.querySelectorAll('[class*="FavoriteItem_listItem"]'));
    return items.some(el => {
      const titleEl = el.querySelector('[class*="FavoriteItem_listItemTitle"]');
      return titleEl && titleEl.textContent.includes(expect);
    });
  }, memo);

  return { status: isSaved ? 'saved' : 'failed', saveClicked };
}
```

## 오류 대응
- 각 Step 실패 시 → 동일 코드를 개별적으로 최대 3회 재실행 (for/while 루프 아님)
- 3회 재시도 후 실패 → `playwright_browser_navigate` 로 페이지 재진입 (`https://www.amap.com/ssr/favorite`)
- **"抱歉！未能获取到该地点信息" 표시 시 → 로딩 실패. 즉시 `page.reload()` 후 재진입**
- 여전히 실패 → 해당 항목 기록 → 다음 항목으로 자동 진행
- 페이지 재로드 시 → Step 0부터 다시 시작 (페이지 진입 필수)

## 핵심 셀렉터 (CSS Modules 해시 클래스 대신 텍스트/속성 기반)

| 용도 | 셀렉터 근거 |
|---|---|
| 즐겨찾기 항목 | `div` (제목 텍스트로 탐색) |
| 3점 메뉴 아이콘 | `svg[viewBox="0 0 16 16"]` (3개의 circle path) |
| "备注" 메뉴 항목 | `div` containing "备注" text |
| 메모 입력 필드 | `input[placeholder="请输入备注"]` |
| 저장 버튼 | `button` with "保存" text |
| 취소 버튼 | `button` with "取消" text |
