"use strict";
const CurrentGame = (() => {
  let key = '', teams = [], note = '', mode = '', epoch = 0, busy = false, timer;
  let lastRefresh = 0, checkedAt = '', detectionError = '', phase = '', rosterPhase = '', rosterRevision = '', draft = false;
  let summaryWorkers = 0, reviewBusy = false;
  const summaryCache = new Map(), pendingSummaries = new Set();
  const APP_NAME = '恁🐎战绩查询';   // 发送队友评价时带上的应用签名
  const PROJECT_URL = 'https://github.com/lifeiyu-44/lol-battle-query';
  const AUTO_PHASES = ['GameStart', 'InProgress', 'Reconnect'];
  let autoSendOn = (() => { try { return localStorage.getItem('reviewAutoSend') !== 'off'; } catch (_) { return true; } })();
  const autoSentKeys = new Set();
  let autoSendTimer = null;
  const phaseNames = {ChampSelect:'正在选择英雄', GameStart:'正在载入游戏', InProgress:'对局进行中', Reconnect:'等待重连', Lobby:'组队大厅', Matchmaking:'正在匹配', ReadyCheck:'等待接受对局', WaitingForStats:'对局结算中', PreEndOfGame:'对局结束', EndOfGame:'对局结束'};
  const notified = new Set();
  const players = () => teams.flatMap(t => t.players);
  /* 队友快评文案：首行是带应用名的标题，之后我方每个队友（不含自己与电脑）一行，末行带项目地址。 */
  function reviewLines() {
    const own = teams.find(t => t.label === '我方') ||
      teams.find(t => t.players.some(p => p.friendStatus === 'self'));
    if (!own) return null;
    const mates = own.players.filter(p => p.friendStatus !== 'self' && !p.isBot);
    if (!mates.length) return null;
    const lines = [`【队友快评 · ${APP_NAME}】`];
    mates.forEach((p, i) => {
      const name = p.name || '匿名玩家';
      const unique = p.summary ? [...new Map(p.summary.map(g => [String(g.gameId), g])).values()] : [];
      const counted = unique.filter(g => !g.remake);
      if (!counted.length) {
        lines.push(`${i + 1}. ${name}｜${p.summary ? '近期无有效战绩' : '近期战绩暂不可查'}`);
        return;
      }
      const wins = counted.filter(g => g.win).length;
      const k = counted.reduce((n,g)=>n+g.kills,0), d = counted.reduce((n,g)=>n+g.deaths,0), a = counted.reduce((n,g)=>n+g.assists,0);
      let line = `${i + 1}. ${name}·${p.championName || '?'}｜近${unique.length}场 胜率${(100 * wins / counted.length).toFixed(1)}%｜KDA ${((k + a) / Math.max(1, d)).toFixed(2)}`;
      const average = MatchRating.average(counted);
      if (average.score !== null) line += `｜评分 ${average.score.toFixed(1)}（${average.label}）`;
      lines.push(line);
    });
    lines.push(`工具开源地址：${PROJECT_URL}`);
    return lines;
  }
  /* 我方队友的评价素材是否都已就绪（摘要加载完成或明确失败）。 */
  function ownMates() {
    const own = teams.find(t => t.label === '我方') ||
      teams.find(t => t.players.some(p => p.friendStatus === 'self'));
    return own ? own.players.filter(p => p.friendStatus !== 'self' && !p.isBot) : null;
  }
  async function sendReview(auto = false) {
    if (reviewBusy) return;
    const lines = reviewLines();
    if (!lines) {
      if (!auto) toast('当前没有可评价的队友（需我方队友身份已公开）');
      return;
    }
    reviewBusy = true; render();
    try {
      const res = await window.pywebview.api.send_team_review(lines);
      if (res.ok) {
        toast(`${auto ? '已自动' : '已'}把 ${res.sent} 条队友评价发进${res.phase === 'ChampSelect' ? '选人' : '对局'}聊天，署名 ${APP_NAME}`);
        // 对局中看不到应用内提示，自动发送的结果用托盘气泡再报一次。
        if (auto) window.pywebview.api.notify_tray('队友评价已发送',
          `已发送 ${res.sent} 条到${res.phase === 'ChampSelect' ? '选人' : '对局'}聊天（${APP_NAME}）`).catch(() => {});
      } else {
        toast(res.error || '发送队友评价失败');
        if (auto) window.pywebview.api.notify_tray('队友评价未发送', res.error || '发送失败').catch(() => {});
      }
    } catch (error) {
      toast('发送队友评价失败：' + (error && error.message || error));
    } finally { reviewBusy = false; render(); }
  }
  /* 进入游戏后自动发送：等战绩摘要就绪（最多约 15 秒），每局只发一次。 */
  function scheduleAutoSend(gameKey, gamePhase) {
    if (!autoSendOn || autoSentKeys.has(gameKey) || !AUTO_PHASES.includes(gamePhase)) return;
    autoSentKeys.add(gameKey);
    let tries = 0;
    const attempt = () => {
      autoSendTimer = null;
      if (!autoSendOn || gameKey !== key) return;   // 对局切换、结束或功能被关闭则放弃
      const mates = ownMates();
      if (mates && (mates.every(p => p.summary || p.error) || tries >= 10)) { sendReview(true); return; }
      if (++tries <= 10) { autoSendTimer = setTimeout(attempt, 1500); return; }
      window.pywebview.api.notify_tray('队友评价未发送', '未能获取本局名单，本局自动发送已跳过').catch(() => {});
    };
    autoSendTimer = setTimeout(attempt, 1500);
  }
  function setAutoSend(on) {
    autoSendOn = on;
    try { localStorage.setItem('reviewAutoSend', on ? 'on' : 'off'); } catch (_) {}
    if (!on && autoSendTimer) { clearTimeout(autoSendTimer); autoSendTimer = null; }
    render();
  }
  function render() {
    $('currentState').textContent = detectionError ? '检测暂不可用' : key ? `${phaseNames[phase] || '当前对局'} · ${mode} · ${players().length} 位玩家` : phaseNames[phase] || '暂无进行中的对局';
    $('currentNote').textContent = detectionError || (key ? `${note} ${checkedAt ? '名单更新于 ' + checkedAt : ''}` : '自动检测新对局，发现后弹窗提醒；关闭弹窗不影响在此查看。');
    $('refreshCurrent').disabled = busy;
    const review = $('sendReviewBtn');
    if (review) {
      review.disabled = reviewBusy || !key ||
        !teams.some(t => t.players.some(p => p.friendStatus !== 'self' && !p.isBot));
      review.textContent = reviewBusy ? '发送中…' : '一键发送队友评价';
    }
    const auto = $('autoSendBtn');
    if (auto) {
      auto.textContent = `进入游戏自动发送：${autoSendOn ? '开' : '关'}`;
      auto.title = autoSendOn ? '进入游戏后自动把队友评价发进队伍聊天（点击关闭）'
                              : '自动发送已关闭（点击开启）';
    }
    const body = $('currentTeams');
    body.innerHTML = '';
    for (const team of teams) {
      const section = document.createElement('section');
      section.className = 'current-team';
      const title = document.createElement('h3');
      title.textContent = `${team.label} · ${team.players.length} 人`;
      section.appendChild(title);
      if (draft) {
        const bans = document.createElement('div'); bans.className = 'current-bans';
        const label = document.createElement('span'); label.textContent = '已禁用'; bans.appendChild(label);
        for (const ban of team.bans || []) {
          const chip = document.createElement('span'); chip.className = 'current-ban';
          chip.appendChild(avatarEl(ban.avatar, ban.championName, 'ban-avatar'));
          chip.appendChild(document.createTextNode(ban.championName)); bans.appendChild(chip);
        }
        if (!team.bans?.length) bans.appendChild(document.createTextNode('暂无已确认禁选'));
        section.appendChild(bans);
      }
      if (!team.players.length) {
        const empty = document.createElement('p'); empty.className = 'current-empty';
        empty.textContent = '名单尚未公开，公开后自动补齐'; section.appendChild(empty);
      }
      for (const p of team.players) {
        const card = document.createElement('div'); card.className = 'current-player';
        const avatar = avatarEl(p.avatar, p.championName, 'current-avatar');
        HeroAnalysis.bind(avatar, p, p.championId, p.championName, p.avatar);
        card.appendChild(avatar);
        const info = document.createElement('div'); info.className = 'current-info';
        const fullId = p.name + (p.tagLine ? '#' + p.tagLine : '');
        info.innerHTML = `<b class="current-name">${escapeHtml(fullId)}</b> ${friendBadge(p.friendStatus)}<div>${escapeHtml(p.championName)}</div>`;
        if (draft && p.pickState) {
          const pick = document.createElement('span'); pick.className = 'current-pick';
          pick.textContent = p.pickState; info.appendChild(pick);
        }
        const stats = document.createElement('div'); stats.className = 'current-stats';
        if (p.summary) {
          const unique = [...new Map(p.summary.map(g => [String(g.gameId), g])).values()];
          const counted = unique.filter(g => !g.remake);
          const wins = counted.filter(g => g.win).length;
          const k = counted.reduce((n,g)=>n+g.kills,0), d = counted.reduce((n,g)=>n+g.deaths,0), a = counted.reduce((n,g)=>n+g.assists,0);
          const ratings = counted.map(g => MatchRating.rate(g).score).filter(n => n !== null);
          stats.textContent = counted.length ? `近 ${unique.length} 场 · ${wins} 胜 ${counted.length-wins} 负 · 胜率 ${(100*wins/counted.length).toFixed(1)}% · KDA ${((k+a)/Math.max(1,d)).toFixed(2)}` : `近 ${unique.length} 场 · 暂无有效战绩`;
          if (ratings.length) {
            const average = MatchRating.average(counted);
            const grade = document.createElement('span');
            grade.className = 'current-grade';
            grade.innerHTML = ratingBadge(average) + ` <span>综合评分</span>`;
            stats.appendChild(grade);
          }
        } else stats.textContent = p.error || (p.puuid ? '正在读取最近 20 场…' : p.isBot ? '电脑玩家无个人战绩' : '身份未公开，无法查询');
        info.appendChild(stats);
        const actions = document.createElement('div'); actions.className = 'current-actions';
        const copy = document.createElement('button'); copy.className = 'ghost'; copy.textContent = '复制 ID';
        copy.disabled = !p.tagLine;
        copy.addEventListener('click', () => copyPlayerId(fullId, copy));
        const view = document.createElement('button'); view.className = 'ghost'; view.textContent = '查看战绩';
        view.disabled = !p.puuid;
        view.addEventListener('click', async () => {
          if (state.loading || state.pageLoading || state.loadingAll) { toast('请等待当前查询完成，或先停止加载'); return; }
          $('queryInput').value = fullId;
          await doSearch(p);
          $('playerBar').scrollIntoView({behavior: 'smooth', block: 'start'});
        });
        actions.append(copy, view); info.appendChild(actions); card.appendChild(info); section.appendChild(card);
      }
      body.appendChild(section);
    }
    // 优选海克斯面板跟随当前对局里自己的英雄（用户手动选过就不再抢占）。
    if (window.AugmentPrefs) {
      const mine = players().find(p => p.friendStatus === 'self');
      AugmentPrefs.followChampion(mine ? mine.championId : 0);
    }
  }
  function loadSummaries() {
    // 战绩最多两个并发；选人刷新可以继续，并复用同一玩家的在途请求。
    while (summaryWorkers < 2) {
      const p = players().find(p => p.puuid && !p.isBot && !p.summary && !p.error && !pendingSummaries.has(key + '/' + p.puuid));
      if (!p) break;
      const gameKey = key, puuid = p.puuid, jobKey = gameKey + '/' + puuid;
      pendingSummaries.add(jobKey); summaryWorkers++;
      Promise.resolve().then(() => window.pywebview.api.get_recent_summary(puuid, gameKey)).catch(() => ({ok:false,error:'战绩暂不可用，点击刷新重试'})).then(result => {
        if (key !== gameKey) return;
        if (result.ok) summaryCache.set(puuid, result.games);
        for (const current of players().filter(p => p.puuid === puuid)) {
          if (result.ok) current.summary = result.games;
          else current.error = result.error || '战绩暂不可用，点击刷新重试';
        }
      }).finally(() => {
        pendingSummaries.delete(jobKey); summaryWorkers--;
        render(); loadSummaries();
      });
    }
  }
  async function refresh() {
    if (busy) return;
    busy = true;
    const generation = ++epoch;
    render();
    try {
      const res = await window.pywebview.api.get_current_game();
      if (generation !== epoch) return;
      if (!res.ok) { detectionError = res.error; return; }
      detectionError = ''; phase = res.phase || '';
      if (!res.active) {
        key = ''; teams = []; summaryCache.clear();
        window.pywebview.api.close_game_notice().catch(() => {});
        return;
      }
      const previous = new Map((key === res.key ? players() : []).filter(p => p.summary).map(p => [p.puuid, p.summary]));
      if (key !== res.key) summaryCache.clear();
      key = res.key; mode = res.mode; teams = res.teams; note = res.note || ''; rosterPhase = phase;
      rosterRevision = res.revision || ''; draft = Boolean(res.draft);
      for (const p of players()) if (summaryCache.has(p.puuid) || previous.has(p.puuid)) p.summary = summaryCache.get(p.puuid) || previous.get(p.puuid);
      detectionError = '';
      checkedAt = new Date().toLocaleTimeString(); lastRefresh = Date.now();
      render();
      loadSummaries();
      scheduleAutoSend(key, phase);
    } catch (_) { if (generation === epoch) detectionError = '读取当前对局失败，可点击刷新重试'; }
    finally { if (generation === epoch) { busy = false; render(); } }
  }
  async function poll() {
    clearTimeout(timer);
    try {
      const res = await window.pywebview.api.get_current_game_status();
      if (!res.ok) { detectionError = res.error || '检测失败，稍后自动重试'; render(); return; }
      detectionError = '';
      phase = res.phase || '';
      if (!res.active) {
        if (key) {
          epoch++; busy = false; key = ''; teams = []; summaryCache.clear();
          window.pywebview.api.close_game_notice().catch(() => {});
        }
        render(); return;
      }
      const changed = key !== res.key;
      if (changed) {
        epoch++; busy = false; key = res.key; mode = res.mode; teams = [];
        summaryCache.clear();
        $('currentGame').open = true;
      }
      if (!changed && busy && rosterPhase !== phase) { epoch++; busy = false; }
      // 自定义房间只做展示，不弹窗打扰（后端返回 notify: false）。
      if (res.notify !== false && !notified.has(key)) {
        notified.add(key);
        window.pywebview.api.notify_current_game(key, mode).then(r => {
          if (!r.ok) toast(r.error);
        }).catch(() => toast('发现当前对局，请在当前对局栏查看'));
      }
      render();
      // 大厅阶段本就没有英雄，不因此判定“名单不完整”而反复刷新。
      const incomplete = players().length < 10 ||
        players().some(p => !p.isBot && (!p.puuid || (phase !== 'Lobby' && !p.championId)));
      if (changed || rosterPhase !== phase || (res.revision && res.revision !== rosterRevision) || ((phase === 'ChampSelect' || incomplete) && Date.now()-lastRefresh > 15000)) refresh();
      scheduleAutoSend(key, phase);
    } catch (_) { detectionError = '检测暂不可用，稍后自动重试'; render(); }
    finally { timer = setTimeout(poll, 5000); }
  }
  function open() {
    $('currentGame').open = true;
    if (window.showPage) showPage('game');
  }
  function init() {
    $('refreshCurrent').addEventListener('click', refresh);
    $('sendReviewBtn').addEventListener('click', () => sendReview(false));
    $('autoSendBtn').addEventListener('click', () => setAutoSend(!autoSendOn));
    poll();
  }
  return {init, open, refresh, poll};
})();
