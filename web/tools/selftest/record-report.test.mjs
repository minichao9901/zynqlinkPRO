import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {recordReport} from '../../../etm-service/web/app/record-report.js';
import {captureTransportFailed,captureTransportText} from '../../../etm-service/web/app/capture-quality.js';
const rows=r=>new Map(recordReport(r).flatMap(g=>g.rows));
test('flight report separates overwritten history, post-window, hardware duration and download',()=>{
  const c=JSON.parse(fs.readFileSync('docs/validation/session-flight-recorder-20261105/raw/final-frozen-flight.json')).rows[0].quality;
  const r=rows({captureQuality:c});assert.match(r.get('触发来源'),/手动/);assert.equal(r.get('帧对齐移除'),'13 B');assert.match(r.get('请求触发后窗口'),/20\.000 ms/);assert.match(r.get('硬件等待与后窗总时长'),/245\.830 ms/);
  assert.equal(captureTransportFailed(c),false);assert.ok(!r.has('LA 毛刺滤波快照'));
});
test('missing legacy fields stay unknown without throwing or fabricating zero',()=>{
  const r=rows({});assert.equal(r.get('未处理输入'),'未记录 B');assert.equal(r.get('周期计数元素'),'未记录');assert.equal(r.get('采集时镜像已核对'),'未记录');
});
test('capture failure cannot be hidden by clean decoder or an ended transport',()=>{
  const c={loss:false,synced:true,ended:true,flight:{},completionReason:'trigger',captureComplete:false,requestedWindowComplete:false};
  assert.ok(captureTransportFailed(c));assert.doesNotMatch(captureTransportText(c),/窗口完成/);
});
test('native performance is offline and target clocks are not labelled SWD',()=>{
  const report=recordReport({targetSnapshot:{clocks:{coreHz:48000000,physicalTraceHz:24000000}},performance:{jobSeconds:.6,decodeSeconds:.5,storePhasesSeconds:{nativeClosedBuild:.4}}});
  assert.equal(new Map(report.flatMap(g=>g.rows)).get('目标 CPU / TRACECLK（快照推算）'),'48.000 / 24.000 MHz');
  assert.match(report.find(g=>g.title==='处理性能 Profile').note,/不相加.*不包括采集/);
});
