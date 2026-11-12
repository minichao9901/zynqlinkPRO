import { OpenOcdProbe, isHpm6800BulkSram } from '../core/openocd-probe.js';
import { hpmBoard } from '../targets/hpm/porting.js';
import { DebugSession } from './session.js';
import { RV_ARCH } from './rv.js';

const REGISTERS = 'zero ra sp gp tp t0 t1 t2 s0 s1 a0 a1 a2 a3 a4 a5 a6 a7 s2 s3 s4 s5 s6 s7 s8 s9 s10 s11 t3 t4 t5 t6 pc'.split(' ');
const openOcdRegName = name => name === 's0' ? 'fp' : name;

export class OpenOcdRiscvSession extends DebugSession {
  constructor(){
    super();
    this.arch = RV_ARCH;
    this.isRiscv = true;
    this.caps = { numCode:8, rev:2 };
  }

  async connect({ cfg, device }){
    if (this.probe) throw Error('已经连接了（先断开）');
    this.target = cfg.target;
    this.port = hpmBoard(cfg.boardId);
    this.sbaFence = cfg.sbaFence ?? [];
    const probe = this.probe = new OpenOcdProbe(device, cfg, line => this._log(line, 'dim'));
    try {
      await probe.connect();
      this.name = cfg.name;
      this.idcode = probe.idcode;
      this.clockHz = probe.clockHz;
      await this.refresh();
    } catch (error){
      try { await this.disconnect(); }
      catch (cleanup){ throw new AggregateError([error, cleanup], `${error.message}；探针清理失败：${cleanup.message}`); }
      throw error;
    }
  }

  async disconnect(){
    await this._memoryTask;
    const probe = this.probe;
    if (probe && this.bps.length){
      const wasHalted = await probe.isHalted();
      if (!wasHalted) await probe.halt();
      try { await this.bpClear(); }
      finally { if (!wasHalted) await probe.run(); }
    }
    await probe?.disconnect();
    this.probe = null;
    this.halted = false;
    this.bps = [];
    this.bpNotes.clear();
    this.regs = [];
    this._xipFallbackLogged = false;
    this.clearFrames();
  }

  _command(line, timeoutMs){ return this.probe.command(line, timeoutMs); }

  async _pollHalted(){
    await this._command('poll');
    const state = await this._command(this.target + ' curstate');
    if (state !== 'halted' && state !== 'running') throw new Error('OpenOCD 目标状态：' + state);
    return state === 'halted';
  }

  async refresh(){
    if (!this.connected) return this.statusInfo();
    this.halted = await this._pollHalted();
    if (this.halted) this.pc = await this.readReg('pc');
    if (this._frames && (!this.halted || this.pc !== this._framePc)) this.clearFrames();
    return this.statusInfo();
  }

  async ensureHalted(){
    if (!await this._pollHalted()) await this._command('halt');
    await this.refresh();
    if (!this.halted) throw new Error('OpenOCD 未能停住目标');
  }

  async _clearDfsr(){}
  async run(){
    await this._command('resume');
    this.clearFrames();
    this.halted = false;
  }
  async step(){
    if (!this.halted) throw new Error('请先暂停目标');
    await this._withBpCleared(await this.readReg('pc'), () => this._command('step'));
    await this.refresh();
    if (!this.halted) throw Error('OpenOCD 单步后未确认停机');
  }
  async resetHalt(){
    await this.ensureHalted();
    const breakpoints = this.bps.map(addr => [addr, this.bpNotes.get(addr)]);
    try {
      await this.bpClear();
      await this.probe.reset(true);
    } finally {
      if (breakpoints.length){
        await this.ensureHalted();
        for (const [addr, note] of breakpoints) await this.bpAdd(addr, note);
      }
    }
    await this.refreshRegs();
    return 'OpenOCD 系统复位 + 停住';
  }

  async resetRun(){
    await this.resetHalt();
    await this.run();
    return 'OpenOCD 系统复位 + 运行';
  }
  async verifyClock(){ return { ok:true, hz:this.clockHz, checked:false }; }

  regInfo(name){
    const key = String(name).trim().toLowerCase();
    const index = /^x(?:[0-9]|[12][0-9]|3[01])$/.test(key) ? Number(key.slice(1)) : -1;
    const canonical = REGISTERS[index] || (key === 'fp' ? 's0' : key === 'dpc' ? 'pc' : key);
    return REGISTERS.includes(canonical) || ['misa','dcsr','mstatus','mtvec','mepc','mcause','mtval'].includes(canonical)
      ? { name:canonical, bits:32 } : null;
  }

  async readRegs(names){
    const openOcdNames = names.map(name => openOcdRegName(this.regInfo(name)?.name));
    if (openOcdNames.some(name => !name)) throw new Error('未知寄存器');
    const out = await this._command(this.target + ' get_reg {' + openOcdNames.join(' ') + '}');
    const entries = new Map([...out.matchAll(/(\w+)\s+(0x[0-9a-f]+)/gi)].map(([,name,value]) => [name, Number(value)]));
    if (openOcdNames.some(name => !entries.has(name))) throw new Error('OpenOCD 寄存器回包不完整：' + out);
    return new Map(names.map((name, i) => [name, entries.get(openOcdNames[i])]));
  }

  async readReg(name){
    const reg = this.regInfo(name);
    if (!reg) throw new Error('未知寄存器：' + name);
    return (await this.readRegs([reg.name])).get(reg.name);
  }

