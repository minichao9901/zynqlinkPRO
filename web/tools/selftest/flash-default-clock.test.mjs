import test from 'node:test';
import assert from 'node:assert/strict';
import { FlashView } from '../../app/flash/view.js';
import { OpenOcdProbe } from '../../app/core/openocd-probe.js';
import { OpenOcdEtmProbe } from '../../app/core/openocd-etm.js';

test('flasher opens the selected clock and uses MEM-AP for ARM identity only', async t => {
  const chip = { value:'stm32f103' }, clock = { value:'0' };
  globalThis.document = { getElementById:id => id === 'f-chip' ? chip : clock };
  globalThis.navigator.usb = { getDevices:async () => [{ vendorId:0x0d28 }] };
  t.after(() => { delete globalThis.document; delete globalThis.navigator.usb; });
  t.mock.method(OpenOcdProbe.prototype, 'connect', async () => {});
  const view = new FlashView();
  await view._openTarget(true);
  assert.equal(view.probe.clockHz, 1000000);
  assert.match(view.probe.cfg.script, /flash bank internal stm32f1x/);
  assert.match(view.probe.cfg.script, /cortex_m/);
  clock.value = '4000';
  await view._openTarget(false);
  assert.ok(view.probe instanceof OpenOcdEtmProbe);
  assert.equal(view.probe.clockHz, 4000000);
  assert.match(view.probe.cfg.script, /mem_ap/);
  assert.doesNotMatch(view.probe.cfg.script, /cortex_m|flash bank/);
  chip.value = 'rp2350';
  await view._openTarget(false);
  assert.match(view.probe.cfg.script, /-adiv6/);
  assert.match(view.probe.cfg.script, /mem_ap .* -ap-num 0x2000/);
});
