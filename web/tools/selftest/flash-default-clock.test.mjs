import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { FlashView } from '../../app/flash/view.js';
import { OpenOcdProbe } from '../../app/core/openocd-probe.js';
import { OpenOcdEtmProbe } from '../../app/core/openocd-etm.js';
import { OpenOcdTargetSession } from '../../app/core/openocd-session.js';
import { createOpenOcdDispatcher } from '../../app/core/openocd-worker.mjs';

test('flasher opens the selected clock and uses MEM-AP for ARM identity only', async t => {
  const chip = { value:'stm32f103' }, clock = { value:'0' };
  globalThis.document = { getElementById:id => id === 'f-chip' ? chip : clock };
  globalThis.navigator.usb = { getDevices:async () => [{ vendorId:0x0d28 }] };
  t.after(() => { delete globalThis.document; delete globalThis.navigator.usb; });
  t.mock.method(OpenOcdProbe.prototype, 'connect', async () => {});
  t.mock.method(globalThis, 'fetch', async url => new Response(await readFile(url)));
  const wasmBinary = await readFile(new URL('../../app/core/openocd-runtime/openocd-core.wasm', import.meta.url));
  t.mock.method(OpenOcdTargetSession, 'createWorker', () => {
    const worker = { terminate(){} };
    worker.postMessage = createOpenOcdDispatcher({wasmBinary,
      select:device => assert.equal(device, null),
      post:data => queueMicrotask(() => worker.onmessage({data}))});
    return worker;
  });
  const view = new FlashView();
  await view._openTarget(true);
  assert.equal(view.probe.clockHz, 1000000);
  assert.equal(view.probe.cfg.raw.entry, 'target/stm32f1x.cfg');
  assert.equal(view.probe.cfg.target, 'stm32f1x.cpu');
  assert.equal(view.probe.cfg.hasFlash, true);
  assert.equal(view.probe.cfg.memoryAp, false);
  clock.value = '4000';
  await view._openTarget(false);
  assert.ok(view.probe instanceof OpenOcdEtmProbe);
  assert.equal(view.probe.clockHz, 4000000);
  assert.equal(view.probe.cfg.raw.entry, 'target/stm32f1x.cfg');
  assert.equal(view.probe.cfg.memoryAp, true);
  chip.value = 'rp2350';
  await view._openTarget(false);
  assert.equal(view.probe.cfg.raw.entry, 'target/rp2350.cfg');
  assert.equal(view.probe.cfg.memoryAp, true);
});
