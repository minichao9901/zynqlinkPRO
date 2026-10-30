import test from 'node:test';
import assert from 'node:assert/strict';
import {RttView} from '../../app/rtt/view.js';
test('RTT Viewer keeps raw history while high-speed rendering is suppressed',()=>{
  const v=Object.create(RttView.prototype);
  Object.assign(v,{stats:{bytes:0},rec:{push(){}},records:[],recBytes:0,suppressed:true,suppBytes:0,_updateEmptyHint(){}});
  v._ingest(Uint8Array.of(1,2,3),new Date());
  assert.equal(v.recBytes,3);assert.equal(v.suppBytes,3);assert.equal(v.stats.bytes,3);
  assert.deepEqual(Array.from(v.records[0].b),[1,2,3]);
});
