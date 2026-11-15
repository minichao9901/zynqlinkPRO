import { OpenOcdEtmProbe } from '../core/openocd-etm.js';
import { OpenOcdUsb } from '../core/openocd-usb.js';
import { u32le, u32leBytes } from '../core/bin.js';
import { exchangeRttDap } from './dap-exchange.js';
import { CB_ID, ENTRY } from './protocol.js';

const CORTEX_M_SRAM = { start:0x20000000, end:0x40000000 };
const TAR_PAGE = 1024;
const CSW_SIZE_INCREMENT = 0x37;

function inRange(address, length, start, end){
  return Number.isInteger(address) && Number.isInteger(length) && length > 0 &&
    address >= start && address + length <= end;
}

const transfer = (request, value) => [request, ...u32leBytes(value)];
const validId = id => Number.isInteger(id) && id > 0 && id < 0xffffffff;
const isMemAp = id => validId(id) && (id >>> 13 & 0xf) === 8;

class ArmMemAp {
  constructor(usb, port){
    this.usb = usb;
    this.port = port;
    this.select = port.ap * 0x1000000;
    this.csw = port.csw & ~CSW_SIZE_INCREMENT;
  }

  async exchange(request, expected, length){
    if (this.fault) throw this.fault;
    try { return await exchangeRttDap(this.usb.device, request, expected, length); }
    catch (error){ this.fault = error; throw error; }
  }

  async open(clockHz){
    await this.usb.invoke('open', []);
    await this.usb.invoke('claimInterface', [0]);
    if (!this.usb.synchronized) throw Error('探针未确认 DAP 队列边界');
    await this.exchange([2, 1], [2, 1]);
    this.connected = true;
    await this.exchange([0x11, ...u32leBytes(clockHz)], [0x11, 0]);
    await this.exchange([0x13, 0], [0x13, 0]);
    await this.exchange([0x12, 152, ...Array(8).fill(0xff), 0x9e, 0xe7, ...Array(8).fill(0xff), 0], [0x12, 0]);
    await this.exchange([0x04, 0, 64, 0, 0, 0], [0x04, 0]);
    await this.checkDp();
    // CMSIS-DAP AP read requests carry A[3:2] in bits 3:2:
    // 0x0f selects IDR (0xfc) and 0x07 selects CFG (0xf4).
    const [idr, cfg] = await this.registers(0xf0, 0x0f, 0x07);
    if (idr !== this.port.apId || cfg !== this.port.apCfg) throw Error('MEM-AP 寄存器与 OpenOCD 不一致');
  }

  async registers(select, ...requests){
    const count = requests.length + 1;
    const bytes = await this.exchange([5, 0, count, ...transfer(8, this.select | select), ...requests],
      [5, count, 1], 3 + requests.length * 4);
    return requests.map((_, i) => u32le(bytes, i*4));
  }

  async checkDp(){
    const { dpId, swdIdentity } = this.port;
    await this.exchange([5, 0, 1, 2], [5, 1, 1, ...u32leBytes(dpId)]);
    if (swdIdentity){
      const [target] = await this.registers(2, 6);
      const [instance] = await this.registers(3, 6);
      if (target !== swdIdentity[0] || instance !== swdIdentity[1]) throw Error('SWD DP 实例与 OpenOCD 不一致');
    }
    await this.exchange([5, 0, 3, ...transfer(8, 0), ...transfer(0, 0x1e),
      ...transfer(4, 0x50000000)], [5, 3, 1]);
  }

  async recoverAck(error){
    const reply = error.dapReply;
    // A short/late USB read still requires a new lease and queue epoch.
    const scalar = reply?.[0] === 5 && reply.length === 3 && reply[2] === 4;
    const block = reply?.[0] === 6 && reply.length >= 4 && reply[3] === 4 &&
      reply.length === 4 + (reply[1] + reply[2] * 256) * 4;
    if (!scalar && !block) throw error;
    this.fault = null;
    await this.exchange([0x08, 0, ...u32leBytes(0x1e)], [0x08, 0]);
    try { await this.checkDp(); }
    catch (failure){ this.fault = failure; throw failure; }
  }

  async close(){
    let failure;
    try {
      if (this.connected && !this.fault) await this.exchange([3], [3, 0]);
    } catch (error){ failure = error; }
    await this.usb.close();
    this.connected = false;
    return failure;
  }

  address(address, csw){
    return this.exchange([5, 0, 3, ...transfer(8, this.select), ...transfer(1, this.csw | csw),
      ...transfer(5, address)], [5, 3, 1]);
  }

