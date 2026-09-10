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
   $('queryInput').value='测试玩家';await doSearch();
   const api=window.pywebview.api;
   window.heroCalls=[]; window.failHero=false; window.inflight=0; window.maxInflight=0;
   window.heroCid=state.games[0].championId;
   api.get_analysis_matches=async(puuid,beg,count)=>{
    window.heroCalls.push({puuid,beg,count});
    window.maxInflight=Math.max(window.maxInflight,++window.inflight);
    await new Promise(r=>setTimeout(r,5)); window.inflight--;
    if(window.failHero&&beg===20)return {ok:false,error:'模拟中断'};
    return {ok:true,source:'sgp',hasMore:beg+count<45,games:Array.from({length:Math.max(0,Math.min(count,45-beg))},(_,j)=>({
     gameId:beg+j,championId:(beg+j)%2===0?window.heroCid:999,
     creation:Date.now(),durationSec:1200,kills:6,deaths:3,assists:6,win:(beg+j)%4===0,
     queueId:(beg+j)%4===0?2400:420,mode:(beg+j)%4===0?'海克斯大乱斗':'排位（单双排）'
    }))};
   };
   const detail=api.get_game_detail;
   api.get_game_detail=async(...args)=>{const r=await detail(...args);r.game.teams[1].players[0].puuid='enemy-exact';r.game.teams[1].players[0].championId=window.heroCid;return r;};
  });
  await page.locator('.mc-champ').first().click();
  await page.waitForFunction(()=>$('heroProgress').textContent.includes('末尾'));
  assert.equal(await page.locator('#detailMask').isVisible(),false);
  assert.equal(await page.locator('.hero-game').count(),23);
  assert.deepEqual(await page.evaluate(()=>window.heroCalls.map(c=>c.beg)),[0,20,40]);
  assert.ok(await page.evaluate(()=>window.maxInflight)>=2,'pages should be fetched concurrently');
  assert.ok(await page.evaluate(()=>window.heroCalls.every(c=>c.puuid==='abc')));
  assert.equal(await page.evaluate(()=>state.games.length),20);
  await page.selectOption('#heroMode','mayhem');
  assert.equal(await page.locator('.hero-game').count(),12);
  assert.match(await page.locator('#heroSummary').textContent(),/100.0%/);
  await page.screenshot({path:path.join(process.env.USERPROFILE,'.codex/visualizations/2026/09/09/01a0855e-cced-79b1-b2ff-8c337343aba8/hero-analysis.png')});
  await page.click('#heroClose');
  await page.evaluate(()=>openDetail(state.games[0].gameId));
  await page.locator('.dtable').nth(1).locator('.detail-champ-avatar').first().click();
  await page.waitForFunction(()=>$('heroProgress').textContent.includes('末尾'));
  assert.ok(await page.evaluate(()=>window.heroCalls.slice(-3).every(c=>c.puuid==='enemy-exact')));
  assert.match(await page.locator('#heroTitle').textContent(),/对手0/);
  await page.click('#heroClose');
  // Failure preserves cursor, resumes successfully, and never claims completion early.
  await page.evaluate(()=>{window.failHero=true;HeroAnalysis.open({puuid:'retry',name:'重试玩家'},window.heroCid,'测试英雄');});
  await page.waitForFunction(()=>$('heroProgress').textContent.includes('扫描中断'));
  assert.match(await page.locator('#heroSummary').textContent(),/当前样本评分/);
  const countBefore=await page.evaluate(()=>window.heroCalls.length);
  await page.evaluate(()=>window.failHero=false);await page.click('#heroResume');
  await page.waitForFunction(()=>$('heroProgress').textContent.includes('末尾'));
  assert.deepEqual(await page.evaluate(n=>window.heroCalls.slice(n).map(c=>c.beg),countBefore),[20,40]);
  await page.click('#heroClose');
  // Closing/switching target discards the previous player's late response.
  await page.evaluate(()=>{
   const api=window.pywebview.api;window.goodHeroApi=api.get_analysis_matches;
   api.get_analysis_matches=(puuid,...args)=>puuid==='slow'?new Promise(resolve=>window.releaseHero=()=>resolve({ok:true,games:[],hasMore:false})):window.goodHeroApi(puuid,...args);
   HeroAnalysis.open({puuid:'slow',name:'旧玩家'},window.heroCid,'旧英雄');
  });
  await page.waitForFunction(()=>Boolean(window.releaseHero));
  await page.click('#heroClose');
  await page.evaluate(()=>{HeroAnalysis.open({puuid:'new',name:'新玩家'},window.heroCid,'新英雄');window.releaseHero();});
  await page.waitForFunction(()=>$('heroProgress').textContent.includes('末尾'));
  assert.match(await page.locator('#heroTitle').textContent(),/新玩家/);
  assert.equal(await page.locator('.hero-game').count(),23);
  await page.click('#heroClose');
  await page.evaluate(()=>HeroAnalysis.open({name:'未知身份'},1,'安妮'));
  assert.equal(await page.locator('#heroDialog').isVisible(),false);
  // A never-ending upstream response must still stop at the 500-game bound.
  await page.evaluate(()=>{
   window.capCalls=[];
   window.pywebview.api.get_analysis_matches=async(p,beg,count)=>{
    window.capCalls.push(beg);
    return {ok:true,hasMore:true,games:Array.from({length:count},(_,i)=>({gameId:beg+i,championId:1,durationSec:1200,kills:1,deaths:10,assists:1,win:false}))};
   };
   HeroAnalysis.open({puuid:'cap',name:'上限测试'},1,'安妮');
  });
  await page.waitForFunction(()=>$('heroProgress').textContent.includes('已达到 500'));
  assert.equal(await page.evaluate(()=>window.capCalls.length),25);
  assert.equal(await page.locator('.hero-game').count(),500);
  // Reopening another hero of the same player uses the existing scan.
  await page.click('#heroClose');
  const reopenMs=await page.evaluate(()=>{
   const start=performance.now();HeroAnalysis.open({puuid:'cap',name:'上限测试'},999,'另一英雄');return performance.now()-start;
  });
  assert.equal(await page.evaluate(()=>window.capCalls.length),25);
  assert.equal(await page.locator('.hero-game').count(),0);
  assert.match(await page.locator('#heroProgress').textContent(),/复用近期数据/);
  await page.click('#heroRefresh');
  await page.waitForFunction(()=>window.capCalls.length===50 && document.querySelectorAll('.hero-game').length===0 && !$('heroRefresh').disabled);
  await page.click('#heroClose');
  // Show the already-loaded first page immediately and continue at its cursor.
  await page.evaluate(()=>{
   state.player={puuid:'seed',name:'已加载玩家'};state.historySource='sgp';state.historyFetchedAt=Date.now();state.nextBeg=20;state.hasMore=true;
   state.games=Array.from({length:20},(_,i)=>({gameId:i,championId:1,kills:6,deaths:3,assists:6,win:true,durationSec:1200}));
   window.seedCalls=[];window.seedResolvers={};
   window.pywebview.api.get_analysis_matches=(p,beg,count)=>{
    window.seedCalls.push(beg);
    return new Promise(resolve=>{
     window.seedResolvers[beg]=resolve;
     window.releaseSeed=()=>Object.values(window.seedResolvers).forEach(r=>r({ok:true,games:[],hasMore:false}));
    });
   };
   HeroAnalysis.open(state.player,1,'安妮');
  });
  assert.equal(await page.locator('.hero-game').count(),20);
  // 游标 20 处一批并发拉取 20/40/60 三页（与上方 [0,20,40] 的整批行为一致）。
  await page.waitForFunction(()=>window.seedCalls.length===3);
  // 扫描进行中必须显示加载特效：加载条可见、弹窗带 scanning 态、进度按 500 上限推进。
  await page.waitForFunction(()=>$('heroLoading') && !$('heroLoading').hidden &&
    $('heroDialog').classList.contains('scanning') &&
    parseInt($('heroLoadingFill').style.width,10) >= 4);
  assert.deepEqual(await page.evaluate(()=>window.seedCalls),[20,40,60]);
  await page.evaluate(()=>HeroAnalysis.open(state.player,999,'其他英雄'));
  await page.evaluate(()=>window.releaseSeed());
  await page.waitForFunction(()=>$('heroProgress').textContent.includes('末尾'));
  assert.deepEqual(await page.evaluate(()=>window.seedCalls),[20,40,60,20,40,60]);
  assert.ok(await page.evaluate(()=>$('heroLoading').hidden && !$('heroDialog').classList.contains('scanning')),
    'loading effect must be hidden after the scan finishes');
  console.log('Cached hero switch:',reopenMs.toFixed(1),'ms; zero repeated requests; immediate seeded results and shared in-flight page verified.');
  assert.deepEqual(errors,[]);
  console.log('Hero analysis UI passed: avatar routing, exact enemy identity, independent full scan, mode filter, retry cursor, late response isolation.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
