import test from 'node:test';
import assert from 'node:assert/strict';
import {HistoryView} from '../../../etm-service/web/app/history.js';

test('display timing refuses an incomplete default timeline',async()=>{
  await assert.rejects(HistoryView.prototype.waitForDisplay.call({recordRevision:1,revision:1,view:'instructions',timelineTask:Promise.resolve(),timelineData:null}),/尚未就绪/);
});
test('display timing rejects a stale record or render generation',async()=>{
  const view={recordRevision:1,revision:1,view:'instructions',timelineData:{}};
  view.timelineTask=Promise.resolve().then(()=>{view.revision++;});
  await assert.rejects(HistoryView.prototype.waitForDisplay.call(view),/发生变化/);
});
test('a hidden document cannot be reported as a painted first screen',async()=>{
  const previous=globalThis.document;globalThis.document={visibilityState:'hidden'};
  try{
    const result=await HistoryView.prototype.waitForDisplay.call({recordRevision:1,revision:1,view:'instructions',timelineData:{}});
    assert.equal(result.painted,false);assert.equal(result.visibility,'hidden');
  }finally{globalThis.document=previous;}
});
