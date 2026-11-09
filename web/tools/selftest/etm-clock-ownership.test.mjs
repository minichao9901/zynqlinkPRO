import test from 'node:test';
import assert from 'node:assert/strict';
import {EtmTarget} from '../../../etm-service/web/app/target.js';
import {identifyTarget,completeClocks,targetPort} from '../../../etm-service/web/app/clock.js';

function target(profile){
  const writes=[];
  const t={info:{profile,traceSupported:true,traceOptions:{branchBroadcast:true,returnStack:true,cycleCount:true},
    clocks:{coreHz:48e6,traceReady:true},config:{idr0:0x080006e1}},osLocked:null,
    inspect:async()=>t.info,halt:async()=>{},unlock:async()=>{},wait:async()=>{},stopFifo:async()=>{},log:()=>{},
    read:async a=>a===0xe0040000?8:a===0x5c015300?2:a===0xe0040010?2:1,
    set:async(a,mask,value)=>{writes.push({address:a,mask,value});},
    managed:async(a,value)=>{writes.push({address:a,value});},write:async(a,value)=>{writes.push({address:a,value});}};
  return {t,writes};
}

test('H743 readback explicitly identifies ETMv4 for the native builder',async()=>{
  const t={profile:'stm32h743',breakpoints:{},hseHz:25e6,
    set:async()=>{},readMany:async addresses=>addresses.map(()=>0),isHalted:async()=>true,
    read:async address=>address===0xe000ed00?0x411fc271:address===0x5c001000?0x20036450:0};
  const info=await EtmTarget.prototype.inspect.call(t);
  assert.equal(info.config.protocol,'ETMv4');
  assert.equal(t.config.protocol,'ETMv4');
});

test('F103 Web trace configuration leaves firmware PLL and AHB/APB dividers intact',async()=>{
  const {t,writes}=target('stm32f103ze');await EtmTarget.prototype.configure.call(t,{traceid:2});
  assert.ok(writes.some(w=>w.address===0xe0041200&&w.value===2));
  assert.ok(writes.some(w=>w.address===0x40011800));
  assert.equal(writes.filter(w=>[0x40021000,0x40021004].includes(w.address)).length,0);
});

test('H743 retains ETMv4 options and full funnel/ETF/TPIU route without programming clock registers',async()=>{
  const {t,writes}=target('stm32h743');
  await EtmTarget.prototype.configure.call(t,{traceid:2,branchBroadcast:true,returnStack:true,cycleCount:true});
  for(const address of [0xe0041010,0x5c013000,0x5c014020,0x5c015004])assert.ok(writes.some(w=>w.address===address),address.toString(16));
  assert.ok(writes.some(w=>w.address===0xe0041300 && w.value===0), 'ETMv4 OSLAR is at 0x300');
  assert.equal(writes.some(w=>w.address===0xe0041310), false, 'PDCR must never be used as OSLAR');
  assert.ok(writes.some(w=>w.address===0xe0041010&&w.value===0x1019));
  const clockOffsets=[0,0x10,0x18,0x28,0x2c,0x30,0x34];
  assert.equal(writes.filter(w=>clockOffsets.some(offset=>w.address===0x58024400+offset)).length,0);
});

test('H743 clock readback keeps CPU and TRACECLK independent and uses board HSE',()=>{
  const port=identifyTarget(1092600433,537093200);assert.equal(port.id,'stm32h743');
  const rcc=Object.freeze({cr:855851045,cfgr:27,domain:64,pllSource:26345554,pllConfig:33489673,pllDiv:117509727,pllFrac:0});
  const c=completeClocks(targetPort('stm32h743'),rcc,25e6);
  assert.equal(c.coreHz,60e6);assert.equal(c.physicalTraceHz,30e6);
});
