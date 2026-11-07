import { withTimeout } from './pace.js';
import { UsbLease } from './usb-device.js';
import { nativeProbeEnabled, nativeUsbDevices } from './native-probe.js';

const filter = { vendorId:0x0d28 };
const readResult = ({ status, data }) => ({ status, data });

async function syncZynqQueue(device){
  const control = (request, length) => device.controlTransferIn({
    requestType:'vendor', recipient:'device', request, value:0x4441, index:0x5052,
  }, length);
  const before = await control(0x5b, 32);
  // Older firmware lacks the queue status request.
  if (before.status === 'stall') return;
  if (before.status !== 'ok' || before.data?.byteLength !== 32) throw Error('DAP 队列状态无效');
  const reset = await control(0x5a, 4);
  if (reset.status !== 'ok' || reset.data?.byteLength !== 4 || reset.data.getUint32(0, true) !== 0x504144)
    throw Error('DAP 队列复位未确认');
  await device.clearHalt('in', 1);
  await device.clearHalt('out', 2);
  const after = await control(0x5b, 32);
  if (after.status !== 'ok' || after.data?.byteLength !== 32 ||
      after.data.getUint32(12, true) === before.data.getUint32(12, true) ||
      [0,4,8].some(offset => after.data.getUint32(offset, true)))
    throw Error('DAP 队列新 epoch 或空闲状态未确认');
}

export async function selectOpenOcdDevice({ all = false, forcePick = false } = {}){
  if (nativeProbeEnabled()){
    const devices = await nativeUsbDevices();
    if (devices.length !== 1) throw Error('本机探针服务需要唯一 ZynqDAP');
    return devices[0];
  }
  const usb = globalThis.navigator?.usb;
  if (!usb) throw Error('OpenOCD Wasm 需要 WebUSB 或本机探针服务');
  const devices = forcePick ? [] : await withTimeout(usb.getDevices(), 5000, '枚举已授权探针');
  const matching = devices.filter(d => d.vendorId === filter.vendorId || /CMSIS-DAP/i.test(d.productName));
  return matching.length === 1 ? matching[0] : usb.requestDevice({ filters:all ? [] : [filter] });
}

export const openOcdUsbSupported = () => nativeProbeEnabled() || !!globalThis.navigator?.usb;

// libusb performs USB calls from the Wasm worker. Keep the actual handle and
// native-service delivery identity with the workbench's existing USB lease.
export class OpenOcdUsb {
  constructor(device){
    this.lease = new UsbLease(device, 'dap');
    this.device = this.lease.device;
    this.zynq = device.nativeService || (device.vendorId === 0x0d28 &&
      device.productId === 0x0204 && device.manufacturerName === 'CherryUSB');
  }

  async invoke(method, args){
    const d = this.device;
    switch (method){
      case 'open':
        await this.lease.open();
        return { configurationValue:d.configuration.configurationValue };
      case 'close': return this.close();
      case 'controlTransferIn': {
        const [setup, length] = args;
        if (setup.requestType !== 'standard' || setup.recipient !== 'device' ||
            setup.request !== 6 || ![1,2,3].includes(setup.value >>> 8))
          throw Error('OpenOCD USB 仅允许读取标准描述符');
        return readResult(await d.controlTransferIn(setup, length));
      }
      case 'selectConfiguration':
        if (args[0] !== d.configuration.configurationValue) throw Error('OpenOCD 不切换 USB 设备配置');
        return { configurationValue:args[0] };
      case 'claimInterface': {
        const iface = d.configuration.interfaces.find(i => i.interfaceNumber === args[0]);
        const endpoints = iface?.alternate.endpoints.filter(e => e.type === 'bulk') || [];
        const [out, input] = endpoints;
        if (out?.direction !== 'out' || input?.direction !== 'in' ||
            (this.zynq && (iface.interfaceNumber !== 0 || out.endpointNumber !== 2 || input.endpointNumber !== 1)))
          throw Error('USB 接口不是 CMSIS-DAP v2');
        await this.lease.claim(iface.interfaceNumber, [out.endpointNumber, input.endpointNumber | 128]);
        if (this.zynq && !d.nativeService) await syncZynqQueue(d);
        this.out = out;
        this.input = input;
        return;
      }
      case 'releaseInterface':
        await this.lease.release(args[0]);
        this.out = this.input = null;
        return;
      case 'transferIn':
        if (args[0] !== this.input?.endpointNumber) throw Error('OpenOCD 只能读 DAP IN 端点');
        return readResult(await d.transferIn(...args));
      case 'transferOut': {
        const [endpoint, data] = args;
        if (endpoint !== this.out?.endpointNumber) throw Error('OpenOCD 只能写 DAP OUT 端点');
        const result = await d.transferOut(endpoint, data);
        // The Zynq firmware's 4096-byte receive buffer ends on a short
        // packet. A smaller integral number of USB packets needs a ZLP.
        if (this.zynq && result.status === 'ok' && result.bytesWritten === data.byteLength &&
            data.byteLength > 0 && data.byteLength < 4096 && data.byteLength % this.out.packetSize === 0){
          const end = await d.transferOut(endpoint, new Uint8Array());
          if (end.status !== 'ok') return { status:end.status, bytesWritten:end.bytesWritten };
        }
        return { status:result.status, bytesWritten:result.bytesWritten };
      }
      default: throw Error('OpenOCD USB 操作不受支持：' + method);
    }
  }

  async close(){
    await this.lease.close();
    this.out = this.input = null;
  }
}
