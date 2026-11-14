import { withTimeout } from './pace.js';
import { UsbLease } from './usb-device.js';
import { nativeProbeEnabled, nativeUsbDevices } from './native-probe.js';

const filter = { vendorId:0x0d28 };
const readResult = ({ status, data }) => ({ status, data });
let selectedDevice = null;

export const isZynqDapDevice = device => device?.vendorId === 0x0d28 && device.productId === 0x0204 &&
  device.manufacturerName === 'CherryUSB' && device.productName === 'CMSIS-DAP';

export function rememberOpenOcdDevice(device){ selectedDevice = device; }

export async function authorizedOpenOcdDevices(){
  if (nativeProbeEnabled()) return await nativeUsbDevices();
  const usb = globalThis.navigator?.usb;
  if (!usb) return [];
  const devices = await withTimeout(usb.getDevices(), 5000, '枚举已授权探针');
  return devices.includes(selectedDevice) ? [selectedDevice] : devices;
}

async function syncZynqQueue(device){
  const control = (request, length) => device.controlTransferIn({
    requestType:'vendor', recipient:'device', request, value:0x4441, index:0x5052,
  }, length);
  const before = await control(0x5b, 32);
  // Older firmware lacks the queue status request.
  if (before.status === 'stall') return false;
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
  return true;
}

export async function selectOpenOcdDevice({ all = false, forcePick = false } = {}){
  if (nativeProbeEnabled()){
    const devices = await nativeUsbDevices();
    if (devices.length !== 1) throw Error('本机探针服务需要唯一的 zynqlinkPRO 探针');
    return devices[0];
  }
  const usb = globalThis.navigator?.usb;
  if (!usb) throw Error('OpenOCD Wasm 需要 WebUSB 或本机探针服务');
  const devices = forcePick ? [] : await authorizedOpenOcdDevices();
  if (devices.includes(selectedDevice)) return selectedDevice;
  const matching = devices.filter(d => d.vendorId === filter.vendorId || /CMSIS-DAP/i.test(d.productName));
  if (matching.length === 1) return matching[0];
  return await usb.requestDevice({ filters:all ? [] : [filter] });
}

export const openOcdUsbSupported = () => nativeProbeEnabled() || !!globalThis.navigator?.usb;

// libusb performs USB calls from the Wasm worker. Keep the actual handle and
// native-service delivery identity with the workbench's existing USB lease.
export class OpenOcdUsb {
  constructor(device, owner = 'dap', armJtag = false){
    this.lease = new UsbLease(device, owner);
    this.device = this.lease.device;
    this.zynq = device.nativeService || (device.vendorId === 0x0d28 &&
      device.productId === 0x0204 && device.manufacturerName === 'CherryUSB');
    this.armJtag = this.zynq && armJtag;
  }

  async _selectArmJtag(){
    let synchronized = true;
    const send = async (packet, expected) => {
      const bytes = Uint8Array.from(packet);
      synchronized = false;
      let reply;
      if (this.device.atomicDapSupported) reply = await this.device.exchangeDap(bytes, 4096);
      else {
        const result = await withTimeout(this.device.transferOut(this.out.endpointNumber, bytes), 2000, 'ARM JTAG 发送');
        if (result.status !== 'ok' || result.bytesWritten !== bytes.length) throw Error('ARM JTAG 选择命令发送失败');
        reply = await withTimeout(this.device.transferIn(this.input.endpointNumber, 4096), 2000, 'ARM JTAG 响应');
      }
      const { status, data } = reply;
      synchronized = status === 'ok' && data?.byteLength >= 2 && data.getUint8(0) === bytes[0];
      if (!synchronized || data.getUint8(1) !== expected) throw Error('ARM JTAG 选择命令未确认');
    };
    try {
      await send([2, 2], 2);
      // Select SWJ at 1 MHz. OpenOCD sets its configured TCK during init.
      await send([0x11, 0x40, 0x42, 0x0f, 0], 0);
      await send([0x12, 88, ...Array(8).fill(0xff), 0x3c, 0xe7, 0x1f], 0);
    } finally {
      // A missing reply leaves the stream ambiguous. Close the lease so a
      // later session can synchronize a new epoch without replaying any write.
      if (synchronized) await send([3], 0);
    }
  }

  async prepareArmJtagStream(clockHz){
    if (!this.armJtag) throw Error('ARM/JTAG 采样和转发需要支持该模式的 zynqlinkPRO 探针');
    let connected = false, framed = true;
    const send = async (packet, expected, length = 2) => {
      const bytes = Uint8Array.from(packet);
      framed = false;
      const write = this.device.atomicDapSupported ? null
        : await withTimeout(this.device.transferOut(2, bytes), 2000, 'ARM/JTAG 请求');
      if (write && (write.status !== 'ok' || write.bytesWritten !== bytes.length)) throw Error('ARM/JTAG 准备命令短写');
      const {status, data} = write ? await withTimeout(this.device.transferIn(1, 4096), 2000, 'ARM/JTAG 应答')
        : await this.device.exchangeDap(bytes, 4096);
      framed = status === 'ok' && data?.byteLength >= 2 && data.getUint8(0) === packet[0];
      if (!framed || data.byteLength !== length || data.getUint8(1) !== expected)
        throw Error('ARM/JTAG 准备命令未确认');
      return data;
    };
    try {
      await this.invoke('open', []);
      await this.invoke('claimInterface', [0]);
      if (!this.synchronized) throw Error('探针未确认 DAP 队列边界');
      await send([2, 2], 2);
      connected = true;
      const instruction = await send([0x8b, 0x0e], 0, 3);
      if (instruction.getUint8(2) !== 0x0e) throw Error('ARM/JTAG IDCODE 指令回读不符');
      await send([0x11, 0x40, 0x42, 0x0f, 0], 0);
      // STM32F103ZE and STM32H743 expose the ARM DP and a boundary TAP.
      // The ARM MEM-AP timing calibration runs against the CPU TAP, so
      // read both reset-default IDCODEs in one raw 64-bit DR scan.
      const sequence = [0x14, 5, 0x46, 0x3f, 1, 0, 0x42, 3, 1, 0, 0x80, ...Array(8).fill(0xff)];
      const observed = await send(sequence, 0, 10);
      const cpu = observed.getUint32(2, true), boundary = observed.getUint32(6, true);
      if (!((cpu === 0x3ba00477 && boundary === 0x06414041) ||
            (cpu === 0x6ba00477 && boundary === 0x06450041)))
        throw Error('ARM/JTAG 未识别到受支持的 STM32F103ZE/H743 双 TAP');
      await send([0x14, 2, 0x46, 0x3f, 1, 0], 0);
      await send([0x15, 2, 4, 5], 0);
      const hz = new Uint8Array(4);
      new DataView(hz.buffer).setUint32(0, clockHz, true);
      await send([0x11, ...hz], 0);
      if ((await send([0x16, 0], 0, 6)).getUint32(2, true) !== cpu)
        throw Error('ARM/JTAG CPU TAP 未在所选 TCK 读回');
      return {cpu, boundary};
    } finally {
      try { if (connected && framed) await send([3], 0); }
      finally { await this.close(); }
    }
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
        this.synchronized = d.nativeService ? d.dapSynchronized : this.zynq && await syncZynqQueue(d);
        this.out = out;
        this.input = input;
        if (this.armJtag) await this._selectArmJtag();
        return;
      }
      case 'releaseInterface':
        await this.lease.release(args[0]);
        this.synchronized = false;
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
    this.synchronized = false;
    this.out = this.input = null;
  }
}
