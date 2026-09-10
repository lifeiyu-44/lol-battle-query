const assert = require('node:assert/strict');
const R = require('../app/ui/ratings.js');
assert.deepEqual(R.tiers.map(t => t.label), ['💣Dick🐎','BigDick🐎','MiddleDick🐎','SmallDick🐎','小男娘🐎']);
assert.equal(R.grade(44.9).label, '小男娘🐎');
assert.equal(R.grade(30).label, '小男娘🐎');
for (const t of R.tiers) assert.equal(R.grade(t.minimum).label, t.label);
const g = {kills: 10, deaths: 5, assists: 20, durationSec: 1200, win: true};
// 没有伤害数据：其余三项（25 + 11.25 + 20 = 56.25）按满分 60 折算成百分制
assert.equal(R.rate(g).score, 93.8);
assert.equal(R.rate(g).label, '💣Dick🐎');
// 伤害占比是第一要素：队伍占比 30% 拿满 40 分
assert.equal(R.rate({...g, damageShare: 30}).score, 96.3);
assert.equal(R.rate({...g, damageShare: 15}).score, 76.3);
assert.equal(R.rate({...g, damageEvaluation: {status: 'ok', teamShare: 30}}).score, 96.3);
assert.equal(R.rate({...g, damageEvaluation: {status: 'unsupported'}}).score, 93.8);
assert.equal(R.rate({...g, damageEvaluation: {status: 'ok', teamShare: null}}).score, 93.8);
assert.equal(R.rate({...g, damageEvaluation: {status: 'ok', teamShare: '30'}}).score, 93.8); // 字符串不当作数据
assert.equal(R.rate({...g, win: false, damageShare: 30}).score, 76.3);
assert.equal(R.rate({...g, deaths: 0, damageShare: 30}).score, 96.3);
assert.equal(R.rate({...g, assists: 100, damageShare: 30}).score, 100);
assert.equal(R.rate({...g, kills: 0, assists: 0, win: false, damageShare: 0}).score, 0);
assert.equal(R.rate({...g, remake: true}).score, null);
assert.equal(R.rate({...g, durationSec: 0}).score, null);
assert.equal(R.rate({...g, kills: 'invalid'}).score, null);
// 十人伤害齐全才算占比，缺一人就整体退回其余项
assert.deepEqual(R.teamShares([{participantId:1,teamId:100,damage:300},{participantId:2,teamId:100,damage:100}]), {1: 75, 2: 25});
assert.equal(R.teamShares([{participantId:1,teamId:100,damage:300},{participantId:2,teamId:100}]), null);
assert.equal(R.teamShares([]), null);
assert.equal(R.average([g,{...g,win:false},{...g,remake:true}]).score,77.1);
assert.equal(R.average([]).score,null);
console.log('Rating passed: exact tiers, damage-share-first weighting, fallbacks, missing data, and filtered averages.');
