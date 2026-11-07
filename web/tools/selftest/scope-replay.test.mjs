import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {ScopeView} from '../../app/scope/view.js';
import {Trigger} from '../../app/scope/store.js';
import { buildData, buildDef, HOST_POLL } from '../../app/scope/protocol.js';

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

test('HSS and host replay use the file definition even with different page variables', async () => {
  globalThis.document = { getElementById:() => ({ value:'0' }) };
  const vars = [{addr:0x20000000,size:1,scalar:'u8'}, {addr:0x20000002,size:2,scalar:'i16'}];
  for (const flags of [0, HOST_POLL]){
    const p = rig();
    p.selected = [{...vars[0], scalar:'i8', name:'wrong type'}];
    const def = buildDef({ vars, flags, periodUs:10000 });
    const data = buildData({seq:1,n:1,payload:Uint8Array.of(255,0,252)});
    const buf = new Uint8Array([...def,...data]);
    await p.replayFile({arrayBuffer:async () => buf.buffer});
    assert.match(p.state, /回放完成：1 个样本/);
    assert.equal(p.store.vars[0].name,'0x20000000');
    assert.deepEqual(p.store.channels.map(c => c.at(0)),[255,-1024]);
    await p.replayFile({arrayBuffer:async () => buf.slice(0,-1).buffer});
    assert.match(p.state, /回放失败/);
  }
});

test('automatic 10 ms polling disables hardware-only advice and controls until the path changes', async t => {
  const p = new ScopeView();
  const fields = new Map([
    ['sc-period',{value:'10000'}], ['sc-sampling-path',{value:'auto'}],
    ['sc-trig-ch',{options:[]}],
  ]);
  globalThis.document = { getElementById(id){
    if (!fields.has(id)) fields.set(id,{});
    return fields.get(id);
  } };
  t.after(() => { delete globalThis.document; });
  let hardwarePlans = 0;
  p._showHardwarePlan = () => { hardwarePlans++; };
  p.mockVars = () => [];
  p.updatePlan();
  assert.match(fields.get('sc-rate-advice').textContent,/WASM 主机轮询/);
  for (const id of ['sc-bench','sc-recc','sc-batch','sc-cdcoff']) assert.equal(fields.get(id).disabled,true);
  await p.applyRecPeriod();
  assert.equal(fields.get('sc-period').value,'10000');
  assert.equal(hardwarePlans,0);
  fields.get('sc-period').value = '9999';
  p.updatePlan();
  assert.equal(hardwarePlans,1);
  assert.equal(fields.get('sc-bench').disabled,false);
});
