import test from 'node:test';
import assert from 'node:assert/strict';
import {WebUsbDapProbe} from '../../../web/app/rtt/dap-webusb.js';

test('framing detection consumes a late Disconnect reply without resending DAP_Info',async()=>{
  const probe=Object.create(WebUsbDapProbe.prototype),sent=[];
  const replies=[[3,0],[0,2,0,16]];
  Object.assign(probe,{pkt:512,epIn:1,epOut:2,_framing:'short',device:{
    transferOut:async(ep,data)=>{sent.push([...data]);return {status:'ok'};},
    transferIn:async()=>{const data=Uint8Array.from(replies.shift());return {status:'ok',data:new DataView(data.buffer)};}
  }});
  assert.deepEqual([...await probe._ctrlRaw(0,Uint8Array.of(255))],[2,0,16]);
  assert.deepEqual(sent,[[0,255]]);assert.equal(probe.stale,1);
});
