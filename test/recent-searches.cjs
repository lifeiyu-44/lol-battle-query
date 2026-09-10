const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1120,height:900}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('https://**/*',r=>r.abort());
  await page.goto(pathToFileURL(path.join(__dirname,'mock.html')).href);
  await page.evaluate(async()=>{
   const api=window.pywebview.api;
   window.saved=[{puuid:'old',name:'历史玩家',tagLine:'CN'}];window.identityCalls=[];window.nameCalls=0;
   api.get_search_history=async()=>({ok:true,players:structuredClone(window.saved)});
   api.remember_search=async p=>{window.saved=[p,...window.saved.filter(s=>s.puuid!==p.puuid)].slice(0,20);return {ok:true,players:structuredClone(window.saved)};};
   api.remove_search=async p=>{window.saved=p?window.saved.filter(s=>s.puuid!==p):[];return {ok:true,players:structuredClone(window.saved)};};
   api.get_status=async()=>({ok:true,connected:true,me:{puuid:'self',name:'当前账号',tagLine:'CN',level:99,friendStatus:'self'}});
   api.get_saved_player=async p=>{window.identityCalls.push(p);return {ok:true,summoner:{puuid:p,name:'改名玩家',tagLine:'NEW',level:88}};};
   api.search_player=async q=>{window.nameCalls++;return {ok:true,summoner:{puuid:'typed',name:q,tagLine:'CN'}};};
   await RecentSearches.load();await refreshStatus();
  });
  assert.equal(await page.evaluate(()=>state.player.puuid),'self');
  assert.equal(await page.evaluate(()=>state.games.length),20);
  assert.equal(await page.evaluate(()=>window.nameCalls),0);
  assert.equal(await page.evaluate(()=>window.saved.length),1); // automatic self load doesn't crowd history
  await page.locator('#recentSearches summary').click();
  await page.locator('.recent-select').first().click();
  await page.waitForFunction(()=>state.player?.puuid==='old'&&!state.loading);
  assert.deepEqual(await page.evaluate(()=>window.identityCalls),['old']);
  assert.match(await page.inputValue('#queryInput'),/改名玩家#NEW/);
  assert.match(await page.locator('.recent-select').first().textContent(),/改名玩家/);
  await page.evaluate(()=>refreshStatus());
  assert.equal(await page.evaluate(()=>state.player.puuid),'old');
  await page.click('#currentAccount');
  await page.waitForFunction(()=>state.player?.puuid==='self'&&!state.loading);
  assert.equal(await page.locator('.recent-select').count(),2);
  await page.locator('.recent-remove').first().click();
  await page.waitForFunction(()=>document.querySelectorAll('.recent-select').length===1);
  await page.click('#clearSearchHistory');
  await page.waitForFunction(()=>document.querySelectorAll('.recent-select').length===0);
  // Late login must not overwrite text already entered by the user.
  await page.evaluate(async()=>{
   state.player=null;state.autoSelfAttempted=false;$('queryInput').value='正在输入的玩家';await refreshStatus();
  });
  assert.equal(await page.inputValue('#queryInput'),'正在输入的玩家');
  assert.equal(await page.evaluate(()=>state.player),null);
  // Failed player lookup isn't remembered.
  await page.evaluate(async()=>{window.pywebview.api.search_player=async()=>({ok:false,error:'查无此人'});await doSearch();});
  assert.equal(await page.evaluate(()=>window.saved.length),0);
  await page.screenshot({path:path.join(process.env.USERPROFILE,'.codex/visualizations/2026/09/09/01a0855e-cced-79b1-b2ff-8c337343aba8/recent-searches.png')});
  assert.deepEqual(errors,[]);
  console.log('Account/history UI passed: default self, precise saved identity, rename refresh, no query takeover, self shortcut, removal/clear, failure exclusion.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
