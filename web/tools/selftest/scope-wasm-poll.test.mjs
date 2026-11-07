import test from 'node:test';
import assert from 'node:assert/strict';
import { WasmScopePoll } from '../../app/scope/wasm-poll.js';
import { decodeSamples, HOST_POLL, KIND, parseDef, parsePacket } from '../../app/scope/protocol.js';
import { SampleStore } from '../../app/scope/store.js';

const vars = [
  { name:'signed', addr:0x200003ff, size:1, scalar:'i8' },
  { name:'word', addr:0x20000400, size:4, scalar:'u32' },
  { name:'other', addr:0x20000420, size:2, scalar:'u16' },
];

test('Wasm polling reads only selected spans, retains bytes and reports a missed deadline', async t => {
  const requests = [];
  let closed = false;
  const probe = {
    async readMem(address, length){
      requests.push([address,length]);
      if (requests.length === 1) await new Promise(resolve=>setTimeout(resolve,36));
      return address === vars[0].addr ? Uint8Array.of(0xfe,0x78,0x56,0x34,0x12) : Uint8Array.of(0x34,0x12);
    },
    async disconnect(){ closed = true; },
  };
  const poll = new WasmScopePoll(probe, vars, 10000);
  t.after(()=>poll.close());
  const packets = [];
  await new Promise((resolve, reject) => poll.start(bytes=>{
    packets.push(parsePacket(bytes));
    if (packets.length===3)resolve();
  },reject));
  await poll.close();
  assert.equal(closed,true);
  assert.equal(packets[0].kind,KIND.DEF);
  assert.ok(parseDef(packets[0].payload).flags & HOST_POLL);
  assert.deepEqual(requests,[[0x200003ff,5],[0x20000420,2],[0x200003ff,5],[0x20000420,2]]);
  assert.deepEqual(decodeSamples(vars, packets[1].payload, 1),[-2,0x12345678,0x1234]);
  assert.ok(poll.skipped>=2);
  const store = new SampleStore(vars, 4, { exactTime:true });
  store.pushFrame([0,0,0],5);
  store.pushFrame([0,0,0],80000);
  store.pushFrame([0,0,0],95000);
  assert.equal(store.timeAt(1),80000);
});

test('closing a Wasm poll drains the in-flight read and publishes no late samples', async () => {
  let started, release, closed = false;
  const reading = new Promise(resolve => { started = resolve; });
  const response = new Promise(resolve => { release = resolve; });
  const probe = { async readMem(){ started(); return response; }, async disconnect(){ closed=true; } };
  const poll = new WasmScopePoll(probe, [vars[0]], 10000);
  const packets = [];
  poll.start(bytes=>packets.push(parsePacket(bytes)),error=>{ throw error; });
  await reading;
  const stopping = poll.close();
  assert.equal(closed,false);
  release(Uint8Array.of(42));
  await stopping;
  assert.equal(closed,true);
  assert.deepEqual(packets.map(p=>p.kind),[KIND.DEF]);
});
