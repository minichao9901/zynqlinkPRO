import { OpenOcdTargetSession } from './openocd-session.js';
import { ocdHex } from './openocd-profile.js';

const MAX_TRANSFER = 2048;
const ARM_REGS = [...Array.from({ length:13 }, (_, index) => `r${index}`), 'sp', 'lr', 'pc', 'xpsr', 'msp', 'psp'];
const CFBP = ['primask', 'basepri', 'faultmask', 'control'];

export function isHpm6800BulkSram(cfg, address, length){
  if (cfg?.boardId !== 'hpm6800evk' || length < 4096 || address % 4 || length % 4) return false;
  // ILM and the noncacheable AXI SRAM bank. Keep cacheable memory and MMIO
  // on their original access paths.
  return address >= 0 && address + length <= 0x40000 ||
    address >= 0x01240000 && address + length <= 0x01280000;
}

function checkRange(address, length){
  if (!Number.isInteger(address) || address < 0 || address > 0xffffffff ||
      !Number.isInteger(length) || length < 0 || address + length > 0x100000000)
    throw Error('内存访问超出 32 位地址空间');
}

function widthAt(address, count){
  if (!(address % 4) && count >= 4) return 4;
  return !(address % 2) && count >= 2 ? 2 : 1;
}

export class OpenOcdProbe {
  constructor(device, cfg, onLog, runningMemory){
    this.device = device;
    this.cfg = cfg;
    this.onLog = onLog;
    this.name = 'OpenOCD Wasm / WebUSB';
    this.clockHz = cfg.clockKhz * 1000;
    this.isRiscv = cfg.arch === 'riscv';
    this.physical = this.isRiscv && runningMemory;
    this.skipNames = this.isRiscv;
    // Release the producer cursor between shorter transfers while its
    // noncacheable AXI ring is being written by the running HPM6800.
    this.rttLivePreview = this.physical && !cfg.boardId;
    this.rttPollLimit = this.physical && (!cfg.boardId || cfg.boardId === 'hpm6800evk') ? 8192 : undefined;
  }

  get _faulted(){ return !!this.link && !this.link.worker; }

  async _selectTarget(link, targets){
    const { target, raw, memoryAp } = this.cfg;
    if (!raw) return target;
    if (!memoryAp){
      await link.command(`targets ${target}`);
      return target;
    }
    const name = 'workbench.memory';
    if (targets.includes(name)) throw Error('CFG 已占用工作台 MEM-AP 目标名');
    // Use the configured DAP/AP but keep every original core unexamined.
    await link.command('foreach core [target names] { $core configure -defer-examine }');
    await link.command(`if {[catch {${target} cget -ap-num} ap]} {if {$ap ne "AP number not configured"} {error $ap}; set ap 0}; target create ${name} mem_ap -dap [${target} cget -dap] -ap-num $ap`);
    await link.command('reset_config none');
    await link.command(`targets ${name}`);
    return name;
  }

  async _initTarget(link){ await link.command('init'); }

