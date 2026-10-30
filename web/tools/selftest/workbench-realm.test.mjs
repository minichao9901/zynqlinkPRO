import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {createWorkbenchAutomation} from '../../app/automation/workbench.js';

test('ETM iframe results retain record IDs, nested quality, maps and binary data',async()=>{
  const child=vm.runInNewContext(`({Object,Map,Set,ArrayBuffer,
    __etm:{result:()=>({record:'capture-real',quality:{loss:false},
      entries:new Map([['source',2]]), ids:new Set([2]), raw:new Uint8Array([0,128,255]).buffer})}})`);
  const root={querySelectorAll:()=>[],textContent:''};
  class Anchor{click(){}}
  Object.assign(child,{document:{getElementById:()=>root},URL:{createObjectURL:()=>'',revokeObjectURL:()=>{}},HTMLAnchorElement:Anchor});
  const tools={etm:{onShow:async()=>{},frame:{contentWindow:child}},errors:[]};
  const automation=createWorkbenchAutomation(tools,{document:{getElementById:()=>null},CSS:{escape:s=>s}});
  const description=await automation.dispatch({page:'etm',op:'describe'});
  assert.deepEqual(description.methods.map(m=>m.name),['result']);
  await assert.rejects(automation.dispatch({page:'etm',op:'invoke',method:'toString'}),/未公开/);
  const result=await automation.dispatch({page:'etm',op:'invoke',method:'result'});
  assert.deepEqual(result.value,{record:'capture-real',quality:{loss:false},entries:[['source',2]],ids:[2],raw:{$bytes:[0,128,255]}});
});
