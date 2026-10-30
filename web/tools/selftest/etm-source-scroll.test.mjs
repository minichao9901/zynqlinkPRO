import test from 'node:test';
import assert from 'node:assert/strict';
import {HistoryView} from '../../../etm-service/web/app/history.js';
test('source following uses viewport geometry across flame/source layout changes',()=>{
  const active={getBoundingClientRect:()=>({top:400,height:20})};
  const box={clientHeight:200,scrollTop:500,querySelector:()=>active,getBoundingClientRect:()=>({top:100})};
  const previous=globalThis.document;globalThis.document={getElementById:()=>box};
  try{HistoryView.prototype.scrollSource();assert.equal(box.scrollTop,710);}
  finally{globalThis.document=previous;}
});