  async read(address, length, retry = true){
    const data = new Uint8Array(length);
    for (let offset = 0; offset < length;){
      const at = address + offset;
      const remaining = length - offset;
      const size = at % 4 || remaining < 4 ? 1 : Math.min(remaining - remaining % 4, TAR_PAGE - at % TAR_PAGE);
      const readChunk = async () => {
        if (size === 1){
          await this.address(at, 0x10);
          const value = await this.exchange([5, 0, 1, 15], [5, 1, 1], 7);
          data[offset] = value[at % 4];
        } else {
          const count = size / 4, lo = count & 255, hi = count >>> 8;
          await this.address(at, 0x12);
          data.set(await this.exchange([6, 0, lo, hi, 15], [6, lo, hi, 1], size + 4), offset);
        }
      };
      try { await readChunk(); }
      catch (error){
        if (!retry) throw error;
        await this.recoverAck(error);
        await readChunk();
      }
      offset += size;
    }
    return data;
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
    await this.writeAddress(address, 0x12);
    try { await this.exchange(packet, [5, 1, 1]); }
    catch (error){
      await this.recoverAck(error);
      const observed = u32le(await this.read(address, 4, false));
      if (observed === next) return;
      if (observed !== previous){ this.fault = error; throw error; }
      // The probe replied and the host-owned cursor is still at the old
      // value. Commit once more, without replaying any payload writes.
      await this.confirmedWrite(address, u32leBytes(next), 0x12, packet, 1);
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
        // Keep write completion on the ordinary DAP_Transfer path.
        const packet = [5, 0, count];
        for (let i = 0; i < size; i += 4) packet.push(13, ...bytes.subarray(offset + i, offset + i + 4));
        await this.confirmedWrite(at, bytes.subarray(offset, offset + size), 0x12, packet, count);
        offset += size;
      } else {
        // Byte lanes preserve adjacent bytes, including unaligned ring edges.
        const packet = [5, 0, 1, ...transfer(13, bytes[offset] << (8 * (at % 4)))];
        await this.confirmedWrite(at, bytes.subarray(offset, offset + 1), 0x10, packet, 1);
        offset++;
      }
    }
  }
}

export class ArmMemApRttProbe extends OpenOcdEtmProbe {
  get _faulted(){ return !!this.memAp?.fault || super._faulted; }

  async _memApPort(){
    const dpId = this.idcode;
    const dap = `[${this.target} cget -dap]`;
    const configuredTarget = this.cfg.raw ? this.cfg.target : this.target;
    if (!validId(dpId) || await this.command(`${configuredTarget} cget -endian`) !== 'little') return;
    const ap = uint(await this.command(`${this.target} cget -ap-num`));
    // ADIv6 addresses cannot be represented by the ADIv5 APSEL field.
    if (!Number.isInteger(ap) || ap > 255) return;
    const version = dpId >>> 12 & 0xf;
    if (version >= 3) return;
    let swdIdentity;
    if (version === 2){
      swdIdentity = [];
      for (const register of [0x24, 0x34]){
        const value = uint(await this.command(`capture {${dap} dpreg ${register}}`));
        if (value === undefined) return;
        swdIdentity.push(value);
      }
    }
    const readAp = async register => uint(await this.command(`capture {${dap} apreg ${ap} ${register}}`));
    const apId = await readAp(0xfc);
    if (!isMemAp(apId)) return;
    const apCfg = await readAp(0xf4);
    const csw = await readAp(0);
    if (apCfg === undefined || (apCfg & 1) || csw === undefined || !(csw & 0x40)) return;
    return { dpId, swdIdentity, ap, apId, apCfg, csw };
  }

  async useRttMemory(info, ranges = []){
    if (this.blockUnavailable || this.memAp) return;
    const regions = rttMemoryRegions(info, ranges);
    if (!regions) return;
    let port;
    try {
      if (!headerMatches(await super.readMem(info.addr, regions.header[1]), info)) return;
      port = await this._memApPort();
    } catch (error){
      this.onLog?.('RTT Viewer 使用 OpenOCD Wasm：' + error.message);
      return;
    }
    if (!port) return;
    this.wasmDisplay = { name:this.name, pollLimit:this.rttPollLimit, livePreview:this.rttLivePreview };
    await super.disconnect();
    try {
      const mem = this.memAp = new ArmMemAp(new OpenOcdUsb(this.device, 'RTT Viewer'), port);
      await mem.open(this.clockHz);
      const observed = await mem.read(...regions.header);
      if (!headerMatches(observed, info) || (await mem.read(info.addr + 1, 1))[0] !== observed[1])
        throw Error('J7 MEM-AP 的 RTT 标识或通道配置与 OpenOCD 不一致');
      this.rttRegions = regions;
      this.rttPollLimit = 8192;
      this.rttLivePreview = false;
      this.name = 'zynqlinkPRO / SWD MEM-AP';
      this.onLog?.(`RTT Viewer 使用 ${this.name} AP${port.ap} 块传输`);
    } catch (error){
      await this._closeMemAp();
      this.blockUnavailable = true;
      this.onLog?.('RTT Viewer 使用 OpenOCD Wasm：' + error.message);
      await super.connect();
      if (!headerMatches(await super.readMem(...regions.header), info))
        throw Error('重连后 RTT 控制块已变更，请重新扫描');
    }
  }

