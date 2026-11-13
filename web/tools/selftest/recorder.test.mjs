import test from 'node:test';
import assert from 'node:assert/strict';
import { FileRecorder, recordButtonState } from '../../app/core/recorder.js';

function writerFixture(t, writable){
  globalThis.window = {
    showSaveFilePicker:async () => ({ name:'capture.bin', createWritable:async () => writable }),
  };
  t.after(() => { delete globalThis.window; });
}

test('stalled writer caps accepted backlog and finalizes the original prefix', async t => {
  let release;
  let closed = false;
  const gate = new Promise(resolve => { release = resolve; });
  const chunks = [];
  writerFixture(t, {
    async write(bytes){ await gate; chunks.push({ first:bytes[0], count:bytes.length }); },
    async close(){ closed = true; },
  });
  const rec = new FileRecorder();
  await rec.start();
  for(let i = 0; i < 25; i++) rec.push(new Uint8Array(1024 * 1024).fill(i));
  assert.equal(rec.active, false);
  assert.equal(rec.draining, true);
  assert.equal(rec.backlog(), 16 * 1024 * 1024);
  assert.match(recordButtonState(rec).text, /不完整/);
  assert.equal(closed, false);
  const stopping = rec.stop();
  release();
  const result = await stopping;
  assert.equal(closed, true);
  assert.equal(rec.backlog(), 0);
  assert.deepEqual(chunks, Array.from({length:16}, (_, i) => ({first:i, count:1024 * 1024})));
  assert.equal(result.overflow, true);
  assert.match(result.error.message, /不完整/);
  assert.match(recordButtonState(rec).text, /记录失败/);
});

test('write failure rejects later batches and closes the partial record explicitly', async t => {
  let reject, closeCount = 0, writeCount = 0;
  const gate = new Promise((_, fail) => { reject = fail; });
  writerFixture(t, {
    write(){ writeCount++; return gate; },
    async close(){ closeCount++; },
  });
  const rec = new FileRecorder();
  await rec.start();
  rec.push(new Uint8Array(256 * 1024));
  rec.push(new Uint8Array(256 * 1024));
  const stopping = rec.stop();
  reject(new Error('disk error'));
  const result = await stopping;
  assert.equal(writeCount, 1);
  assert.equal(closeCount, 1);
  assert.equal(result.written, 0);
  assert.equal(result.error.message, 'disk error');
  assert.equal(rec.needsClose, false);
});

test('tiny chunks cannot grow the retained queue beyond its object limit', async t => {
  let written = 0;
  writerFixture(t, {
    async write(bytes){ written += bytes.length; },
    async close(){},
  });
  const rec = new FileRecorder();
  await rec.start();
  const chunk = Uint8Array.of(0xc3);
  for(let i = 0; i < 65537; i++) rec.push(chunk);
  assert.equal(rec.active, false);
  assert.equal(rec.frames, 65536);
  const result = await rec.stop();
  assert.equal(written, 65536);
  assert.match(result.error.message, /65536 段/);
});
