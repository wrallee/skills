// AMap ADD FAVORITE — SSR 버전 스크립트
// playwright_browser_run_code_unsafe의 code 파라미터로 실행
// 버전 감지: page.url().includes('/ssr/') → true면 SSR

// ===== Step 1: 검색 =====
// LLM에서 name(장소명), city(도시명) 주입
async (page) => {
  const nameName = '<PLACE_NAME>';
  const cityName = '<CITY_NAME>';
  const query = `${nameName}+${cityName}`;

  // 검색창 포커스
  await page.evaluate(() => {
    const ipt = document.querySelector('input.search-bar__input, input[placeholder*="搜索"]');
    if (ipt) { ipt.focus(); ipt.click(); }
  });
  await page.waitForTimeout(500);

  // 검색어 입력
  const ok = await page.evaluate((q) => {
    const ipt = document.querySelector('input.search-bar__input, input[placeholder*="搜索"]');
    if (!ipt) return false;
    ipt.value = q;
    ipt.dispatchEvent(new Event('input', { bubbles: true }));
    return ipt.value === q;
  }, query);

  // 엔터키 전송
  await page.keyboard.press('Enter');
  await page.waitForTimeout(5000);

  return { step: 1, status: ok ? 'search_ok' : 'failed' };
}

// ===== Step 2: 첫 검색결과 클릭 =====
async (page) => {
  const result = await page.evaluate(() => {
    const first = document.querySelector('.poi-card');
    if (!first) return { status: 'no_result' };

    const titleEl = first.querySelector('.poi-card-name, .poi-card-left > div:first-child');
    const name = titleEl?.textContent?.trim() || '';

    if (titleEl) {
      titleEl.click();
    } else {
      first.click();
    }
    return { status: 'clicked', name };
  });

  await page.waitForTimeout(4000);
  return { step: 2, ...result };
}

// ===== Step 3: 상세페이지 주소 검증 =====
// LLM에서 scheduleCities(배열) 주입
async (page) => {
  const cities = ['도시1', '도시2']; // ← LLM이 교체

  const result = await page.evaluate((cityList) => {
    const locIcon = document.querySelector('img[alt="位置"]');
    if (!locIcon) return { status: 'no_location_img' };

    const row = locIcon.closest('div');
    const feedAddr = row?.querySelector('span')?.textContent?.trim() || '';
    const ok = feedAddr.length === 0 || cityList.some(c => feedAddr.includes(c));
    if (!ok) return { status: 'skip', reason: '도시 불일치', feedAddr };

    return { status: 'ok', feedAddr };
  }, cities);

  await page.waitForTimeout(500);
  return { step: 3, ...result };
}

// ===== Step 4: 즐겨찾기 버튼 클릭 =====
async (page) => {
  const result = await page.evaluate(() => {
    const filled = document.querySelector('img[src*="ic-star-filled"][alt="收藏"]');
    if (filled) return { status: 'already_saved' };

    const empty = document.querySelector('img[src*="ic-star-o"][alt="收藏"]');
    if (empty) {
      const btn = empty.closest('button');
      if (btn) btn.click();
      return { status: 'clicked' };
    }
    return { status: 'no_fav_btn' };
  });

  await page.waitForTimeout(2000);
  return { step: 4, ...result };
}

// ===== Step 5: 최종 검증 =====
async (page) => {
  const verified = await page.evaluate(() => {
    return !!document.querySelector('img[src*="ic-star-filled"][alt="收藏"]');
  });
  return { step: 5, status: verified ? 'saved' : 'failed' };
}

// ===== Step 6: 다음 항목 준비 =====
async (page) => {
  await page.evaluate(() => {
    const ipt = document.querySelector('input.search-bar__input, input[placeholder*="搜索"]');
    if (ipt) ipt.value = '';
  });
  await page.waitForTimeout(1000);
  return { step: 5, status: 'ready' };
}