  async writeReg(name, value){
    const reg = this.regInfo(name);
    if (!reg || !Number.isInteger(value)) throw new Error('无效的寄存器写入');
    await this._command(this.target + ' set_reg {' + openOcdRegName(reg.name) + ' ' + (value >>> 0) + '}');
    if (reg.name === 'pc') this.pc = value >>> 0;
    this.clearFrames();
  }

  async refreshRegs(){
    if (!this.halted) return this.regs;
    const csrs = ['mstatus','mtvec','mepc','mcause','mtval','dcsr'];
    const values = await this.readRegs(REGISTERS);
    for (const csr of csrs){
      try { values.set(csr, await this.readReg(csr)); }
      catch (error){ if (this.probe._faulted) throw error; }
    }
    const prev = new Map(this.regs.map(r => [r.name,r.value]));
    this.regs = [...values.keys()].map(name => ({ name, value:values.get(name), changed:prev.has(name) && prev.get(name) !== values.get(name) }));
    this.pc = values.get('pc');
    return this.regs;
  }

  async memRead(addr, len){
    if (!Number.isInteger(addr) || !Number.isInteger(len) || addr < 0 || len < 0 || addr + len > 0x100000000)
      throw new Error('内存地址或长度超出 32 位地址空间');
    if (len && this.sbaFence.some(range => addr < range.end && addr + len > range.start)){
      const inside = this.sbaFence.some(range => addr >= range.start && addr + len <= range.end);
      const bytes = inside ? this.sym?.codeBytes?.(addr, len) : null;
      if (!bytes || bytes.length !== len) throw new Error('XIP/flash 数据不可用：载入的 ELF 只读段未完整覆盖请求');
      if (!this._xipFallbackLogged){
        this._xipFallbackLogged = true;
        this._log('XIP/flash 使用已载入 ELF 的只读镜像，请核对 ELF 与目标固件一致。', 'warn');
      }
      return bytes;
    }
    return this._withMemory(() => this.probe.readMem(addr, len), addr, len);
  }

  async memWrite(addr, bytes){
    if (!(bytes instanceof Uint8Array)) throw Error('内存写入需要字节数组');
    return this._withMemory(() => this.probe.writeMem(addr, bytes), addr, bytes.length);
  }

  async _withMemory(fn, address, length){
    const task = (this._memoryTask || Promise.resolve()).then(() => this._accessMemory(fn, address, length));
    this._memoryTask = task.catch(() => {});
    return task;
  }

  async _accessMemory(fn, address, length){
    const memory = this.probe;
    await this.port?.hooks.checkMemoryReady({ dm:memory, sym:this.sym }, address, length);
    if (await this._pollHalted() && !isHpm6800BulkSram(memory.cfg, address, length)) return fn();
    const prefix = this.target + ' riscv mem_access';
    const previous = await this._command(prefix);
    if (!/^(?:progbuf|sysbus|abstract)(?: (?:progbuf|sysbus|abstract))*$/.test(previous))
      throw Error('无法确认 OpenOCD RISC-V 内存访问方式');
    await this._command(prefix + ' sysbus');
    memory.physical = true;
    let failure;
    try { return await fn(); }
    catch (error){ failure = error; throw error; }
    finally {
      memory.physical = false;
      try { await this._command(prefix + ' ' + previous); }
      catch (cleanup){
        if (failure) throw new AggregateError([failure, cleanup], `${failure.message}；恢复内存访问方式失败：${cleanup.message}`);
        throw cleanup;
      }
    }
  }

  async bpAdd(addr, note = ''){
    const index = this.bps.indexOf(addr);
    if (index >= 0) return { index, warn:'这个地址上已经有断点了' };
    await this._command('bp ' + (addr >>> 0) + ' 2 hw');
    this.bps.push(addr);
    if (note) this.bpNotes.set(addr,note);
    return { index:this.bps.length-1 };
  }

  async bpDel(addr){
    const index = this.bps.indexOf(addr);
    if (index < 0) return false;
    await this._command('rbp ' + (addr >>> 0));
    this.bps.splice(index,1);
    this.bpNotes.delete(addr);
    return true;
  }

  async bpClear(){
    const bps = this.bps.slice();
    for (const addr of bps) await this.bpDel(addr);
    return bps.length;
  }

  async verifyBreakpoints(){
    const output = await this._command('bp');
    const installed = output ? output.split(/\r?\n/).map(line => {
      const address = /^Hardware breakpoint\(IVA\): addr=(0x[0-9a-f]+)/i.exec(line)?.[1];
      if (!address) throw new Error('无法识别 OpenOCD 断点：' + line);
      return Number(address);
    }) : [];
    if (installed.length !== this.bps.length || this.bps.some(addr => !installed.includes(addr)))
      throw new Error('OpenOCD 实际断点与调试页不一致：' + output);
    return installed;
  }

  async _withBpCleared(addr, fn){
    const hit = this._bpAt(addr);
    if (hit === undefined) return await fn();
    const index = this.bps.indexOf(hit);
    const note = this.bpNotes.get(hit);
    await this.bpDel(hit);
    let failure;
    try { return await fn(); }
    catch (error){ failure = error; throw error; }
    finally {
      try {
        await this.bpAdd(hit, note);
        this.bps.splice(this.bps.indexOf(hit), 1);
        this.bps.splice(index, 0, hit);
      } catch (cleanup){
        if (!failure) throw cleanup;
        this._log('恢复断点失败：' + cleanup.message, 'err');
      }
    }
  }

}
