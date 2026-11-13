import test from 'node:test';
import assert from 'node:assert/strict';
import {RttCdcView} from '../../app/hid/view.js';

test('RTT STOP waits for the probe to drain and re-enables the start controls',async t=>{
  globalThis.document={getElementById:()=>null};
  globalThis.window={};
  t.after(()=>{delete globalThis.document;delete globalThis.window;});
  const view=Object.create(RttCdcView.prototype);
  const replies=[{rc:-7,status:{running:true}}, {rc:0,status:{running:false}}];
  const rendered=[];
  Object.assign(view,{
    dev:{stop:async()=>replies.shift()},
    _bridgeRequested:true,
    render(){rendered.push(!!this._stopPromise);},
  });
  await view.stop();
  assert.equal(replies.length,0);
  assert.equal(view._bridgeRequested,false);
  assert.equal(view.last.running,false);
  assert.equal(rendered.at(-1),false);
});
