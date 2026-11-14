import { OpenOcdProbe } from '../core/openocd-probe.js';
import { OpenOcdUsb } from '../core/openocd-usb.js';
import { u32leBytes } from '../core/bin.js';
import { withTimeout } from '../core/pace.js';
import { ENTRY } from './protocol.js';

const USB_PACKET = 4096;
const READ_BLOCK = USB_PACKET - 4;
const WRITE_BLOCK = USB_PACKET - 8;

function inSram(address, length){
  const end = address + length;
  if (!Number.isInteger(address) || !Number.isInteger(length) || length <= 0) return false;
  return address >= 0 && end <= 0x40000 ||
    address >= 0x01240000 && end <= 0x01280000 ||
    address >= 0xf0400000 && end <= 0xf0408000;
}

const transfer = (request, value) => [request, ...u32leBytes(value)];

// The PL owns the TAP during RTT streaming. OpenOCD owns it during scans
// and target control. Never mix the two TAP state machines on an open link.
export class Hpm6800RttProbe extends OpenOcdProbe {
  get _faulted(){ return !!this.sbaFault || super._faulted; }

  async useRttMemory(info){
    if (this.sbaUnavailable || this.sbaUsb) return;
    const entries = [...info.up, ...info.down];
    if (!info.up[0]?.size || !inSram(info.addr, 24 + ENTRY * entries.length) ||
        entries.some(e => e.size && !inSram(e.pbuf, e.size))) return;

    // Retain immutable fields from the already validated Wasm connection.
    const expected = await super.readMem(info.addr, ENTRY + 12);
    await super.disconnect();
    try {
      const usb = this.sbaUsb = new OpenOcdUsb(this.device, 'RTT Viewer');
      await usb.invoke('open', []);
      await usb.invoke('claimInterface', [0]);
      if (!usb.synchronized) throw Error('探针未确认 DAP 队列边界');
      await this._exchange([2, 2], [2, 2]);
      this.sbaConnected = true;
      // J7 vendor command selects the RISC-V IDCODE instruction and the
      // PL SBA frontend for subsequent CMSIS-DAP transfers.
      await this._exchange([0x8b, 1], [0x8b, 0, 1]);
      await this._exchange([0x15, 1, 5], [0x15, 0]);
      await this._exchange([0x04, 8, 64, 0, 0, 0], [0x04, 0]);
      await this._exchange([0x11, ...u32leBytes(this.clockHz)], [0x11, 0]);
      await this._exchange([0x16, 0], [0x16, 0, ...u32leBytes(this.idcode)]);
      // Clear stale SBA errors and activate the DM, keeping the hart running.
      await this._exchange([5, 0, 2, ...transfer(0, 0x1e), ...transfer(4, 0x50000032)], [5, 2, 1]);
      const observed = await this.readMem(info.addr, expected.length);
      if (!observed.every((byte, i) => byte === expected[i]))
        throw Error('探针 SBA 回读的 RTT 标识或通道配置不一致');
      this.name = 'zynqlinkPRO / JTAG SBA';
      this.onLog?.('RTT Viewer 使用探针 JTAG SBA 块传输');
    } catch (error){
      await this._closeSba();
      this.sbaUnavailable = true;
      this.onLog?.('RTT Viewer 使用 OpenOCD Wasm：' + error.message);
      await super.connect();
    }
  }

  async prepareRttScan(){
    if (!this.sbaUsb) return;
    await this._closeSba();
    await super.connect();
  }

  async reset(halt){
    await this.prepareRttScan();
    return super.reset(halt);
  }

  async disconnect(){
    await this._closeSba();
    await super.disconnect();
  }

  async _closeSba(){
    const usb = this.sbaUsb;
    if (!usb) return;
    try {
      // A missing response may still be in flight. Close the interface
      // without appending a command to an ambiguous response stream.
      if (this.sbaConnected && !this.sbaFault){
        try { await this._exchange([3], [3, 0]); }
        catch (error){ this.onLog?.('RTT Viewer 断开命令未确认：' + error.message); }
      }
    } finally {
      await usb.close();
      this.sbaUsb = null;
      this.sbaConnected = false;
      this.sbaFault = null;
      this.name = 'OpenOCD Wasm / WebUSB';
    }
  }

  async _exchange(request, expected, length = expected.length){
    if (this.sbaFault) throw this.sbaFault;
    const usb = this.sbaUsb, device = usb.device;
    const bytes = Uint8Array.from(request);
    try {
      let result;
      if (device.atomicDapSupported) result = await device.exchangeDap(bytes, USB_PACKET);
      else {
        // Keep the raw write to one transfer so timeout cannot leave a late ZLP.
        // Current requests (5 + a multiple of 4 for writes) always end short.
        const out = await withTimeout(device.transferOut(2, bytes), 2000, 'JTAG SBA 写请求');
        if (out.status !== 'ok' || out.bytesWritten !== bytes.length) throw Error('DAP 请求短写');
        result = await withTimeout(device.transferIn(1, USB_PACKET), 2000, 'JTAG SBA 读响应');
      }
      const reply = result.data && new Uint8Array(result.data.buffer, result.data.byteOffset, result.data.byteLength);
      if (result.status !== 'ok' || reply?.length !== length || !expected.every((n, i) => n === reply[i]))
        throw Error('JTAG SBA 响应状态或长度错误');
      return reply.subarray(expected.length);
    } catch (error){
      this.sbaFault = error;
      throw error;
    }
  }

  _address(address){
    return this._exchange([5, 0, 3, ...transfer(8, 0), ...transfer(1, 0x23000052), ...transfer(5, address)], [5, 3, 1]);
  }

  async readMem(address, length){
    if (!this.sbaUsb) return super.readMem(address, length);
    if (length === 0) return new Uint8Array();
    if (!inSram(address, length)) throw Error('RTT 缓冲地址已变更或超出 HPM6800 SRAM，请重新扫描');
    const start = address - address % 4, end = Math.ceil((address + length) / 4) * 4;
    const data = new Uint8Array(end - start);
    for (let at = start; at < end;){
      const size = Math.min(end - at, READ_BLOCK);
      const words = size / 4, lo = words & 255, hi = words >>> 8;
      await this._address(at);
      data.set(await this._exchange([6, 0, lo, hi, 15], [6, lo, hi, 1], size + 4), at - start);
      at += size;
    }
    return data.subarray(address - start, address - start + length);
  }

  async writeMem(address, bytes){
    if (!this.sbaUsb) return super.writeMem(address, bytes);
    if (!bytes.length) return;
    if (!inSram(address, bytes.length)) throw Error('RTT 缓冲地址已变更或超出 HPM6800 SRAM，请重新扫描');
    const start = address - address % 4, end = Math.ceil((address + bytes.length) / 4) * 4;
    const data = new Uint8Array(end - start);
    if (start !== address) data.set(await this.readMem(start, 4));
    if (end !== address + bytes.length && (end - start !== 4 || start === address))
      data.set(await this.readMem(end - 4, 4), data.length - 4);
    data.set(bytes, address - start);
    for (let at = start; at < end;){
      const size = Math.min(end - at, WRITE_BLOCK);
      const words = size / 4, lo = words & 255, hi = words >>> 8;
      await this._address(at);
      await this._exchange([6, 0, lo, hi, 13, ...data.subarray(at - start, at - start + size)], [6, lo, hi, 1]);
      await this._exchange([5, 0, 1, 14], [5, 1, 1], 7);
      at += size;
    }
  }
}
