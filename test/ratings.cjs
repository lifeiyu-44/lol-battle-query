const assert = require('node:assert/strict');
const R = require('../app/ui/ratings.js');
assert.deepEqual(R.tiers.map(t => t.label), ['恁🐎👍','BJ🐎','MJ🐎','SJ🐎','No🐎','XN🐎']);
for (const t of R.tiers) assert.equal(R.grade(t.minimum).label, t.label);
const g = {kills: 10, deaths: 5, assists: 20, durationSec: 1200, win: true};
assert.equal(R.rate(g).score, 95); // 60 KDA + 15 combat frequency + 20 win
assert.equal(R.rate(g).label, '恁🐎👍');
assert.equal(R.rate({...g,win:false}).score,75);
assert.equal(R.rate({...g,deaths:0}).score,95);
assert.equal(R.rate({...g,assists:100}).score,100);
assert.equal(R.rate({...g,kills:0,assists:0,win:false}).score,0);
assert.equal(R.rate({...g,remake:true}).score,null);
assert.equal(R.rate({...g,durationSec:0}).score,null);
assert.equal(R.rate({...g,kills:'invalid'}).score,null);
assert.equal(R.average([g,{...g,win:false},{...g,remake:true}]).score,85);
assert.equal(R.average([]).score,null);
console.log('Rating passed: exact tiers, boundaries, formula, zero deaths, remakes, invalid data, and filtered averages.');
