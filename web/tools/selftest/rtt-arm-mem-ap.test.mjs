import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ArmMemApRttProbe } from '../../app/rtt/arm-mem-ap-probe.js';
import { OpenOcdEtmProbe } from '../../app/core/openocd-etm.js';
import { u32le, u32leBytes } from '../../app/core/bin.js';

const base = 0x20000000;
function fixture(t, {dp = 0x1ba01477, base: ram = base, clockKhz = 60000,
  ap = 0, apId = 0x24770011, cswBase = 0x23000040, endian = 'little', apCfg = 0} = {}){
  const memory = Uint8Array.from({length:65536}, (_, i) => (i * 13 + (i >>> 8)) & 255);
  const requests = [];
  const dpIdentities = [0x01000427, 0x10000000];
  const apRegisters = new Map([[0xfc,apId], [0xf4,apCfg], [0xf8,0xe00ff003]]);
  let tar, csw, select = 0, short = false, failedAck, mismatchedInstance = false, fallback = 0;
  function read(at, length){
    assert(at >= ram && at + length <= ram + memory.length);
    return memory.slice(at - ram, at - ram + length);
  }
  const usb = {
    nativeService:true, dapSynchronized:true, atomicDapSupported:true, opened:false,
    configuration:{configurationValue:1, interfaces:[{interfaceNumber:0, alternate:{endpoints:[
      {type:'bulk',direction:'out',endpointNumber:2}, {type:'bulk',direction:'in',endpointNumber:1},
    ]}}]},
    async open(){ this.opened = true; },
    async close(){ this.opened = false; },
    async claimInterface(){},
    async releaseInterface(){},
    async exchangeDap(packet){
      requests.push([...packet]);
      const op = packet[0];
      let answer = [op, 0];
      if (op === 2) answer[1] = packet[1];
      else if (op === 5){
        if (packet[3] !== 13) assert.equal(packet[1], 0);
        answer = [5, packet[2], 1];
        if (packet[3] === 8){
          select = u32le(packet, 4);
          if (packet[8] === 1){ csw = u32le(packet, 9); tar = u32le(packet, 14); }
          if (select % 256 === 0xf0){
            for (const request of packet.slice(8)){
              assert.equal(request & 3, 3);
              const address = (select & 0xf0) | (request & 0x0c);
              assert(apRegisters.has(address));
              answer.push(...u32leBytes(apRegisters.get(address)));
            }
          }
          if (packet[8] === 6) answer.push(...u32leBytes(select % 16 === 2 ? dpIdentities[0] :
            mismatchedInstance ? 0 : dpIdentities[1]));
        }
        if (packet[3] === 2) answer.push(...u32leBytes(dp));
        if (packet[3] === 15){
          assert.equal(csw, cswBase | 0x10);
          const word = new Uint8Array(4);
          word[tar % 4] = read(tar, 1)[0];
          answer.push(...word);
        }
        if (packet[3] === 13){
          const failure = failedAck?.operation === 'write' && failedAck;
          if (!failure || failure.committed){
            if (csw === (cswBase | 0x10)) memory[tar - ram] = packet[4 + (tar % 4)];
            else for (let i = 0; i < packet[2]; i++) memory.set(packet.subarray(4+i*5, 8+i*5), tar-ram+i*4);
          }
          if (failure){ answer[2] = 4; failedAck = null; }
        }
      } else if (op === 6){
        const size = (packet[2] + packet[3] * 256) * 4;
        assert.equal(packet[1], 0);
        assert.equal(select, ap * 0x1000000);
        assert.equal(csw, cswBase | 0x12);
        assert(tar % 1024 + size <= 1024);
        answer = [6, packet[2], packet[3], 1];
        if (packet[4] === 15){
          if (failedAck?.operation === 'read'){
            answer = [6,1,0,4,...read(tar,4)];
            failedAck = null;
          } else answer.push(...read(tar, size - (short ? 4 : 0)));
        }
        else memory.set(packet.subarray(5), tar - ram);
      }
      return {status:'ok', data:new DataView(Uint8Array.from(answer).buffer)};
    },
  };
  t.mock.method(OpenOcdEtmProbe.prototype, 'readMem', async (at, length) => read(at, length));
  t.mock.method(OpenOcdEtmProbe.prototype, 'connect', async () => { fallback++; });
  const probe = new ArmMemApRttProbe(usb, {arch:'arm',transport:'swd',clockKhz,target:'board.cpu'});
  probe.target = 'workbench.memory';
  const commands = {
    'workbench.memory cget -ap-num':String(ap), 'workbench.memory cget -endian':endian,
    'capture {[workbench.memory cget -dap] dpreg 36}':String(dpIdentities[0]),
    'capture {[workbench.memory cget -dap] dpreg 52}':String(dpIdentities[1]),
    [`capture {[workbench.memory cget -dap] apreg ${ap} 252}`]:String(apId),
    [`capture {[workbench.memory cget -dap] apreg ${ap} 244}`]:String(apCfg),
    [`capture {[workbench.memory cget -dap] apreg ${ap} 0}`]:String(cswBase | 0x12),
  };
  probe.command = async line => { assert(Object.hasOwn(commands, line), line); return commands[line]; };
  probe.idcode = dp;
  const info = {addr:ram + 0x200,maxUp:1,maxDown:1,
    up:[{pbuf:ram + 0x400,size:8192,flags:0}],down:[{pbuf:ram + 0x3000,size:64,flags:0}]};
  memory.set(new TextEncoder().encode('SEGGER RTT'), 0x200);
  memory.set(Uint8Array.of(1,0,0,0,1,0,0,0), 0x210);
  for (const [index, {pbuf, size, flags}] of [...info.up, ...info.down].entries()){
    const at = 0x218 + index * 24;
    memory.set(u32leBytes(pbuf), at + 4);
    memory.set(u32leBytes(size), at + 8);
    memory.set(u32leBytes(flags), at + 20);
  }
  return {memory, probe, usb, requests, info, truncate:() => { short = true; },
    mismatchInstance:() => { mismatchedInstance = true; }, fallback:() => fallback,
    failAck:(operation, committed) => { failedAck = {operation, committed}; }};
}

