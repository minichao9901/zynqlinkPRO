import test from 'node:test';
import assert from 'node:assert/strict';
import {DebugSession} from '../../../web/app/dbg/session.js';

function scenario(reads,pc){
  const writes=[];let cleaned=0;
  const session={probe:{_readWord:async()=>reads.shift()??0x20003,_dhcsr:async value=>writes.push(value>>>0)},
    readReg:async()=>pc,_log:()=>{},_clearStepResidue:async()=>{cleaned++;}};
  return {session,writes,cleaned:()=>cleaned};
}

test('Cortex-M step sets interrupt masking while halted, then releases C_HALT',async()=>{
  const s=scenario([0x1020003,0x2000f],0x08000592);
  assert.equal(await DebugSession.prototype._stepByDhcsr.call(s.session,0x08000590),true);
  assert.deepEqual(s.writes,[0xa05f000b,0xa05f000d]);
  assert.equal(s.cleaned(),1);
});

test('a retired self-branch is a completed instruction even when PC is unchanged',async()=>{
  const s=scenario([0x1020003,0x102000f],0x08000590);
  assert.equal(await DebugSession.prototype._stepByDhcsr.call(s.session,0x08000590),true);
  assert.equal(s.cleaned(),1);
});

test('a failed step write still clears interrupt-mask and step residue',async()=>{
  const s=scenario([0x20003],0x08000590);
  s.session.probe._dhcsr=async()=>{throw Error('transport lost');};
  assert.equal(await DebugSession.prototype._stepByDhcsr.call(s.session,0x08000590),false);
  assert.equal(s.cleaned(),1);
});
