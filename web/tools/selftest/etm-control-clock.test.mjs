import test from 'node:test';
import assert from 'node:assert/strict';
import {EtmTarget} from '../../../etm-service/web/app/target.js';

function fixture(){
  const calls=[],device={vendorId:0x0d28,productId:0x0204};
  const Probe={supported:()=>true,authorized:async()=>[device],
    open:async(_device,{clockKhz})=>{calls.push(clockKhz);return {clockHz:clockKhz*1000,disconnect:async()=>{}};}};
  const t=new EtmTarget(()=>{},{host:{probeType:Probe}});
  t.inspect=async()=>({connected:true});
  return {t,calls};
}

test('ETM defaults to 10MHz and preserves it across local capture handoff',async()=>{
  const {t,calls}=fixture();await t.connect();await t.suspendUsb();await t.resumeUsb();
  assert.deepEqual(calls,[10000,10000]);
});

test('explicit 1MHz comparison survives capture handoff without defaulting to 10MHz',async()=>{
  const {t,calls}=fixture();t.setControlClockKhz(1000);await t.connect();
  await t.suspendUsb();await t.resumeUsb();assert.deepEqual(calls,[1000,1000]);
  assert.throws(()=>t.setControlClockKhz(10000),/断开/);
});

test('invalid SWD rates are rejected before opening any device',()=>{
  const {t,calls}=fixture();
  for(const rate of [0,249,50001,NaN,1000.1])assert.throws(()=>t.setControlClockKhz(rate));
  assert.equal(calls.length,0);
});
