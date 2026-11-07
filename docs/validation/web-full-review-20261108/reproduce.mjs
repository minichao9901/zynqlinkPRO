// Offline review reproductions. Run from the repository root with Node.js.
import assert from 'node:assert/strict';
import { DebugSession } from '../../../web/app/dbg/session.js';
import { Rtt } from '../../../web/app/rtt/protocol.js';
import { OpenOcdProbe } from '../../../web/app/core/openocd-probe.js';
import { ScopeView } from '../../../web/app/scope/view.js';
import { Trigger } from '../../../web/app/scope/store.js';
import * as P from '../../../web/app/scope/protocol.js';

const debug = new DebugSession();
const readings = [0x01010001, 0x00010001, 0x01010001];
let clock;
debug.probe = { _readWord:async()=>readings.shift(), setClock:async hz=>{clock=hz;} };
const result = await debug.verifyClock();
assert.equal(clock, 1000000);
console.log('DHCSR S_RETIRE_ST variation reduces healthy requested clock to', clock, 'Hz', result.seen);

debug.caps = {numCode:2,rev:1};
debug.bps = [0x08000100];
debug._programFpb = async()=>{throw Error('injected USB failure');};
await assert.rejects(debug.bpClear(), /injected/);
assert.equal(debug.bps.length, 0);
console.log('Failed bpClear loses software breakpoint ownership before hardware confirmation');

const writes = [];
const ring = new Rtt({writeMem:async(address,bytes)=>{writes.push([address,[...bytes]]);}}, {addr:0x20000000});
ring.downBase = 0x20000030;
ring._entry = async()=>({size:16,rd:0,wr:0,pbuf:0x20000100});
const counts = await Promise.all([ring.writeDown(0,Uint8Array.of(65)),ring.writeDown(0,Uint8Array.of(66))]);
assert.deepEqual(counts,[1,1]);
assert.equal(writes.filter(([address])=>address===0x20000100).length,2);
console.log('Concurrent RTT sends both report success but overwrite the same ring byte', writes);

const probe = new OpenOcdProbe(null,{arch:'arm',clockKhz:10000});
assert.equal(typeof probe.recover, 'undefined');
assert.equal(typeof probe.reopen, 'undefined');
console.log('RTT legacy recover/reopen hooks are absent from OpenOcdProbe');

globalThis.document={getElementById:()=>({value:'10000'})};
const view=Object.create(ScopeView.prototype);
Object.assign(view,{selected:[{name:'x',addr:0x20000000,size:4,scalar:'u32'}],
  running:false,trigger:new Trigger(),periodUs:()=>10000,
  setBackend(){},updatePlan(){},setStatusText(text){this.state=text;},
  renderer:{setStore(){},clearMarks(){},fitAll(){},setTrigger(){}}});
const sourceVars=[{addr:0x20000000,size:4,scalar:'u32'},{addr:0x20000004,size:4,scalar:'u32'}];
const raw=new Uint8Array(P.PACKET*2);
raw.set(P.buildDef({vars:sourceVars,periodUs:10000}));
raw.set(P.buildData({seq:1,n:1,payload:new Uint8Array(8)}),P.PACKET);
await view.replayFile({name:'two-channels.jsp',arrayBuffer:async()=>raw.buffer});
assert.ok(view.defMismatch);
assert.equal(view.store.count,0);
assert.match(view.state,/回放完成/);
console.log('Hardware replay with a different selection silently ends as',view.state,'despite',view.defMismatch);
