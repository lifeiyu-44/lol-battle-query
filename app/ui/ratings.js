/* A transparent entertainment score, not an official LoL rating. */
"use strict";
const MatchRating = (() => {
  const tiers = [
    {minimum: 90, label: "💣Dick🐎", level: 0},
    {minimum: 75, label: "BigDick🐎", level: 1},
    {minimum: 60, label: "MiddleDick🐎", level: 2},
    {minimum: 45, label: "SmallDick🐎", level: 3},
    {minimum: 0, label: "小男娘🐎", level: 4},
  ];
  // 伤害占比是第一要素：占 40 分，其余三项共 60 分。
  const weights = {damage: 40, kda: 25, combat: 15, win: 20};
  const fullShare = 30;      // 队伍对英雄伤害占比达到 30%（5 人均分 20%）即满分
  const fullKda = 6;         // (击杀+助攻)/max(死亡,1) 达到 6 即满分
  const fullFrequency = 2;   // 每分钟击杀+助攻达到 2 即满分
  const baseMax = weights.kda + weights.combat + weights.win;
  const formula = "伤害占比得分（最高 40：队伍对英雄伤害占比达 30% 满分）＋KDA 得分（最高 25：KDA 达 6 满分）" +
    "＋每分钟参战得分（最高 15：达 2 满分）＋胜利 20 分；KDA=(击杀+助攻)/max(死亡,1)。" +
    "伤害数据不可用的对局（重开、资料不足或不适用该模式的场次）按其余三项折算成百分制，不把缺失当作零。";

  function grade(score) { return tiers.find(t => score >= t.minimum) || tiers[tiers.length - 1]; }

  /* 只接受真正的数字：null / undefined / 字符串都不算数据。 */
  function finite(value) {
    return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
  }

  /* 单局的队伍伤害占比：优先后端评价结果，其次调用方算好传入的 damageShare。 */
  function shareOf(g) {
    if (g?.damageEvaluation?.status === 'ok') {
      const share = finite(g.damageEvaluation.teamShare);
      if (share !== null) return share;
    }
    return finite(g?.damageShare);
  }

  /* 十人数据里算每人的队伍伤害占比；任何人缺伤害数据就整体返回 null，不猜。 */
  function teamShares(players) {
    if (!Array.isArray(players) || !players.length) return null;
    const totals = {};
    for (const p of players) {
      const damage = finite(p?.damage);
      if (damage === null) return null;
      totals[p.teamId] = (totals[p.teamId] || 0) + damage;
    }
    const shares = {};
    players.forEach(p => {
      shares[p.participantId] = totals[p.teamId] > 0 ? p.damage * 100 / totals[p.teamId] : null;
    });
    return shares;
  }

  function rate(g) {
    if (g.remake) return {score: null, label: "重开不评分", level: -1, reason: "重开不计入综合评分"};
    const k = Number(g.kills), d = Number(g.deaths), a = Number(g.assists), sec = Number(g.durationSec);
    if (![k, d, a, sec].every(Number.isFinite) || Math.min(k, d, a) < 0 || sec <= 0) {
      return {score: null, label: "暂不评分", level: -1, reason: "对局数据不足"};
    }
    const kda = (k + a) / Math.max(d, 1), frequency = (k + a) / (sec / 60);
    const kdaPoints = weights.kda * Math.min(kda / fullKda, 1);
    const combatPoints = weights.combat * Math.min(frequency / fullFrequency, 1);
    const winPoints = g.win ? weights.win : 0;
    const base = kdaPoints + combatPoints + winPoints;
    const share = shareOf(g);
    let score, damageText;
    if (share === null) {
      // 没有伤害数据时把其余三项折算成百分制，避免这些对局被系统性压低。
      score = base * 100 / baseMax;
      damageText = "伤害数据不可用：其余三项按满分折算";
    } else {
      const damagePoints = weights.damage * Math.min(share / fullShare, 1);
      score = base + damagePoints;
      damageText = `队伍伤害占比 ${share.toFixed(1)}%：${damagePoints.toFixed(1)} 分`;
    }
    score = Math.round(score * 10) / 10;
    return {score, ...grade(score), reason:
      `${damageText}；KDA ${kda.toFixed(2)}：${kdaPoints.toFixed(1)} 分；` +
      `每分钟参战 ${frequency.toFixed(2)}：${combatPoints.toFixed(1)} 分；胜负：${winPoints} 分。`};
  }

  function average(games) {
    const valid = games.map(rate).filter(r => r.score !== null);
    if (!valid.length) return {score: null, count: 0, label: "暂无评分", level: -1};
    const score = Math.round(valid.reduce((sum, r) => sum + r.score, 0) / valid.length * 10) / 10;
    return {score, count: valid.length, ...grade(score)};
  }

  function award(game, participantId = game.participantId) {
    if (game.remake || !Number.isFinite(game.durationSec) || game.durationSec <= 0) return null;
    const players = game.ratingParticipants;
    if (!Array.isArray(players) || players.length !== 10) return null;
    const ids = players.map(p => p.participantId);
    if (ids.some(id => id === null || id === undefined) || new Set(ids).size !== 10) return null;
    if (players.some(p => typeof p.win !== 'boolean' || ![p.kills,p.deaths,p.assists].every(n =>
      typeof n === 'number' && Number.isFinite(n) && n >= 0))) return null;
    const teams = [100,200].map(id => players.filter(p => p.teamId === id));
    if (teams.some(t => t.length !== 5 || t.some(p => p.win !== t[0].win)) || teams[0][0].win === teams[1][0].win) return null;
    const me = players.find(p => p.participantId === participantId);
    if (!me) return null;
    // 伤害数据齐全时一起参与评选；缺数据就退回其余三项（所有人同一标准）。
    const shares = teamShares(players);
    const scoreFor = p => rate({...p, durationSec: game.durationSec,
      damageShare: shares && shares[p.participantId] !== null ? shares[p.participantId] : undefined}).score;
    const team = players.filter(p => p.teamId === me.teamId);
    const scores = team.map(scoreFor);
    const best = Math.max(...scores);
    if (scoreFor(me) !== best) return null;
    return {label: me.win ? 'MVP' : 'SVP', tied: scores.filter(score => score === best).length > 1,
      reason: '本工具估算：按现有娱乐评分（伤害占比优先）评选胜方 MVP、败方 SVP；同分并列，非官方称号。'};
  }
  return {tiers, formula, weights, fullShare, grade, rate, average, award, teamShares};
})();
if (typeof module !== "undefined") module.exports = MatchRating;
