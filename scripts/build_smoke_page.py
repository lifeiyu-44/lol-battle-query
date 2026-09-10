# -*- coding: utf-8 -*-
"""构建临时冒烟页：复制 test/mock.html 并追加驱动脚本（验证用，跑完即删）。

生成两个页面：
- test/_smoke_tmp.html       战绩全量/英雄专项批量加载与加载特效
- test/_smoke_review_tmp.html 一键发送/进入游戏自动发送队友评价
"""
from pathlib import Path

root = Path(__file__).resolve().parent.parent
mock = (root / "test" / "mock.html").read_text(encoding="utf-8")


def build(driver: str, name: str):
    markup = mock[: mock.rindex("</body>")] + driver + "</body>\n</html>"
    target = root / "test" / name
    target.write_text(markup, encoding="utf-8")
    print("built", target, len(markup), "bytes")


# ---------- 页面一：批量加载与加载特效 ----------
build("""
<script>
(async () => {
  const NL = String.fromCharCode(10);
  const out = [];
  const ok = (name, cond) => out.push((cond ? 'PASS ' : 'FAIL ') + name);
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  try {
    $('queryInput').value = '冒烟玩家';
    await doSearch();
    ok('A 战绩全量批量加载完成(上限20场)', state.games.length === 20 && !state.loadingAll && !state.loading);
    ok('B 查询页加载条节点存在', !!$('loadingAll'));
    state.historySource = 'sgp'; state.historyFetchedAt = Date.now();
    const api = window.pywebview.api;
    let calls = [];
    let resolvers = [];
    api.get_analysis_matches = (puuid, beg, count) => { calls.push(beg); return new Promise(res => { resolvers.push(res); }); };
    const releaseAll = () => { const list = resolvers; resolvers = []; list.forEach(r => r({ok:true, source:'sgp', hasMore:false, games: []})); };
    HeroAnalysis.open({puuid:'abc', name:'冒烟玩家'}, 1, '安妮');
    await sleep(100);
    ok('C 英雄弹窗加载条可见', $('heroLoading') && !$('heroLoading').hidden);
    ok('D 弹窗带 scanning 态', $('heroDialog').classList.contains('scanning'));
    ok('E 加载条含转圈动画节点', !!document.querySelector('#heroLoading .spinner'));
    ok('F 进度按500上限推进(>=4%)', parseInt($('heroLoadingFill').style.width, 10) >= 4);
    ok('G 加载文案含扫描进度', $('heroLoadingText').textContent.includes('批量扫描'));
    ok('I 从主列表游标处继续批量扫描', state.games.length === 20 && calls[0] === 20 && calls.length >= 1);
    releaseAll();
    await sleep(100);
    ok('H 结束后加载条隐藏且去掉scanning', $('heroLoading').hidden && !$('heroDialog').classList.contains('scanning'));
    $('heroClose').click();
  } catch (e) { out.push('FAIL exception: ' + (e && e.message || e)); }
  const el = document.createElement('pre');
  el.id = 'smoke-result';
  el.textContent = 'SMOKE-BEGIN | ' + out.join(' | ') + ' | SMOKE-END';
  document.body.appendChild(el);
})();
</script>
""", "_smoke_tmp.html")

