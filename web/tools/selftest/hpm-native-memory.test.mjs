import test from 'node:test';
import assert from 'node:assert/strict';
import {HpmNativeMemory} from './fixtures/native-memory.js';

function fixture(fail){
  const calls=[],ram=new Uint8Array(4096);let address=0,mode=0x0e;
  const probe={pkt:512,requestedClockHz:10000000,device:{nativeService:true,dapSynchronized:true},
    setClock:async hz=>calls.push(['clock',hz]),_ctrl:async(code,payload)=>{
      calls.push([code,payload.slice()]);
      if(code===0x8b){mode=payload[0];return Uint8Array.of(0,payload[0]);}
      if(code===0x80){const bytes=new Uint8Array(11);const v=new DataView(bytes.buffer);v.setUint32(3,mode===1?120000000:20000000,true);v.setUint32(7,mode===1?0x2a011:0x20011,true);return bytes;}
      if(code===5){address=new DataView(payload.buffer,payload.byteOffset).getUint32(13,true);return Uint8Array.of(3,1);}
      if(code===6){
        const n=payload[1]+payload[2]*256;
        if(fail==='partial')return Uint8Array.of(n-1,0,1);
        if(fail)throw Error(fail);
        if(payload[3]===13){ram.set(payload.subarray(4),address);return Uint8Array.of(n&255,n>>>8,1);}
        return Uint8Array.of(n&255,n>>>8,1,...ram.subarray(address,address+n*4));
      }
      throw Error('unexpected command');
    }};
  const dm={_exclusive:async(key,fn)=>await fn(),dap:{resetTapAndLoadIR:async ir=>calls.push(['ir',ir])},
    readMem:async()=>{calls.push(['fallback']);return Uint8Array.of(1);},writeMem:async()=>calls.push(['fallback'])};
  const port={id:'hpm6800evk',memory:{workArea:{addr:0,size:4096}}};
  return {calls,ram,probe,dm,port,native:new HpmNativeMemory(dm,probe,port)};
}

test('native RAM block writes and exact readback restore raw mode and invalidate SBA cache',async()=>{
  const f=fixture(),data=Uint8Array.from({length:1024},(_,i)=>i&255);f.native.install();
  await f.dm.writeMem(256,data);assert.deepEqual(await f.dm.readMem(256,1024),data);
  assert.equal(f.native.stats.blocks,6);assert.equal(f.native.stats.writeBytes,1024);
  assert.equal(f.dm._sbcsCfg,null);assert.equal(f.dm._holdAddr,null);
  assert.ok(f.calls.some(c=>c[0]===0x8b&&c[1][0]===0x0e));
  assert.ok(f.calls.some(c=>c[0]==='ir'&&c[1]===0x11));
  assert.equal(f.native.stats.nativeClock.tckHz,10000000);
});

test('other probes, boards and clock profiles do not enable the optimized path',()=>{
  const f=fixture();assert.ok(HpmNativeMemory.eligible(f.probe,f.port));
  assert.ok(!HpmNativeMemory.eligible({...f.probe,device:{}},f.port));
  assert.ok(!HpmNativeMemory.eligible(f.probe,{...f.port,id:'hpm5300evk'}));
  assert.ok(!HpmNativeMemory.eligible({...f.probe,requestedClockHz:50000000},f.port));
});

test('small, unaligned and out-of-work-area accesses retain original validation and transport',async()=>{
  const f=fixture();f.native.install();
  await f.dm.readMem(0,4);await f.dm.readMem(1,64);await f.dm.readMem(0x80000000,64);
  assert.equal(f.calls.length,3);assert.ok(f.calls.every(c=>c[0]==='fallback'));
});

test('wire timeout never replays or falls back, and quarantines later native operations',async()=>{
  const f=fixture('USB超时');f.native.install();
  await assert.rejects(f.dm.writeMem(0,new Uint8Array(64)),/超时/);
  const count=f.calls.length;assert.ok(f.dm._wireFault);
  await assert.rejects(f.dm.writeMem(0,new Uint8Array(64)),/超时/);
  assert.equal(f.calls.length,count);assert.equal(f.calls.filter(c=>c[0]===6).length,1);
  assert.ok(!f.calls.some(c=>c[0]==='fallback'||c[0]==='ir'));
});

test('partial block completion fails without replay or a slower replacement write',async()=>{
  const f=fixture('partial');f.native.install();
  await assert.rejects(f.dm.writeMem(0,new Uint8Array(64)),/不完整/);
  assert.equal(f.calls.filter(c=>c[0]===6).length,1);
  assert.ok(!f.calls.some(c=>c[0]==='fallback'));
});
