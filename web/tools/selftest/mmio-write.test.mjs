import test from 'node:test';
import assert from 'node:assert/strict';
import {WebUsbDapProbe} from '../../app/rtt/dap-webusb.js';

test('MMIO writes flush once without re-reading or replaying command/W1C registers',async()=>{
  const p=Object.create(WebUsbDapProbe.prototype),calls=[];
  p._writeMemOnce=async a=>calls.push(['write',a]);
  p._flushPosted=async()=>calls.push(['flush']);
  p._readMemLocked=async()=>{throw Error('must not read side-effect register');};
  for(const a of [0xe000edf4,0xe000ed0c,0xe000ed30,0x40021004])await p._writeMemLocked(a,new Uint8Array([1,0,0,0]));
  assert.equal(calls.filter(c=>c[0]==='write').length,4);
  assert.equal(calls.filter(c=>c[0]==='flush').length,4);
});

test('ordinary SRAM writes retain exact readback verification',async()=>{
  const p=Object.create(WebUsbDapProbe.prototype),calls=[];
  p._writeMemOnce=async()=>calls.push('write');
  p._readMemLocked=async()=>{calls.push('verify');return new Uint8Array([1,2,3,4]);};
  await p._writeMemLocked(0x20001000,new Uint8Array([1,2,3,4]));
  assert.deepEqual(calls,['write','verify']);
});
