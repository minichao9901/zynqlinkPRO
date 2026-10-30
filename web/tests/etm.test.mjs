import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {TracePackets} from '../app/etm/protocol.js';
import {decodeTrace} from '../app/etm/decode.js';
import {readRecord} from '../app/etm/record.js';
import {EtmTarget,REG} from '../app/etm/target.js';
import {buildOutputs,parseUvprojx} from '../app/gen/model.js';
import {EP_SCOPE} from '../app/scope/transport.js';
import {EtmTransport} from '../app/etm/transport.js';
import {elfImages} from '../app/etm/decode.js';
const record=JSON.parse(fs.readFileSync(new URL('../samples/cm3-orbtrace.zetm',import.meta.url)));
function packet(seq,records=[],flags=3){const b=new Uint8Array(32+records.length*2),v=new DataView(b.buffer);for(const [o,n]of [[0,0x3154455a],[4,seq],[8,flags|(60000<<16)],[12,records.length],[20,120000000],[24,12],[28,1]])v.setUint32(o,n>>>0,true);records.forEach(([id,data],i)=>{b[32+2*i]=data;b[33+2*i]=id;});return b;}
test('ZET1 split reads, source demux, sequence gaps, end/trailer, actual clocks',()=>{
  const p=new TracePackets(),first=packet(0,[[2,0x80],[1,0x55],[2,0x08]]),last=packet(1,[],10);
  for(let i=0;i<first.length;i++)p.feed(first.subarray(i,i+1));p.feed(last);
  assert.deepEqual([...p.stream(2)],[0x80,8]);assert.equal(p.quality().tckKhz,60000);assert.equal(p.quality().fclk,120000000);assert.equal(p.loss,false);assert.equal(p.ended,true);
  const gap=new TracePackets();gap.feed(packet(2));assert.equal(gap.loss,true);
  const malformed=packet(0);new DataView(malformed.buffer).setUint32(12,241,true);assert.throws(()=>new TracePackets().feed(malformed),/越界/);
  const trailing=new Uint8Array(last.length+1);trailing.set(last);assert.throws(()=>new TracePackets().feed(trailing),/残留/);
});
test('native read-ahead retires every request after END without a USB device reset',async()=>{
  let issued=0,finished=0,active=0,peak=0;
  const payloads=[packet(0,[[2,0xa5]]),packet(1,[],10)];
  const device={transferIn(ep,n){assert.equal(ep,2);assert.equal(n,8192);const bytes=payloads[issued++]||new Uint8Array(0);active++;peak=Math.max(peak,active);return Promise.resolve().then(()=>{active--;finished++;return {status:'ok',data:new DataView(bytes.buffer)};});}};
  const t=new EtmTransport(device);t.device=device;t.parser=new TracePackets();t.inFlight=4;
  await t.receive();assert(peak>=4);assert.equal(issued,finished);assert.equal(t.parser.ended,true);assert.deepEqual([...t.parser.stream(2)],[0xa5]);
});
test('ELF instruction images use VMA while Flash verification uses LMA',()=>{
  const b=new Uint8Array(88),v=new DataView(b.buffer);b.set([0x7f,69,76,70,1,1]);v.setUint16(18,40,true);v.setUint32(28,52,true);v.setUint16(42,32,true);v.setUint16(44,1,true);
  for(const [offset,value]of [[52,1],[56,84],[60,0x20000000],[64,0x08001000],[68,4]])v.setUint32(offset,value,true);b.set([1,2,3,4],84);
  assert.equal(elfImages(b)[0].addr,0x20000000);assert.equal(elfImages(b,{physical:true})[0].addr,0x08001000);
});
test('record fingerprints and image/config bounds reject corrupted input',async()=>{
  const good=await readRecord(record);assert.equal(good.etm.length,1948);assert.equal(good.images[0].addr,256);
  await assert.rejects(readRecord({...record,etmSha:'0'.repeat(64)}),/SHA-256/);
  await assert.rejects(readRecord({...record,config:{...record.config,traceid:127}}),/source ID/);
  await assert.rejects(readRecord({...record,images:[{addr:-1,data:'AA=='}]}),/地址/);
});
test('real CM3 ETM decodes in WASM and follows every Thumb branch',async()=>{
  const input=await readRecord(record),result=await decodeTrace(input);
  assert.equal(result.ranges.length,22036);assert.equal(result.status.lastErrorCode,0);assert.equal(result.status.processed,1948);
  const visited=new Set();for(let i=0;i<result.ranges.length-1;i++){
    const a=result.ranges[i],b=result.ranges[i+1];visited.add(a.start);assert.equal(a.end,a.start+2);
    const next=a.start===0x106?(a.lastExecuted?0x102:0x108):a.start===0x108?0x100:a.start+2;assert.equal(b.start,next);
  }
  assert.deepEqual([...visited].sort((a,b)=>a-b),[0x100,0x102,0x104,0x106,0x108]);
  await assert.rejects(decodeTrace({...input,etm:Uint8Array.of(0)}),/没有恢复/);
});
test('F103ZE CoreSight program and restore preserves registers and locks',async()=>{
  const registers=new Map(Object.values(REG).map((a,i)=>[a,(i+4)*16]));
  registers.set(0xe000ed00,0x412fc231);registers.set(0xe0042000,0x414);registers.set(0xe0040000,8);
  registers.set(0xe00411e4,record.config.idr);registers.set(0xe00411e8,record.config.ccer);
  registers.set(0xe0041fb4,3);registers.set(0xe0040fb4,3);
  registers.set(REG.demcr,0); // Real F103ZE TPIU reads are gated by TRCENA.
  const original=new Map(registers);
  const probe={async flushWrites(){},async readMemDiagnostic(a){const b=new Uint8Array(4);const gated=a>=0xe0040000&&a<0xe0041000&&!(registers.get(REG.demcr)&0x01000000);new DataView(b.buffer).setUint32(0,gated?0:registers.get(a)||0,true);return b;},async writeMemDiagnostic(a,b){const n=new DataView(b.buffer,b.byteOffset).getUint32(0,true);registers.set(a,n);if(a===REG.etmcr)registers.set(0xe0041010,n&0x400?2:0);if(a===0xe0041fb0||a===0xe0040fb0)registers.set(a+4,n===0xc5acce55?1:3);}};
  const t=new EtmTarget(probe);const config=await t.prepare();assert.equal(config.traceid,2);assert.equal(registers.get(REG.cspsr),8);await t.start();assert.equal(registers.get(REG.etmcr)&0x400,0);await t.stop();await t.restore();
  for(const address of Object.values(REG))assert.equal(registers.get(address),original.get(address));
  assert.equal(registers.get(0xe0041fb4),3);assert.equal(registers.get(0xe0040fb4),3);assert.equal(t.saved,null);
});
test('project generator and J-Scope use this project CMSIS-DAP/HSS path',()=>{
  const config=parseUvprojx('<Device>STM32F103ZE</Device><TargetName>demo</TargetName>');assert.equal(config.device,'STM32F103ZE');
  const files=buildOutputs({projectName:'demo',checks:{pyocd:true,openocd:true,testBin:true}});
  assert(files.some(f=>f.name==='Makefile.openocd'&&f.text.includes('cmsis-dap')));assert(files.some(f=>f.name==='test_sram.bin'&&f.data.length===20480));assert.equal(EP_SCOPE,0x87);
});
