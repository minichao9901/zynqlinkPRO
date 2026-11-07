import test from 'node:test';
import assert from 'node:assert/strict';
import {WebUsbDapProbe} from './fixtures/legacy-dap-webusb.js';
import {EtmTarget} from '../../../etm-service/web/app/target.js';

{
const name='legacy DAP', Probe=WebUsbDapProbe;
  test(name+' grouped reads preserve per-address double/third samples and reset TAR',async()=>{
    const p=Object.create(Probe.prototype);let calls=0,flush=0;
    Object.assign(p,{device:{nativeService:true},pkt:512,_withLock:f=>f(),_flushPosted:async()=>{flush++;},
      _transfer:async ops=>{
        calls++;if(calls===1){assert.equal(ops.length,8);assert.deepEqual(ops.filter(o=>!o.rnw).map(o=>o.data),[0xe000ed00,0xe000ed00,0x40021000,0x40021000]);return [10,10,20,21];}
        assert.deepEqual(ops,[{ap:true,rnw:false,addr:4,data:0x40021000},{ap:true,rnw:true,addr:12}]);return [22];
      }});
    assert.deepEqual(await p.readWordsDiagnostic([0xe000ed00,0x40021000]),[10,22]);assert.equal(calls,2);assert.equal(flush,1);
  });
  test(name+' grouped writes retain a completion barrier before every next TAR',async()=>{
    const p=Object.create(Probe.prototype);let calls=0;
    Object.assign(p,{device:{nativeService:true},pkt:64,_withLock:f=>f(),_flushPosted:async()=>{},_transfer:async ops=>{
      calls++;assert.ok(ops.length<=15);
      for(let i=0;i<ops.length;i+=3){assert.equal(ops[i].addr,4);assert.equal(ops[i+1].addr,12);assert.equal(ops[i+1].rnw,false);assert.deepEqual(ops[i+2],{ap:false,rnw:true,addr:12});}
      return Array(ops.length/3).fill(0);
    }});
    await p.writeWordsDiagnostic(Array.from({length:8},(_,i)=>({address:0xe0041000+4*i,value:i})));
    assert.equal(calls,2);assert.equal(p._posted,false);
  });
  test(name+' invalid grouped inputs cause no USB access and failures never replay writes',async()=>{
    const p=Object.create(Probe.prototype);let calls=0;
    Object.assign(p,{device:{nativeService:true},pkt:512,_withLock:f=>f(),_flushPosted:async()=>{},_transfer:async()=>{calls++;throw Error('WAIT');}});
    await assert.rejects(p.writeWordsDiagnostic([{address:1,value:1}]),/对齐/);assert.equal(calls,0);
    await assert.rejects(p.readWordsDiagnostic([0xe000ed00,3]),/对齐/);assert.equal(calls,0);
    await assert.rejects(p.writeWordsDiagnostic([{address:0xe0041000,value:3},{address:0xe0041004,value:4}]),/WAIT/);assert.equal(calls,1);
  });
}

function targetModel(){
  const t=Object.create(EtmTarget.prototype),memory=new Map([[0xe0041008,0xa5a51234],[0xe0041020,0x11223344]]);
  t.saved=new Map();t.probe={device:{nativeService:true},readWordsDiagnostic:async a=>a.map(x=>memory.get(x)),
    writeWordsDiagnostic:async entries=>{for(const e of entries)memory.set(e.address,e.value);}};
  return {t,memory};
}
test('batched masked configuration merges ownership and restores only owned bits',async()=>{
  const {t,memory}=targetModel();
  await t.setMany([{address:0xe0041008,mask:255,value:0xab},{address:0xe0041020,mask:0xff00,value:0x5600}]);
  assert.equal(memory.get(0xe0041008),0xa5a512ab);assert.equal(memory.get(0xe0041020),0x11225644);
  await t.setMany([{address:0xe0041008,mask:0xff00,value:0x7800}]);
  assert.deepEqual(t.saved.get(0xe0041008),{before:0x1234,mask:0xffff});
  memory.set(0xe0041008,0x55a578ab);
  await t.restoreMany([0xe0041008,0xe0041020]);
  assert.equal(memory.get(0xe0041008),0x55a51234);assert.equal(memory.get(0xe0041020),0x11223344);
});
test('batched configuration verifies every mask and retains restoration data on failure',async()=>{
  const {t,memory}=targetModel();t.probe.writeWordsDiagnostic=async entries=>{for(const e of entries)memory.set(e.address,e.value^1);};
  await assert.rejects(t.setMany([{address:0xe0041008,mask:255,value:9}]),/回读不匹配/);
  assert.deepEqual(t.saved.get(0xe0041008),{before:0x34,mask:255});
});
test('duplicate grouped configuration addresses are rejected before reading or writing',async()=>{
  const {t}=targetModel();let reads=0;t.probe.readWordsDiagnostic=async()=>{reads++;return [];};
  await assert.rejects(t.setMany([{address:0xe0041008,mask:255,value:1},{address:0xe0041008,mask:255,value:2}]),/重复地址/);assert.equal(reads,0);
});
