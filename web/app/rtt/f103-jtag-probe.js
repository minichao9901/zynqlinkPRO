import { OpenOcdEtmProbe } from '../core/openocd-etm.js';
import { OpenOcdUsb } from '../core/openocd-usb.js';
import { u32le, u32leBytes } from '../core/bin.js';
import { exchangeRttDap } from './dap-exchange.js';
import { CB_ID, ENTRY } from './protocol.js';

const ARM_TAP = 0x3ba00477, BOUNDARY_TAP = 0x06414041;
const CPUID = 0xe000ed00, DBGMCU_IDCODE = 0xe0042000;
const SRAM_START = 0x20000000, SRAM_END = 0x20010000;
const TAR_PAGE = 1024;

function inSram(address, length){
  return Number.isInteger(address) && Number.isInteger(length) && length > 0 &&
    address >= SRAM_START && address + length <= SRAM_END;
}

const transfer = (request, value) => [request, ...u32leBytes(value)];
const matchesF103 = (cpuid, device) => (cpuid >>> 4 & 0xfff) === 0xc23 && (device & 0xfff) === 0x414;

class F103MemAp {
  constructor(usb){ this.usb = usb; }

  async exchange(request, expected, length){
    if (this.fault) throw this.fault;
    try { return await exchangeRttDap(this.usb.device, request, expected, length); }
    catch (error){ this.fault = error; throw error; }
  }

  async open(clockHz){
    await this.usb.invoke('open', []);
    // The ARM/JTAG claim runs the SWJ select sequence before handing over.
    await this.usb.invoke('claimInterface', [0]);
    if (!this.usb.synchronized) throw Error('探针未确认 DAP 队列边界');
    await this.exchange([2, 2], [2, 2]);
    this.connected = true;
    await this.exchange([0x8b, 0x0e], [0x8b, 0, 0x0e]);
    await this.exchange([0x15, 2, 4, 5], [0x15, 0]);
    // Allow the running F103 AHB-AP to settle between high-rate scans.
    await this.exchange([0x04, 15, 64, 0, 0, 0], [0x04, 0]);
    await this.exchange([0x11, ...u32leBytes(clockHz)], [0x11, 0]);
    await this.checkTap();
    if (clockHz === 60_000_000){
      const [phase] = await this.exchange([0x89, 255], [0x89, 0], 15);
      if (phase === 17){
        // Keep the previous-bit window, with the other capture edge. The
        // auto-selected mode 17 can pass discovery yet drop ACKs on a stream.
        await this.exchange([0x89, 16], [0x89, 0, 16], 15);
        this.previousPhase = phase;
        await this.checkTap();
      }
    }
  }

  async checkTap(){
    await this.exchange([0x16, 0], [0x16, 0, ...u32leBytes(ARM_TAP)]);
    await this.exchange([5, 0, 2, ...transfer(0, 0x1e), ...transfer(4, 0x50000032)], [5, 2, 1]);
  }

  async recoverAck(error){
    const reply = error.dapReply;
    // Accept only a framed probe reply for the observed ARM/JTAG ACK 3.
    // A short/late USB read still requires a new lease and queue epoch.
    const scalar = reply?.[0] === 5 && reply.length === 3 && reply[2] === 3;
    const block = reply?.[0] === 6 && reply.length >= 4 && reply[3] === 3 &&
      reply.length === 4 + (reply[1] + reply[2] * 256) * 4;
    if (!scalar && !block) throw error;
    this.fault = null;
    await this.exchange([0x12, 8, 0x7f], [0x12, 0]);
    await this.checkTap();
  }

  async close(){
    let failure;
    try {
      if (this.previousPhase !== undefined && !this.fault)
        await this.exchange([0x89, this.previousPhase], [0x89, 0, this.previousPhase], 15);
      if (this.connected && !this.fault) await this.exchange([3], [3, 0]);
    } catch (error){ failure = error; }
    await this.usb.close();
    this.connected = false;
    return failure;
  }

