// AMap UPDATE MEMO — 구버전 스크립트
// playwright_browser_run_code_unsafe의 code 파라미터로 실행

// ===== Step 1: 항목 찾기 및 备注 클릭 =====
async (page) => {
  const zh = '<PLACE_NAME>';

  const result = await page.evaluate((name) => {
    const items = Array.from(document.querySelectorAll('li.favitem'));
    const target = items.find(item => {
      const title = item.querySelector('.favtitle')?.textContent?.trim() || '';
      return title.includes(name);
    });
    if (!target) return { status: 'not_found' };

    const editBtn = target.querySelector('.favedit');
    if (!editBtn) return { status: 'no_edit_btn' };
    editBtn.click();
    return { status: 'clicked' };
  }, zh);

  await page.waitForTimeout(1000);
  return { step: 1, ...result };
}

// ===== Step 2: 수정 모드 진입 확인 =====
async (page) => {
  const zh = '<PLACE_NAME>';

  const result = await page.evaluate((name) => {
    const items = Array.from(document.querySelectorAll('li.favitem'));
    const target = items.find(item => {
      const title = item.querySelector('.favtitle')?.textContent?.trim() || '';
      return title.includes(name);
    });
    if (!target) return { status: 'not_found' };

    const input = target.querySelector('input.fav-edit-input');
    if (!input) return { status: 'no_input' };

    return { status: 'edit_mode', current_value: input.value };
  }, zh);

  return { step: 2, ...result };
}

// ===== Step 3: 메모 입력 =====
async (page) => {
  const memo = '<MEMO_TEXT>';

  const filled = await page.evaluate((m) => {
    const input = document.querySelector('input.fav-edit-input');
    if (!input) return false;

    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
    if (nativeSetter) {
      nativeSetter.call(input, m);
    } else {
      input.value = m;
    }

    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));

    return input.value === m;
  }, memo);

  return { step: 3, status: filled ? 'filled' : 'failed' };
}

// ===== Step 4: 저장 =====
async (page) => {
  const memo = '<MEMO_TEXT>';

  // .fav-edit-save 는 단순 .click() 작동 안함. MouseEvent 체인 필요.
  const clicked = await page.evaluate(() => {
    const saveBtn = document.querySelector('.fav-edit-save');
    if (!saveBtn) return 'no_save_btn';
    saveBtn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
    saveBtn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
    saveBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
    return 'clicked';
  });

  await page.waitForTimeout(3000);

  const verified = await page.evaluate((memo) => {
    const items = Array.from(document.querySelectorAll('li.favitem'));
    return items.some(item => {
      const title = item.querySelector('.favtitle')?.textContent?.trim() || '';
      return title.includes(memo);
    });
  }, memo);

  return { step: 4, status: clicked, verified };
}
