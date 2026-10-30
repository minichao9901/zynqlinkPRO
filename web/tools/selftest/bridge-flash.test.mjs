import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {spawn} from 'node:child_process';
import {firmwareLoadBytes,releaseBackend} from '../../bridge/rtt-bridge.mjs';

test('flash accounting uses ELF load bytes instead of debug-bearing file size',()=>{
  const bytes=fs.readFileSync(new URL('../../../etm-service/firmware/stm32f103_cdc_trace/fw-ze.elf',import.meta.url));
  assert.equal(firmwareLoadBytes('fw.elf',bytes),20168);
  assert(bytes.length>1000000);
});
test('release waits for the owned backend child to exit before confirming USB availability',async()=>{
  const child=spawn(process.execPath,['-e','setInterval(()=>{},1000)'],{stdio:'ignore',windowsHide:true});
  await new Promise((resolve,reject)=>{child.once('spawn',resolve);child.once('error',reject);});
  let stopped=false;
  await releaseBackend({child,stop(){stopped=true;child.kill();}});
  assert(stopped);
  assert(child.exitCode!==null||child.signalCode!==null);
});