  async connect(){
    this._f103HighDensity = undefined;
    const link = this.link = new OpenOcdTargetSession(line => this.onLog?.(line));
    try {
      await link.open(this.cfg, this.device);
      const targets = (await link.command('target names')).split(/\s+/);
      if (!targets.includes(this.cfg.target)) throw Error('OpenOCD CFG 目标不匹配');
      const target = this.target = await this._selectTarget(link, targets);
      await this._initTarget(link);
      if (this.cfg.raw){
        await link.command(`targets ${target}`);
        // The workbench controls one selected core. A peer can be parked in
        // ROM and make a group resume fail even after the selected core halted.
        if (!this.cfg.memoryAp && this.cfg.cores?.length > 1 && !this.isRiscv) await link.command('cortex_m smp off');
      }
      if (!this.cfg.memoryAp){
        let status = await link.command(`${this.cfg.target} curstate`);
        // Cortex-M examination can finish before the first DHCSR poll updates curstate.
        if (!this.isRiscv && status === 'unknown'){
          await link.command('poll');
          status = await link.command(`${this.cfg.target} curstate`);
        }
        if (!['running', 'halted', 'reset', 'sleeping'].includes(status))
          throw Error('OpenOCD 未识别目标：' + status);
      }
      if (this.isRiscv || this.cfg.transport === 'jtag'){
        const tap = await link.command(`${this.cfg.target} cget -chain-position`);
        const chain = await link.command('capture {scan_chain}');
        const id = [...chain.matchAll(/^\s*\d+\s+(\S+)\s+Y\s+(0x[0-9a-f]{8})\b/gim)].find(row => row[1] === tap);
        this.idcode = Number(id?.[2] ?? 0);
        if (!this.idcode || this.idcode === 0xffffffff || this.cfg.tapIdcode != null && this.idcode !== this.cfg.tapIdcode)
          throw Error('OpenOCD 未识别 CFG 中的 JTAG TAP');
        if (this.physical) await link.command(`${this.cfg.target} riscv mem_access sysbus`);
      } else {
        const dap = `${target} cget -dap`;
        this.idcode = Number(await link.command(`capture {[${dap}] dpreg 0}`)) >>> 0;
        if (!this.idcode || this.idcode === 0xffffffff || this.cfg.dpidr != null && this.idcode !== this.cfg.dpidr)
          throw Error('OpenOCD 未确认目标 SWD DPIDR');
      }
    } catch (error){
      try { await this.disconnect(); }
      catch (cleanup){ throw new AggregateError([error, cleanup], `${error.message}；探针清理失败：${cleanup.message}`); }
      throw error;
    }
  }

  async command(line, timeoutMs){
    if (!this.link) throw Error('OpenOCD 会话未连接');
    const value = await this.link.command(line, timeoutMs);
    this.lastOkAt = Date.now();
    return value;
  }

  targetCommand(line){ return this.command(`${this.target ?? this.cfg.target} ${line}`); }

  async disconnect(){
    await this.link?.close();
    this.link = null;
  }

  async recoverDebugPort(){
    await this.disconnect();
    await this.connect();
  }

  async setClock(hz){
    if (!Number.isInteger(hz) || hz < 1000 || hz > 60000000) throw Error('调试时钟超出范围');
    await this.command(`adapter speed ${Math.round(hz / 1000)}`);
    this.clockHz = hz;
  }
  async isHalted(){ await this.command('poll'); return await this.targetCommand('curstate') === 'halted'; }
  async halt(){ await this.command('halt'); }
  async run(){ await this.command('resume'); }
  async reset(halt = false){
    if (!this.isRiscv || !(this.cfg.boardId || this.cfg.raw?.hpmSdk)){
      await this.command(halt ? 'reset halt' : 'reset run');
      if (await this.isHalted() !== halt) throw Error('未确认目标复位后的运行状态');
      return 'OpenOCD 目标复位';
    }
    // HPM uses ndmreset. Confirm a fresh reset and release haltreq/ndmreset
    // even when the assert command fails.
    if (!await this.isHalted()) await this.halt();
    await this.targetCommand('riscv exec_progbuf 0x00000013');
    const pollMode = /background polling: (on|off)\b/.exec(await this.command('capture {poll}'))?.[1];
    if (!pollMode) throw Error('未确认 OpenOCD 后台轮询状态');
    const status = async () => Number(await this.targetCommand('riscv dmi_read 0x11'));
    const control = bits => this.targetCommand(`riscv dmi_write 0x10 ${ocdHex(bits)}`);
    const active = 1, ack = 0x10000000, resetSeen = 0x40000;
    const request = active + (halt ? 0x80000000 : 0);
    let failure;
    try {
      await this.command('poll off');
      await control(ack + active);
      if (await status() & resetSeen) throw Error('HPM 旧复位标志未清除');
      try {
        await control(request + 2);
        await new Promise(resolve => setTimeout(resolve, 50));
      } finally { await control(request); }
      const released = Number(await this.targetCommand('riscv dmi_read 0x10'));
      if (!Number.isInteger(released) || (released & 3) !== active) throw Error('未确认 HPM 系统复位已释放');
      const mask = resetSeen | (halt ? 0x200 : 0x800);
      const end = performance.now() + 3000;
      while (((await status()) & mask) !== mask){
        if (performance.now() >= end) throw Error('未确认 HPM 复位后的运行状态');
        await new Promise(resolve => setTimeout(resolve, 10));
      }
      await control(ack + active);
    } catch (error){
      failure = error;
      throw error;
    } finally {
      try { await this.command('poll ' + pollMode); }
      catch (error){
        if (failure) throw new AggregateError([failure,error], failure.message + '；恢复后台轮询失败：' + error.message);
        throw error;
      }
    }
    if (await this.isHalted() !== halt) throw Error('OpenOCD 未确认 HPM 复位后的运行状态');
    return 'HPM 系统复位';
  }