test('F103 SWD RTT uses AP0 blocks split at 1 KiB and writes only its own bytes', async t => {
  const {memory, probe, usb, requests, info} = fixture(t);
  try {
    await probe.useRttMemory(info);
    assert.match(probe.name, /SWD MEM-AP/);
    const start = 0x7f8;
    assert.deepEqual(await probe.readMem(base + start, 1040), memory.slice(start,start+1040));
    assert.deepEqual(requests.slice(-6).filter(r => r[0] === 6).map(r => r.slice(2)), [[2,0,15],[0,1,15],[2,0,15]]);
    const expected = memory.slice();
    const data = Uint8Array.of(0x35,0x99,0x12,0x23,0x31,0x41,0x51,0x61,0x75);
    await probe.writeMem(base + 0x3001, data);
    expected.set(data, 0x3001);
    assert.deepEqual(memory, expected);
    await assert.rejects(probe.writeMem(base + 0x303f, Uint8Array.of(1,2)), /RTT 地址/);
    assert.equal(requests.at(-1)[0], 5);
  } finally { await probe.disconnect(); }
  assert.equal(usb.opened, false);
  assert.deepEqual(requests.at(-1), [3]);
});

test('ARM SWD FAULT recovery retries a read and confirms a write without replaying it', async t => {
  const {probe, memory, info, requests, failAck} = fixture(t);
  try {
    await probe.useRttMemory(info);
    failAck('read');
    assert.deepEqual(await probe.readMem(base+0x400, 8), memory.slice(0x400,0x408));
    const payload = Uint8Array.of(0,1,2,3);
    for (const committed of [true,false]){
      const at = 0x3000 + (committed ? 0 : 4);
      const first = requests.length;
      failAck('write', committed);
      const write = probe.writeMem(base+at, payload);
      if (committed){ await write; assert.deepEqual(memory.slice(at, at+4), payload); }
      else await assert.rejects(write, /05 01 04/);
      assert.equal(requests.slice(first).filter(r => r[0] === 5 && r[3] === 13).length, 1);
      assert.equal(probe._faulted, !committed);
    }
    assert.equal(requests.filter(r => r[0] === 0x08).length, 3);
  } finally { await probe.disconnect(); }
});

test('ARM SWD only retries a read cursor that is still at its previous value', async t => {
  const {probe, memory, info, requests, failAck} = fixture(t);
  const cursor = info.addr + 40;
  try {
    await probe.useRttMemory(info);
    await assert.rejects(probe.writeRttReadOffset(cursor + 24, 1, 0), /读游标地址/);
    for (const [current, previous, next, committed, expectedWrites] of [
      [16,16,32,true,1], [64,64,80,false,2], [96,112,128,false,1],
    ]){
      memory.set(u32leBytes(current),cursor-base);
      const first = requests.length;
      failAck('write', committed);
      const write = probe.writeRttReadOffset(cursor, next, previous);
      if (current === previous){
        await write;
        assert.equal(u32le(memory,cursor-base),next);
      } else {
        await assert.rejects(write, /05 01 04/);
        assert.equal(u32le(memory,cursor-base),current);
      }
      assert.equal(requests.slice(first).filter(r => r[0] === 5 && r[3] === 13).length,expectedWrites);
    }
  } finally { await probe.disconnect(); }
});

