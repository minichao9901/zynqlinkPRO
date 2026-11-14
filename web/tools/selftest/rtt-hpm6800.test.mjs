import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Hpm6800RttProbe } from '../../app/rtt/hpm6800-probe.js';
import { u32le } from '../../app/core/bin.js';

function fixture(){
  const base = 0x01240000;
  const memory = Uint8Array.from({ length:16384 }, (_, i) => (i * 13 + (i >>> 8)) & 255);
  const requests = [];
  let tar, truncate = false;
  const probe = new Hpm6800RttProbe({}, { arch:'riscv', clockKhz:8000 }, undefined, true);
  probe.sbaUsb = { device:{ atomicDapSupported:true, async exchangeDap(request, length){
    assert.equal(length, 4096);
    requests.push([...request]);
    let response;
    if (request[0] === 5 && request[2] === 3){
      tar = u32le(request, 14);
      assert.equal(tar % 4, 0);
      response = [5, 3, 1];
    } else if (request[0] === 6){
      const size = (request[2] + 256 * request[3]) * 4;
      response = [6, request[2], request[3], 1];
      if (request[4] === 15) response.push(...memory.subarray(tar - base, tar - base + size - (truncate ? 4 : 0)));
      else memory.set(request.subarray(5), tar - base);
    } else {
      assert.deepEqual([...request], [5, 0, 1, 14]);
      response = [5, 1, 1, 0, 0, 0, 0];
    }
    return { status:'ok', data:new DataView(Uint8Array.from(response).buffer) };
  } } };
  return { base, memory, requests, probe, truncate:() => { truncate = true; } };
}

test('HPM6800 RTT uses bounded SBA blocks and preserves unaligned write edges', async () => {
  const { base, memory, requests, probe } = fixture();
  assert.deepEqual(await probe.readMem(base + 3, 8192), memory.slice(3, 8195));
  assert.equal(requests.length, 6);
  assert.deepEqual(requests.filter(r => r[0] === 6).map(r => r.slice(2)), [[255, 3, 15], [255, 3, 15], [3, 0, 15]]);
  const before = memory.slice();
  await probe.writeMem(base + 1, Uint8Array.of(222, 223));
  before.set([222, 223], 1);
  assert.deepEqual(memory, before);
  assert.deepEqual(requests.at(-1), [5, 0, 1, 14]);
  await assert.rejects(probe.readMem(0x80000000, 4), /SRAM/);
  await assert.rejects(probe.writeMem(0xf0407ffc, Uint8Array.of(1, 2, 3, 4, 5)), /SRAM/);
  assert.equal(requests.length, 11);
});

test('short JTAG SBA reports fault before advancing the RTT read cursor', async () => {
  const { base, probe, requests, truncate } = fixture();
  truncate();
  await assert.rejects(probe.readMem(base, 8192), /响应状态或长度错误/);
  await assert.rejects(probe.writeMem(base, Uint8Array.of(1, 2, 3, 4)), /响应状态或长度错误/);
  assert.equal(probe._faulted, true);
  assert.equal(requests.length, 2);
});
