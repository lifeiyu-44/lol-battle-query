const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const {pathToFileURL} = require('node:url');
const path = require('node:path');
(async () => {
  const browser = await chromium.launch({channel:'msedge',headless:true});
  try {
    const page = await browser.newPage({viewport:{width:920,height:800}});
    const errors = []; page.on('pageerror',e=>errors.push(e.message));
    await page.route('https://**/*', route=>route.abort());
    await page.goto(pathToFileURL(path.join(__dirname,'mock.html')).href);
    await page.evaluate(async () => {
      const api = window.pywebview.api;
      const games = (await api.get_matches('test',0)).games;
      window.notices = []; window.summaries = []; window.noticeClosed = 0;
      window.current = {ok:true,active:true,key:'game-1',mode:'海克斯大乱斗',note:'近20场',teams:[100,200].map((teamId,t)=>({
        teamId,label:t?'对手':'我方',players:Array.from({length:5},(_,i)=>({
          puuid:t===1&&i===4?'':`${t}-${i}`,summonerId:i+1,name:`玩家${t}-${i}`,tagLine:'CN1',
          level:100,championId:266,championName:'暗裔剑魔',friendStatus:i===0?'friend':'not_friend'
        }))}))};
      api.get_current_game_status = async () => structuredClone(window.current);
      api.get_current_game = async () => structuredClone(window.current);
      api.get_recent_summary = async puuid => {
        window.summaries.push(puuid);
        return puuid==='1-3'?{ok:false,error:'战绩暂不可用'}:{ok:true,games};
      };
      api.notify_current_game = async key => {window.notices.push(key);return {ok:true};};
      api.close_game_notice = async () => {window.noticeClosed++;};
      await CurrentGame.poll();
    });
    await page.waitForFunction(()=>!document.querySelector('#refreshCurrent').disabled);
    assert.equal(await page.locator('.current-player').count(),10);
    assert.equal(await page.locator('.current-stats').filter({hasText:'胜率'}).count(),8);
    assert.equal(await page.locator('.current-stats').filter({hasText:'身份未公开'}).count(),1);
    assert.equal(await page.locator('.current-stats').filter({hasText:'暂不可用'}).count(),1);
    assert.equal(await page.evaluate(()=>window.summaries.length),9);
    await page.evaluate(async()=>{await window.pywebview.api.close_game_notice();await CurrentGame.poll();});
    assert.deepEqual(await page.evaluate(()=>window.notices),['game-1']);
    await page.locator('.current-actions button').filter({hasText:'查看战绩'}).first().click();
    await page.waitForFunction(()=>state.player?.puuid==='0-0'&&!state.loading);
    assert.equal(await page.locator('.match-card').count(),20);
    // Native popup opens the persistent panel; no new match notification on refresh.
    await page.evaluate(()=>CurrentGame.open());
    assert.equal(await page.locator('#currentGame').evaluate(e=>e.open),true);
    await page.evaluate(async()=>{window.current.key='game-2';await CurrentGame.poll();});
    await page.waitForFunction(()=>!document.querySelector('#refreshCurrent').disabled);
    assert.deepEqual(await page.evaluate(()=>window.notices),['game-1','game-2']);
    await page.screenshot({path:path.join(process.env.USERPROFILE,'.codex/visualizations/2026/09/09/01a0855e-cced-79b1-b2ff-8c337343aba8/current-game.png')});
    await page.evaluate(async()=>{window.current={ok:true,active:false};await CurrentGame.poll();});
    assert.equal(await page.locator('.current-player').count(),0);
    assert.match(await page.locator('#currentState').textContent(),/暂无/);
    assert.ok(await page.evaluate(()=>window.noticeClosed>=2));
    // Selection data can arrive with no opponents, then expand during the same game.
    await page.evaluate(async()=>{
      window.current={ok:true,active:true,key:'select-1',phase:'ChampSelect',mode:'海克斯大乱斗',teams:[{teamId:100,label:'我方',players:[{puuid:'select-self',name:'本人',championName:'未选择'}]}]};
      await CurrentGame.poll();
    });
    await page.waitForFunction(()=>!document.querySelector('#refreshCurrent').disabled);
    assert.match(await page.locator('#currentState').textContent(),/正在选择英雄/);
    assert.equal(await page.locator('.current-player').count(),1);
    await page.evaluate(async()=>{
      window.current.phase='InProgress';
      window.current.teams[0].players[0].championName='暗裔剑魔';
      window.current.teams.push({teamId:200,label:'对手',players:[{puuid:'select-enemy',name:'对手',championName:'提莫'}]});
      await CurrentGame.poll();
    });
    await page.waitForFunction(()=>!document.querySelector('#refreshCurrent').disabled);
    assert.match(await page.locator('#currentState').textContent(),/对局进行中/);
    assert.equal(await page.locator('.current-player').count(),2);
    assert.equal(await page.evaluate(()=>window.notices.filter(k=>k==='select-1').length),1);
    assert.equal(await page.evaluate(()=>window.summaries.filter(k=>k==='select-self').length),1);
    assert.deepEqual(errors,[]);
    console.log('Current game passed: auto-detect, once-per-game notice, both teams, hidden identities, per-player failures, open history, game end.');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
