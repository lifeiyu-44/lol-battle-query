/* Personal statistics only: no inferred global strength or causal win-rate uplift. */
"use strict";
const AugmentAnalysis = (() => {
  function mayhem(g) {
    return [2400, 3270].includes(Number(g.queueId)) || g.mode === "海克斯大乱斗";
  }

  function performance(wins, count, baselineWins, baselineCount) {
    const withoutCount = baselineCount - count;
    const withoutWins = baselineWins - wins;
    const delta = count && withoutCount ? 100 * (wins / count - withoutWins / withoutCount) : null;
    if (count < 10 || withoutCount < 10) return {label: "样本不足", delta, withoutCount, withoutWins};
    return {label: delta >= 5 ? "表现偏高" : delta <= -5 ? "表现偏低" : "表现接近",
            delta, withoutCount, withoutWins};
  }

  function personal(games, championId = 0) {
    const seen = new Set();
    const completed = games.filter(g => {
      const id = String(g.gameId);
      if (!mayhem(g) || g.remake || seen.has(id)) return false;
      seen.add(id);
      return true;
    });
    const scope = completed.filter(g => !championId || Number(g.championId) === Number(championId));
    // Missing augment records cannot be treated as "played without this augment".
    const recorded = scope.filter(g => (g.augmentNames || []).some(a => Number(a.id) > 0));
    const champions = new Map(), augments = new Map();
    for (const g of recorded) {
      const cid = Number(g.championId), win = Number(Boolean(g.win));
      if (!champions.has(cid)) champions.set(cid, {id: cid, name: g.championName, count: 0, wins: 0});
      const champ = champions.get(cid);
      champ.count++; champ.wins += win;
      const inGame = new Set();
      for (const a of g.augmentNames || []) {
        const id = Number(a.id);
        if (!Number.isInteger(id) || id <= 0 || inGame.has(id)) continue;
        inGame.add(id);
        if (!augments.has(id)) augments.set(id, {id, augment: a, count: 0, wins: 0, champions: new Map()});
        const row = augments.get(id);
        row.count++; row.wins += win;
        if (!row.champions.has(cid)) row.champions.set(cid, {id: cid, name: g.championName, count: 0, wins: 0});
        const pair = row.champions.get(cid);
        pair.count++; pair.wins += win;
      }
    }
    const wins = recorded.filter(g => g.win).length;
    const rows = [...augments.values()].map(row => ({...row,
      winRate: 100 * row.wins / row.count,
      performance: performance(row.wins, row.count, wins, recorded.length),
      champions: [...row.champions.values()].map(pair => ({...pair,
        winRate: 100 * pair.wins / pair.count,
        performance: performance(pair.wins, pair.count, champions.get(pair.id).wins, champions.get(pair.id).count),
      })).sort((a, b) => b.count - a.count || b.winRate - a.winRate),
    })).sort((a, b) => b.count - a.count || b.winRate - a.winRate || a.id - b.id);
    return {total: scope.length, recorded: recorded.length, wins, rows};
  }
  return {personal, performance, mayhem};
})();
if (typeof module !== "undefined") module.exports = AugmentAnalysis;
