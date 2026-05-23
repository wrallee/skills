// AMap ADD FAVORITE — 구버전 스크립트
// playwright_browser_run_code_unsafe의 filename 파라미터로 실행

// ===== Step 1: 검색어 입력 =====
// LLM에서 name(장소명), city(도시명) 주입
async (page) => {
  const name = '<PLACE_NAME>';
  const city = '<CITY_NAME>';
  const query = `${name}+${city}`;

  // 1) 검색창 포커스
  await page.evaluate(() => {
    const ipt = document.querySelector('#searchipt');
    if (ipt) { ipt.focus(); ipt.click(); }
  });
  await page.waitForTimeout(500);

  // 2) 검색어 입력 (이벤트 포함)
  const ok = await page.evaluate((q) => {
    const ipt = document.querySelector('#searchipt');
    if (!ipt) return false;
    ipt.value = q;
    ipt.dispatchEvent(new Event('input', { bubbles: true }));
    return ipt.value === q;
  }, query);

  // 3) 검색 버튼은 작동하지 않음. Enter키 전송만 유효.
  await page.keyboard.press('Enter');
  await page.waitForTimeout(5000);

  return { step: 1, status: ok ? 'search_ok' : 'failed' };
}

// ===== Step 2: 이름 매칭 (exact → prefix → 4개↑ 시 파일저장) =====
// LLM에서 name(장소명), city(도시명), outputDir 주입
async (page) => {
  const name = '<PLACE_NAME>';
  const city = '<CITY_NAME>';
  const outputDir = '<OUTPUT_DIR>';

  const result = await page.evaluate(({ searchName, city, outputDir }) => {
    const items = document.querySelectorAll('li.poibox');
    if (!items.length) return { status: 'no_result' };

    const results = [];
    items.forEach((item, idx) => {
      const poiName = item.getAttribute('data-poiinfo-name') || '';
      const poiX = item.getAttribute('data-poiinfo-x') || '';
      const poiY = item.getAttribute('data-poiinfo-y') || '';
      const displayName =
        item.querySelector('.poi-name')?.textContent?.replace(/^\d+\.\s*/, '').trim() || '';
      const addr = item.querySelector('.poi-addr')?.textContent?.trim() || '';

      results.push({
        idx,
        poiName,
        displayName,
        address: addr,
        lng: poiX,
        lat: poiY,
        exactMatch: poiName === searchName,
        prefixMatch: !exactMatch && poiName.startsWith(searchName),
      });
    });

    const exactMatches = results.filter(r => r.exactMatch);
    const prefixMatches = results.filter(r => r.prefixMatch);

    // 1. 정확히 일치하는 항목이 있으면 선택
    if (exactMatches.length >= 1) {
      items[exactMatches[0].idx].click();
      return {
        status: 'clicked_exact',
        index: exactMatches[0].idx,
        name: exactMatches[0].poiName,
        totalExact: exactMatches.length,
        prefixMatchList: prefixMatches.map(r => ({ idx: r.idx, name: r.poiName, addr: r.address })),
      };
    }

    // 2. Prefix match가 4개 이상이면 파일로 저장하고 직접 지정하도록 알림
    if (prefixMatches.length >= 4) {
      const prefixList = prefixMatches.map(r => ({
        idx: r.idx,
        name: r.poiName,
        address: r.address,
      }));
      // Note: Cannot write file from browser context. Save data to window for LLM to extract.
      window.__AMAP_TOO_MANY_RESULTS = {
        query: searchName,
        city: city,
        prefixMatches: prefixList,
      };
      return {
        status: 'too_many_prefix',
        count: prefixMatches.length,
        list: prefixList,
        message: '검색결과가 많아 직접 선택하세요. window.__AMAP_TOO_MANY_RESULTS에 데이터 저장됨.',
      };
    }

    // 3. Prefix match 1~3개면 첫번째 선택
    if (prefixMatches.length > 0) {
      items[prefixMatches[0].idx].click();
      return {
        status: 'clicked_prefix',
        index: prefixMatches[0].idx,
        name: prefixMatches[0].poiName,
        addr: prefixMatches[0].address,
      };
    }

    // 4. 매칭 없음 - 첫번째 fallback
    items[0].click();
    return { status: 'clicked_first_fallback', index: 0 };
  }, { searchName: name, city, outputDir });

  // If too_many_prefix, save to file from Node side
  if (result.status === 'too_many_prefix') {
    const fs = require('fs');
    const path = require('path');
    const fileName = `amap-search-results-${name}.json`;
    const filePath = path.join(outputDir || '/tmp', fileName);
    fs.writeFileSync(filePath, JSON.stringify(result, null, 2), 'utf-8');
    result.fileSaved = filePath;
  }

  await page.waitForTimeout(3000);
  return { step: 2, ...result };
}

// ===== Step 3: 상세패널 주소 검증 =====
// LLM에서 scheduleCities(배열) 주입
async (page) => {
  const cities = ['도시1', '도시2']; // ← LLM이 교체

  const result = await page.evaluate((cityList) => {
    const panel = document.querySelector('.place-panel');
    if (!panel) return { status: 'no_panel' };

    const feedAddr = panel.querySelector('.feedaddr')?.textContent?.trim() || '';
    const ok = cityList.some(c => feedAddr.includes(c));
    if (!ok && feedAddr.length > 0) return { status: 'skip', reason: '도시 불일치', feedAddr };

    return { status: 'ok', feedAddr };
  }, cities);

  await page.waitForTimeout(500);
  return { step: 3, ...result };
}

// ===== Step 4: 즐겨찾기 버튼 클릭 =====
async (page) => {
  const result = await page.evaluate(() => {
    const panel = document.querySelector('.place-panel');
    if (!panel) return { status: 'no_panel' };

    const favBtn = panel.querySelector('.collect.favit');
    if (!favBtn) return { status: 'no_fav_btn' };
    if (favBtn.classList.contains('faved')) return { status: 'already_saved' };

    favBtn.click();
    return { status: 'clicked' };
  });

  await page.waitForTimeout(2000);
  return { step: 4, ...result };
}

// ===== Step 5: 최종 검증 =====
async (page) => {
  const verified = await page.evaluate(() => {
    const fav = document.querySelector('.collect.favit');
    return !!(fav && fav.classList.contains('faved'));
  });
  return { step: 5, status: verified ? 'saved' : 'failed' };
}

// ===== Step 6: 다음 항목 준비 =====
async (page) => {
  await page.evaluate(() => {
    const back = document.querySelector('#placereturnfixed i.icon-angleleft');
    if (back) back.click();
    const ipt = document.querySelector('#searchipt');
    if (ipt) ipt.value = '';
  });
  await page.waitForTimeout(1000);
  return { step: 5, status: 'ready' };
}
