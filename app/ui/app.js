/* 英雄联盟国服战绩查询 - 前端逻辑 */
"use strict";

const $ = (id) => document.getElementById(id);

const state = {
  player: null,      // 当前查询的召唤师
  games: [],         // 已加载战绩
  hasMore: false,
  nextBeg: 0,
  loading: false,    // 加载中（防并发）
  loadingAll: false,
  statusTimer: null,
  pageLoading: false,
  analysisCatalog: [],
  reference: null,
  referenceLoading: false,
  referenceError: "",
  referenceSeq: 0,
  detailGame: null,
  damageBusy: false,
  damageEpoch: 0,
};

/* ---------- 工具 ---------- */

function toast(msg, sticky) {
  const t = $("toast");
  t.textContent = msg;
  t.hidden = false;
  if (!sticky) {
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => { t.hidden = true; }, 6000);
  }
}
function hideToast() { $("toast").hidden = true; }

function timestamp(ts) {
  if (ts === null || ts === undefined || ts === "") return NaN;
  const n = Number(ts);
  return Number.isFinite(n) ? (n < 1e12 ? n * 1000 : n) : Date.parse(ts);
}

function fmtTime(ts) {
  const d = new Date(timestamp(ts));
  if (Number.isNaN(d.getTime())) return "日期未知";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function queueGroup(g) {
  const q = Number(g.queueId);
  if ([2400, 3270].includes(q) || g.mode === "海克斯大乱斗") return "mayhem";
  if (q === 450) return "aram";
  if (q === 420) return "ranked-solo";
  if (q === 440) return "ranked-flex";
  if ([400, 430, 490].includes(q)) return "normal";
  if ([7, 8, 9, 1700, 1710].includes(q)) return "arena";
  if ([900, 910, 920, 1900].includes(q)) return "urf";
  return "other";
}

function visibleGames() {
  const mode = $("queueFilter").value;
  const from = $("dateFrom").value, to = $("dateTo").value;
  return state.games.filter(g => {
    if (mode !== "all" && queueGroup(g) !== mode) return false;
    const day = fmtDay(g.creation);
    if ((from || to) && !day) return false;
    return (!from || day >= from) && (!to || day <= to);
  });
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, c =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
}

function fmtDuration(sec) {
  const m = Math.floor(sec / 60), s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function kdaRatio(k, d, a) {
  return ((k + a) / Math.max(d, 1)).toFixed(2);
}

function avatarEl(url, name, cls) {
  const wrap = document.createElement("div");
  wrap.className = cls;
  if (url) {
    const img = document.createElement("img");
    img.src = url;
    img.loading = "lazy";
    img.onerror = () => { img.remove(); wrap.textContent = (name || "?")[0]; };
    wrap.appendChild(img);
  } else {
    wrap.textContent = (name || "?")[0];
  }
  return wrap;
}

/* ---------- 连接状态 ---------- */

async function refreshStatus() {
  const res = await window.pywebview.api.get_status();
  const badge = $("connBadge");
  const btn = $("retryBtn");
  if (res.ok && res.connected) {
    badge.className = "badge online";
    $("connText").textContent = `已连接客户端：${res.me.name}（Lv.${res.me.level}）`;
    btn.hidden = true;
    clearTimeout(state.statusTimer);
    hideToast();
  } else {
    badge.className = "badge offline";
    $("connText").textContent = "未检测到英雄联盟客户端";
    btn.hidden = false;
    toast(res.error || "未检测到客户端，请先登录英雄联盟客户端。", true);
    clearTimeout(state.statusTimer);
    state.statusTimer = setTimeout(refreshStatus, 8000); // 自动重试
  }
}

/* ---------- 查询 ---------- */

async function doSearch() {
  const q = $("queryInput").value.trim();
  if (!q) { toast("请输入玩家 ID"); return; }
  if (state.loading || state.pageLoading || state.loadingAll) return;
  state.loading = true;
  $("searchBtn").disabled = true;
  $("searchBtn").textContent = "查询中…";
  try {
    const res = await window.pywebview.api.search_player(q);
    if (!res.ok) { toast(res.error); return; }
    state.player = res.summoner;
    state.damageEpoch++;
    state.damageBusy = false;
    state.games = [];
    state.hasMore = false;
    renderPlayer();
    await loadPage(0);
  } finally {
    state.loading = false;
    $("searchBtn").disabled = false;
    $("searchBtn").textContent = "查 询";
  }
}

async function loadPage(beg) {
  if (state.pageLoading || !state.player) return false;
  state.pageLoading = true;
  $("loadMoreBtn").disabled = true;
  $("loadAllBtn").disabled = true;
  try {
    const res = await window.pywebview.api.get_matches(state.player.puuid, beg);
    if (!res.ok) { toast(res.error); return false; }
    if (beg === 0) state.games = [];
    // 服务端分页参数在当前客户端已失效（任何 begIndex 都返回最新 20 场），
    // 按 gameId 去重；整页全部重复即视为没有更多，避免「加载全部」无限重复。
    const seen = new Set(state.games.map(g => g.gameId));
    const fresh = res.games.filter(g => {
      if (seen.has(g.gameId)) return false;
      seen.add(g.gameId);
      return true;
    });
    state.games.push(...fresh);
    state.nextBeg = beg + res.games.length;
    state.hasMore = res.hasMore && fresh.length > 0 && state.nextBeg < 2000;
    return true;
  } catch (error) {
    toast(`加载战绩失败：${error.message || error}`);
    return false;
  } finally {
    state.pageLoading = false;
    renderAll();
  }
}

async function loadAll() {
  if (state.loadingAll || state.pageLoading || !state.player) return;
  state.loadingAll = true;
  $("loadAllBtn").disabled = true;
  $("loadMoreBtn").disabled = true;
  const box = $("loadingAll");
  box.hidden = false;
  try {
    while (state.hasMore) {
      if (!await loadPage(state.nextBeg)) { box.hidden = true; return; }
      box.textContent = `已加载 ${state.games.length} 场战绩…`;
      if (state.games.length > 2000) { toast("已达拉取上限"); break; }
    }
    if (!state.hasMore && state.games.length <= 20) {
      box.textContent = `已加载 ${state.games.length} 场，客户端未返回更多战绩`;
    } else {
      box.textContent = `加载完成，共 ${state.games.length} 场战绩`;
    }
    setTimeout(() => { box.hidden = true; }, 2500);
  } finally {
    state.loadingAll = false;
    renderAll();
  }
}

/* ---------- 渲染 ---------- */

function renderPlayer() {
  const s = state.player;
  const bar = $("playerBar");
  bar.hidden = false;
  bar.innerHTML = "";
  const av = avatarEl("", s.name || "?", "avatar");
  const info = document.createElement("div");
  const tag = s.tagLine ? `#${s.tagLine}` : "";
  info.innerHTML = `<div class="name"></div>
    <div class="sub">等级 ${s.level} · 已加载 <b class="gcount">0</b> 场战绩 ${friendBadge(s.friendStatus)}</div>
    <div id="playerRating" class="player-rating"></div>`;
  info.querySelector(".name").textContent = (s.name || "未知玩家") + tag;
  bar.appendChild(av);
  bar.appendChild(info);
}

function summarize(games) {
  const counted = games.filter(g => !g.remake);
  const wins = counted.filter(g => g.win).length;
  const k = games.reduce((a, g) => a + g.kills, 0);
  const d = games.reduce((a, g) => a + g.deaths, 0);
  const ast = games.reduce((a, g) => a + g.assists, 0);
  const champ = {};
  games.forEach(g => {
    const c = champ[g.championId] || (champ[g.championId] = { n: 0, w: 0, name: g.championName, avatar: g.avatar });
    c.n++;
    if (g.win && !g.remake) c.w++;
  });
  const top = Object.values(champ).sort((a, b) => b.n - a.n).slice(0, 6);
  return {
    total: games.length,
    counted: counted.length,
    winRate: counted.length ? (wins * 100 / counted.length) : 0,
    avgKda: ((k + ast) / Math.max(d, 1)).toFixed(2),
    top,
  };
}

function renderSummary(games) {
  const s = summarize(games);
  const cards = $("summaryCards");
  cards.hidden = games.length === 0;
  const wrCls = s.winRate >= 50 ? "wr-good" : "wr-bad";
  const range = dateRange(games);
  cards.innerHTML = `
    <div class="stat-card"><div class="label">筛选场次</div>
      <div class="value">${s.total}<span class="unit"> 场</span></div>
      ${range ? `<div class="sublabel">${range}</div>` : ""}</div>
    <div class="stat-card"><div class="label">胜率（不含重开）</div>
      <div class="value ${wrCls}">${s.winRate.toFixed(1)}<span class="unit"> %</span></div></div>
    <div class="stat-card"><div class="label">场均 KDA</div>
      <div class="value ${+s.avgKda >= 3 ? "kda-good" : ""}">${s.avgKda}</div></div>
    <div class="stat-card"><div class="label">常用英雄</div>
      <div class="champ-row">${s.top.map(c => `
        <span class="champ-chip" title="${c.name} ${((c.w * 100) / c.n).toFixed(1)}%">
          ${c.avatar ? `<img src="${c.avatar}" onerror="this.style.display='none'">` : ""}
          <span class="cname"><b>${c.name}</b></span>
          <span class="wr">${((c.w * 100) / c.n).toFixed(0)}%</span>
        </span>`).join("") || '<span style="color:#55637a">—</span>'}
      </div></div>`;
  $("playerBar").querySelector(".gcount").textContent = state.games.length;
  const rating = MatchRating.average(games);
  $("playerRating").innerHTML = rating.score === null ? "暂无可评分对局" :
    `当前筛选综合评分 ${ratingBadge(rating)} <span>基于 ${rating.count} 场，排除重开</span>`;
}

function friendBadge(status) {
  const labels = {self: "本人", friend: "好友", not_friend: "非好友", unknown: "好友状态未知"};
  const key = Object.hasOwn(labels, status) ? status : "unknown";
  return `<span class="friend-badge friend-${key}" title="按当前登录客户端账号的好友列表判断，最多缓存 60 秒；读取失败时显示未知">${labels[key]}</span>`;
}

function ratingBadge(rating) {
  return `<span class="rating-badge rating-${rating.level}" title="${escapeHtml(rating.reason || MatchRating.formula)}">${escapeHtml(rating.label)}${rating.score === null ? '' : ` <b>${rating.score.toFixed(1)}</b> 分`}</span>`;
}

/* 已加载战绩的对局日期范围，如「2026-09-01 ~ 2026-09-09」 */
function dateRange(games) {
  if (!games.length) return "";
  let min = Infinity, max = -Infinity;
  games.forEach(g => {
    const t = timestamp(g.creation);
    if (!Number.isFinite(t)) return;
    if (t < min) min = t;
    if (t > max) max = t;
  });
  if (min === Infinity) return "";
  return `${fmtDay(min)} ~ ${fmtDay(max)}`;
}

function fmtDay(ts) {
  const d = new Date(timestamp(ts));
  if (Number.isNaN(d.getTime())) return "";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/* 海克斯强化符文小徽章行 */
function augmentChips(augmentNames, mayhem = false) {
  const list = augmentNames || [];
  if (!list.length) return mayhem ? '<div class="aug-empty">客户端未提供海克斯记录</div>' : "";
  const rarities = { kSilver: "白银", kGold: "黄金", kPrismatic: "棱彩" };
  return `<div class="aug-chips" aria-label="海克斯强化">${list.map(a => {
    const name = escapeHtml(a.name || "未知海克斯（资料待更新）");
    const rarity = Object.hasOwn(rarities, a.rarity) ? a.rarity : "unknown";
    const icon = /^(https:\/\/|data:image\/png;base64,)/.test(a.icon || "") ? a.icon : "";
    return `<span class="aug-chip ${rarity}" title="${rarities[rarity] || '资料待更新'} · ${name} · ID ${escapeHtml(a.id)}">
      ${icon ? `<img src="${escapeHtml(icon)}" alt="${name}" loading="lazy" onerror="this.hidden=true;this.nextElementSibling.hidden=false">` : ""}
      <span class="aug-placeholder" ${icon ? 'hidden' : ''} aria-hidden="true">⬡</span><span>${name}</span></span>`;
  }).join("")}</div>`;
}

function matchCard(g) {
  const card = document.createElement("div");
  card.className = `match-card ${g.win ? "win" : "lose"}`;
  card.dataset.gameId = g.gameId;

  const champ = document.createElement("div");
  champ.className = "mc-champ";
  champ.appendChild(avatarEl(g.avatar, g.championName, "ph"));
  if (g.level) {
    const lv = document.createElement("span");
    lv.className = "lvl"; lv.textContent = "Lv." + g.level;
    champ.appendChild(lv);
  }

  const main = document.createElement("div");
  main.className = "mc-main";
  const winWord = g.remake
    ? '<span class="remake-tag">重开</span>'
    : (g.win ? '<span class="win-word">胜利</span>' : '<span class="lose-word">失败</span>');
  main.innerHTML = `<div class="cname"></div>
    <div class="meta">${winWord} · <time>${fmtTime(g.creation)}</time></div>
    ${augmentChips(g.augmentNames, queueGroup(g) === "mayhem")}`;
  main.querySelector(".cname").textContent = g.championName;

  const kda = document.createElement("div");
  kda.className = "mc-kda";
  const ratio = +kdaRatio(g.kills, g.deaths, g.assists);
  kda.innerHTML = `<div class="nums">${g.kills} / <span class="d">${g.deaths}</span> / ${g.assists}</div>
    <div class="ratio ${ratio >= 3 ? "kda-good" : ""}">${ratio.toFixed(2)} KDA</div>`;

  const stats = document.createElement("div");
  stats.className = "mc-stats";
  stats.innerHTML = `
    <div class="mc-stat"><div class="v">${g.cs}</div><div class="k">补刀</div></div>
    <div class="mc-stat"><div class="v">${(g.gold / 1000).toFixed(1)}k</div><div class="k">金币</div></div>
    <div class="mc-stat"><div class="v">${(g.damage / 1000).toFixed(1)}k</div><div class="k">伤害</div>${damageBadge(g.damageEvaluation, g.remake)}</div>`;

  const right = document.createElement("div");
  right.className = "mc-right";
  right.innerHTML = `<div class="dur">${fmtDuration(g.durationSec)}</div>
    <div class="mode">${g.mode || ""}</div>${ratingBadge(MatchRating.rate(g))}<span class="arrow">▸</span>`;

  card.appendChild(champ);
  card.appendChild(main);
  card.appendChild(kda);
  card.appendChild(stats);
  card.appendChild(right);
  card.addEventListener("click", () => openDetail(g.gameId));
  return card;
}

function renderAll() {
  if (!state.player) return;
  const games = visibleGames();
  games.sort((a, b) => {
    if ($("matchSort").value === "score") {
      const delta = (MatchRating.rate(b).score ?? -1) - (MatchRating.rate(a).score ?? -1);
      if (delta) return delta;
    }
    return (timestamp(b.creation) || 0) - (timestamp(a.creation) || 0);
  });
  const list = $("matchList");
  list.innerHTML = "";
  games.forEach(g => list.appendChild(matchCard(g)));
  $("listHead").hidden = false;
  $("emptyHint").hidden = games.length > 0;
  $("emptyHint").textContent = "已加载战绩中没有符合条件的对局，可调整筛选或加载更多。";
  const invalidDates = $("dateFrom").value && $("dateTo").value && $("dateFrom").value > $("dateTo").value;
  $("filterHint").textContent = invalidDates ? "开始日期不能晚于结束日期" :
    `显示 ${games.length} / ${state.games.length} 场 · 日期按本地时间筛选（含结束日）`;
  $("loadMoreBtn").disabled = !state.hasMore || state.loadingAll || state.pageLoading;
  $("loadAllBtn").disabled = state.loadingAll || state.pageLoading || !state.hasMore;
  $("exportBtn").disabled = games.length === 0;
  const tag = state.player.tagLine ? "#" + state.player.tagLine : "";
  $("listTitle").textContent = `${state.player.name}${tag} 的战绩（筛选 ${games.length} / 已加载 ${state.games.length} 场）`;
  renderSummary(games);
  renderDamageSummary();
  renderAnalysis();
  ensureDamageAnalysis();
}

/* ---------- 最近二十场全场伤害最高占比 ---------- */

function damageBadge(e, remake = false) {
  if (remake || e?.status === 'remake') return '<span class="damage-badge">重开不计</span>';
  if (!e) return '<span class="damage-badge">待核验</span>';
  if (e.status !== 'ok') return `<span class="damage-badge" title="${escapeHtml(e.reason)}">${e.status === 'unsupported' ? '不适用' : '资料不足'}</span>`;
  if (e.maxDamage === 0) return '<span class="damage-badge">全场均无伤害</span>';
  const label = e.isTop ? (e.tied ? '并列全场最高' : '全场伤害最高') : `全场第 ${e.rank} / 10`;
  return `<span class="damage-badge ${e.isTop ? 'damage-top' : ''}" title="对英雄伤害；全场最高 ${e.maxDamage}，本人 ${e.damage}">${label}</span>`;
}

function renderDamageSummary() {
  const report = DamageAnalysis.summarize(visibleGames());
  $("damageSummary").hidden = !state.player;
  const verdict = $("damageVerdict");
  verdict.textContent = report.verdict;
  verdict.className = !report.unknown && report.percent !== null && report.percent >= 30 ? 'damage-top' : '';
  const proportion = report.percent === null ? '暂无已核验占比' :
    `全场伤害最高 ${report.top} / ${report.verified} 场（${report.percent.toFixed(1)}%${report.unknown ? '，仅已核验部分' : ''}）`;
  $("damageProgress").textContent = `当前筛选最近 ${report.total} 场非重开对局（最多 20 场） · ${proportion}` +
    ` · 待确认 ${report.unknown} 场${report.skipped ? ` · 模式不适用 ${report.skipped} 场` : ''}` +
    (state.damageBusy ? ' · 正在核验…' : '') + '。仅比较对英雄伤害，并列最高计入；全部零伤害不计最高。';
  $("retryDamage").hidden = !DamageAnalysis.recent(visibleGames()).some(g => g.damageEvaluation?.status === 'unknown');
  $("retryDamage").disabled = state.damageBusy;
}

async function ensureDamageAnalysis() {
  if (!state.player || state.damageBusy) return;
  const todo = DamageAnalysis.recent(visibleGames()).filter(g => !g.damageEvaluation).slice(0, 5);
  if (!todo.length) return;
  const epoch = state.damageEpoch, puuid = state.player.puuid;
  state.damageBusy = true;
  renderDamageSummary();
  try {
    const res = await window.pywebview.api.get_damage_evaluations(puuid, todo.map(g => g.gameId));
    if (epoch !== state.damageEpoch) return;
    const results = new Map((res.results || []).map(r => [String(r.gameId), r.evaluation]));
    todo.forEach(g => {
      if (['ok', 'remake'].includes(g.damageEvaluation?.status)) return;
      g.damageEvaluation = res.ok && results.get(String(g.gameId)) ||
        {status:'unknown', reason:res.error || '伤害详情暂不可用，可重试'};
      if (g.damageEvaluation.status === 'remake') g.remake = true;
    });
  } catch (error) {
    if (epoch === state.damageEpoch) todo.forEach(g => {
      if (['ok', 'remake'].includes(g.damageEvaluation?.status)) return;
      g.damageEvaluation = {status:'unknown', reason:'读取伤害详情失败，可重试'};
    });
  } finally {
    if (epoch === state.damageEpoch) {
      state.damageBusy = false;
      renderAll();
    }
  }
}

/* ---------- 海克斯胜率、强度及英雄适配 ---------- */

function analysisChampions() {
  const select = $("analysisChampion"), old = select.value;
  const isPublic = $("analysisSource").value === "public";
  const played = state.games.filter(AugmentAnalysis.mayhem).map(g => ({id: g.championId, name: g.championName}));
  const choices = new Map((isPublic ? [...state.analysisCatalog, ...played] : played).map(c => [String(c.id), c]));
  select.innerHTML = '<option value="0">全部英雄</option>';
  [...choices.values()].sort((a, b) => (a.name || "").localeCompare(b.name || "", "zh-CN")).forEach(c => {
    const option = document.createElement("option");
    option.value = c.id; option.textContent = c.name; select.appendChild(option);
  });
  select.value = choices.has(old) ? old : "0";
}

function performanceHtml(p) {
  const delta = p.delta === null ? "没有未选取样本" : `较未选取时 ${p.delta >= 0 ? '+' : ''}${p.delta.toFixed(1)} 个百分点`;
  return `<span title="${delta}；未选取 ${p.withoutCount} 场">${p.label}</span>`;
}

function renderAnalysis() {
  analysisChampions();
  const body = $("analysisBody"), note = $("analysisNote");
  const cid = Number($("analysisChampion").value);
  const search = $("analysisSearch").value.trim().toLocaleLowerCase();
  const isPublic = $("analysisSource").value === "public";
  $("refreshReference").hidden = !isPublic;
  $("refreshReference").disabled = state.referenceLoading;
  if (!isPublic) {
    const report = AugmentAnalysis.personal(visibleGames(), cid);
    note.textContent = `当前查询玩家 · ${report.recorded} / ${report.total} 场海克斯大乱斗有强化记录（排除重开）；` +
      "按当前类型和日期筛选。选取与未选取各满 10 场才比较表现，差值达 ±5 个百分点标记偏高/偏低；个人相关性不代表全服强度或因果收益。";
    if (!report.rows.length) {
      body.textContent = state.player ? "当前筛选下没有可分析的海克斯记录，请调整类型、日期或英雄。" :
        "查询玩家后显示个人胜率和英雄搭配表现；也可切换到公开参考，无需启动游戏客户端。";
      return;
    }
    const rows = report.rows.filter(r => (r.augment.name || "").toLocaleLowerCase().includes(search));
    body.innerHTML = `<table class="analysis-table"><thead><tr><th>海克斯</th><th>个人胜率</th><th>样本</th><th>个人表现</th><th>英雄搭配（个人样本）</th></tr></thead><tbody>${rows.map(r =>
      `<tr><td>${augmentChips([r.augment])}</td><td class="analysis-rate">${r.winRate.toFixed(1)}%</td><td>${r.wins} 胜 / ${r.count} 场</td><td>${performanceHtml(r.performance)}</td>
      <td>${r.champions.map(c => `<div class="analysis-pair">${escapeHtml(c.name)}：${c.winRate.toFixed(1)}%（${c.wins}/${c.count} 场），${performanceHtml(c.performance)}</div>`).join('')}</td></tr>`).join('')}</tbody></table>`;
    if (!rows.length) body.textContent = "没有匹配该名称的海克斯。";
    return;
  }
  note.textContent = "公开参考按来源版本统计，不随个人日期筛选；选择英雄可查看专属搭配。不会上传玩家或战绩数据。";
  if (state.referenceLoading) { body.textContent = "正在获取公开参考…"; return; }
  if (state.referenceError) { body.textContent = state.referenceError; return; }
  const data = state.reference;
  if (!data || data.championId !== cid) { body.textContent = "点击“刷新公开参考”获取数据。"; return; }
  note.innerHTML = `${data.stale ? '<strong class="reference-stale">刷新失败，显示旧缓存。</strong> ' : ''}` +
    `<a href="${escapeHtml(data.sourceUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(data.source)}</a> · ` +
    `版本 ${escapeHtml(data.patch)} · ${escapeHtml(data.scope)} · 获取：${fmtTime(data.fetchedAt)}` +
    `${data.sourceUpdated ? ` · 来源日期：${escapeHtml(data.sourceUpdated)}` : ' · 来源未标明统计日期'}。` +
    `${data.minimumSample ? `来源公布门槛 ≥${data.minimumSample} 场，逐项样本数见表。` : '来源未提供逐项样本数。'}` +
    "梯队沿用来源的 T1–T5（T1 最高），不等于稀有度；公开参考不随个人日期筛选。";
  const rows = data.rows.filter(r => (r.augment.name || '').toLocaleLowerCase().includes(search));
  body.innerHTML = `<table class="analysis-table"><thead><tr><th>海克斯</th><th>${cid ? '该英雄搭配胜率' : '公开胜率'}</th><th>${cid ? '该英雄适配梯队' : '公开强度梯队'}</th><th>统计样本</th></tr></thead><tbody>${rows.map(r =>
    `<tr><td>${augmentChips([r.augment])}</td><td class="analysis-rate">${r.winRate === null ? '暂无统计' : r.winRate.toFixed(2) + '%'}</td><td><span class="reference-tier tier-${escapeHtml(r.tier)}">${escapeHtml(r.tier)}</span></td><td>${r.sampleSize ?? '未公开'}</td></tr>`).join('')}</tbody></table>`;
  if (!rows.length) body.textContent = "来源没有提供匹配该名称的记录，不将缺失数据视为零胜率或不适配。";
}

async function loadReference(force = false) {
  const request = ++state.referenceSeq;
  const cid = Number($("analysisChampion").value);
  state.referenceLoading = true;
  state.referenceError = "";
  renderAnalysis();
  try {
    const res = await window.pywebview.api.get_augment_reference(cid, force);
    if (request !== state.referenceSeq) return;
    if (res.ok) state.reference = res.data;
    else state.referenceError = res.error || "公开参考暂不可用";
  } catch (error) {
    if (request === state.referenceSeq) state.referenceError = `公开参考暂不可用：${error.message || error}`;
  } finally {
    if (request === state.referenceSeq) {
      state.referenceLoading = false;
      renderAnalysis();
    }
  }
}

/* ---------- 详情 ---------- */

async function copyPlayerId(text, button) {
  try {
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard API unavailable");
      await navigator.clipboard.writeText(text);
    } catch (_) {
      // WebView installations without Clipboard API permission still support the
      // user-initiated copy command. Keep the exact name and Tag as plain text.
      const input = document.createElement("textarea");
      input.value = text;
      input.style.cssText = "position:fixed;left:-9999px;top:0";
      document.body.appendChild(input);
      try {
        input.select();
        if (!document.execCommand("copy")) throw new Error("复制失败，请手动选中玩家 ID 复制");
      } finally { input.remove(); button.focus(); }
    }
    button.textContent = "已复制";
    setTimeout(() => { if (button.isConnected) button.textContent = "复制 ID"; }, 1800);
  } catch (error) {
    button.textContent = "复制失败";
    toast(error.message || "复制失败，请重试");
  }
}

async function openDetail(gameId) {
  state.detailGame = null;
  $("detailMask").hidden = false;
  $("detailBody").textContent = "加载中…";
  const myPuuid = state.player ? (state.player.puuid || "") : "";
  const res = await window.pywebview.api.get_game_detail(gameId, myPuuid);
  if (state.player?.puuid !== myPuuid) return;
  if (!res.ok) { $("detailBody").textContent = res.error; return; }
  const g = res.game;
  const match = state.games.find(m => String(m.gameId) === String(gameId));
  if (match && g.damageEvaluation) {
    match.damageEvaluation = g.damageEvaluation;
    if (g.damageEvaluation.status === 'remake') match.remake = true;
    renderAll();
  }
  state.detailGame = g;
  renderDetail(g);
}

function renderDetail(g) {
  const myPuuid = state.player ? (state.player.puuid || "") : "";
  $("detailTitle").textContent =
    `${g.mode} · ${fmtDuration(g.durationSec)} · ${fmtTime(g.creation)}`;
  const body = $("detailBody");
  body.innerHTML = "";
  const notice = document.createElement("p");
  notice.className = "detail-friend-note";
  notice.textContent = "好友关系相对于当前登录客户端账号；评分为自定义娱乐参考，悬停可看计算依据。";
  body.appendChild(notice);
  // 「我方」= 被查询玩家所在队伍；接口没给 myTeamId 时回退为 team 100
  const myTeamId = g.myTeamId || 100;
  g.teams.forEach(team => {
    if (!team.players.length) return;
    const isMy = team.teamId === myTeamId;
    const won = team.players[0].win;
    const t = document.createElement("div");
    t.className = `detail-team-title ${won ? "win" : "lose"}`;
    t.textContent = `${isMy ? "我方队伍" : "敌方队伍"} · ${won ? "胜利" : "失败"}`;
    const table = document.createElement("table");
    table.className = "dtable";
    const players = [...team.players];
    if ($("detailSort").value === "score") {
      players.sort((a, b) => (MatchRating.rate({...b, durationSec:g.durationSec, remake:g.remake}).score ?? -1) -
        (MatchRating.rate({...a, durationSec:g.durationSec, remake:g.remake}).score ?? -1));
    }
    players.forEach(p => {
      const tr = document.createElement("tr");
      if (myPuuid && p.puuid === myPuuid) tr.className = "me";
      const items = p.itemIcons.filter(Boolean).map(u =>
        `<img src="${u}" onerror="this.style.visibility='hidden'">`).join("");
      const pname = p.name ? (p.tagLine ? `${p.name}#${p.tagLine}` : p.name) : "";
      tr.innerHTML = `
        <td><div class="dchamp">
          <img src="${p.avatar}" onerror="this.style.visibility='hidden'"><span></span>
          <span class="pname"></span></div></td>
        <td class="dkda"><b>${p.kills}</b> / <span class="d">${p.deaths}</span> / <b>${p.assists}</b></td>
        <td>补刀 ${p.cs}</td>
        <td>${(p.gold / 1000).toFixed(1)}k 金币</td>
        <td>${(p.damage / 1000).toFixed(1)}k 伤害<div>${damageBadge(p.damageEvaluation, g.remake)}</div></td>
        <td><div class="items">${items}</div></td>`;
      tr.querySelector(".dchamp span").textContent = p.championName || p.name;
      tr.querySelector(".pname").textContent = pname;
      tr.querySelector(".pname").title = pname;
      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "copy-id";
      copy.textContent = "复制 ID";
      copy.disabled = !p.name;
      copy.title = pname ? `复制 ${pname}${p.tagLine ? '' : '（客户端未提供 Tag，只能复制名称）'}` : "客户端未提供玩家 ID";
      copy.setAttribute("aria-label", pname ? `复制玩家 ID：${pname}` : "无法复制玩家 ID");
      copy.addEventListener("click", e => { e.stopPropagation(); copyPlayerId(pname, copy); });
      tr.querySelector(".dchamp").appendChild(copy);
      const status = document.createElement("span");
      status.innerHTML = friendBadge(p.friendStatus);
      tr.querySelector(".dchamp").appendChild(status);
      const rating = document.createElement("div");
      rating.className = "detail-rating";
      rating.innerHTML = ratingBadge(MatchRating.rate({...p, durationSec:g.durationSec, remake:g.remake}));
      tr.querySelector(".dkda").appendChild(rating);
      const augCell = document.createElement("td");
      augCell.className = "daug";
      augCell.colSpan = 6;
      augCell.innerHTML = augmentChips(p.augments, g.mode === "海克斯大乱斗");
      table.appendChild(tr);
      if (augCell.innerHTML) {
        const augRow = document.createElement("tr");
        augRow.className = tr.className;
        augRow.appendChild(augCell);
        table.appendChild(augRow);
      }
    });
    body.appendChild(t);
    body.appendChild(table);
  });
}

/* ---------- 导出 ---------- */

function exportCsv() {
  const games = visibleGames();
  if (!games.length) return;
  const head = "英雄,模式,结果,击杀,死亡,助攻,KDA,补刀,金币,对英雄伤害,时长(分),对局时间,海克斯强化,gameId,娱乐评分,评分等级,全场伤害排名,全场伤害最高";
  const rows = games.map(g => [
    g.championName, g.mode, g.remake ? "重开" : (g.win ? "胜" : "负"),
    g.kills, g.deaths, g.assists, kdaRatio(g.kills, g.deaths, g.assists),
    g.cs, g.gold, g.damage, (g.durationSec / 60).toFixed(1), fmtTime(g.creation),
    (g.augmentNames || []).map(a => a.name).join("|"), g.gameId,
    MatchRating.rate(g).score ?? '', MatchRating.rate(g).label,
    g.damageEvaluation?.status === 'ok' && !g.remake ? g.damageEvaluation.rank : '',
    g.remake ? '重开不计' : g.damageEvaluation?.status === 'ok' ?
      (g.damageEvaluation.isTop ? (g.damageEvaluation.tied ? '并列最高' : '是') : '否') : '未核验或不适用',
  ].map(v => `"${String(v ?? '').replace(/"/g, '""')}"`).join(","));
  const csv = "\ufeff" + head + "\n" + rows.join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${state.player.name}_战绩.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

/* ---------- 启动 ---------- */

function bindEvents() {
  $("retryDamage").addEventListener("click", () => {
    DamageAnalysis.recent(visibleGames()).forEach(g => {
      if (g.damageEvaluation?.status === 'unknown') delete g.damageEvaluation;
    });
    ensureDamageAnalysis();
  });
  $("matchSort").addEventListener("change", renderAll);
  $("detailSort").addEventListener("change", () => { if (state.detailGame) renderDetail(state.detailGame); });
  $("analysisSource").addEventListener("change", () => {
    state.referenceSeq++;
    state.referenceLoading = false;
    analysisChampions();
    renderAnalysis();
    if ($("analysisSource").value === "public") loadReference();
  });
  $("analysisChampion").addEventListener("change", () => {
    renderAnalysis();
    if ($("analysisSource").value === "public") loadReference();
  });
  $("analysisSearch").addEventListener("input", renderAnalysis);
  $("refreshReference").addEventListener("click", () => loadReference(true));
  ["queueFilter", "dateFrom", "dateTo"].forEach(id => $(id).addEventListener("change", renderAll));
  $("resetFilters").addEventListener("click", () => {
    $("queueFilter").value = "all";
    $("dateFrom").value = "";
    $("dateTo").value = "";
    renderAll();
  });
  $("searchBtn").addEventListener("click", doSearch);
  $("queryInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") doSearch();
  });
  $("loadMoreBtn").addEventListener("click", () => loadPage(state.nextBeg));
  $("loadAllBtn").addEventListener("click", loadAll);
  $("exportBtn").addEventListener("click", exportCsv);
  $("retryBtn").addEventListener("click", () => { hideToast(); refreshStatus(); });
  $("detailClose").addEventListener("click", () => { $("detailMask").hidden = true; });
  $("detailMask").addEventListener("click", (e) => {
    if (e.target === $("detailMask")) $("detailMask").hidden = true;
  });
}

function init() {
  bindEvents();
  $("ratingRules").textContent = MatchRating.formula + " 等级从高到低：" +
    MatchRating.tiers.map((t, i) => `${t.label}（${t.minimum}${i === 0 ? '–100' : '–<' + MatchRating.tiers[i-1].minimum} 分）`).join('；') +
    "。综合评分取当前筛选对局的均分，重开和资料不足的对局不计分。不同模式节奏不同，本评分不是官方实力或段位。";
  refreshStatus();
  renderAnalysis();
  window.pywebview.api.get_champion_map().then(res => {
    if (res.ok) state.analysisCatalog = res.champions || [];
    renderAnalysis();
  }).catch(() => {});
}

if (window.pywebview) {
  init();
} else {
  window.addEventListener("pywebviewready", init);
}
