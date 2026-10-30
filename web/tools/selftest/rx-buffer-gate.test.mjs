import test from 'node:test';
import assert from 'node:assert/strict';
import {RxBuffer} from '../../app/core/rxview.js';
test('automatic display suppression preserves bounded raw data for save/byte accounting',()=>{
  const rx=Object.create(RxBuffer.prototype);
  Object.assign(rx,{displayOff:true,suppressedBytes:0,_raw:[],_rawHead:0,rawBytes:0,maxRaw:4,maxChunks:8,truncated:false});
  rx.push(Uint8Array.of(1,2,3));rx.push(Uint8Array.of(4,5,6));
  assert.equal(rx.suppressedBytes,6);assert.equal(rx.bytes,3);assert.equal(rx.truncated,true);
  assert.deepEqual(Array.from(rx.raw[0].b),[4,5,6]);
});
