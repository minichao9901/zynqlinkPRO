import test from 'node:test';
import assert from 'node:assert/strict';
import { DebugSession } from '../../app/dbg/session.js';
import { FPB, compAddr, encodeComparator } from '../../app/dbg/bp.js';
import { OpenOcdProbe } from '../../app/core/openocd-probe.js';
import { Rtt } from '../../app/rtt/protocol.js';
import { RttView } from '../../app/rtt/view.js';
import { MockProbe } from '../../app/rtt/mock.js';

test('partial FPB cleanup retains ownership and resumes only after a verified retry', async () => {
  const session = new DebugSession();
  const probe = session.probe = new OpenOcdProbe(null, { clockKhz:10000, arch:'arm' });
  const words = new Map();
  const installed = new Map();
  let halted = false, closed = false, dropWrite = false;
  probe.isHalted = async () => halted;
  probe.halt = async () => { halted = true; };
  probe.run = async () => { halted = false; };
  probe.disconnect = async () => { closed = true; };
  probe._readWord = async addr => words.get(addr) ?? 0;
  probe.command = async line => {
    if (line === 'capture {bp}') return [...installed.keys()].map(a => `Hardware breakpoint(IVA): addr=0x${a.toString(16)}, len=2`).join('\n');
    const [op,text] = line.split(' '), address = Number(text);
    if (op === 'bp'){
      const slot = [0,1].find(i => ![...installed.values()].includes(i));
      installed.set(address,slot); words.set(compAddr(slot),encodeComparator(address,1));
    } else {
      assert.equal(op,'rbp');const slot = installed.get(address);
      if (dropWrite && slot === 1) throw Error('USB failed mid-FPB write');
      installed.delete(address);words.set(compAddr(slot),0);
    }
    words.set(FPB.CTRL,installed.size ? 1 : 0);
    return '';
  };
  session.caps = { numCode:2, rev:1 };
  await session.bpAdd(0x08000100, 'first');
  await session.bpAdd(0x08000200, 'second');
  dropWrite = true;
  await assert.rejects(session.disconnect(), /USB failed/);
  assert.equal(words.get(compAddr(0)), 0);
  assert.notEqual(words.get(compAddr(1)), 0);
  assert.deepEqual(session.bps, [0x08000100, 0x08000200]);
  assert.equal(session.bpNotes.get(0x08000200), 'second');
  assert.equal(halted, true);
  assert.equal(closed, false);
  await assert.rejects(session.run(), /FPB 状态未确认/);
  dropWrite = false;
  await session.disconnect();
  assert.equal(words.get(compAddr(1)), 0);
  assert.equal(words.get(FPB.CTRL) & 1, 0);
  assert.equal(halted, false);
  assert.equal(closed, true);
});

test('OpenOCD owns FPB registrations and failed removal remains retryable', async () => {
  const session = new DebugSession();
  const probe = session.probe = new OpenOcdProbe(null, { clockKhz:10000, arch:'arm' });
  session.caps = { numCode:2, rev:2 };
  const installed = new Set(), words = new Map();
  let failRemoval = false, corruptReadback = false;
  probe._readWord = async a => corruptReadback && a === compAddr(0) ? 0 : words.get(a) ?? 0;
  probe.command = async line => {
    if (line === 'capture {bp}') return [...installed].map(a => `Hardware breakpoint(IVA): addr=0x${a.toString(16)}, len=2`).join('\n');
    const [op, text] = line.split(' '), address = Number(text);
    if (op === 'rbp' && failRemoval) throw Error('remove failed');
    if (op === 'bp') installed.add(address); else if (op === 'rbp') installed.delete(address); else assert.fail(line);
    words.set(FPB.CTRL, installed.size ? 1 : 0);
    const values = [...installed].map(a => encodeComparator(a,2));
    for (let i=0;i<2;i++) words.set(compAddr(i), values[i] ?? 0);
    return '';
  };
  await session.bpAdd(0x08000100);
  failRemoval = true;
  await assert.rejects(session.bpClear(), /remove failed/);
  assert.deepEqual(session.bps,[0x08000100]);
  failRemoval = false;
  await session.bpClear();
  assert.equal(installed.size,0);
  corruptReadback = true;
  await assert.rejects(session.bpAdd(0x08000200), /比较器/);
  assert.deepEqual(session.bps,[]);
  corruptReadback = false;
  await session.bpClear();
  assert.equal(installed.size,0, 'failed additions must also be removed');
});

test('unconfirmed FPB readback never commits an added breakpoint', async () => {
  const session = new DebugSession();
  session.caps = { numCode:1, rev:1 };
  session.probe = { writeMem:async () => {}, _readWord:async () => 0 };
  await assert.rejects(session.bpAdd(0x08000100), /回读/);
  assert.deepEqual(session.bps, []);
  assert.equal(session._fpbUnconfirmed, true);
});

test('DHCSR activity bits can change without a downshift, invalid reads still trigger it', async () => {
  const session = new DebugSession();
  let values = [0x01010001, 0x00010001, 0x01050001], downshifts = 0;
  session.probe = { _readWord:async () => values.shift(), setClock:async () => { downshifts++; } };
  assert.equal((await session.verifyClock()).ok, true);
  assert.equal(downshifts, 0);
  values = [0x00010001, 0, 0x00010001];
  assert.equal((await session.verifyClock()).hz, 1000000);
  assert.equal(downshifts, 1);
});

test('RTT concurrent writes publish distinct offsets and teardown waits for the full queue', async () => {
  const ringBase = 0x20000100, cursorAddr = 0x2000003c;
  const ring = new Uint8Array(16);
  let wr = 15, release;
  const firstWrite = new Promise(resolve => { release = resolve; });
  const rtt = new Rtt({ writeMem:async (addr, bytes) => {
    if (addr === cursorAddr) wr = bytes[0];
    else {
      if (addr === ringBase + 15) await firstWrite;
      ring.set(bytes, addr - ringBase);
    }
  } }, { addr:0x20000000 });
  rtt.downBase = cursorAddr - 12;
  rtt._entry = async () => ({ size:ring.length, pbuf:ringBase, wr, rd:8 });
  const first = rtt.writeDown(0, Uint8Array.of(65, 66));
  const second = rtt.writeDown(0, Uint8Array.of(67));
  const view = new RttView();
  view.rtt = rtt;
  let drained = false;
  const drain = view._drainRtt().then(() => { drained = true; });
  assert.equal(view.rtt, null);
  await Promise.resolve();
  assert.equal(drained, false);
  release();
  assert.deepEqual(await Promise.all([first, second]), [2, 1]);
  await drain;
  assert.deepEqual([ring[15], ring[0], ring[1], wr], [65, 66, 67, 2]);
});

test('RTT rescan reconnects the same probe and validates the control block after a read failure', async t => {
  const view = new RttView();
  const probe = view.probe = new MockProbe();
  const fields = new Map([['r-addr',{ value:'0x' + probe.cbAddr.toString(16) }],['r-range',{ value:'' }]]);
  globalThis.document = { getElementById(id){
    if (!fields.has(id)) fields.set(id,{});
    return fields.get(id);
  } };
  t.after(() => { delete globalThis.document; });
  let recovered = 0;
  probe.recoverDebugPort = async () => { recovered++; };
  view._startPoll = () => {};
  view._fail(Error('injected read error'));
  assert.match(fields.get('r-err').textContent,/重新扫描/);
  assert.equal(recovered,0);
  await view._startRtt();
  assert.equal(recovered,1);
  assert.equal(view.rtt.addr,probe.cbAddr);
  assert.equal(view._needsRttReconnect,false);
});
