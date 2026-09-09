// Run with Node and Playwright installed (or available via NODE_PATH).
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1120, height: 800 }, timezoneId: 'Asia/Shanghai' });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    // Network-independent rendering; real LCU PNGs are checked separately.
    await page.route('https://**/*', route => route.fulfill({ contentType: 'image/png',
      body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=', 'base64') }));
    await page.goto(pathToFileURL(path.join(__dirname, 'mock.html')).href);
    await page.selectOption('#queueFilter', 'mayhem');
    await page.fill('#queryInput', '测试玩家');
    await page.click('#searchBtn');
    await page.waitForFunction(() => document.querySelectorAll('.match-card').length === 5);
    await page.waitForFunction(() => !state.damageBusy && DamageAnalysis.recent(visibleGames()).every(g => g.damageEvaluation));
    assert.match(await page.locator('#damageVerdict').textContent(), /^达标/);
    assert.match(await page.locator('#damageProgress').textContent(), /5 \/ 5 场/);
    assert.equal(await page.locator('.match-card .damage-top').count(), 5);
    assert.equal(await page.locator('.match-card .aug-chip').count(), 15);
    assert.equal(await page.locator('.match-card .rating-badge').count(), 5);
    assert.match(await page.locator('#playerRating').textContent(), /基于 5 场/);
    assert.match(await page.locator('#playerBar .friend-badge').textContent(), /好友/);
    assert.match(await page.locator('#listTitle').textContent(), /筛选 5 \/ 已加载 20/);
    await page.locator('.match-card').first().click();
    await page.waitForFunction(() => document.querySelectorAll('.daug .aug-chip').length === 30);
    assert.match(await page.locator('#detailTitle').textContent(), /海克斯大乱斗/);
    assert.equal(await page.locator('.copy-id').count(), 10);
    assert.equal(await page.locator('.detail-rating .rating-badge').count(), 10);
    assert.equal(await page.locator('.dchamp .friend-friend').count(), 2);
    assert.equal(await page.locator('.dchamp .friend-unknown').count(), 2);
    await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', {configurable: true,
      value: {writeText: async value => {window.copiedId = value;}}}));
    await page.locator('.copy-id').first().click();
    assert.equal(await page.evaluate(() => window.copiedId), '队友0#CN1');
    assert.equal(await page.locator('.copy-id').first().textContent(), '已复制');
    await page.evaluate(() => {
      navigator.clipboard.writeText = async () => {throw new Error('Permission unavailable');};
      document.execCommand = command => {window.fallbackId = document.querySelector('textarea').value; return command === 'copy';};
    });
    await page.locator('.copy-id').nth(5).click();
    assert.equal(await page.evaluate(() => window.fallbackId), '对手0#CN1');
    await page.evaluate(() => state.detailGame.teams.forEach(t => t.players.reverse()));
    await page.selectOption('#detailSort', 'score');
    assert.equal(await page.evaluate(() => [...document.querySelectorAll('.dtable')].every(table => {
      const values = [...table.querySelectorAll('.detail-rating b')].map(b => Number(b.textContent));
      return values.every((v,i) => i === 0 || values[i-1] >= v);
    })), true);
    await page.click('#detailClose');
    await page.selectOption('#matchSort', 'score');
    assert.equal(await page.evaluate(() => {
      const values = [...document.querySelectorAll('.match-card .rating-badge b')].map(b => Number(b.textContent));
      return values.every((v,i) => i === 0 || values[i-1] >= v);
    }), true);
    assert.match(await page.locator('#analysisNote').textContent(), /个人相关性/);
    assert.equal(await page.locator('#analysisBody tbody tr').count(), 3);
    await page.selectOption('#analysisSource', 'public');
    await page.waitForFunction(() => document.querySelector('#analysisNote').textContent.includes('ARAMGG'));
    assert.match(await page.locator('#analysisBody').textContent(), /52.31%/);
    await page.selectOption('#analysisChampion', '266');
    await page.waitForFunction(() => document.querySelector('#analysisNote').textContent.includes('255'));
    assert.match(await page.locator('#analysisBody').textContent(), /该英雄适配梯队/);
    assert.match(await page.locator('#analysisBody').textContent(), /1000/);
    await page.selectOption('#analysisSource', 'personal');
    await page.selectOption('#analysisChampion', '0');
    await page.click('#loadAllBtn');
    await page.waitForFunction(() => document.querySelectorAll('.match-card').length === 12);
    assert.equal(await page.locator('#loadMoreBtn').isDisabled(), true);
    // Both known Mayhem queue IDs; ISO timestamps, numeric strings, seconds,
    // milliseconds, inclusive local-day boundaries and invalid timestamps.
    await page.evaluate(() => {
      const base = state.games[0];
      state.games = [
        {...base, gameId: 1, queueId: 2400, creation: '2026-09-08T16:00:00Z'},
        {...base, gameId: 2, queueId: '3270', creation: '2026-09-09T15:59:59Z'},
        {...base, gameId: 3, queueId: 2400, creation: '2026-09-09T16:00:00Z'},
        {...base, gameId: 4, queueId: 450, mode: '极地大乱斗', creation: '2026-09-09T00:00:00Z'},
        {...base, gameId: 5, queueId: 2400, creation: null},
      ];
      renderAll();
    });
    await page.fill('#dateFrom', '2026-09-09');
    await page.fill('#dateTo', '2026-09-09');
    await page.locator('#dateTo').dispatchEvent('change');
    assert.equal(await page.locator('.match-card').count(), 2);
    const exported = await page.evaluate(() => {
      let result;
      URL.createObjectURL = blob => { result = blob; return 'blob:test'; };
      HTMLAnchorElement.prototype.click = () => {};
      exportCsv();
      return result.text();
    });
    assert.equal(exported.trim().split('\n').length, 3);
    assert.match(exported, /大力\|尖端发明家\|利刃华尔兹/);
    await page.fill('#dateFrom', '2026-09-10');
    await page.locator('#dateFrom').dispatchEvent('change');
    assert.equal(await page.locator('.match-card').count(), 0);
    assert.match(await page.locator('#filterHint').textContent(), /开始日期不能晚于结束日期/);
    assert.equal(await page.locator('#exportBtn').isDisabled(), true);
    await page.click('#resetFilters');
    assert.equal(await page.locator('.match-card').count(), 5);
    const checks = await page.evaluate(async () => {
      const date = Date.parse('2026-09-09T00:00:00Z');
      const sameDate = fmtTime(date) === fmtTime(String(date)) && fmtTime(date) === fmtTime(date / 1000);
      const escaped = augmentChips([{id: 1, name: '<img src=x onerror=alert(1)>', icon: 'javascript:x'}]);
      state.hasMore = true;
      let calls = 0;
      window.pywebview.api.get_matches = async () => { calls++; return {ok: false, error: '模拟网络失败'}; };
      await loadAll();
      const stopped = calls === 1 && !state.loadingAll && !state.pageLoading;
      window.pywebview.api.get_matches = async () => ({ok: true, games: state.games, hasMore: true});
      await loadPage(20);
      return {sameDate, escaped: !escaped.includes('<img') && escaped.includes('&lt;img'), stopped,
              duplicateStopped: !state.hasMore};
    });
    assert.deepEqual(checks, {sameDate: true, escaped: true, stopped: true, duplicateStopped: true});
    assert.deepEqual(errors, []);
    console.log('UI passed: mode/date filters, dates, 10-player augments, filtered CSV, empty results, pagination failures and duplicates.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
