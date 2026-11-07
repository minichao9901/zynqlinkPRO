import { readFile } from 'node:fs/promises';
import { createInterface } from 'node:readline';
import { OpenOcdEtmProbe } from '../../web/app/core/openocd-etm.js';
import { OpenOcdTargetSession } from '../../web/app/core/openocd-session.js';
import { createOpenOcdDispatcher } from '../../web/app/core/openocd-worker.mjs';
import { makeOpenOcdProfile } from '../../web/app/core/openocd-profile.js';

const wasmBinary = await readFile(new URL('../../web/app/core/openocd-runtime/openocd-core.wasm', import.meta.url));
let selected, device, probe, nextUsbId = 0;
const transfers = new Map();
const send = value => process.stdout.write(JSON.stringify(value) + '\n');

function usbCall(method, args){
  return new Promise((resolve, reject) => {
    const id = ++nextUsbId;
    transfers.set(id, { resolve, reject });
    send({ usb:{ id, method, args } });
  });
}

Object.defineProperty(globalThis, 'navigator', { configurable:true, value:{
  usb:{ async getDevices(){ return selected && device ? [device] : []; } },
}});
// As in superlinkPRO's native adapter, run the browser dispatcher in Node
// with the USB handle supplied by the host that already owns the probe.
OpenOcdTargetSession.createWorker = () => {
  let closed = false;
  const worker = {
    postMessage(value){ queueMicrotask(() => dispatch(value)); },
    terminate(){ closed = true; selected = null; },
  };
  const dispatch = createOpenOcdDispatcher({
    wasmBinary,
    select:identity => { selected = identity; },
    post:data => queueMicrotask(() => { if (!closed) worker.onmessage({ data }); }),
  });
  return worker;
};

const input = createInterface({ input:process.stdin });
let pending = false;
input.on('line', async line => {
  const msg = JSON.parse(line);
  if (msg.usbReply){
    const { id, error, value } = msg.usbReply;
    const transfer = transfers.get(id);
    if (!transfer) return;
    transfers.delete(id);
    if (error) transfer.reject(new DOMException(error, 'NetworkError'));
    else transfer.resolve(value);
    return;
  }
  if (pending){ send({ id:msg.id, error:'OpenOCD native command is already in flight' }); return; }
  pending = true;
  try {
    let value;
    if (msg.op === 'check'){
      const link = new OpenOcdTargetSession();
      try {
        await link.open(makeOpenOcdProfile({ memoryAp:true }));
        value = await link.command('capture {workbench.cpu cget -type}');
      } finally { await link.close(); }
    } else if (msg.op === 'open'){
      const inputResult = async (method, args) => {
        const data = Buffer.from(await usbCall(method, args), 'hex');
        return { status:'ok', data:new DataView(data.buffer, data.byteOffset, data.byteLength) };
      };
      device = {
        ...msg.identity, configuration:null,
        async open(){ this.configuration = { configurationValue:await usbCall('open', []) }; },
        async close(){ await usbCall('close', []); },
        selectConfiguration(number){ return usbCall('configuration', [number]); },
        claimInterface(number){ return usbCall('claim', [number]); },
        releaseInterface(number){ return usbCall('release', [number]); },
        controlTransferIn(setup, length){ return inputResult('descriptor', [setup,length]); },
        transferIn(endpoint, length){ return inputResult('read', [endpoint,length]); },
        async transferOut(endpoint, bytes){
          return { status:'ok', bytesWritten:await usbCall('write', [endpoint,Buffer.from(bytes).toString('hex')]) };
        },
      };
      probe = await OpenOcdEtmProbe.open(device, { clockKhz:msg.clockKhz });
      value = probe.idcode;
    } else if (msg.op === 'read'){
      value = Buffer.from(await probe.readMem(msg.address, msg.length)).toString('hex');
    } else if (msg.op === 'write'){
      await probe.writeMem(msg.address, new Uint8Array(Buffer.from(msg.data,'hex')));
    } else if (msg.op === 'close'){
      await probe?.disconnect();
      probe = device = null;
    } else throw Error('Unknown OpenOCD native command');
    send({ id:msg.id, value:value ?? null });
  } catch (error){ send({ id:msg.id, error:error.message }); }
  finally { pending = false; }
});
