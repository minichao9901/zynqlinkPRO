import test from 'node:test';
import assert from 'node:assert/strict';
import {ScopeView} from '../../app/scope/view.js';

function rig(replies){
  const p=Object.create(ScopeView.prototype),calls=[];
  Object.assign(p,{hid:{},targetMode:'arm-jtag',_stopUnconfirmed:false,signed:n=>(n<<24)>>24,
    transport:{epAddr:0x87,drainCounted:async done=>{assert.equal(done(),true);calls.push('release USB');},
      quiesce:async()=>calls.push('quiesce'),stop:async()=>calls.push('retire')},
    hidXfer:async()=>{calls.push('STOP');return Uint8Array.of(3,0x32,replies.shift());},
    probeManager:{confirm:()=>calls.push('confirmed'),narrow:()=>{},fail:()=>calls.push('failed')}});
  return {p,calls};
}
test('Zynq STOP keeps the reader alive while busy and confirms before retiring reads',async()=>{
  const {p,calls}=rig([249,249,0]);await p._stopData();
  assert.deepEqual(calls,['STOP','STOP','STOP','release USB','retire','confirmed']);
  assert.equal(p._stopUnconfirmed,false);
});
test('a negative STOP reply cannot claim a successful hardware release',async()=>{
  const {p,calls}=rig([252]);await assert.rejects(p._stopData(),/无法确认采样已停止/);
  assert.equal(p._stopUnconfirmed,true);assert.ok(calls.includes('failed'));assert.ok(!calls.includes('confirmed'));
});
test('host overflow keeps the failure visible and confirms STOP only after quiet discard',async()=>{
  const {p,calls}=rig([249,0]);
  p.transport.hostOverflow=true;
  p.transport.lastError='本机HSS接收队列溢出';
  p.transport.drainOverflow=async()=>calls.push('overflow USB quiet');
  await p._stopData();
  assert.deepEqual(calls,['STOP','STOP','overflow USB quiet','retire','confirmed']);
  assert.equal(p.metricsError,'本机HSS接收队列溢出');
  assert.equal(p._stopUnconfirmed,false);
});
test('failed overflow drain retains the hardware recovery requirement',async()=>{
  const {p,calls}=rig([0]);
  p.transport.hostOverflow=true;
  p.transport.drainOverflow=async()=>{throw Error('USB still active');};
  await assert.rejects(p._stopData(),/USB still active/);
  assert.equal(p._stopUnconfirmed,true);
  assert.ok(!calls.includes('confirmed'));
});
