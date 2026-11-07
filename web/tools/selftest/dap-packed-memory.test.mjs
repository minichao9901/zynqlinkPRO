import test from 'node:test';
import assert from 'node:assert/strict';
import {WebUsbDapProbe} from './fixtures/legacy-dap-webusb.js';

{
const name='legacy DAP', Probe=WebUsbDapProbe;
  test(name+' invalid transfer counts never reach USB',async()=>{
    const p=Object.create(Probe.prototype);p._ctrl=async()=>{throw Error('must not send');};
    await assert.rejects(p._transfer([]),/条数/);
    await assert.rejects(p._transfer(Array.from({length:256},()=>({ap:false,rnw:true,addr:0}))),/条数/);
  });
  test(name+' mixed transfers use one-byte reads and five-byte writes',async()=>{
    const p=Object.create(Probe.prototype);
    p.pkt=512;p._ctrl=async(cmd,payload)=>{
      assert.equal(cmd,5);
      assert.deepEqual([...payload],[0,3,2,5,0xf0,0xed,0,0xe0,15]);
      return Uint8Array.of(3,1,0x78,0x56,0x34,0x12,0xef,0xcd,0xab,0x90);
    };
    assert.deepEqual(await p._transfer([{ap:false,rnw:true,addr:0},
      {ap:true,rnw:false,addr:4,data:0xe000edf0},{ap:true,rnw:true,addr:12}]),[0x12345678,0x90abcdef]);
  });
  test(name+' incomplete batched replies are rejected instead of padded',async()=>{
    const p=Object.create(Probe.prototype);p.pkt=512;
    p._ctrl=async()=>Uint8Array.of(2,1,1,0,0,0);
    await assert.rejects(p._transfer([{ap:true,rnw:true,addr:12},{ap:true,rnw:true,addr:12}]),/响应不完整/);
  });
  test(name+' packed PPB read keeps two actual same-address samples and third on mismatch',async()=>{
    const p=Object.create(Probe.prototype);let flush=0,reads=0,transfers=0;
    Object.assign(p,{device:{nativeService:true},_withLock:fn=>fn(),_flushPosted:async()=>{flush++;},
      _transfer:async ops=>{
        transfers++;const values=[];
        for(let i=0;i<ops.length;i+=2){
          assert.deepEqual(ops[i],{ap:true,rnw:false,addr:4,data:0xe000edf0});
          assert.deepEqual(ops[i+1],{ap:true,rnw:true,addr:12});values.push(++reads);
        }
        return values;
      }});
    assert.deepEqual([...await p.readMemDiagnostic(0xe000edf0,4)],[3,0,0,0]);
    assert.equal(flush,1);assert.equal(reads,3);assert.equal(transfers,2);
  });
  test(name+' scalar control write sends the keyed value once and retains posted-write barrier',async()=>{
    const p=Object.create(Probe.prototype);let flush=0,sends=0;
    Object.assign(p,{device:{nativeService:true},_flushPosted:async()=>{flush++;},_transfer:async ops=>{
      sends++;assert.deepEqual(ops,[{ap:true,rnw:false,addr:4,data:0xe000edf0},{ap:true,rnw:false,addr:12,data:0xa05f0003}]);return [];
    }});
    await p._writeMemOnce(0xe000edf0,Uint8Array.of(3,0,0x5f,0xa0));
    assert.equal(flush,1);assert.equal(sends,1);assert.equal(p._posted,true);
  });
  test(name+' packed control failure is not retried or healed',async()=>{
    const p=Object.create(Probe.prototype);let sends=0;
    Object.assign(p,{device:{nativeService:true},_flushPosted:async()=>{},_transfer:async()=>{sends++;throw Error('SWD WAIT');}});
    await assert.rejects(p._writeMemOnce(0xe000edf0,Uint8Array.of(3,0,0x5f,0xa0)),/SWD WAIT/);
    assert.equal(sends,1);
  });
}
