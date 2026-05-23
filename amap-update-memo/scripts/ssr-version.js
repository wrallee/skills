// AMap UPDATE MEMO — SSR 버전 스크립트
// playwright_browser_run_code_unsafe의 code 파라미터로 실행
// 버전 감지: page.url().includes('/ssr/') → true면 SSR

// ===== Step 1: 항목 찾기 및 3점 메뉴 클릭 =====
async (page) => {
  const zh = '<PLACE_NAME>';

  const triggered = await page.evaluate((name) => {
    const items = Array.from(document.querySelectorAll('[class*="FavoriteItem_listItem"]'));
    const target = items.find(el => {
      const titleEl = el.querySelector('[class*="FavoriteItem_listItemTitle"]');
      return titleEl && titleEl.textContent.includes(name);
    });
    if (!target) return false;

    const menuWrapper = target.querySelector('[class*="FavoriteItemMenu_moreIconWrapper"]');
    const svgIcon = menuWrapper?.querySelector('svg[viewBox="0 0 16 16"]');
    if (svgIcon) { svgIcon.click(); return true; }

    const allSvgs = target.querySelectorAll('svg');
    const threeDotSvg = Array.from(allSvgs).find(svg => svg.querySelectorAll('path').length === 3);
    if (threeDotSvg) { threeDotSvg.click(); return true; }

    return false;
  }, zh);

  await page.waitForTimeout(1000);
  return { step: 1, status: triggered ? 'menu_opened' : 'not_found' };
}

// ===== Step 2: 备注 클릭하여 수정 모드 진입 =====
async (page) => {
  const triggered = await page.evaluate(() => {
    const memoItems = Array.from(document.querySelectorAll('[class*="FavoriteItemMenu_menuItem"]'));
    const memoBtn = memoItems.find(el => el.textContent.trim() === '备注');
    if (!memoBtn) return false;
    memoBtn.click();
    return true;
  });
  await page.waitForTimeout(1000);

  const editing = await page.evaluate(() => {
    const editingItem = document.querySelector('[class*="FavoriteItem_listItemEditing"]');
    const input = document.querySelector('input[placeholder="请输入备注"]');
    return !!(editingItem && input);
  });

  return { step: 2, status: editing ? 'edit_mode' : 'failed' };
}

// ===== Step 3: 메모 입력 =====
async (page) => {
  const memo = '<MEMO_TEXT>';

  const filled = await page.evaluate((m) => {
    const inp = document.querySelector('input[placeholder="请输入备注"]');
    if (!inp) return false;

    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
    if (nativeSetter) { nativeSetter.call(inp, m); } else { inp.value = m; }

    inp.dispatchEvent(new Event('input', { bubbles: true }));
    inp.dispatchEvent(new Event('change', { bubbles: true }));

    return inp.value === m;
  }, memo);

  return { step: 3, status: filled ? 'filled' : 'failed' };
}

// ===== Step 4: 저장 =====
async (page) => {
  const memo = '<MEMO_TEXT>';

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

  return { step: 4, saveClicked, verified: isSaved };
}