  address(address, csw){
    return this.exchange([5, 0, 3, ...transfer(8, 0), ...transfer(1, csw), ...transfer(5, address)], [5, 3, 1]);
  }

  async read(address, length, retry = true){
    const start = address - address % 4;
    const data = new Uint8Array(Math.ceil((address - start + length) / 4) * 4);
    for (let offset = 0; offset < data.length;){
      const at = start + offset;
      const size = Math.min(data.length - offset, TAR_PAGE - at % TAR_PAGE);
      const count = size / 4, lo = count & 255, hi = count >>> 8;
      const readBlock = async () => {
        await this.address(at, 0x23000052);
        return this.exchange([6, 0, lo, hi, 15], [6, lo, hi, 1], size + 4);
      };
      try { data.set(await readBlock(), offset); }
      catch (error){
        if (!retry) throw error;
        await this.recoverAck(error);
        data.set(await readBlock(), offset);
      }
      offset += size;
    }
    return data.subarray(address - start, address - start + length);
  }

  async confirmedWrite(address, bytes, csw, packet, count){
    await this.writeAddress(address, csw);
    try { await this.exchange(packet, [5, count, 1]); }
    catch (error){
      await this.recoverAck(error);
      const observed = await this.read(address, bytes.length, false);
      if (!bytes.every((byte, i) => byte === observed[i])){
        this.fault = error;
        throw error;
      }
    }
  }

  async writeAddress(address, csw){
    try { await this.address(address, csw); }
    catch (error){
      await this.recoverAck(error);
      await this.address(address, csw);
    }
  }

  async writeReadOffset(address, next, previous){
    const packet = [5, 0, 1, ...transfer(13, next)];
    await this.writeAddress(address, 0x23000052);
    try { await this.exchange(packet, [5, 1, 1]); }
    catch (error){
      await this.recoverAck(error);
      const observed = u32le(await this.read(address, 4, false));
      if (observed === next) return;
      if (observed !== previous){ this.fault = error; throw error; }
      // The probe replied and the host-owned cursor is still at the old
      // value. Commit once more, without replaying any payload writes.
      await this.confirmedWrite(address, u32leBytes(next), 0x23000052, packet, 1);
    }
  }

  async write(address, bytes){
    for (let offset = 0; offset < bytes.length;){
      const at = address + offset;
      const remaining = bytes.length - offset;
      const wordAligned = at % 4 === 0 && remaining >= 4;
      if (wordAligned){
        const size = Math.min(remaining - remaining % 4, TAR_PAGE - at % TAR_PAGE, 255 * 4);
        const count = size / 4;
        // Keep write completion on the ordinary DAP_Transfer path. At 60 MHz the block
        // writer has returned an invalid ACK during the final posted fence.
        const packet = [5, 0, count];
        for (let i = 0; i < size; i += 4) packet.push(13, ...bytes.subarray(offset + i, offset + i + 4));
        await this.confirmedWrite(at, bytes.subarray(offset, offset + size), 0x23000052, packet, count);
        offset += size;
      } else {
        // Byte lanes preserve adjacent bytes, including unaligned ring edges.
        const packet = [5, 0, 1, ...transfer(13, bytes[offset] << (8 * (at % 4)))];
        await this.confirmedWrite(at, bytes.subarray(offset, offset + 1), 0x23000050, packet, 1);
        offset++;
      }
    }
  }
}

export class F103JtagRttProbe extends OpenOcdEtmProbe {
  get _faulted(){ return !!this.memAp?.fault || super._faulted; }

