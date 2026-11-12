import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { OpenOcdTargetSession } from '../../app/core/openocd-session.js';
import { OpenOcdUsb } from '../../app/core/openocd-usb.js';
import { OpenOcdEtmProbe } from '../../app/core/openocd-etm.js';
import { OpenOcdProbe } from '../../app/core/openocd-probe.js';
import { makeOpenOcdProfile } from '../../app/core/openocd-profile.js';
import { createOpenOcdDispatcher } from '../../app/core/openocd-worker.mjs';
import { inspectOpenOcdCfg } from '../../app/dbg/openocd-cfg.js';
import { programOpenOcdFlash } from '../../app/flash/openocd-program.js';
import { OpenOcdH7FlashProbe } from '../../app/flash/openocd-h7.js';
import { hpmBoard } from '../../app/targets/hpm/porting.js';
import { OpenOcdResetSession, pulseTargetReset } from '../../app/flash/target-reset.js';

test('ARM JTAG confirms the selected TAP without reading a SWD DPIDR', async t => {
  t.mock.method(OpenOcdTargetSession.prototype,'open',async()=>{});
  t.mock.method(OpenOcdTargetSession.prototype,'close',async()=>{});
  t.mock.method(OpenOcdTargetSession.prototype,'command',async line => {
    const replies = {'target names':'h743.cpu0', init:'', 'h743.cpu0 curstate':'running',
      'h743.cpu0 cget -chain-position':'h743.cpu',
      'capture {scan_chain}':'0 h743.cpu Y 0x6ba00477\n1 h743.boundary Y 0x06450041'};
    assert.ok(Object.hasOwn(replies,line),line);
    return replies[line];
  });
  const probe = new OpenOcdProbe(null,{target:'h743.cpu0',clockKhz:50000,arch:'arm',transport:'jtag'});
  await probe.connect();
  assert.equal(probe.idcode,0x6ba00477);
  await probe.disconnect();
});

function h743FlashUsb({ ap0Id, ap2Id, flashKb = 2048, control = 0x00100000 }){
  const ports = new Map([[0,{ csw:0, tar:0 }],[2,{ csw:0, tar:0 }]]);
  const reads = [], writes = [], packets = [];
  let select = 0;
  const words = new Map([[0xe000edf0,0x01010000],[0xe0002000,0x10000080],[0xe0001000,0x40000000]]);
  const toWord = v => [v & 255, v >>> 8 & 255, v >>> 16 & 255, v >>> 24];
  const transfer = bytes => ({ status:'ok', data:new DataView(Uint8Array.from(bytes).buffer) });
  function access(request, value){
    const read = request & 2;
    let register = request & 12;
    if (!(request & 1)){
      if (!read && register === 8) select = value;
      if (read) return register === 0 ? 0x6ba02477 : register === 4 ? 0xf0000000 : 0;
      return;
    }
    const ap = select >>> 24;
    const port = ports.get(ap);
    assert.ok(port, `AP ${ap}`);
    register |= select & 0xf0;
    if (register === 0){
      if (read) return port.csw | 0x40;
      port.csw = value;
    } else if (register === 4){
      if (read) return port.tar;
      port.tar = value;
    } else if (register === 12 || register >= 0x10 && register <= 0x1c){
      const address = (register === 12 ? port.tar : (port.tar & ~15) + (register & 12)) >>> 0;
      if (register === 12 && (port.csw & 0x30) === 0x10) port.tar += 1 << (port.csw & 7);
      if (!read){
        writes.push([ap,address,value]);
        if (ap === 2 && address === 0xe00e1004) control = value;
        else if (address === 0xe000edf0) words.set(address,0x01010000 | (value & 15) | ((value & 2) << 16));
        else words.set(address,value);
        return;
      }
      reads.push([ap,address]);
      if (ap === 2 && address === 0xe00e1000) return ap2Id;
      if (ap === 2 && address === 0xe00e1004) return control;
      if (ap === 0 && address === 0x5c001000) return ap0Id;
      if (ap === 0 && address === 0x1ff1e880) return flashKb;
      if (ap === 0 && address === 0xe000ed00) return (ap2Id & 0xfff) !== 0x450 || (control & 0x00600007) === 0x00600007 ? 0x411fc271 : 0;
      return words.get(address) ?? 0;
    } else if (register === 0xfc && read) return ap === 0 ? 0x84770004 : 0x54770002;
    return 0;
  }
  return {
    reads, writes, get debugControl(){ return control; },
    vendorId:0x0d28, productId:0x0204, productName:'CMSIS-DAP', serialNumber:'H743-model',
    async open(){ this.configuration = { configurationValue:1 }; },
    async close(){},
    async claimInterface(number){ assert.equal(number,0); },
    async releaseInterface(){},
    async controlTransferIn({value}, length){
      const descriptors = {
        0x100:[18,1,16,2,0xef,2,1,64,40,13,4,2,0,1,0,2,3,1],
        0x200:[9,2,32,0,1,1,0,128,50,9,4,0,0,2,255,0,0,0,7,5,2,2,0,2,0,7,5,0x81,2,0,2,0],
        0x300:[4,3,9,4],
      };
      const name = value === 0x302 ? 'CMSIS-DAP' : this.serialNumber;
      return transfer((descriptors[value] || [2 + name.length * 2, 3, ...Array.from(name,c=>[c.charCodeAt(0),0]).flat()]).slice(0,length));
    },
    async transferOut(endpoint, bytes){
      assert.equal(endpoint,2);
      const [op,arg] = bytes;
      const view = new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
      if (op === 0x05 || op === 0x06){
        const block = op === 0x06;
        const count = block ? view.getUint16(2,true) : bytes[2];
        const reply = block ? [op,bytes[2],bytes[3],1] : [op,count,1];
        let offset = block ? 5 : 3;
        for (let n=0;n<count;n++){
          const request = block ? bytes[4] : bytes[offset++];
          assert.equal(request & ~15,0);
          if (request & 2) reply.push(...toWord(access(request)));
          else {
            access(request, view.getUint32(offset,true));
            offset += 4;
          }
        }
        packets.push(reply);
      } else if (op === 0){
        const data = { 0xf0:[1], 0xfe:[8], 0xff:[0,2] }[arg] || [];
        packets.push([0,data.length,...data]);
      } else packets.push([op, op === 2 ? 1 : 0]);
      return { status:'ok',bytesWritten:bytes.length };
    },
    async transferIn(endpoint){
      assert.equal(endpoint,1);
      assert.ok(packets.length);
      return transfer(packets.shift());
    },
  };
}

