"use strict";
const DamageAnalysis = (() => {
  const LIMIT = 20;
  function recent(games) {
    const seen = new Set();
    const stamp = value => {
      const n = Number(value);
      return Number.isFinite(n) ? (n < 1e12 ? n * 1000 : n) : Date.parse(value) || 0;
    };
    return games.filter(g => {
      if (g.remake || g.damageEvaluation?.status === 'remake' || seen.has(String(g.gameId))) return false;
      seen.add(String(g.gameId)); return true;
    }).sort((a, b) => stamp(b.creation) - stamp(a.creation)).slice(0, LIMIT);
  }
  function summarize(games) {
    const scope = recent(games);
    const valid = scope.filter(g => g.damageEvaluation?.status === 'ok');
    const skipped = scope.filter(g => g.damageEvaluation?.status === 'unsupported').length;
    const unknown = scope.length - valid.length - skipped;
    const top = valid.filter(g => g.damageEvaluation.isTop).length;
    const percent = valid.length ? top * 100 / valid.length : null;
    return {total: scope.length, verified: valid.length, skipped, unknown, top, percent,
      verdict: unknown ? '统计未完成' : !valid.length ? '暂无可评价对局' :
        top * 100 >= valid.length * 30 ? '达标：伤害最高占比 ≥30%' : '未达标：伤害最高占比 <30%'};
  }
  return {recent, summarize, LIMIT};
})();
if (typeof module !== 'undefined') module.exports = DamageAnalysis;
