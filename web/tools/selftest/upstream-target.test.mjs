import test from 'node:test';
import assert from 'node:assert/strict';
import { OpenOcdProbe } from '../../app/core/openocd-probe.js';
import { OpenOcdRiscvSession } from '../../app/dbg/openocd-riscv.js';
import { captureFault } from '../../app/dbg/fault.js';
import { callEndingAt, decodeJal, nextAddrsOf } from '../../app/dbg/rv.js';
import { SampleStore } from '../../app/scope/store.js';
import { RttView } from '../../app/rtt/view.js';
import { AnsiDisplay } from '../../app/core/display-stream.js';

test('HPM reset masks polling, reads release back and restores polling on failure', async () => {
  for (const release of [1,3]){
    const p = new OpenOcdProbe(null, { arch:'riscv', boardId:'hpm6800evk', clockKhz:1000 });
    const commands = [], statuses = [0,0x40800];
    p.isHalted = async () => commands.length === 0;
    p.command = async line => {
      commands.push(line);
      return line === 'capture {poll}' ? 'background polling: on' : '';
    };
    p.targetCommand = async line => {
      commands.push(line);
      if (line === 'riscv dmi_read 0x10') return release;
      if (line === 'riscv dmi_read 0x11') return statuses.shift();
    };
    if (release === 1) assert.equal(await p.reset(),'HPM 系统复位');
    else await assert.rejects(p.reset(),/未确认.*复位已释放/);
    assert.equal(commands.at(-1),'poll on');
    assert.ok(commands.indexOf('poll off') < commands.indexOf('riscv dmi_write 0x10 0x3'));
    assert.ok(commands.indexOf('riscv dmi_write 0x10 0x1') < commands.indexOf('riscv dmi_read 0x10'));
  }
});

test('RV32 Wasm fault snapshot reads named CSRs and detects an expired PC', async () => {
  const s = new OpenOcdRiscvSession();
  s.probe = {};
  s.halted = true;
  s._pollHalted = async () => true;
  s.target = 'workbench.cpu';
  const values = {pc:0x18000,mcause:2,mepc:0x18004,mtval:0xffffffff,mstatus:0,mtvec:0x1e4,dcsr:0};
  s._command = async line => line.match(/\{([^}]+)\}/)[1].split(' ')
    .map(name => name + ' 0x' + values[name].toString(16)).join(' ');
  const fault = await captureFault(s);
  assert.equal(fault.error,null);
  assert.deepEqual(fault.raw,values);
  const read = s._command;
  s._command = line => line.endsWith('{pc}') ? 'pc 0x18008' : read(line);
  assert.match((await captureFault(s)).error,/现场已过期/);
});

test('RV32 halfwords reconstruct JAL, signed branch and AUIPC/JALR calls', async () => {
  assert.equal(decodeJal(0x00ef,0x0080,0x1000).target,0x1008); // jal ra,+8
  const halves = new Map([[0x1000,0x0ce3],[0x1002,0xfe00]]); // beq x0,x0,-8
  const branch = await nextAddrsOf(0x1000,{ readHalf:async addr => halves.get(addr) });
  assert.deepEqual(branch.addrs,[0xff8,0x1004]);
  const code = Uint8Array.of(0x97,0x10,0,0,0xe7,0x80,0x80,0xff); // auipc ra,1 / jalr ra,-8(ra)
  const target = await callEndingAt(async (addr,len) => code.slice(addr - 0x1000,addr - 0x1000 + len),0x1008);
  assert.equal(target,0x1ff8);
});

test('F103 binary SRAM is gated by identity, aligned range and the built-in profile', async () => {
  for (const device of [0x414,0x410]){
    const p = new OpenOcdProbe(null,{ arch:'arm', family:'stm32f103', clockKhz:1000 });
    let identities = 0;
    const requests = [];
    p._readWord = async addr => { assert.equal(addr,0xe0042000); identities++; return device; };
    p._readUnits = async (_,__,count) => Array(count).fill(0);
    p.link = { request:async (type,args) => {
      requests.push([type,args]);
      return { bytes:new Uint8Array(args.length) };
    }};
    assert.equal((await p.readMem(0x20000000,4096)).length,4096);
    assert.equal((await p.readMem(0x2000f004,4096)).length,4096);
    if (device === 0x414) await p.writeMem(0x20000004,new Uint8Array(4096));
    assert.equal((await p.readMem(0x20000001,4096)).length,4096);
    p.cfg.raw = {};
    assert.equal((await p.readMem(0x20000000,4096)).length,4096);
    assert.equal(identities,1);
    assert.equal(requests.length, device === 0x414 ? 2 : 0);
    for (const [type,args] of requests){
      assert.equal(type,'memoryImage');
      assert.equal(args.physical,false);
    }
  }
});

test('scope sample budget matches actual arrays with interpolated or exact timestamps', () => {
  const vars = [{name:'a',scalar:'u8'},{name:'b',scalar:'f64'}];
  for (const exactTime of [false,true]){
    const opts = {exactTime};
    const cap = SampleStore.fitCapacity(vars,10000,4096,opts);
    assert.ok(new SampleStore(vars,cap,opts).bytes() <= 4096);
    assert.ok(new SampleStore(vars,cap+1,opts).bytes() > 4096);
  }
});

test('RTT terminal lag bounds its queue while raw bytes and recording keep advancing', t => {
  const view = new RttView();
  view.mode = 'term';
  view._updateEmptyHint = () => {};
  const recorded = [], writes = [];
  view.rec.push = bytes => recorded.push(...bytes);
  view.ansiDisplay = new AnsiDisplay({write:bytes => writes.push(bytes)},{
    limit:4,
    format:(bytes,time) => view._formatTerminal(bytes,time),
  });
  t.after(() => clearInterval(view.ansiDisplay.timer));
  view._ingest(Uint8Array.of(1,2,3),new Date());
  view._ingest(Uint8Array.of(4,5,6),new Date());
  assert.deepEqual(recorded,[1,2,3,4,5,6]);
  assert.equal(view.recBytes,6);
  assert.equal(view.ansiDisplay.bytes,3);
  view.ansiDisplay.flush();
  assert.deepEqual([...writes[0].subarray(0,5)],[24,27,91,48,109]);
  assert.deepEqual([...writes[0].subarray(-3)],[4,5,6]);
});
