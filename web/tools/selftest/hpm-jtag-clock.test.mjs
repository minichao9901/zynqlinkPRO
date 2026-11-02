import test from 'node:test';
import assert from 'node:assert/strict';
import { DapJtagTransport } from '../../app/flash/hpm/dap-transport.js';
import { WebUsbDapProbe } from '../../app/rtt/dap-webusb.js';

test('RISC-V reconnect restores the latest requested clock after a resetting DAP_Connect', async () => {
  const calls=[];
  let actual=0;
  const p={device:{opened:true},requestedClockHz:10000000,
    _ctrl:async(cmd)=>{calls.push(cmd);if(cmd===2){actual=50000000;return Uint8Array.of(2);}return Uint8Array.of(0);},
    setClock:async(hz)=>{calls.push(['clock',hz]);actual=hz;p.requestedClockHz=hz;}};
  const j=new DapJtagTransport(p);
  await j.connectJtag();assert.equal(actual,10000000);
  await p.setClock(5000000);await j.connectJtag();assert.equal(actual,5000000);
  assert.deepEqual(calls.slice(-3),[2,0x15,['clock',5000000]]);
});

test('new raw RISC-V connection uses 10MHz and rejected DAP clock is never recorded as applied', async () => {
  let actual;
  const p={device:{opened:true},_ctrl:async cmd=>Uint8Array.of(cmd===2?2:0),setClock:async hz=>{actual=hz;}};
  await new DapJtagTransport(p).connectJtag();assert.equal(actual,10000000);
  const real=Object.create(WebUsbDapProbe.prototype);
  real._ctrl=async()=>Uint8Array.of(0);await real.setClock(10000000);assert.equal(real.requestedClockHz,10000000);
  real._ctrl=async()=>Uint8Array.of(255);await assert.rejects(real.setClock(100000000),/拒绝/);
  assert.equal(real.requestedClockHz,10000000);
});
