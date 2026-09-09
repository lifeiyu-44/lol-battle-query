const assert = require('node:assert/strict');
const {personal} = require('../app/ui/analysis.js');
const a = {id: 1007, name: '大力'}, b = {id: 1006, name: '利刃华尔兹'};
const game = (id, win, augment = a, championId = 266) => ({gameId: id, win, queueId: 2400,
  championId, championName: `英雄${championId}`, augmentNames: [augment]});
const data = [game(1, true), game(2, false), game(3, true, a, 103),
  {...game(4, true), queueId: 450}, {...game(5, true), remake: true}, game(1, true),
  {...game(6, true), augmentNames: [b, b]}, {...game(7, false), augmentNames: []}];
let report = personal(data);
assert.equal(report.total, 5);
assert.equal(report.recorded, 4);
assert.equal(report.rows[0].count, 3);
assert.equal(report.rows[0].wins, 2);
assert.equal(report.rows[0].performance.label, '样本不足');
assert.equal(report.rows[1].count, 1);
report = personal(data, 266);
assert.equal(report.rows[0].winRate, 50);
assert.equal(report.rows[0].champions[0].performance.withoutCount, 1);
assert.equal(personal([]).rows.length, 0);
const sufficient = Array.from({length: 20}, (_, i) => game(100+i, i<10, i<10?a:b));
report = personal(sufficient);
assert.equal(report.rows[0].performance.label, '表现偏高');
assert.equal(report.rows[0].performance.delta, 100);
assert.equal(report.rows[1].performance.label, '表现偏低');
console.log('Personal analysis passed: deduplication, remakes, mode/hero scope, missing records, sample thresholds and comparisons.');
