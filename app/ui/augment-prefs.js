"use strict";
/* 优选海克斯：按英雄维护强化优先级，贴在当前对局下方，保存在本机。 */
const AugmentPrefs = (() => {
  const MAX = 12;
  const rarities = { kSilver: "白银", kGold: "黄金", kPrismatic: "棱彩" };
  let root, selectEl, searchEl, listEl, suggestEl, noteEl;
  let catalog = [], byId = new Map(), preferences = {}, current = 0;
  let manual = false, saveTimer, epoch = 0;

  const list = () => preferences[String(current)] || [];

  function rarityLabel(augment) {
    return rarities[augment?.rarity] || "资料待更新";
  }

  // state 是 app.js 顶层的 const，不在 window 上，只能按全局词法作用域引用。
  function championCatalog() {
    return (typeof state !== "undefined" && Array.isArray(state.analysisCatalog)) ? state.analysisCatalog : [];
  }

  function championName(id) {
    const info = championCatalog().find(c => Number(c.id) === Number(id));
    return info?.name || `英雄 #${id}`;
  }

  function scheduleSave() {
    // 防抖落盘；保存成功后以后端归一化结果为准（去重、限量、丢弃非法值）。
    clearTimeout(saveTimer);
    saveTimer = setTimeout(async () => {
      const mine = ++epoch;
      try {
        const res = await window.pywebview.api.save_augment_preferences(preferences);
        if (mine === epoch && res.ok) preferences = res.preferences || {};
      } catch (error) { /* 本机保存失败不打断操作 */ }
    }, 400);
  }

  function setList(ids) {
    if (ids.length) preferences[String(current)] = ids;
    else delete preferences[String(current)];
    renderList();
    scheduleSave();
  }

  function renderNote() {
    if (!noteEl) return;
    if (!current) {
      noteEl.textContent = "先选一个英雄，再按优先级添加你想要的强化；进游戏后这里会自动跟着你当前对局使用的英雄。";
      return;
    }
    const count = list().length;
    noteEl.textContent = count
      ? `已为「${championName(current)}」设置 ${count} 个优选强化，顺序即优先级；进入强化选择时照此顺序挑。`
      : `「${championName(current)}」还没有优选强化，可在右侧搜索添加。`;
  }

  function renderChampions() {
    if (!selectEl) return;
    const champions = [...championCatalog()]
      .filter(c => Number(c.id) > 0)
      .sort((a, b) => String(a.name || "").localeCompare(String(b.name || ""), "zh"));
    selectEl.innerHTML = '<option value="0">请选择英雄</option>' + champions.map(c =>
      `<option value="${Number(c.id)}">${escapeHtml(c.name || ("英雄 #" + c.id))}</option>`).join("");
    selectEl.value = String(current || 0);
  }

  function renderList() {
    if (!listEl) return;
    const ids = list();
    if (!ids.length) {
      listEl.innerHTML = '<p class="prefs-empty">还没有设置优选强化。</p>';
      renderNote();
      return;
    }
    listEl.innerHTML = ids.map((id, index) => {
      const info = byId.get(String(id)) || { id, name: `海克斯 #${id}`, rarity: "", icon: "" };
      const name = escapeHtml(info.name);
      const icon = /^(https:\/\/|data:image\/png;base64,)/.test(info.icon || "") ? info.icon : "";
      return `<span class="prefs-chip ${escapeHtml(info.rarity || "unknown")}">
        <b>${index + 1}</b>
        ${icon ? `<img src="${escapeHtml(icon)}" alt="" loading="lazy" onerror="this.hidden=true">` : ""}
        <span class="prefs-name" title="${escapeHtml(`${rarityLabel(info)} · ${info.name} · ID ${id}`)}">${name}</span>
        <button type="button" class="prefs-up" data-up="${id}" title="提高优先级" aria-label="提高 ${name} 的优先级" ${index === 0 ? "disabled" : ""}>↑</button>
        <button type="button" class="prefs-remove" data-remove="${id}" title="移除" aria-label="移除 ${name}">×</button>
      </span>`;
    }).join("");
    renderNote();
  }

  function renderSuggest() {
    if (!suggestEl) return;
    const query = (searchEl?.value || "").trim().toLocaleLowerCase();
    if (!query) { suggestEl.hidden = true; suggestEl.innerHTML = ""; return; }
    const owned = new Set(list().map(String));
    const rows = catalog.filter(a => !owned.has(String(a.id)) &&
      (a.name.toLocaleLowerCase().includes(query) || String(a.id) === query)).slice(0, 10);
    if (!rows.length) {
      suggestEl.hidden = false;
      suggestEl.innerHTML = '<p class="prefs-empty">没有匹配的海克斯。</p>';
      return;
    }
    suggestEl.hidden = false;
    suggestEl.innerHTML = rows.map(a => {
      const icon = /^(https:\/\/|data:image\/png;base64,)/.test(a.icon || "") ? a.icon : "";
      return `<button type="button" class="prefs-option ${escapeHtml(a.rarity || "unknown")}" data-add="${a.id}">
        ${icon ? `<img src="${escapeHtml(icon)}" alt="" loading="lazy" onerror="this.hidden=true">` : ""}
        <span>${escapeHtml(a.name)}</span><small>${escapeHtml(rarityLabel(a))}</small></button>`;
    }).join("");
  }

  function add(id) {
    const augment = Number(id);
    if (!augment) return;
    const ids = list();
    if (ids.includes(augment)) return;
    if (ids.length >= MAX) { toast(`每个英雄最多 ${MAX} 个优选强化`); return; }
    setList([...ids, augment]);
    if (searchEl) searchEl.value = "";
    renderSuggest();
  }

  function remove(id) {
    setList(list().filter(item => item !== Number(id)));
  }

  function moveUp(id) {
    const ids = list();
    const index = ids.indexOf(Number(id));
    if (index <= 0) return;
    const next = [...ids];
    [next[index - 1], next[index]] = [next[index], next[index - 1]];
    setList(next);
  }

  function selectChampion(id, fromGame) {
    const champion = Number(id) || 0;
    if (champion === current) { renderNote(); return; }
    current = champion;
    if (!fromGame) manual = true;
    if (selectEl) selectEl.value = String(champion);
    renderList();
    renderSuggest();
  }

  /* 当前对局里自己的英雄变化时调用；用户手动选过英雄就不再抢占。 */
  function followChampion(id) {
    const champion = Number(id) || 0;
    if (manual || !champion || champion === current) return;
    selectChampion(champion, true);
  }

  async function load() {
    // 先出本地清单，再补全整张强化表（表较大，不让它拖慢面板显示）。
    try {
      const prefRes = await window.pywebview.api.get_augment_preferences();
      if (prefRes?.ok) { preferences = prefRes.preferences || {}; renderList(); }
    } catch (error) { /* 读不到就当空清单 */ }
    try {
      const catalogRes = await window.pywebview.api.get_augment_catalog();
      if (catalogRes?.ok) {
        catalog = catalogRes.augments || [];
        byId = new Map(catalog.map(a => [String(a.id), a]));
        renderList();
        renderSuggest();
      }
    } catch (error) {
      if (noteEl) noteEl.textContent = "海克斯资料读取失败，重新进入「对局」页可重试。";
    }
  }

  function init() {
    root = document.getElementById("augmentPrefs");
    if (!root) return;
    selectEl = document.getElementById("prefsChampion");
    searchEl = document.getElementById("prefsSearch");
    listEl = document.getElementById("prefsList");
    suggestEl = document.getElementById("prefsSuggest");
    noteEl = document.getElementById("prefsNote");
    selectEl.addEventListener("change", () => selectChampion(selectEl.value));
    searchEl.addEventListener("input", renderSuggest);
    searchEl.addEventListener("focus", renderSuggest);
    listEl.addEventListener("click", (event) => {
      const up = event.target.closest(".prefs-up");
      if (up) { moveUp(up.dataset.up); return; }
      const removeButton = event.target.closest(".prefs-remove");
      if (removeButton) remove(removeButton.dataset.remove);
    });
    suggestEl.addEventListener("click", (event) => {
      const option = event.target.closest(".prefs-option");
      if (option) add(option.dataset.add);
    });
    document.addEventListener("click", (event) => {
      if (!suggestEl.hidden && !root.contains(event.target)) suggestEl.hidden = true;
    });
    renderChampions();
    renderNote();
    load();
  }

  /* 英雄表是异步加载的，加载完要刷新下拉框与「当前对局」英雄名。 */
  function refreshChampions() {
    if (!root) return;
    renderChampions();
    renderNote();
  }

  return { init, followChampion, refreshChampions };
})();
// 顶层 const 不会挂到 window 上，这里显式暴露给 app.js / current-game.js 做可选调用。
window.AugmentPrefs = AugmentPrefs;