test('A short block prevents later writes and retires the USB lease', async t => {
  const {probe, usb, requests, info, truncate} = fixture(t);
  await probe.useRttMemory(info);
  truncate();
  await assert.rejects(probe.readMem(base + 0x400, 16), /响应状态或长度错误/);
  const count = requests.length;
  await assert.rejects(probe.writeMem(base + 0x3000, Uint8Array.of(1)), /响应状态或长度错误/);
  assert.equal(probe._faulted, true);
  await probe.disconnect();
  assert.equal(requests.length, count);
  assert.equal(usb.opened, false);
});

test('H743 SWD with AXI RAM uses the MEM-AP fast path', async t => {
  const ram = 0x24040000;
  const {probe, requests, memory, info} = fixture(t, {base:ram, dp:0x6ba02477, clockKhz:50000});
  try {
    await probe.useRttMemory(info);
    assert.match(probe.name, /SWD MEM-AP/);
    assert.deepEqual(await probe.readMem(ram + 0x7fd, 1032), memory.slice(0x7fd,0x7fd+1032));
    assert(requests.some(r => r[0] === 6 && r[3] === 1));
    await assert.rejects(probe.writeMem(info.up[0].pbuf, Uint8Array.of(1)), /RTT 地址/);
    await assert.rejects(probe.writeMem(info.addr + 40, u32leBytes(0)), /RTT 地址/);
  } finally { await probe.disconnect(); }
});

test('a reconfigured live RTT channel cannot reuse the previous ring and cursor lease', async t => {
  const {probe, memory, info, requests} = fixture(t);
  try {
    await probe.useRttMemory(info);
    const entry = info.addr + 24;
    memory.set(u32leBytes(info.down[0].pbuf), entry + 4 - base);
    const first = requests.length;
    await assert.rejects(probe.readMem(entry, 24), /通道配置已变更/);
    assert(!requests.slice(first).some(r => r[0] === 5 && r[3] === 13));
  } finally { await probe.disconnect(); }
});

test('an imported SWD target can select a nonzero AP using the configured RAM and CSW', async t => {
  const ram = 0x60000000;
  const {probe, requests, memory, info} = fixture(t, {base:ram, ap:3, cswBase:0x2b000040, clockKhz:20000});
  try {
    await probe.useRttMemory(info);
    assert.equal(requests.length, 0);
    await probe.useRttMemory(info, [{start:ram,end:ram + memory.length}]);
    assert.match(probe.name, /SWD MEM-AP/);
    assert.deepEqual(await probe.readMem(ram + 0x500, 128), memory.slice(0x500,0x580));
  } finally { await probe.disconnect(); }
});

test('SWD v2 confirms the DP instance and AP before using generic RTT blocks', async t => {
  const {probe, usb, requests, memory, info} = fixture(t, {dp:0x6ba02477, clockKhz:50000});
  try {
    await probe.useRttMemory(info);
    assert.match(probe.name, /SWD MEM-AP/);
    assert.deepEqual(await probe.readMem(base + 0x402, 10), memory.slice(0x402,0x40c));
    assert(requests.some(r => r[0] === 0x12 && r[1] === 152));
    assert.equal(requests.some(r => r[0] === 0x15), false);
  } finally { await probe.disconnect(); }
  assert.equal(usb.opened, false);
});

test('a changed SWD instance releases the bulk lease and reconnects Wasm before RAM access', async t => {
  const {probe, requests, usb, info, mismatchInstance, fallback} = fixture(t, {dp:0x6ba02477});
  mismatchInstance();
  await probe.useRttMemory(info);
  assert.equal(fallback(), 1);
  assert.equal(usb.opened, false);
  assert.equal(requests.some(r => r[0] === 6 || r[0] === 5 && r[8] === 1), false);
  assert.deepEqual(requests.at(-1), [3]);
});

for (const options of [{ap:0x2000}, {apId:0x02880000}, {endian:'big'}, {apCfg:1}]){
  test(`unsupported MEM-AP metadata stays on Wasm (${JSON.stringify(options)})`, async t => {
    const {probe, requests, info} = fixture(t, options);
    await probe.useRttMemory(info);
    assert.equal(requests.length, 0);
  });
}