test('real Wasm H743 Flash probes AP2 when the AP0 DBGMCU alias returns zero', async t => {
  const wasmBinary = await readFile(new URL('../../app/core/openocd-runtime/openocd-core.wasm', import.meta.url));
  let selected, device;
  const old = Object.getOwnPropertyDescriptor(globalThis,'navigator');
  Object.defineProperty(globalThis,'navigator',{ configurable:true,value:{ usb:{ async getDevices(){ return selected ? [device] : []; } } } });
  t.after(() => Object.defineProperty(globalThis,'navigator',old));
  t.mock.method(OpenOcdTargetSession,'createWorker',() => {
    const worker = { terminate(){} };
    worker.postMessage = createOpenOcdDispatcher({ wasmBinary,select:value => { selected = value; },
      post:data => queueMicrotask(() => worker.onmessage({ data })) });
    return worker;
  });
  const cfg = makeOpenOcdProfile({ family:'stm32h7',clockKhz:10000,flash:true });
  for (const [ap0Id, ap2Id, legacy, flashKb] of [[0,0x20036450,true],[0,0x20036450,false],
    [0x20036450,0,false],[0,0,false],[0,0x20036450,false,0]]){
    device = h743FlashUsb({ ap0Id,ap2Id,flashKb });
    const profile = legacy ? { ...cfg,script:cfg.script.replaceAll(' -dbgmcu-target workbench.h7dbg','') } : cfg;
    const probe = new OpenOcdH7FlashProbe(device,profile);
    try {
      await probe.connect();
      if (legacy || !(ap0Id || ap2Id)){
        await assert.rejects(probe.command('flash probe 0'),/Cannot identify target/);
      } else if (flashKb === 0){
        await assert.rejects(probe.command('flash probe 0'),/valid STM32H74x\/75x Flash size/);
      } else {
        for (const bank of [0,1]) await probe.command(`flash probe ${bank}`);
        const banks = await probe.command('capture {flash banks}');
        assert.match(banks,/at 0x08000000, size 0x00100000/);
        assert.match(banks,/at 0x08100000, size 0x00100000/);
        await probe.targetCommand('configure -work-area-size 0');
        assert.equal(Number(await probe.targetCommand('cget -work-area-size')),0);
      }
      assert.equal(device.reads.some(([ap,address]) => ap === 0 && address === 0x5c001000),legacy || !ap2Id);
    } finally { await probe.disconnect(); }
    assert.equal(device.debugControl,0x00100000);
    assert.deepEqual(device.writes.filter(([ap]) => ap === 2), ap2Id ?
      [[2,0xe00e1004,0x00700007],[2,0xe00e1004,0x00100000]] : []);
    assert.ok(!device.writes.some(([,address]) => address >= 0x52002000 && address < 0x52002200));
  }
});