  async _closeMemAp(){
    if (!this.memAp) return;
    const failure = await this.memAp.close();
    this.memAp = null;
    this.rttRegions = null;
    this.rttPollLimit = this.wasmDisplay.pollLimit;
    this.rttLivePreview = this.wasmDisplay.livePreview;
    this.name = this.wasmDisplay.name;
    if (failure) this.onLog?.('RTT Viewer 断开命令未确认：' + failure.message);
  }

  async recoverDebugPort(){
    if (this.memAp?.fault) this.blockUnavailable = true;
    await super.recoverDebugPort();
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

  _checkRttRange(address, length, regions){
    if (!regions.some(([start, size]) => inRange(address, length, start, start + size)))
      throw Error('RTT 地址已变更或超出已确认的 RAM 缓冲，请重新扫描');
  }

  async readMem(address, length){
    if (!this.memAp) return super.readMem(address, length);
    if (!length) return new Uint8Array();
    this._checkRttRange(address, length, this.rttRegions.read);
    const bytes = await this.memAp.read(address, length);
    const entry = length === ENTRY && this.rttRegions.entries.get(address);
    if (entry && !ringMatches(bytes, 0, entry)) throw Error('RTT 通道配置已变更，请重新扫描');
    return bytes;
  }

  async writeMem(address, bytes){
    if (!this.memAp) return super.writeMem(address, bytes);
    if (!bytes.length) return;
    this._checkRttRange(address, bytes.length, this.rttRegions.write);
    await this.memAp.write(address, bytes);
  }

  async writeRttReadOffset(address, next, previous){
    if (!this.memAp) return super.writeMem(address, u32leBytes(next));
    const size = this.rttRegions.cursors.get(address);
    if (!size || !inRange(next, 1, 0, size) || !inRange(previous, 1, 0, size))
      throw Error('RTT 读游标地址超出已确认的控制块');
    await this.memAp.writeReadOffset(address, next, previous);
  }
}

function uint(text){
  if (!/^(?:0x[0-9a-f]{1,8}|[0-9]{1,10})$/i.test(text)) return;
  const value = Number(text);
  if (value <= 0xffffffff) return value;
}

function rttMemoryRegions(info, ranges){
  const { addr, up, down } = info;
  if (addr % 4 || !up[0]?.size || up.length !== info.maxUp || down.length !== info.maxDown) return;
  const header = [addr, 24 + ENTRY * (up.length + down.length)];
  const read = [header], write = [], cursors = new Map(), entries = new Map();
  for (const [index, channel] of [...up, ...down].entries()){
    const entry = addr + 24 + index * ENTRY;
    entries.set(entry, channel);
    const {pbuf, size} = channel;
    if (!size) continue;
    if (!pbuf || pbuf % 4) return;
    const ring = [pbuf, size];
    if (read.some(([start, length]) => pbuf < start + length && start < pbuf + size)) return;
    read.push(ring);
    if (index < up.length) cursors.set(entry + 16, size);
    else write.push(ring, [entry + 12, 4]);
  }
  const ram = [CORTEX_M_SRAM, ...ranges.filter(({start, end}) => inRange(start, end - start, 0, 0x100000000))];
  if (read.every(([addr, size]) => ram.some(({start, end}) => inRange(addr, size, start, end))))
    return { header, read, write, cursors, entries };
}

function ringMatches(bytes, at, {pbuf, size}){
  return u32le(bytes, at + 4) === pbuf && u32le(bytes, at + 8) === size;
}

function headerMatches(bytes, info){
  if (bytes.length !== 24 + ENTRY * (info.maxUp + info.maxDown) ||
      !Array.from(CB_ID).every((letter, i) => bytes[i] === letter.charCodeAt(0)) ||
      u32le(bytes, 16) !== info.maxUp || u32le(bytes, 20) !== info.maxDown) return false;
  return [...info.up, ...info.down].every((entry, i) => {
    const at = 24 + i * ENTRY;
    return ringMatches(bytes, at, entry) && u32le(bytes, at + 20) === entry.flags;
  });
}
