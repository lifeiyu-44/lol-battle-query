"use strict";
const HeroStats = (() => {
  const rating = typeof module !== 'undefined' ? require('./ratings.js') : MatchRating;
  function summarize(games, championId) {
    const matches = [...new Map(games.filter(g => Number(g.championId) === Number(championId)).map(g => [String(g.gameId), g])).values()];
    const valid = matches.filter(g => !g.remake && typeof g.win === 'boolean' &&
      [g.kills,g.deaths,g.assists,g.durationSec].every(v => typeof v === 'number' && Number.isFinite(v)) &&
      Math.min(g.kills,g.deaths,g.assists) >= 0 && g.durationSec > 0);
    const sum = field => valid.reduce((n,g) => n + g[field], 0);
    const wins = valid.filter(g => g.win).length;
    return {matches, count:valid.length, excluded:matches.length-valid.length, wins, losses:valid.length-wins,
      winRate:valid.length ? 100*wins/valid.length : null,
      kda:valid.length ? (sum('kills')+sum('assists'))/Math.max(sum('deaths'),1) : null,
      deaths:valid.length ? sum('deaths')/valid.length : null, rating:rating.average(valid)};
  }
  function verdict(s) {
    if (!s.count) return '没有有效对局，先不下结论。';
    if (s.count < 5) return `只有 ${s.count} 场有效样本，封神和判菜都太早。再打几场，数据才有发言权。`;
    const score = s.rating.score, win = s.winRate;
    let text;
    if (win >= 60 && score >= 80) text = '胜率和个人表现都硬，这英雄确实是你的招牌，不是头像框撑场面。';
    else if (win < 40 && score < 45) text = '胜率低，个人评分也低。这英雄目前更像给对面发福利，先把基础操作练明白。';
    else if (win < 50 && s.kda >= 4) text = 'KDA 账面挺漂亮，胜利却没到账。别只顾着保住数据，看看关键团和终结比赛做得怎么样。';
    else if (win >= 60 && score < 60) text = '赢得不少，个人评分却没跟上。战绩页很风光，招牌英雄的说服力还差点意思。';
    else if (s.deaths >= 9 && score < 60) text = '场均死亡偏高，复活倒计时比操作还稳定。先少送几次，再谈这英雄有多熟。';
    else if (win < 45) text = '这英雄的胜率暂时撑不起自信秒锁。与其继续硬选，不如回看输在哪一波。';
    else if (score >= 75) text = '个人表现拿得出手，但还没到闭眼选就能赢。把好看的操作换成稳定胜利，才算真招牌。';
    else if (win >= 60) text = '这英雄能赢，但个人评分还没到碾压级。继续稳住，别把一波顺风当成永久免检。';
    else text = '能玩，但数据还没到值得吹的程度。熟练度不是免检证，稳定发挥比偶尔高光更有用。';
    return (s.count < 10 ? '样本偏少，暂评：' : '') + text;
  }
  return {summarize, verdict};
})();
if (typeof module !== 'undefined') module.exports = HeroStats;

