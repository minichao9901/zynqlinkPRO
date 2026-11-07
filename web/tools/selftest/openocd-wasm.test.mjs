import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { OpenOcdTargetSession } from '../../app/core/openocd-session.js';
import { OpenOcdUsb } from '../../app/core/openocd-usb.js';
import { OpenOcdEtmProbe } from '../../app/core/openocd-etm.js';
import { makeOpenOcdProfile } from '../../app/core/openocd-profile.js';
import { createOpenOcdDispatcher } from '../../app/core/openocd-worker.mjs';
import { inspectOpenOcdCfg } from '../../app/dbg/openocd-cfg.js';
import { programOpenOcdFlash } from '../../app/flash/openocd-program.js';
import { hpmBoard } from '../../app/targets/hpm/porting.js';

test('the bundled Wasm registers ARM, HPM and RP2350 profiles and resolves imported Tcl without USB', async t => {
  const wasmBinary = await readFile(new URL('../../app/core/openocd-runtime/openocd-core.wasm', import.meta.url));
  t.mock.method(OpenOcdTargetSession, 'createWorker', () => {
    const worker = { terminate(){} };
    const dispatch = createOpenOcdDispatcher({
      wasmBinary,
      select:device => assert.equal(device, null, 'configuration must not enable USB'),
      post:data => queueMicrotask(() => worker.onmessage({ data })),
    });
    worker.postMessage = message => dispatch(message);
    return worker;
  });
  for (const [family, arch, driver, base] of [
    ['stm32f103','arm','stm32f1x','0x08000000'],
    ['stm32h7','arm','stm32h7x','0x08000000'],
    ['nrf52','arm','nrf5','0x00000000'],
    ['rp2350','arm','rp2xxx','0x10000000'],
    ['hpm6800evk','riscv','hpm_xpi','0x80000000'],
  ]){
    const cfg = makeOpenOcdProfile({ family, arch, port:hpmBoard(family), flash:true });
    const link = new OpenOcdTargetSession();
    try {
      await link.open(cfg);
      assert.equal(await link.command('command mode'), 'config');
      assert.match(await link.command('capture {flash banks}'), new RegExp(`\\(${driver}\\) at ${base}`));
    } finally { await link.close(); }
  }
  const entry = 'board/selected.cfg';
  const board = 'set BOARD_FREQ 4000\nsource [find target/nested.cfg]';
  const target = makeOpenOcdProfile({ family:'stm32f103', flash:true }).script.replace('adapter speed 1000','adapter speed $BOARD_FREQ');
  const cfg = await inspectOpenOcdCfg(board, entry, new Map([[entry,board],['target/nested.cfg',target]]));
  assert.equal(cfg.clockKhz, 4000);
  assert.deepEqual(cfg.cores,[{ target:'workbench.cpu', arch:'arm' }]);
  assert.equal(cfg.flashBase, '0x08000000');
  assert.match(cfg.hash,/^[0-9a-f]{64}$/);
  await assert.rejects(inspectOpenOcdCfg(board, entry));
  await assert.rejects(inspectOpenOcdCfg(target, '../escape.cfg'), /所选脚本目录/);
  const etm = new OpenOcdTargetSession();
  try {
    await etm.open(makeOpenOcdProfile({ clockKhz:250, memoryAp:true }));
    assert.equal(await etm.command('command mode'), 'config');
    assert.equal(await etm.command('capture {workbench.cpu cget -type}'), 'mem_ap');
    assert.equal(await etm.command('workbench.cpu cget -dap'), 'workbench.dap');
    assert.match(await etm.command('capture {adapter speed}'), /250 kHz/);
  } finally { await etm.close(); }
});

test('ETM core control uses physical DHCSR and issues only one resume per request', async () => {
  const probe = new OpenOcdEtmProbe({}, makeOpenOcdProfile({ memoryAp:true }));
  const writes = [];
  let status = 0;
  probe.readMemDiagnostic = async (addr, length) => {
    assert.deepEqual([addr, length], [0xe000edf0, 4]);
    const bytes = new Uint8Array(4);
    new DataView(bytes.buffer).setUint32(0, status, true);
    return bytes;
  };
  probe.writeMemDiagnostic = async (addr, data) => {
    assert.equal(addr, 0xe000edf0);
    writes.push(new DataView(data.buffer).getUint32(0, true));
  };
  await probe.run();
  await probe.halt();
  status = (1 << 17) | 8;
  await probe.halt();
  await probe.run();
  assert.deepEqual(writes, [0xa05f0003, 0xa05f0003, 0xa05f0001]);
});