  async useRttMemory(info){
    if (this.blockUnavailable || this.memAp) return;
    const taps = this.jtagTaps;
    if (this.idcode !== ARM_TAP || taps?.length !== 2 ||
        !taps.every((t, i) => t.enabled && t.index === i && t.irLength === 4 + i &&
          t.idcode === (i ? BOUNDARY_TAP : ARM_TAP))) return;
    const entries = [...info.up, ...info.down];
    const headerSize = 24 + ENTRY * entries.length;
    if (!inSram(info.addr, headerSize) || !info.up[0]?.size ||
        entries.some(e => e.size && !inSram(e.pbuf, e.size))) return;
    const [cpuid, device] = await Promise.all([CPUID, DBGMCU_IDCODE].map(async at => u32le(await super.readMem(at, 4))));
    if (!matchesF103(cpuid, device)) return;
    if (await this.command(`${this.target} cget -ap-num`) !== '0') return;
    const expected = await super.readMem(info.addr, headerSize);
    if (!headerMatches(expected, info, entries)) return;
    await super.disconnect();
    try {
      const mem = this.memAp = new F103MemAp(new OpenOcdUsb(this.device, 'RTT Viewer', true));
      await mem.open(this.clockHz);
      if (u32le(await mem.read(CPUID, 4)) !== cpuid || u32le(await mem.read(DBGMCU_IDCODE, 4)) !== device)
        throw Error('J7 MEM-AP 的 F103 身份与 OpenOCD 不一致');
      const observed = await mem.read(info.addr, headerSize);
      if (!headerMatches(observed, info, entries))
        throw Error('J7 MEM-AP 的 RTT 标识或通道配置与 OpenOCD 不一致');
      this.rttRegions = [[info.addr, headerSize], ...entries.filter(e => e.size).map(e => [e.pbuf, e.size])];
      this.upChannels = info.maxUp;
      this.rttPollLimit = 8192;
      this.rttLivePreview = false;
      this.name = 'zynqlinkPRO / JTAG MEM-AP';
    } catch (error){
      await this._closeMemAp();
      this.blockUnavailable = true;
      this.onLog?.('RTT Viewer 使用 OpenOCD Wasm：' + error.message);
      await super.connect();
    }
  }

  async _closeMemAp(){
    if (!this.memAp) return;
    const failure = await this.memAp.close();
    this.memAp = null;
    this.rttRegions = null;
    this.rttPollLimit = 512;
    this.rttLivePreview = true;
    this.name = 'OpenOCD Wasm / WebUSB';
    if (failure) this.onLog?.('RTT Viewer 断开命令未确认：' + failure.message);
  }

  async prepareRttScan(){
    if (!this.memAp) return;
    await this._closeMemAp();
    await super.connect();
  }

  async reset(){
    await this.prepareRttScan();
    return super.reset();
  }

  async disconnect(){
    await this._closeMemAp();
    await super.disconnect();
  }

  _checkRttRange(address, length){
    if (!inSram(address, length) || !this.rttRegions.some(([start, size]) =>
      address >= start && address + length <= start + size))
      throw Error('RTT 地址已变更或超出已确认的 F103 SRAM 缓冲，请重新扫描');
  }

  async readMem(address, length){
    if (!this.memAp) return super.readMem(address, length);
    if (!length) return new Uint8Array();
    this._checkRttRange(address, length);
    return this.memAp.read(address, length);
  }

  async writeMem(address, bytes){
    if (!this.memAp) return super.writeMem(address, bytes);
    if (!bytes.length) return;
    this._checkRttRange(address, bytes.length);
    await this.memAp.write(address, bytes);
  }

  async writeRttReadOffset(address, next, previous){
    if (!this.memAp) return super.writeMem(address, u32leBytes(next));
    const [header] = this.rttRegions[0];
    const offset = address - header - 24;
    if (offset < 0 || offset >= this.upChannels * ENTRY || offset % ENTRY !== 16)
      throw Error('RTT 读游标地址超出已确认的控制块');
    await this.memAp.writeReadOffset(address, next, previous);
  }
}

function headerMatches(bytes, info, entries){
  if (!Array.from(CB_ID).every((letter, i) => bytes[i] === letter.charCodeAt(0)) ||
      u32le(bytes, 16) !== info.maxUp || u32le(bytes, 20) !== info.maxDown) return false;
  return entries.every(({pbuf, size, flags}, i) => {
    const at = 24 + i * ENTRY;
    return u32le(bytes, at + 4) === pbuf && u32le(bytes, at + 8) === size && u32le(bytes, at + 20) === flags;
  });
}
