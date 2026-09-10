const assert=require('node:assert/strict');
const {summarize,verdict}=require('../app/ui/hero-analysis.js');
const g={championId:266,kills:6,deaths:3,assists:6,durationSec:1200,win:true};
const s=summarize([{...g,gameId:1},{...g,gameId:1},{...g,gameId:2,win:false},
  {...g,gameId:3,remake:true},{...g,gameId:4,kills:null},{...g,gameId:5,championId:103}],266);
assert.equal(s.matches.length,4); assert.equal(s.count,2);assert.equal(s.excluded,2);
assert.equal(s.winRate,50);assert.equal(s.kda,4);assert.equal(s.rating.score,56);
assert.match(verdict(s),/只有 2 场/);
assert.equal(summarize([],266).rating.score,null);
const poor=summarize(Array.from({length:10},(_,i)=>({...g,gameId:i,win:false,kills:0,assists:1,deaths:10})),266);
assert.match(verdict(poor),/给对面发福利/);
console.log('Hero statistics passed: exact champion, duplicate/remake/missing exclusions, cumulative KDA, average score, sample-aware verdict.');