  async armRegisters(names){
    await this.command('poll');
    const output = await this.targetCommand(`get_reg {${names.join(' ')}}`);
    const values = new Map(Array.from(output.matchAll(/^(\S+)\s+(0x[\da-f]+)\s*$/gim),
      ([, name, value]) => [name, Number(value)]));
    if (names.some(name => !values.has(name))) throw Error('OpenOCD 寄存器回读不完整');
    return values;
  }

  async _cfbpRegisters(){
    if (this.armV6m === undefined){
      const part = (await this._readWord(0xe000ed00) >>> 4) & 0xfff;
      this.armV6m = [0xc20, 0xc60].includes(part);
    }
    return this.armV6m ? ['primask', 'control'] : CFBP;
  }

  async regRead(selector){
    if (selector === 0x14){
      const values = await this.armRegisters(await this._cfbpRegisters());
      return CFBP.reduce((word, name, index) => word | ((values.get(name) ?? 0) << (index * 8)), 0) >>> 0;
    }
    const name = ARM_REGS[selector];
    if (!name) throw Error('OpenOCD 不支持此 Cortex-M 寄存器');
    return (await this.armRegisters([name])).get(name);
  }

  async regWrite(selector, value){
    const name = ARM_REGS[selector];
    if (!name && selector !== 0x14) throw Error('OpenOCD 不支持此 Cortex-M 寄存器');
    const pairs = selector === 0x14 ? (await this._cfbpRegisters()).map(reg =>
      `${reg} ${(value >>> (CFBP.indexOf(reg) * 8)) & 255}`) : [`${name} ${ocdHex(value >>> 0)}`];
    await this.targetCommand(`set_reg {${pairs.join(' ')}}`);
  }

  _checkFence(address, length){
    if (length && this.cfg.sbaFence?.some(range => address < range.end && address + length > range.start))
      throw Error('目标 Flash/XIP 区域禁止通过 SBA 访问');
  }

  async _readUnits(address, width, count){
    const out = await this.targetCommand(`read_memory ${ocdHex(address)} ${width * 8} ${count}${this.physical ? ' phys' : ''}`);
    const values = out ? out.split(/\s+/) : [];
    if (values.length !== count || values.some(value => !/^(?:0x[\da-f]+|\d+)$/i.test(value)))
      throw Error('OpenOCD 内存回读格式或长度不匹配');
    return values.map(Number);
  }

  async _memoryImageOptions(address, length){
    if (this.physical && isHpm6800BulkSram(this.cfg, address, length)) return { physical:true };
    if (this.isRiscv || this.cfg.family !== 'stm32f103' || this.cfg.raw ||
        length < 4096 || address % 4 || length % 4 ||
        address < 0x20000000 || address + length > 0x20010000) return null;
    if (this._f103HighDensity === undefined){
      const device = await this._readWord(0xe0042000).catch(error => {
        if (this._faulted) throw error;
        return null;
      });
      if (device === null) return null;
      this._f103HighDensity = (device & 0xfff) === 0x414;
    }
    return this._f103HighDensity ? { physical:false } : null;
  }

