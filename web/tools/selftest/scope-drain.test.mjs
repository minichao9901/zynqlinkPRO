import test from 'node:test';
import assert from 'node:assert/strict';
import {VendorEpTransport} from '../../app/scope/transport.js';
import {ScopeView} from '../../app/scope/view.js';
const packet=n=>({status:'ok',data:new DataView(Uint8Array.of(n).buffer)});

test('producer-stopped drain delivers in-flight and queued tail bytes before retiring the generation',async()=>{
  let first,reads=0;
  const device={nativeService:true,transferIn(){reads++;return reads===1 ? new Promise(r=>first=r) : Promise.resolve(reads===2?packet(2):{status:'ok',data:new DataView(new ArrayBuffer(0))});}};
  const t=new VendorEpTransport(device),received=[];
  await t.start(b=>received.push(...b));
  const drained=t.drain(100);first(packet(1));await drained;
  assert.deepEqual(received,[1,2]);assert.equal(reads,3);assert.equal(t._nativeInFlight,0);
  await t.stop();
});

test('stop cancels startup immediately but accepts this capture tail only until confirmed drain',async()=>{
  const p=Object.create(ScopeView.prototype);let finish;
  Object.assign(p,{_captureGen:7,_capturing:true,transport:{epAddr:0x87},probeManager:{cancel(){}},syncButtons(){},
    _stopOnce:()=>new Promise(r=>finish=r)});
  const stopped=p.stop();
  assert.equal(p._captureAlive(7),false);assert.equal(p._dataAlive(7),true);
  finish();await stopped;assert.equal(p._dataAlive(7),false);assert.equal(p._capturing,false);
});

test('a drain deadline is a failure, never a zero-loss confirmation',async()=>{
  let finish;
  const t=new VendorEpTransport({nativeService:true,transferIn:()=>new Promise(r=>finish=r)});
  const received=[];await t.start(b=>received.push(...b));
  await assert.rejects(t.drain(5),/无法确认/);
  finish(packet(9));await t.stop();assert.deepEqual(received,[]);
});

test('an empty completion cannot hide data in other already submitted reads',async()=>{
  const pending=[];let reads=0;
  const device={transferIn(){reads++;return reads<=3 ? new Promise(r=>pending.push(r)) : Promise.resolve({status:'ok',data:new DataView(new ArrayBuffer(0))});}};
  const t=new VendorEpTransport(device,{inFlight:3,chunkBytes:512}),received=[];
  await t.start(b=>received.push(...b));const drained=t.drain(100);
  pending[0](packet(1));pending[1]({status:'ok',data:new DataView(new ArrayBuffer(0))});pending[2](packet(2));
  await drained;assert.deepEqual(received,[1,2]);assert.equal(reads,4);await t.stop();
});
