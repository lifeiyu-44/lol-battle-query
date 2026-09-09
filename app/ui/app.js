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

function fmtTime(ts) {
  if (!ts) return "";
  if (ts < 1e12) ts *= 1000; // 秒 → 毫秒
  const d = new Date(ts);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
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
  if (state.loading) return;
  state.loading = true;
  $("searchBtn").disabled = true;
  $("searchBtn").textContent = "查询中…";
  try {
    const res = await window.pywebview.api.search_player(q);
    if (!res.ok) { toast(res.error); return; }
    state.player = res.summoner;
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
  const res = await window.pywebview.api.get_matches(state.player.puuid, beg);
  if (!res.ok) { toast(res.error); return; }
  if (beg === 0) state.games = [];
  state.games.push(...res.games);
  state.hasMore = res.hasMore;
  state.nextBeg = beg + res.games.length;
  renderAll();
}

async function loadAll() {
  if (state.loadingAll || !state.player) return;
  state.loadingAll = true;
  $("loadAllBtn").disabled = true;
  $("loadMoreBtn").disabled = true;
  const box = $("loadingAll");
  box.hidden = false;
  try {
    while (state.hasMore) {
      await loadPage(state.nextBeg);
      box.textContent = `已加载 ${state.games.length} 场战绩…`;
      if (state.games.length > 2000) { toast("已达拉取上限"); break; }
    }
    box.textContent = `加载完成，共 ${state.games.length} 场战绩`;
    setTimeout(() => { box.hidden = true; }, 2500);
  } finally {
    state.loadingAll = false;
    $("loadAllBtn").disabled = false;
    $("loadMoreBtn").disabled = false;
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
    <div class="sub">等级 ${s.level} · 已加载 <b class="gcount">0</b> 场战绩</div>`;
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

function renderSummary() {
  const s = summarize(state.games);
  const cards = $("summaryCards");
  cards.hidden = state.games.length === 0;
  const wrCls = s.winRate >= 50 ? "wr-good" : "wr-bad";
  cards.innerHTML = `
    <div class="stat-card"><div class="label">总场次</div>
      <div class="value">${s.total}<span class="unit"> 场</span></div></div>
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
    <div class="meta">${winWord} · ${fmtTime(g.creation)}</div>`;
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
    <div class="mc-stat"><div class="v">${(g.damage / 1000).toFixed(1)}k</div><div class="k">伤害</div></div>`;

  const right = document.createElement("div");
  right.className = "mc-right";
  right.innerHTML = `<div class="dur">${fmtDuration(g.durationSec)}</div>
    <div class="mode">${g.mode || ""}</div><span class="arrow">▸</span>`;

  card.appendChild(champ);
  card.appendChild(main);
  card.appendChild(kda);
  card.appendChild(stats);
  card.appendChild(right);
  card.addEventListener("click", () => openDetail(g.gameId));
  return card;
}

function renderAll() {
  const list = $("matchList");
  list.innerHTML = "";
  state.games.forEach(g => list.appendChild(matchCard(g)));
  $("listHead").hidden = false;
  $("emptyHint").hidden = true;
  $("loadMoreBtn").disabled = !state.hasMore || state.loadingAll;
  $("loadAllBtn").disabled = state.loadingAll || !state.hasMore;
  $("exportBtn").disabled = state.games.length === 0;
  const tag = state.player.tagLine ? "#" + state.player.tagLine : "";
  $("listTitle").textContent = `${state.player.name}${tag} 的战绩（已加载 ${state.games.length} 场）`;
  renderSummary();
}

/* ---------- 详情 ---------- */

async function openDetail(gameId) {
  $("detailMask").hidden = false;
  $("detailBody").textContent = "加载中…";
  const res = await window.pywebview.api.get_game_detail(gameId);
  if (!res.ok) { $("detailBody").textContent = res.error; return; }
  const g = res.game;
  $("detailTitle").textContent =
    `${g.mode} · ${fmtDuration(g.durationSec)} · ${fmtTime(g.creation)}`;
  const body = $("detailBody");
  body.innerHTML = "";
  const names = ["我方队伍", "敌方队伍"];
  g.teams.forEach((team, i) => {
    if (!team.players.length) return;
    const won = team.players[0].win;
    const t = document.createElement("div");
    t.className = `detail-team-title ${won ? "win" : "lose"}`;
    t.textContent = `${i === 0 ? names[0] : names[1]} · ${won ? "胜利" : "失败"}`;
    const table = document.createElement("table");
    table.className = "dtable";
    const meName = state.player ? state.player.name : "";
    team.players.forEach(p => {
      const tr = document.createElement("tr");
      if (p.name && meName && p.name === meName) tr.className = "me";
      const items = p.itemIcons.filter(Boolean).map(u =>
        `<img src="${u}" onerror="this.style.visibility='hidden'">`).join("");
      tr.innerHTML = `
        <td><div class="dchamp">
          <img src="${p.avatar}" onerror="this.style.visibility='hidden'"><span></span></div></td>
        <td class="dkda"><b>${p.kills}</b> / <span class="d">${p.deaths}</span> / <b>${p.assists}</b></td>
        <td>补刀 ${p.cs}</td>
        <td>${(p.gold / 1000).toFixed(1)}k 金币</td>
        <td>${(p.damage / 1000).toFixed(1)}k 伤害</td>
        <td><div class="items">${items}</div></td>`;
      tr.querySelector(".dchamp span").textContent = p.championName || p.name;
      table.appendChild(tr);
    });
    body.appendChild(t);
    body.appendChild(table);
  });
}

/* ---------- 导出 ---------- */

function exportCsv() {
  if (!state.games.length) return;
  const head = "英雄,模式,结果,击杀,死亡,助攻,KDA,补刀,金币,对英雄伤害,时长(分),对局时间,gameId";
  const rows = state.games.map(g => [
    g.championName, g.mode, g.remake ? "重开" : (g.win ? "胜" : "负"),
    g.kills, g.deaths, g.assists, kdaRatio(g.kills, g.deaths, g.assists),
    g.cs, g.gold, g.damage, (g.durationSec / 60).toFixed(1), fmtTime(g.creation), g.gameId,
  ].join(","));
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
  refreshStatus();
}

if (window.pywebview) {
  init();
} else {
  window.addEventListener("pywebviewready", init);
}