  async readMem(address, length){
    checkRange(address, length);
    const start = this.physical && length ? address - address % 4 : address;
    const end = this.physical && length ? Math.ceil((address + length) / 4) * 4 : address + length;
    this._checkFence(start, end - start);
    const image = await this._memoryImageOptions(start, end - start);
    if (image){
      const { bytes } = await this.link.request('memoryImage', { address:start, length:end - start, ...image });
      if (bytes?.length !== end - start) throw Error('OpenOCD 二进制内存回读长度不匹配');
      return bytes.subarray(address - start, address - start + length);
    }
    const data = new Uint8Array(end - start);
    const view = new DataView(data.buffer);
    for (let at = start; at < end;){
      const width = widthAt(at, end - at);
      const count = at % 4 ? 1 : Math.min(MAX_TRANSFER, end - at) / width | 0;
      const values = await this._readUnits(at, width, count);
      for (const value of values){
        if (width === 4) view.setUint32(at - start, value, true);
        else if (width === 2) view.setUint16(at - start, value, true);
        else view.setUint8(at - start, value);
        at += width;
      }
    }
    return data.subarray(address - start, address - start + length);
  }

  async writeMem(address, bytes){
    checkRange(address, bytes.length);
    this._checkFence(address, bytes.length);
    const image = await this._memoryImageOptions(address, bytes.length);
    if (image){
      await this.link.request('memoryImage', { address, length:bytes.length, input:bytes, ...image });
      return;
    }
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    for (let offset = 0; offset < bytes.length;){
      const at = address + offset, remaining = bytes.length - offset;
      const width = widthAt(at, remaining);
      if (this.physical && width < 4){
        const first = at - at % 4, n = Math.min(4 - at % 4, remaining);
        this._checkFence(first, 4);
        const [word] = await this._readUnits(first, 4, 1);
        const aligned = new DataView(new ArrayBuffer(4));
        aligned.setUint32(0, word, true);
        for (let i = 0; i < n; i++) aligned.setUint8(at % 4 + i, bytes[offset + i]);
        await this._writeUnits(first, 4, [aligned.getUint32(0, true)]);
        offset += n;
        continue;
      }
      const count = at % 4 ? 1 : Math.min(MAX_TRANSFER, remaining) / width | 0;
      const values = Array.from({ length:count }, (_, i) => {
        const index = offset + i * width;
        return width === 4 ? view.getUint32(index, true) : width === 2 ? view.getUint16(index, true) : bytes[index];
      });
      await this._writeUnits(at, width, values);
      offset += count * width;
    }
  }

  _writeUnits(address, width, values){
    return this.targetCommand(`write_memory ${ocdHex(address)} ${width * 8} {${values.join(' ')}}${this.physical ? ' phys' : ''}`);
  }

  readMemDiagnostic(address, length){ return this.readMem(address, length); }
  writeMemDiagnostic(address, bytes){ return this.writeMem(address, bytes); }
  regReadDiagnostic(selector){ return this.regRead(selector); }
  async setHardFaultCatch(enabled){
    const address = 0xe000edfc, mask = 1 << 10;
    const original = await this._readWord(address);
    const value = enabled ? original | mask : original & ~mask;
    await this._writeUnits(address, 4, [value >>> 0]);
    if (!!((await this._readWord(address)) & mask) !== enabled) throw Error('HardFault 捕获状态回读失败');
    return !!(original & mask);
  }
  async _readWord(address){ return (await this._readUnits(address, 4, 1))[0]; }
  async _dhcsr(value){ await this._writeUnits(0xe000edf0, 4, [value >>> 0]); }
}