test('H7 work area is restored after block writes and skipped when the MPU is enabled', async () => {
  for (const scenario of ['success','write-failure','short-backup','mpu-enabled','short-mpu','disable-rejected']){
    const failWrite = scenario === 'write-failure';
    const mpuEnabled = scenario === 'mpu-enabled' || scenario === 'disable-rejected';
    const original = Uint8Array.of(1,2,3,4,5,6,7,8);
    let ram = original.slice(), image, flash;
    let erased = false, workAreaSize = 8;
    const probe = {target:'h743.cpu0',halt:async()=>{},
      readMem:async address => {
        if (address === 0xe000ed94)
          return scenario === 'short-mpu' ? new Uint8Array() : Uint8Array.of(Number(mpuEnabled),0,0,0);
        assert.equal(mpuEnabled,false,'MPU fallback must avoid the RAM work area');
        return scenario === 'short-backup' ? ram.slice(0,4) : ram.slice();
      },
      writeMem:async(_a,b)=>{ram=b.slice();},
      command:async line => {
        if (line === 'capture {flash banks}') return '#0 : internal (stm32h7x) at 0x08000000, size 0x00000004';
        if (line.includes('flash info')) return '#0 : internal (stm32h7x) at 0x08000000, size 0x00000004\n # 0: 0x00000000 (0x00000004 0 KiB)';
        if (line.endsWith('cget -work-area-phys')) return '0x24060000';
        if (line.endsWith('cget -work-area-size')) return String(workAreaSize);
        if (line.endsWith('configure -work-area-size 0') && scenario !== 'disable-rejected') workAreaSize = 0;
        if (line.startsWith('flash erase_sector')) erased = true;
        if (line.startsWith('flash write_bank')){
          assert.equal(workAreaSize,mpuEnabled ? 0 : 8);
          if (workAreaSize) ram.fill(0xee);
          if (failWrite) throw Error('write failed');
          flash = image.slice();
        }
        return '';
      },link:{request:async(_t,p)=>{
        if(p?.input)image=p.input;
        return p?.read?{bytes:flash.slice()}:{};
      }},
    };
    const run=()=>programOpenOcdFlash(probe,[{addr:0x08000000,data:Uint8Array.of(9,8,7,6)}],{verify:true,progress(){}});
    const rejectedBeforeErase = {'short-backup':/备份不完整/,'short-mpu':/MPU 状态回读不完整/,'disable-rejected':/禁用未确认/};
    if(rejectedBeforeErase[scenario]){
      await assert.rejects(run(),rejectedBeforeErase[scenario]);
      assert.equal(erased,false);
    }else if(failWrite)await assert.rejects(run(),/write failed/);else await run();
    assert.deepEqual(ram,original);
  }
});

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
  const jtagScript = 'adapter driver cmsis-dap\ntransport select jtag\n' +
    'jtag newtap h743 cpu -irlen 4\njtag newtap h743 boundary -irlen 5\n' +
    'dap create h743.dap -chain-position h743.cpu\n' +
    'target create h743.cpu0 cortex_m -dap h743.dap\n';
  const jtag = await inspectOpenOcdCfg(jtagScript,'h743.cfg');
  assert.equal(jtag.transport,'jtag');
  assert.equal(jtag.arch,'arm');
  assert.equal(jtag.target,'h743.cpu0');
  assert.match(cfg.hash,/^[0-9a-f]{64}$/);
  const memory = new OpenOcdEtmProbe(null, { ...cfg, memoryAp:true });
  const importedLink = new OpenOcdTargetSession();
  try {
    await importedLink.open(cfg);
    const name = await memory._selectTarget(importedLink, [cfg.target]);
    assert.equal(await importedLink.command(`capture {${name} cget -type}`), 'mem_ap');
    assert.equal(await importedLink.command(`${name} cget -dap`), 'workbench.dap');
    assert.equal(Number(await importedLink.command(`${name} cget -ap-num`)), 0);
  } finally { await importedLink.close(); }
  const rp2350 = makeOpenOcdProfile({ family:'rp2350' });
  const rpLink = new OpenOcdTargetSession();
  try {
    await rpLink.open(rp2350);
    const probe = new OpenOcdEtmProbe(null, { ...rp2350, memoryAp:true, raw:{} });
    const name = await probe._selectTarget(rpLink, [rp2350.target]);
    assert.equal(Number(await rpLink.command(`${name} cget -ap-num`)), 0x2000);
  } finally { await rpLink.close(); }
  await assert.rejects(inspectOpenOcdCfg(board, entry));
  await assert.rejects(inspectOpenOcdCfg(target, '../escape.cfg'), /所选脚本目录/);
  const etm = new OpenOcdTargetSession();
  try {
    await etm.open(makeOpenOcdProfile({ clockKhz:250, memoryAp:true }));
    assert.equal(await etm.command('command mode'), 'config');
    assert.equal(await etm.command('capture {workbench.cpu cget -type}'), 'mem_ap');
    assert.equal(await etm.command('workbench.cpu cget -dap'), 'workbench.dap');
    assert.match(await etm.command('capture {adapter speed}'), /250 kHz/);
    const first = Number(await etm.command('ms'));
    await new Promise(resolve => setTimeout(resolve, 25));
    const second = Number(await etm.command('ms'));
    assert.ok(first >= 0 && second > first, `Wasm monotonic clock: ${first} → ${second}`);
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

test('ARM RTT reset confirms the sticky reset bit after reconnect without replaying AIRCR', async () => {
  const probe = new OpenOcdEtmProbe({}, makeOpenOcdProfile({ memoryAp:true }));
  const status = [0, 1 << 25];
  const operations = [];
  probe.readDhcsr = async () => status.shift();
  probe.writeMemDiagnostic = async (addr, bytes) => {
    operations.push([addr, ...bytes]);
    throw Error('debug transport dropped during reset');
  };
  probe.recoverDebugPort = async () => { operations.push('reconnect'); };
  assert.match(await probe.reset(), /SYSRESETREQ/);
  assert.deepEqual(operations, [[0xe000ed0c,4,0,0xfa,5], 'reconnect']);
});

test('global reset runs real Wasm adapter commands without examining a target', async t => {
  const wasmBinary = await readFile(new URL('../../app/core/openocd-runtime/openocd-core.wasm', import.meta.url));
  const writes = [];
  let selected, command;
  const result = bytes => ({ status:'ok', data:new DataView(Uint8Array.from(bytes).buffer) });
  const device = {
    vendorId:0x0d28, productId:0x0204, productName:'CMSIS-DAP', serialNumber:'FAKE',
    async open(){ this.configuration = { configurationValue:1 }; },
    async close(){},
    async claimInterface(number){ assert.equal(number,0); },
    async releaseInterface(){},
    async controlTransferIn({value}, length){
      const descriptors = {
        0x100:[18,1,16,2,0xef,2,1,64,40,13,4,2,0,1,0,2,3,1],
        0x200:[9,2,32,0,1,1,0,128,50,9,4,0,0,2,255,0,0,0,7,5,2,2,0,2,0,7,5,0x81,2,0,2,0],
        0x300:[4,3,9,4],
      };
      const name = value === 0x302 ? 'CMSIS-DAP' : 'FAKE';
      return result((descriptors[value] || [2 + name.length * 2, 3, ...Array.from(name,c=>[c.charCodeAt(0),0]).flat()]).slice(0,length));
    },
    async transferOut(endpoint, bytes){
      assert.equal(endpoint,2);
      command = [...bytes]; writes.push(command);
      return { status:'ok',bytesWritten:bytes.length };
    },
    async transferIn(endpoint){
      assert.equal(endpoint,1);
      const [op,arg] = command;
      if (op === 0){
        const data = { 0xf0:[1], 0xfe:[1], 0xff:[64,0] }[arg] || [];
        return result([0,data.length,...data]);
      }
      return result([op, op === 2 ? 1 : op === 0x10 ? arg & 0x80 : 0, 0, 0, 0]);
    },
  };
  const old = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
  Object.defineProperty(globalThis, 'navigator', { configurable:true, value:{ usb:{ async getDevices(){ return selected ? [device] : []; } } } });
  t.after(() => Object.defineProperty(globalThis, 'navigator', old));
  t.mock.method(OpenOcdTargetSession, 'createWorker', () => {
    const worker = { terminate(){} };
    const dispatch = createOpenOcdDispatcher({ wasmBinary,
      select:value => { selected = value; },
      post:data => queueMicrotask(() => worker.onmessage({ data })),
    });
    worker.postMessage = dispatch;
    return worker;
  });
  const session = new OpenOcdResetSession();
  try {
    await session.connect(device);
    await pulseTargetReset(session);
  } finally { await session.close(); }
  assert.deepEqual(writes.filter(row => row[0] === 0x10 && row[2] !== 0), [
    [0x10,0,0x80,0,0,0,0], [0x10,0x80,0x80,0x50,0xc3,0,0],
  ]);
  assert.ok(!writes.some(row => row[0] === 5 || row[0] === 6));
});

test('reset still releases NRST after a failed assert, and surfaces the first error', async () => {
  const values = [];
  const probe = { async swjResetPin(value){
    values.push(value);
    if (!value) throw Error('assert failed');
    return true;
  } };
  await assert.rejects(pulseTargetReset(probe), /assert failed/);
  assert.deepEqual(values,[0,0x80]);
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
