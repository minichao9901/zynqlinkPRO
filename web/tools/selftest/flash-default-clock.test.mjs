import test from 'node:test';
import assert from 'node:assert/strict';
import { FlashRunner } from '../../app/flash/runner.js';

test('default flash data transfer uses 10MHz and restores 1MHz execution control', async () => {
  const clocks=[];
  const probe={setClock:async hz=>clocks.push(hz),readMem:async()=>Uint8Array.of(1,2,3)};
  const data=await new FlashRunner(probe).data.readMem(0x20000000,3);
  assert.deepEqual([...data],[1,2,3]);
  assert.deepEqual(clocks,[10000000,1000000]);
});

test('explicit flash clock remains selected and failed transfer restores execution control', async () => {
  const clocks=[];
  const probe={setClock:async hz=>clocks.push(hz),readMem:async()=>{throw new Error('read failed');}};
  await assert.rejects(new FlashRunner(probe,{clockKhz:4000}).data.readMem(0x20000000,3),/4 MHz/);
  assert.deepEqual(clocks,[4000000,1000000]);
});
