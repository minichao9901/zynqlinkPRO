import test from 'node:test';
import assert from 'node:assert/strict';
import {DapProfile} from '../../app/core/dap-profile.js';
const le=v=>[v&255,v>>>8&255,v>>>16&255,v>>>24];
function prepared(){const p=new DapProfile();p.record(Uint8Array.of(5,0,3,8,...le(0),1,...le(0x23000052),5,...le(0xe000ed00)),Uint8Array.of(5,3,1));p.reset();return p;}
test('profiling retains observed AP setup across counter reset without inventing memory values',()=>{
  const p=prepared();
  p.record(Uint8Array.of(6,0,2,0,15),Uint8Array.of(6,2,0,1,...le(0x12345678),...le(0x87654321)));
  p.record(Uint8Array.of(5,0,2,5,...le(0xe000ed00),15),Uint8Array.of(5,2,1,...le(0x12345678)));
  const s=p.snapshot();assert.deepEqual(s.commands,{'0x06':1,'0x05':1});assert.equal(s.unknownWords,0);
  assert.deepEqual(s.registers['0xe000ed00'],{reads:2,writes:0});assert.deepEqual(s.registers['0xe000ed04'],{reads:1,writes:0});
  assert.ok(!JSON.stringify(s).includes('12345678'));
});
test('profiling counts completed operations only and handles flash block autoincrement',()=>{
  const p=prepared();p.record(Uint8Array.of(5,0,1,5,...le(0x080003fc)),Uint8Array.of(5,1,1));
  p.record(Uint8Array.of(6,0,2,0,15),Uint8Array.of(6,1,0,2,...le(7)));
  const s=p.snapshot();assert.equal(s.regions.flash.reads,1);assert.equal(p.state.tar,0x08000000);assert.equal(s.unknownWords,0);
});
test('stage timers close before idle time and device reopen invalidates AP assumptions',()=>{
  let now=0;const p=new DapProfile(()=>now);p.reset();p.setStage('prepare');now=5;p.setStage('capture');now=25;p.setStage(null);now=100;
  const s=p.snapshot();assert.equal(s.stages.prepare.wallMs,5);assert.equal(s.stages.capture.wallMs,20);
  p.open();p.record(Uint8Array.of(6,0,1,0,15),Uint8Array.of(6,1,0,1,...le(0)));assert.equal(p.snapshot().unknownWords,1);
});
