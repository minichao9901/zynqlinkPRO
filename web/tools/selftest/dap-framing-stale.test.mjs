import test from 'node:test';
import assert from 'node:assert/strict';
import {WebUsbDapProbe} from '../../../web/app/rtt/dap-webusb.js';
import {WebUsbDapProbe as EtmDapProbe} from '../../../etm-service/web/app/shared/rtt/dap-webusb.js';

for(const [name,Probe] of [['workbench',WebUsbDapProbe],['ETM standalone',EtmDapProbe]]){
test(name+' native control exchanges once and keeps response validation',async()=>{
  const probe=Object.create(Probe.prototype);let exchanges=0;
  Object.assign(probe,{_ready:true,pkt:512,epOut:2,epIn:1,device:{nativeService:true,
    exchangeDap:async req=>{exchanges++;assert.deepEqual([...req],[17,1]);const b=Uint8Array.of(17,0);return {data:new DataView(b.buffer)};},
    transferOut:async()=>{throw Error('duplicate write');},transferIn:async()=>{throw Error('duplicate read');}}});
  assert.deepEqual([...await probe._ctrl(17,Uint8Array.of(1))],[0]);assert.equal(exchanges,1);
});
test(name+' native stale response never replays the control write',async()=>{
  const probe=Object.create(Probe.prototype);let exchanges=0,reads=0;
  Object.assign(probe,{_ready:true,pkt:512,epOut:2,epIn:1,device:{nativeService:true,
    exchangeDap:async()=>{exchanges++;const b=Uint8Array.of(3,0);return {data:new DataView(b.buffer)};},
    transferOut:async()=>{throw Error('duplicate write');},transferIn:async()=>{reads++;const b=Uint8Array.of(17,0);return {data:new DataView(b.buffer)};}}});
  assert.deepEqual([...await probe._ctrl(17,Uint8Array.of(1))],[0]);assert.equal(exchanges,1);assert.equal(reads,1);
});
test(name+' trusts acknowledged native queue synchronization without speculative reads',async()=>{
  const probe=Object.create(Probe.prototype);
  probe.device={nativeService:true,dapSynchronized:true,
    transferOut:async()=>{throw Error('unexpected framing write');},
    transferIn:async()=>{throw Error('unexpected framing read');}};
  assert.equal(await probe._detectFraming(),'short');
});
test(name+' framing consumes a late Disconnect reply without resending DAP_Info',async()=>{
  const probe=Object.create(Probe.prototype),sent=[];
  const replies=[[3,0],[0,2,0,16]];
  Object.assign(probe,{pkt:512,epIn:1,epOut:2,_framing:'short',device:{
    transferOut:async(ep,data)=>{sent.push([...data]);return {status:'ok'};},
    transferIn:async()=>{const data=Uint8Array.from(replies.shift());return {status:'ok',data:new DataView(data.buffer)};}
  }});
  assert.deepEqual([...await probe._ctrlRaw(0,Uint8Array.of(255))],[2,0,16]);
  assert.deepEqual(sent,[[0,255]]);assert.equal(probe.stale,1);
});
}
