import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {ScopeView} from '../../app/scope/view.js';
import {Trigger} from '../../app/scope/store.js';

function rig(){
  const p=Object.create(ScopeView.prototype);
  const fields=[['i8',0x21,1],['f64',0x101,8],['u8',0x300,1],['u16',0x304,2],['u32',0x3ff,4],['f32',0x580,4],['i16',0x6ff,2],['i32',0x7fd,4]];
  Object.assign(p,{selected:fields.map(([scalar,offset,size])=>({name:'mixed.'+scalar,scalar,addr:0x20004000+offset,size})),
    captureRaw:true,raw:[],rawBytes:0,_capturing:false,running:false,trigger:new Trigger(),
    periodUs:()=>1000,setBackend(){},updatePlan(){},setStatusText(text){this.state=text;},
    renderer:{setStore(){},clearMarks(){},fitAll(){},setTrigger(){}}});
  return p;
}

test('real F103 mixed-scalar capture replays all values after stop without recording itself',async()=>{
  globalThis.document={getElementById:()=>({value:'60000'})};
  const bytes=await readFile(new URL('./fixtures/hss-mixed-scalars.jsp',import.meta.url));
  const p=rig();p._awaitDef=true;p.usbDrop=99;
  await p.replayFile({name:'mixed.jsp',arrayBuffer:async()=>bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength)});
  assert.equal(p.store.count,3231);assert.equal(p.receivedSamples,3231);
  assert.equal(p.lost,0);assert.equal(p.usbDrop,52719,'original firmware STAT defect remains visible');assert.equal(p.decodeErr,0);
  assert.equal(p.raw.length,0);assert.equal(p._replaying,false);assert.equal(p._capturing,false);
  const expected=[-77,123.456,211,48350,0x89abcdef,.25,-23456,-123456789];
  for(let i=0;i<p.store.count;i++)for(let k=0;k<8;k++)assert.equal(p.store.channels[k].at(i),expected[k]);
  const count=p.store.count;p.onChunk(bytes);assert.equal(p.store.count,count,'late live DATA stays blocked after replay');
});

test('file replay refuses to replace an active hardware capture',async()=>{
  const p=rig();p._capturing=true;let read=false;
  await p.replayFile({arrayBuffer:async()=>{read=true;}});
  assert.equal(read,false);assert.match(p.state,/先停止采样/);assert.equal(p._capturing,true);
});
