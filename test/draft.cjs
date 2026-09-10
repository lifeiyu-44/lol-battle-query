const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const {pathToFileURL} = require('node:url');
const path = require('node:path');
(async () => {
  const browser = await chromium.launch({channel:'msedge',headless:true});
  try {
    const page = await browser.newPage({viewport:{width:920,height:800}});
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.route('https://**/*', route=>route.abort());
    await page.goto(pathToFileURL(path.join(__dirname,'mock.html')).href);
    await page.evaluate(async () => {
      const api = window.pywebview.api;
      window.requests = []; window.notices = [];
      window.current = {ok:true, active:true, key:'ranked', phase:'ChampSelect', revision:'a', draft:true, mode:'排位（单双排）', teams:[
        {teamId:100,label:'我方',bans:[{championName:'疾风剑豪',championId:157}],players:[{name:'本人',puuid:'self',championId:266,championName:'暗裔剑魔',pickState:'预选'}]},
        {teamId:200,label:'对手',bans:[],players:Array.from({length:5},()=>({name:'身份未公开',puuid:'',championId:0,championName:'英雄未公开',pickState:'待选择 / 尚未公开'}))}
      ]};
      api.get_current_game_status = async()=>structuredClone(window.current);
      api.get_current_game = async()=>structuredClone(window.current);
      api.notify_current_game = async key=>{window.notices.push(key);return {ok:true};};
      api.get_recent_summary = puuid => {
        window.requests.push(puuid);
        if(puuid==='self') return new Promise(resolve=>window.releaseSummary=()=>resolve({ok:true,games:[]}));
        return Promise.resolve({ok:true,games:[]});
      };
      await CurrentGame.poll();
    });
    await page.waitForFunction(()=>!!window.releaseSummary);
    assert.equal(await page.locator('.current-ban').count(),1);
    assert.match(await page.locator('.current-pick').first().textContent(),/预选/);
    // Draft updates even while history remains pending; reuse that request.
    await page.evaluate(async()=>{
      window.current.revision='b';
      window.current.teams[0].players[0].pickState='已锁定';
      window.current.teams[0].players[0].championName='九尾妖狐';
      window.current.teams[1].bans=[{championName:'迅捷斥候',championId:17}];
      window.current.teams[1].players[0].championId=99;
      window.current.teams[1].players[0].championName='光辉女郎';
      window.current.teams[1].players[0].pickState='已锁定';
      await CurrentGame.poll();
    });
    await page.waitForFunction(()=>document.querySelectorAll('.current-ban').length===2);
    assert.match(await page.locator('.current-pick').first().textContent(),/已锁定/);
    assert.deepEqual(await page.evaluate(()=>window.requests),['self']);
    assert.ok(await page.locator('.current-team').nth(1).getByText('光辉女郎',{exact:true}).count());
    await page.screenshot({path:path.join(process.env.USERPROFILE,'.codex/visualizations/2026/09/09/01a0855e-cced-79b1-b2ff-8c337343aba8/draft.png')});
    // Identity arrives while still loading, with unchanged player count.
    await page.evaluate(async()=>{
      window.releaseSummary(); window.current.phase='GameStart'; window.current.draft=false;
      window.current.revision='c'; window.current.teams[1].players[0].puuid='enemy';
      window.current.teams[1].players[0].name='公开玩家';
      await CurrentGame.poll();
    });
    await page.waitForFunction(()=>window.requests.includes('enemy'));
    assert.equal(await page.locator('.current-bans').count(),0);
    assert.match(await page.locator('#currentState').textContent(),/正在载入/);
    assert.deepEqual(await page.evaluate(()=>window.notices),['ranked']);
    assert.equal(await page.evaluate(()=>window.requests.filter(p=>p==='self').length),1);
    assert.deepEqual(errors,[]);
    console.log('Draft passed: public picks, bans, live revisions during pending history, identity during loading, no duplicate request/notice.');
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
