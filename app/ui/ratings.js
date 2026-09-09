/* A transparent entertainment score, not an official LoL rating. */
"use strict";
const MatchRating = (() => {
  const tiers = [
    {minimum: 90, label: "恁🐎👍", level: 0},
    {minimum: 75, label: "BJ🐎", level: 1},
    {minimum: 60, label: "MJ🐎", level: 2},
    {minimum: 45, label: "SJ🐎", level: 3},
    {minimum: 30, label: "No🐎", level: 4},
    {minimum: 0, label: "XN🐎", level: 5},
  ];
  const formula = "KDA 得分（最高 60）＋每分钟参战得分（最高 20）＋胜利 20 分。KDA=(击杀+助攻)/max(死亡,1)，KDA 达 6 得满分；每分钟击杀+助攻达 2 得满分。";
  function grade(score) { return tiers.find(t => score >= t.minimum) || tiers[tiers.length - 1]; }
  function rate(g) {
    if (g.remake) return {score: null, label: "重开不评分", level: -1, reason: "重开不计入综合评分"};
    const k = Number(g.kills), d = Number(g.deaths), a = Number(g.assists), sec = Number(g.durationSec);
    if (![k, d, a, sec].every(Number.isFinite) || Math.min(k, d, a) < 0 || sec <= 0) {
      return {score: null, label: "暂不评分", level: -1, reason: "对局数据不足"};
    }
    const kda = (k + a) / Math.max(d, 1), frequency = (k + a) / (sec / 60);
    const kdaPoints = 60 * Math.min(kda / 6, 1);
    const combatPoints = 20 * Math.min(frequency / 2, 1);
    const winPoints = g.win ? 20 : 0;
    const score = Math.round((kdaPoints + combatPoints + winPoints) * 10) / 10;
    return {score, ...grade(score), reason: `KDA ${kda.toFixed(2)}：${kdaPoints.toFixed(1)} 分；每分钟参战 ${frequency.toFixed(2)}：${combatPoints.toFixed(1)} 分；胜负：${winPoints} 分。`};
  }
  function average(games) {
    const valid = games.map(rate).filter(r => r.score !== null);
    if (!valid.length) return {score: null, count: 0, label: "暂无评分", level: -1};
    const score = Math.round(valid.reduce((sum, r) => sum + r.score, 0) / valid.length * 10) / 10;
    return {score, count: valid.length, ...grade(score)};
  }
  return {tiers, formula, grade, rate, average};
})();
if (typeof module !== "undefined") module.exports = MatchRating;
