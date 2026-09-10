const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const {pathToFileURL} = require('node:url');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route('https://**/*', route => route.abort());
    await page.goto(pathToFileURL(path.join(__dirname, 'mock.html')).href);
    await page.evaluate(async () => {
      const template = (await window.pywebview.api.get_matches('test', 0)).games[0];
      window.calls = [];
      window.total = 650;
      window.failAt = -1;
      window.repeat = false;
      window.pywebview.api.get_matches = async (puuid, beg, count) => {
        window.calls.push({beg, count});
        if (beg === window.failAt) return {ok: false, error: '模拟失败'};
        const start = window.repeat ? 0 : beg;
        return {ok: true, hasMore: beg + count < window.total,
          games: Array.from({length: Math.min(count, Math.max(0, window.total - beg))}, (_, i) => ({
            ...template, gameId: start + i + 1, creation: Date.now() - (start+i)*3600000,
            damageEvaluation: {status: 'ok', isTop: true, rank: 1}
          }))};
      };
      document.querySelector('#queryInput').value = '测试玩家';
    });
    await page.selectOption('#historyLimit', '500');
    await page.evaluate(() => doSearch());
    assert.equal(await page.locator('.match-card').count(), 500);
    assert.equal(await page.evaluate(() => window.calls.length), 25);
    assert.match(await page.locator('#historyProgress').textContent(), /500 \/ 500.*已达到所选上限/);
    await page.selectOption('#historyLimit', '20');
    assert.equal(await page.locator('.match-card').count(), 20);
    assert.equal(await page.evaluate(() => summarize(visibleGames()).total), 20);
    assert.equal(await page.evaluate(() => window.calls.length), 25);
    await page.selectOption('#historyLimit', '50');
    await page.evaluate(async () => {window.calls = []; await doSearch();});
    assert.deepEqual(await page.evaluate(() => window.calls), [{beg:0,count:20},{beg:20,count:20},{beg:40,count:10}]);
    assert.equal(await page.locator('.match-card').count(), 50);
    await page.selectOption('#historyLimit', '100');
    await page.waitForFunction(() => !state.loadingAll);
    assert.equal(await page.locator('.match-card').count(), 100);
    assert.equal(await page.evaluate(() => new Set(state.games.map(g=>g.gameId)).size), 100);
    await page.evaluate(async () => {window.total = 45; await doSearch();});
    assert.equal(await page.locator('.match-card').count(), 45);
    assert.match(await page.locator('#historyProgress').textContent(), /45 \/ 100.*本次可获取的全部/);
    await page.evaluate(async () => {window.total = 650; window.failAt = 20; await doSearch();});
    assert.equal(await page.locator('.match-card').count(), 20);
    assert.match(await page.locator('#historyProgress').textContent(), /模拟失败.*可重试/);
    await page.evaluate(async () => {window.failAt = -1; await loadAll();});
    assert.equal(await page.locator('.match-card').count(), 100);
    await page.evaluate(async () => {window.repeat = true; await doSearch();});
    assert.equal(await page.locator('.match-card').count(), 20);
    assert.match(await page.locator('#historyProgress').textContent(), /分页未完成/);
    assert.equal(await page.evaluate(() => state.nextBeg), 20);
    // Stop while a request is outstanding, then resume from the next page.
    await page.evaluate(() => {
      window.repeat = false;
      const api = window.pywebview.api;
      const original = api.get_matches;
      api.get_matches = async (...args) => {
        if (args[1] === 20) await new Promise(resolve => {window.releasePage = resolve;});
        return original(...args);
      };
      window.searchDone = doSearch();
    });
    await page.waitForFunction(() => !!window.releasePage);
    await page.click('#stopLoadBtn');
    await page.evaluate(async () => {window.releasePage(); await window.searchDone;});
    assert.equal(await page.locator('.match-card').count(), 40);
    assert.match(await page.locator('#historyProgress').textContent(), /已停止/);
    await page.evaluate(() => loadAll());
    assert.equal(await page.locator('.match-card').count(), 100);
    assert.deepEqual(errors, []);
    console.log('Pagination passed: 500 cap, 50 partial page, changing limit, exhaustion, failure/retry, duplicates, stop/resume.');
  } finally { await browser.close(); }
})().catch(e => {console.error(e); process.exitCode = 1;});