const HeroAnalysis = (() => {
  let dialog, player, championId, championName, games = [], cursor = 0, more = true;
  let seq = 0, busy = false, stopped = false, error = '', source = '', note = '', returnFocus;
  const snapshots = new Map(), pageCache = new Map(), inFlight = new Map(), cacheEpoch = new Map();
  const TTL = 5 * 60 * 1000;
  let cacheUsed = false, lastListKey = '', renderTimer, renderedIds = [], renderedGroup = '', championAvatar = '';
  // 后端未取到英雄资料时会返回「英雄#ID」，视为占位名，避免覆盖真实名称。
  const isPlaceholderName = n => !n || /^英雄#\d+$/.test(n) || n === '英雄资料待更新';
  const leanFields = ['gameId','championId','championName','avatar','queueId','mode','creation','durationSec','win','remake','kills','deaths','assists','damageEvaluation'];
  const lean = g => Object.fromEntries(leanFields.filter(k => k in g).map(k => [k,g[k]]));
  const pageKey = (id,start,count) => JSON.stringify([id,cacheEpoch.get(id)||0,start,count]);
  function prune(map, limit) { while(map.size>limit) map.delete(map.keys().next().value); }
  function saveSnapshot() {
    snapshots.delete(player.puuid);
    snapshots.set(player.puuid,{games:games.slice(),cursor,more,source,note,time:Date.now()});
    prune(snapshots,6);
  }
  function scheduleRender() {
    if (!renderTimer) renderTimer=setTimeout(()=>{renderTimer=null;if(dialog.open)render();},60);
  }
  function requestPage(id,start,count) {
    const key=pageKey(id,start,count), cached=pageCache.get(key);
    if(cached && Date.now()-cached.time<TTL) return Promise.resolve(cached.result);
    if(inFlight.has(key)) return inFlight.get(key);
    const request=Promise.resolve().then(()=>window.pywebview.api.get_analysis_matches(id,start,count)).then(result=>{
      if(result.ok && Array.isArray(result.games)) {pageCache.set(key,{time:Date.now(),result});prune(pageCache,150);}
      return result;
    }).finally(()=>inFlight.delete(key));
    inFlight.set(key,request);return request;
  }
  function init() {
    if (dialog) return;
    dialog = document.createElement('dialog'); dialog.className = 'hero-dialog'; dialog.id = 'heroDialog';
    dialog.setAttribute('aria-labelledby','heroTitle');
    dialog.innerHTML = `<div class="hero-head"><img id="heroPortrait" class="hero-portrait" alt="英雄头像"><div class="hero-heading"><small>CHAMPION REPORT / 英雄专项</small><h2 id="heroTitle"></h2></div><button id="heroClose" class="ghost">关闭</button></div>
      <p class="hero-scope">自动扫描该玩家最近最多 500 场可获取战绩，只统计指定英雄；不受主列表条数与日期筛选影响，不代表账号全部历史。</p>
      <div class="hero-controls"><label>对局类型 <select id="heroMode"><option value="all">全部对局</option><option value="mayhem">海克斯大乱斗</option><option value="aram">极地大乱斗</option><option value="ranked-solo">排位（单双排）</option><option value="ranked-flex">排位（灵活组排）</option><option value="normal">匹配模式</option><option value="arena">斗魂竞技场</option><option value="urf">无限火力</option><option value="other">其他模式</option></select></label><button id="heroStop" class="ghost">停止加载</button><button id="heroResume" class="ghost" hidden>继续加载 / 重试</button><button id="heroRefresh" class="ghost">刷新最新战绩</button></div>
      <div id="heroLoading" class="loading-all hero-loading" hidden>
        <span class="spinner" aria-hidden="true"></span>
        <div class="load-body"><b id="heroLoadingText">正在扫描战绩…</b>
          <div class="load-track"><i id="heroLoadingFill"></i></div></div>
      </div>
      <p id="heroProgress" role="status"></p><div id="heroSummary" class="hero-summary"></div><div id="heroVerdict" class="hero-verdict"></div>
      <p class="hero-scope">评分以队伍伤害占比为第一要素（最高 40 分，占比达 30% 满分），叠加 KDA、每分钟击杀＋助攻与胜负，取有效对局均分；重开与资料不足不计入胜率、KDA 和评分。锐评只针对本次样本中的游戏表现。</p><div id="heroGames" class="hero-games"></div>`;
    document.body.appendChild(dialog);
    // 头像链接失效时回退到本地内置图标，避免标题区只剩空白。
    $('heroPortrait').addEventListener('error', () => {
      const fallback = `champion-icons/${championId}.png`;
      if ($('heroPortrait').getAttribute('src') !== fallback) $('heroPortrait').src = fallback;
    });
    $('heroClose').addEventListener('click', () => dialog.close());
    // 点遮罩也能关闭，不必非要点「关闭」。
    dialog.addEventListener('click', (event) => {
      if (event.target !== dialog) return;
      const rect = dialog.getBoundingClientRect();
      const outside = event.clientX < rect.left || event.clientX > rect.right ||
        event.clientY < rect.top || event.clientY > rect.bottom;
      if (outside) dialog.close();
    });
    dialog.addEventListener('close', () => {
      seq++; busy=false; clearTimeout(renderTimer);renderTimer=null; returnFocus?.focus();
      if (window.showPage) showPage('query');
    });
    $('heroMode').addEventListener('change', render);
    $('heroStop').addEventListener('click', () => { stopped=true; render(); });
    $('heroResume').addEventListener('click', () => { stopped=false; load(); });
    $('heroRefresh').addEventListener('click', () => open(player,championId,championName,true,championAvatar));
    // 点任意一场进入该场对局详情（事件委托，列表增量渲染也不用重新绑定）。
    $('heroGames').addEventListener('click', (event) => {
      const row = event.target.closest('.hero-game');
      if (row && row.dataset.gameId) openGameDetail(row.dataset.gameId);
    });
  }
  // 详情是页面级弹层，会盖住模态 dialog：先收起英雄页，再打开详情。
  // 关闭详情后由主页面统一回到默认首页（app.js 的 closeDetail）。
  function openGameDetail(gameId) {
    if (dialog.open) dialog.close();
    openDetail(gameId, player?.puuid || '');
  }
  function render() {
    const mode = $('heroMode').value;
    const s = HeroStats.summarize(games.filter(g => mode==='all' || queueGroup(g)===mode), championId);
    const metadata=games.find(g=>Number(g.championId)===championId && g.championName);
    if(metadata) {
      // 只有当前名字是占位名时才用战绩里的名字，避免用「英雄#ID」覆盖真实名称。
      if(isPlaceholderName(championName) && !isPlaceholderName(metadata.championName)) championName=metadata.championName;
      championAvatar=metadata.avatar||championAvatar;
    }
    $('heroTitle').textContent=`${player.name||'玩家'}${player.tagLine?'#'+player.tagLine:''} · ${championName}`;
    if(!championAvatar) championAvatar=`champion-icons/${championId}.png`;
    if($('heroPortrait').getAttribute('src')!==championAvatar) $('heroPortrait').src=championAvatar;
    $('heroPortrait').alt=championName;
    const label = busy ? (stopped ? '正在停止，保留已取得数据' : '扫描中，当前为暂评') : error ? '扫描中断，统计未完成' : stopped ? '已停止，仅统计已取得数据' : cursor>=500 ? '已达到 500 场扫描上限' : '已扫描至接口可获取的末尾';
    $('heroProgress').textContent = `已扫描 ${games.length} 场 · 筛出本英雄 ${s.matches.length} 场 · ${label}${cacheUsed?' · 已复用近期数据（缓存有效期 5 分钟，可刷新最新）':''}${source==='lcu' ? ' · 当前为客户端缓存' : ''}${note ? ' · '+note : ''}${error ? ' · '+error : ''}`;
    dialog.classList.toggle('scanning', busy);
    // 扫描期间的加载条：转圈 + 进度（向 500 场上限推进）+ 流光，完成后整体隐藏。
    $('heroLoading').hidden = !busy;
    if (busy) {
      const ratio = Math.min(cursor / SCAN_LIMIT, 0.98);
      $('heroLoadingFill').style.width = Math.round(ratio * 100) + '%';
      $('heroLoadingText').textContent = stopped ? '正在停止，保留已扫描数据…'
        : `正在批量扫描战绩 ${cursor} / ${SCAN_LIMIT} 场上限…`;
    }
    $('heroStop').hidden = !busy; $('heroStop').disabled = stopped;
    $('heroResume').hidden = busy || !more || cursor>=500;
    $('heroRefresh').disabled = busy;
    $('heroSummary').innerHTML = `<div><small>有效场次</small><b>${s.count}</b><span>排除 ${s.excluded} 场</span></div><div><small>胜率</small><b>${s.winRate===null?'—':s.winRate.toFixed(1)+'%'}</b><span>${s.wins} 胜 ${s.losses} 负</span></div><div><small>综合 KDA</small><b>${s.kda===null?'—':s.kda.toFixed(2)}</b><span>累计击杀＋助攻 / 死亡</span></div><div><small>${busy||error||stopped?'当前样本评分':'总体评分'}</small>${ratingBadge(s.rating)}<span>${s.count} 场有效对局均分</span></div>`;
    $('heroVerdict').textContent = HeroStats.verdict(s);
    const group=`${championId}/${mode}/${championName}`;
    const ids=s.matches.map(g=>String(g.gameId));
    const listKey=`${group}/${ids.join(',')}`;
    if(listKey!==lastListKey) {
      lastListKey=listKey;
      const append=group===renderedGroup && renderedIds.length>0 && renderedIds.every((id,i)=>ids[i]===id);
      const rows=append?s.matches.slice(renderedIds.length):s.matches;
      const markup=rows.map(g => {
        const rowName=!isPlaceholderName(g.championName)?g.championName:championName;
        return `<div class="hero-game ${g.win?'win':'lose'}" data-game-id="${escapeHtml(g.gameId)}" title="点击查看对局详情"><div class="hero-row-champion"><img class="hero-row-avatar" src="${escapeHtml(g.avatar||championAvatar)}" alt="${escapeHtml(rowName)}" loading="lazy" onerror="this.onerror=null;this.src='champion-icons/${championId}.png'"><span class="hero-row-name">${escapeHtml(rowName)}</span></div><span class="hero-result">${g.remake?'重开':g.win?'胜利':'失败'}<small>${escapeHtml(fmtTime(g.creation))}</small></span><span>${escapeHtml(g.mode)}<small>${escapeHtml(fmtDuration(g.durationSec))}</small></span><span>${escapeHtml(g.kills)} / ${escapeHtml(g.deaths)} / ${escapeHtml(g.assists)}<small>K / D / A</small></span>${ratingBadge(MatchRating.rate(g))}</div>`;
      }).join('');
      if(append) $('heroGames').insertAdjacentHTML('beforeend',markup);
      else $('heroGames').innerHTML=markup || '<p class="current-empty">扫描范围内暂未找到该英雄符合条件的战绩。</p>';
      renderedIds=ids;renderedGroup=group;
    }
  }
  const PAGE_SIZE = 20, CONCURRENCY = 3, SCAN_LIMIT = 500;
  async function load() {
    if (busy) return;
    busy=true; error=''; const generation=seq;
    render();
    try {
      if(more && cursor<500) await new Promise(resolve=>setTimeout(resolve,0));
      while (generation===seq && more && cursor<SCAN_LIMIT && !stopped) {
        // 同批并发拉取多页，按序处理；游标推进与单页串行时完全一致。
        const batch=[];
        for (let i=0; i<CONCURRENCY && cursor+i*PAGE_SIZE<SCAN_LIMIT; i++) {
          const start=cursor+i*PAGE_SIZE, count=Math.min(PAGE_SIZE,SCAN_LIMIT-start);
          batch.push({start,count,promise:requestPage(player.puuid,start,count)
            .catch(e=>({ok:false,error:e&&e.message||'读取失败'}))});
        }
        for (let i=0;i<batch.length;i++) {
          const result=await batch[i].promise;
          if (generation!==seq) return;
          if (!result.ok || !Array.isArray(result.games)) { error=result.error||'战绩数据不可用'; break; }
          const rows=result.games.slice(0,batch[i].count), seen=new Set(games.map(g=>String(g.gameId)));
          const fresh=rows.filter(g=>{const id=String(g.gameId);if(seen.has(id))return false;seen.add(id);return true;});
          if(rows.length && !fresh.length) { pageCache.delete(pageKey(player.puuid,batch[i].start,batch[i].count));error='接口返回重复页，已暂停，请重试'; break; }
          pageCache.set(pageKey(player.puuid,batch[i].start,batch[i].count),{time:Date.now(),result});prune(pageCache,150);
          games.push(...fresh); cursor=batch[i].start+rows.length;
          source=result.source||''; note=result.note||'';
          if (!result.hasMore || rows.length<batch[i].count) { more=false; break; }
          saveSnapshot();scheduleRender();
        }
        if (error) throw new Error(error);
        saveSnapshot();scheduleRender();
      }
    } catch(e) { if(generation===seq) error=e.message||'读取失败'; }
    finally { if(generation===seq) {busy=false;clearTimeout(renderTimer);renderTimer=null;render();} }
  }
  function open(target, cid, name, force=false, avatar='') {
    if (!target?.puuid) {toast('该玩家身份未公开，无法查询英雄战绩');return;}
    if (!Number.isInteger(Number(cid)) || Number(cid)<=0) {toast('英雄尚未确定，暂时无法分析');return;}
    init(); seq++; busy=false; stopped=false; error=''; source=''; note=''; games=[];cursor=0;more=true;
    clearTimeout(renderTimer);renderTimer=null;lastListKey='';cacheUsed=false;renderedIds=[];renderedGroup='';
    const info=state.analysisCatalog.find(c=>Number(c.id)===Number(cid));
    player={...target}; championId=Number(cid);
    // 名字与头像优先用点击入口已有的资料，其次查英雄表，最后退回本地图标，
    // 这样即使英雄表尚未加载完也不会只剩一个 ID。
    championName=!isPlaceholderName(name) ? name : (info?.name || name || `英雄 #${championId}`);
    championAvatar=avatar||info?.avatar||`champion-icons/${championId}.png`;
    if(!dialog.open) returnFocus=document.activeElement;
    const seed=!force && state.player?.puuid===target.puuid && state.historySource==='sgp' && Date.now()-state.historyFetchedAt<TTL && state.games.length ? state.games : null;
    let cached=snapshots.get(target.puuid);
    if(force || (seed && cached?.games.length && seed[0].gameId!==cached.games[0].gameId) || (cached && Date.now()-cached.time>=TTL)) {
      snapshots.delete(target.puuid);cacheEpoch.set(target.puuid,(cacheEpoch.get(target.puuid)||0)+1);cached=null;
    }
    if(cached) {({cursor,more,source,note}=cached);games=cached.games.slice();cacheUsed=true;}
    if(seed && seed.length>games.length) {
      games=seed.slice(0,500).map(lean);cursor=state.nextBeg;more=state.hasMore;source=state.historySource;note=state.historyNote;cacheUsed=true;
      saveSnapshot();
    }
    $('heroTitle').textContent=`${target.name||'玩家'}${target.tagLine?'#'+target.tagLine:''} · ${championName}`;
    $('heroMode').value='all';
    if(!dialog.open) dialog.showModal();
    load();
  }
  function bind(el, target, cid, name, avatar='') {
    el.classList.add('hero-trigger'); el.tabIndex=0; el.setAttribute('role','button');
    el.title=`分析${target?.name||'该玩家'}的${name||'该英雄'}战绩`;
    el.setAttribute('aria-label',el.title);
    el.addEventListener('click',e=>{e.stopPropagation();open(target,cid,name,false,avatar);});
    el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();e.stopPropagation();open(target,cid,name,false,avatar);}});
  }
  return {open,bind};
})();
