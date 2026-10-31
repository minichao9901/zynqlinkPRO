import test from 'node:test';
import assert from 'node:assert/strict';
import {captureTransportFailed,captureTransportText} from '../../../etm-service/web/app/capture-quality.js';

test('known acquisition loss stays failed independently of decoder packet counts',()=>{
  assert.equal(captureTransportFailed({loss:true,synced:true,ended:true}),true);
  assert.match(captureTransportText({loss:true,synced:true,ended:true}),/有丢失/);
  assert.equal(captureTransportFailed({loss:false,synced:false,ended:true}),true);
  assert.equal(captureTransportFailed({loss:false,synced:true,ended:false}),true);
  assert.equal(captureTransportFailed({loss:false,synced:true,ended:true}),false);
});

test('absent or numeric placeholder flags cannot be shown as a clean acquisition',()=>{
  assert.equal(captureTransportText(null),'');
  assert.match(captureTransportText({}),/未知/);
  assert.doesNotMatch(captureTransportText({}),/无丢失/);
  assert.match(captureTransportText({loss:0,synced:1,ended:1}),/丢失状态未知/);
});
