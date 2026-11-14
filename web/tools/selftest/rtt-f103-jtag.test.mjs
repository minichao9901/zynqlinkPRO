import { test } from 'node:test';
import assert from 'node:assert/strict';
import { F103JtagRttProbe } from '../../app/rtt/f103-jtag-probe.js';
import { OpenOcdEtmProbe } from '../../app/core/openocd-etm.js';
import { u32le, u32leBytes } from '../../app/core/bin.js';

const base = 0x20000000;
const cpuid = 0x411fc231, deviceId = 0x10036414;

function fixture(t){
  const memory = Uint8Array.from({length:65536}, (_, i) => (i * 13 + (i >>> 8)) & 255);
  const requests = [];
  let tar, csw, short = false, failedAck;
  function read(at, length){
    if (at === 0xe000ed00) return u32leBytes(cpuid);
    if (at === 0xe0042000) return u32leBytes(deviceId);
    return memory.slice(at - base, at - base + length);
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
      if (op === 2) answer[1] = 2;
      else if (op === 0x8b) answer.push(0x0e);
      else if (op === 0x89) answer.push(packet[1] === 255 ? 17 : packet[1], ...new Uint8Array(12));
      else if (op === 0x16) answer.push(...u32leBytes(0x3ba00477));
      else if (op === 5){
        answer = [5, packet[2], 1];
        if (packet[2] === 3 && packet[3] === 8){ csw = u32le(packet, 9); tar = u32le(packet, 14); }
        if (packet[3] === 14) answer.push(0, 0, 0, 0);
        if (packet[3] === 13){
          const failure = failedAck?.operation === 'write' && failedAck;
          if (!failure || failure.committed){
            if (csw === 0x23000050) memory[tar - base] = packet[4 + (tar % 4)];
            else for (let i = 0; i < packet[2]; i++) memory.set(packet.subarray(4+i*5, 8+i*5), tar-base+i*4);
          }
          if (failure){ answer[2] = 3; failedAck = null; }
        }
      } else if (op === 6){
        const size = (packet[2] + packet[3] * 256) * 4;
        assert.equal(csw, 0x23000052);
        assert(tar % 1024 + size <= 1024);
        answer = [6, packet[2], packet[3], 1];
        if (packet[4] === 15){
          if (failedAck?.operation === 'read'){
            answer = [6,1,0,3,...read(tar,4)];
            failedAck = null;
          } else answer.push(...read(tar, size - (short ? 4 : 0)));
        }
        else memory.set(packet.subarray(5), tar - base);
      }
      return {status:'ok', data:new DataView(Uint8Array.from(answer).buffer)};
    },
  };
  t.mock.method(OpenOcdEtmProbe.prototype, 'readMem', async (at, length) => read(at, length));
  const probe = new F103JtagRttProbe(usb, {arch:'arm',clockKhz:60000});
  probe.target = 'workbench.memory';
  probe.command = async line => {
    assert.equal(line, 'workbench.memory cget -ap-num');
    return '0';
  };
  probe.idcode = 0x3ba00477;
  probe.jtagTaps = [probe.idcode,0x06414041].map((idcode,index) => ({idcode,index,enabled:true,irLength:4+index}));
  const info = {addr:base + 0x200,maxUp:1,maxDown:1,
    up:[{pbuf:base + 0x400,size:8192,flags:0}],down:[{pbuf:base + 0x3000,size:64,flags:0}]};
  memory.set(new TextEncoder().encode('SEGGER RTT'), 0x200);
  memory.set(Uint8Array.of(1,0,0,0,1,0,0,0), 0x210);
  for (const [index, {pbuf, size, flags}] of [...info.up, ...info.down].entries()){
    const at = 0x218 + index * 24;
    memory.set(u32leBytes(pbuf), at + 4);
    memory.set(u32leBytes(size), at + 8);
    memory.set(u32leBytes(flags), at + 20);
  }
  return {memory, probe, usb, requests, info, truncate:() => { short = true; },
    failAck:(operation, committed) => { failedAck = {operation, committed}; }};
}

test('F103 JTAG RTT uses AP0 blocks split at 1 KiB and writes only its own bytes', async t => {
  const {memory, probe, usb, requests, info} = fixture(t);
  try {
    await probe.useRttMemory(info);
    assert.match(probe.name, /JTAG MEM-AP/);
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
  assert.deepEqual(requests.filter(r => r[0] === 0x89), [[0x89,255],[0x89,16],[0x89,17]]);
  assert.deepEqual(requests.at(-1), [3]);
});

test('ARM JTAG ACK recovery retries a read and confirms a write without replaying it', async t => {
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
      else await assert.rejects(write, /05 01 03/);
      assert.equal(requests.slice(first).filter(r => r[0] === 5 && r[3] === 13).length, 1);
      assert.equal(probe._faulted, !committed);
    }
    assert.equal(requests.filter(r => r[0] === 0x12 && r[1] === 8).length, 3);
  } finally { await probe.disconnect(); }
});

test('ARM JTAG only retries a read cursor that is still at its previous value', async t => {
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
        await assert.rejects(write, /05 01 03/);
        assert.equal(u32le(memory,cursor-base),current);
      }
      assert.equal(requests.slice(first).filter(r => r[0] === 5 && r[3] === 13).length,expectedWrites);
    }
  } finally { await probe.disconnect(); }
});

test('F103 JTAG mismatched TAP keeps Wasm and a short block prevents later writes', async t => {
  const {probe, usb, requests, info, truncate} = fixture(t);
  probe.jtagTaps[1].enabled = false;
  await probe.useRttMemory(info);
  assert.equal(requests.length, 0);
  probe.jtagTaps[1].enabled = true;
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
