import test from 'node:test';
import assert from 'node:assert/strict';
import {ScopeView} from '../../app/scope/view.js';
import {scopeRcText} from '../../app/scope/protocol.js';
test('each real start explicitly confirms the requested ARM or RISC-V architecture',async()=>{
  const calls=[];
  for(const riscv of [false,true])await ScopeView.prototype.confirmTargetArchitecture.call({usingMock:false,targetRiscv:riscv,signed:n=>n,
    hidXfer:async(cmd,data)=>{calls.push([cmd,...data]);return Uint8Array.of(3,cmd,0);}});
  assert.deepEqual(calls,[[0x31,10,0],[0x31,10,1]]);
});
test('negative or missing architecture ACK blocks configuration and is not called a width error',async()=>{
  for(const reply of [Uint8Array.of(3,0x31,249),Uint8Array.of(1)]){
    const calls=[];const v={usingMock:false,targetRiscv:true,signed:n=>(n<<24)>>24,hidXfer:async()=>reply};
    await assert.rejects(async()=>{await ScopeView.prototype.confirmTargetArchitecture.call(v);calls.push('CONFIG');},/目标类型确认/);
    assert.deepEqual(calls,[]);
  }
  assert.match(scopeRcText(-6,true),/目标类型/);
});
test('mock sampling does not send any architecture command',async()=>{
  await ScopeView.prototype.confirmTargetArchitecture.call({usingMock:true,hidXfer:()=>{throw Error('hardware');}});
});