# ---------- 页面二：一键发送/进入游戏自动发送队友评价 ----------
build("""
<script>
(async () => {
  const out = [];
  const ok = (name, cond) => out.push((cond ? 'PASS ' : 'FAIL ') + name);
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const PROJ = 'https://github.com/lifeiyu-44/lol-battle-query';
  try {
    ok('R1 无对局时按钮禁用', $('sendReviewBtn').disabled);
    ok('R1b 自动发送默认开启', $('autoSendBtn').textContent.includes('开'));
    const api = window.pywebview.api;
    const game = (championId, championName) => ({gameId: 900000+championId, championId, championName, avatar:'',
      queueId: 420, mode: '排位（单双排）', creation: Date.now()-3600000, durationSec: 1500,
      win: championId % 2 === 1, remake: false, kills: 8, deaths: 4, assists: 8, damage: 20000});
    const roster = (key) => ({ok:true, active:true, phase:'InProgress', key, mode:'排位（单双排）',
      revision:'r-'+key, draft:false, note:'', teams:[
        {teamId:100, label:'我方', players:[
          {puuid:'me', summonerId:'1', name:'自己', tagLine:'CN1', championId:22, championName:'卢锡安', avatar:'', friendStatus:'self', isBot:false},
          {puuid:'mate1-'+key, summonerId:'2', name:'队友甲', tagLine:'CN1', championId:412, championName:'锤石', avatar:'', friendStatus:'not_friend', isBot:false},
          {puuid:'mate2-'+key, summonerId:'3', name:'队友乙', tagLine:'CN1', championId:238, championName:'亚索', avatar:'', friendStatus:'friend', isBot:false}]},
        {teamId:200, label:'对手', players:[
          {puuid:'foe1', summonerId:'4', name:'对手甲', tagLine:'CN1', championId:1, championName:'安妮', avatar:'', friendStatus:'not_friend', isBot:false}]}]});
    window.reviewCalls = [];
    api.send_team_review = async (lines) => { window.reviewCalls.push(lines); return {ok:true, sent:lines.length, phase:'InProgress'}; };
    api.get_recent_summary = async (puuid, gk) => ({ok:true, games:[game(1),game(2),game(3)]});
    let gameKey = 'g1';
    api.get_current_game_status = async () => ({ok:true, active:true, phase:'InProgress', key:gameKey, notify:false});
    api.get_current_game = async () => roster(gameKey);
    // 进入对局：应自动发送一次
    await CurrentGame.refresh();
    for (let i = 0; i < 80 && window.reviewCalls.length < 1; i++) await sleep(100);
    ok('R2 进入游戏后自动发送', window.reviewCalls.length === 1);
    const autoLines = window.reviewCalls[0] || [];
    ok('R3 标题带应用名', (autoLines[0] || '').includes('队友快评') && (autoLines[0] || '').includes('恁🐎战绩查询'));
    ok('R4 评价=标题+2队友+项目地址', autoLines.length === 4);
    ok('R5 评价含胜率KDA评分', /队友甲.*胜率.*KDA.*评分/.test(autoLines[1] || ''));
    ok('R6 末行带项目地址', (autoLines[3] || '').includes(PROJ));
    ok('R7 不含自己与对手', !autoLines.join().includes('自己') && !autoLines.join().includes('对手甲'));
    // 同一对局重复刷新不重复发送
    await CurrentGame.refresh();
    await sleep(2000);
    ok('R8 每局只自动发一次', window.reviewCalls.length === 1);
    // 关闭自动发送后，新对局不再自动发送
    $('autoSendBtn').click();
    ok('R9 开关切换为关', $('autoSendBtn').textContent.includes('关'));
    gameKey = 'g2';
    await CurrentGame.refresh();
    await sleep(3000);
    ok('R10 关闭后新对局不自动发', window.reviewCalls.length === 1);
    // 手动点击仍可发送，内容同样带项目地址
    for (let i = 0; i < 60 && $('sendReviewBtn').disabled; i++) await sleep(50);
    $('sendReviewBtn').click();
    for (let i = 0; i < 40 && window.reviewCalls.length < 2; i++) await sleep(50);
    ok('R11 手动发送仍可用', window.reviewCalls.length === 2 && (window.reviewCalls[1][3] || '').includes(PROJ));
    // 重新开启后，新对局恢复自动发送
    $('autoSendBtn').click();
    gameKey = 'g3';
    await CurrentGame.refresh();
    for (let i = 0; i < 80 && window.reviewCalls.length < 3; i++) await sleep(100);
    ok('R12 重新开启后恢复自动发送', window.reviewCalls.length === 3);
    for (let i = 0; i < 40 && !/条队友评价/.test($('toast').textContent); i++) await sleep(50);
    ok('R13 发送成功提示', /条队友评价/.test($('toast').textContent));
  } catch (e) { out.push('FAIL exception: ' + (e && e.message || e)); }
  const el = document.createElement('pre');
  el.id = 'smoke-result';
  el.textContent = 'SMOKE-BEGIN | ' + out.join(' | ') + ' | SMOKE-END';
  document.body.appendChild(el);
})();
</script>
""", "_smoke_review_tmp.html")