test('the Zynq lease synchronizes DAP and terminates aligned OUT packets without touching ETM', async () => {
  const calls = [];
  const transfer = data => ({ status:'ok', data:new DataView(Uint8Array.from(data).buffer) });
  let epoch = 4;
  const device = {
    vendorId:0x0d28, productId:0x0204, manufacturerName:'CherryUSB', opened:false,
    configuration:{ configurationValue:1, interfaces:[{ interfaceNumber:0, alternate:{ endpoints:[
      { type:'bulk', direction:'out', endpointNumber:2, packetSize:512 },
      { type:'bulk', direction:'in', endpointNumber:1 },
      { type:'bulk', direction:'in', endpointNumber:2 },
    ] } }] },
    async open(){ this.opened = true; calls.push('open'); },
    async close(){ this.opened = false; calls.push('close'); },
    async claimInterface(iface){ calls.push(['claim', iface]); },
    async releaseInterface(iface){ calls.push(['release', iface]); },
    async clearHalt(direction, endpoint){ calls.push(['clear', direction, endpoint]); },
    async controlTransferIn(setup, length){
      calls.push(['ctrl', setup.request, length]);
      if (setup.request === 0x5a){ epoch++; return transfer([68,65,80,0]); }
      const words = new Uint8Array(32);
      new DataView(words.buffer).setUint32(12, epoch, true);
      return transfer(words);
    },
    async transferOut(endpoint, data){
      calls.push(['write', endpoint, data.byteLength]);
      return { status:'ok', bytesWritten:data.byteLength };
    },
  };
  const usb = new OpenOcdUsb(device);
  await usb.invoke('open', []);
  await usb.invoke('claimInterface',[0]);
  await usb.invoke('transferOut',[2,new Uint8Array(512)]);
  await usb.invoke('transferOut',[2,new Uint8Array(4096)]);
  await assert.rejects(usb.invoke('transferIn',[2,512]), /DAP IN/);
  await assert.rejects(usb.invoke('reset',[]), /不受支持/);
  await usb.close();
  assert.deepEqual(calls, ['open', ['claim',0], ['ctrl',0x5b,32], ['ctrl',0x5a,4],
    ['clear','in',1], ['clear','out',2], ['ctrl',0x5b,32], ['write',2,512], ['write',2,0],
    ['write',2,4096], ['release',0], 'close']);
});

test('Flash preflight rejects a late invalid range before erase, and preserves unwritten sector bytes', async () => {
  const lines = [];
  const original = Uint8Array.of(1,2,3,4);
  let image, data = original.slice();
  const probe = {
    async command(line){
      lines.push(line);
      if (line === 'capture {flash banks}') return '#0 : sample (stm32f1x) at 0x08000000, size 0x00000000';
      if (line.includes('flash info')) return '#0 : sample (stm32f1x) at 0x08000000, size 0x00000004\n # 0: 0x00000000 (0x00000004 0 KiB)';
      if (line.startsWith('flash write_bank')) data = image.slice();
      return '';
    },
    link:{ async request(_type, payload){
      if (payload?.input) image = payload.input;
      if (payload?.read) return { bytes:data.slice() };
      return {};
    } },
  };
  const patch = { addr:0x08000001, data:Uint8Array.of(0xab) };
  const opts = { verify:true, progress(){} };
  await assert.rejects(programOpenOcdFlash(probe, [patch,{ ...patch, addr:0x08000004 }],opts), /超出/);
  assert.ok(!lines.some(line => line.startsWith('flash erase_sector')));
  assert.deepEqual(await programOpenOcdFlash(probe,[patch],opts), { bytes:1, sectors:1, verified:true });
  assert.deepEqual(data,Uint8Array.of(1,0xab,3,4));
});
