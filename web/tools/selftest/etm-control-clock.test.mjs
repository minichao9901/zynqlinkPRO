import test from 'node:test';
import assert from 'node:assert/strict';
import {EtmTarget} from '../../../etm-service/web/app/target.js';

function fixture(){
  const calls=[],device={vendorId:0x0d28,productId:0x0204};
  const devices=[device];
  const Probe={supported:()=>true,authorized:async()=>devices,
    open:async(_device,{clockKhz})=>{calls.push(clockKhz);return {clockHz:clockKhz*1000,disconnect:async()=>{}};}};
  const t=new EtmTarget(()=>{},{host:{probeType:Probe}});
  t.inspect=async()=>({connected:true});
  return {t,calls,device,devices};
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

test('handoff retains the probe and prevents capture if USB release fails', async()=>{
  const {t,calls}=fixture();
  await t.connect();
  const probe=t.probe;
  probe.disconnect=async()=>{throw Error('close failed');};
  await assert.rejects(t.suspendUsb(),/close failed/);
  assert.equal(t.probe,probe);
  assert.equal(t.transportFault,true);
  assert.deepEqual(calls,[10000]);
});

test('capture restore refuses a different probe and retains the chosen SWD clock',async()=>{
  const {t,calls,device,devices}=fixture();
  device.serialNumber='original';
  t.setControlClockKhz(250);
  await t.connect();
  await t.suspendUsb();
  devices[0]={...device,serialNumber:'another'};
  await assert.rejects(t.resumeUsb(),/原探针/);
  devices.push({...device});
  await t.resumeUsb();
  assert.deepEqual(calls,[250,250]);
});
