import { OpenOcdProbe } from './openocd-probe.js';
import { makeOpenOcdProfile } from './openocd-profile.js';
import { openOcdUsbSupported } from './openocd-usb.js';
import { nativeProbeEnabled, nativeUsbDevices } from './native-probe.js';

const DHCSR = 0xe000edf0;
const DEBUG_KEY = 0xa05f0000;
const DEBUG_ENABLE = 1, HALT = 2, MASK_INTERRUPTS = 8, HALTED = 1 << 17;

/** Open only physical MEM-AP0; Cortex-M examination would overwrite
 * DEMCR/ITM and clear FPB on every capture handoff. ETM owns those registers. */
export class OpenOcdEtmProbe extends OpenOcdProbe {
  static supported(){
    return globalThis.document?.body?.dataset?.nativeOffline !== '1' && openOcdUsbSupported();
  }

  static authorized(){
    if (!this.supported()) throw Error('ETM 目标控制需要 WebUSB 或已启用的本机探针服务');
    return nativeProbeEnabled() ? nativeUsbDevices() : navigator.usb.getDevices();
  }

  static async open(device, { clockKhz, onLog, retain }){
    const probe = new this(device, makeOpenOcdProfile({ clockKhz, memoryAp:true }), onLog);
    probe.name = 'OpenOCD Wasm / MEM-AP0';
    try { await probe.connect(); }
    catch (error){
      if (probe.link) retain?.(probe);
      throw error;
    }
    return probe;
  }

  get _faulted(){ return !!this.controlFault || super._faulted; }

  async connect(){
    await super.connect();
    this.controlFault = false;
  }

  async readMemDiagnostic(address, length){
    try { return await super.readMemDiagnostic(address, length); }
    catch (error){ this.controlFault = true; throw error; }
  }

  async writeMemDiagnostic(address, bytes){
    try { await super.writeMemDiagnostic(address, bytes); }
    catch (error){ this.controlFault = true; throw error; }
  }

  async isHalted(){ return !!((await this.readDhcsr()) & HALTED); }
  async readDhcsr(){
    const bytes = await this.readMemDiagnostic(DHCSR, 4);
    return new DataView(bytes.buffer, bytes.byteOffset, 4).getUint32(0, true);
  }

  async halt(){
    if (!await this.isHalted()) await this.writeDhcsr(DEBUG_ENABLE | HALT);
  }

  async run(){
    const status = await this.readDhcsr();
    if (!(status & HALTED)) return;
    // MASKINTS is writable only while the core remains halted.
    if (status & MASK_INTERRUPTS) await this.writeDhcsr(DEBUG_ENABLE | HALT);
    // ETM checks execution and breakpoints. A second resume could skip a new halt.
    await this.writeDhcsr(DEBUG_ENABLE);
  }

  async reset(){
    const resetSeen = 1 << 25;
    await this.readDhcsr(); // Discard an old sticky reset indication.
    const request = Uint8Array.of(4, 0, 0xfa, 5);
    let writeError;
    try { await this.writeMemDiagnostic(0xe000ed0c, request); }
    catch (error){ writeError = error; }
    // Reset can drop the debug connection. Reacquire it without replaying AIRCR.
    await this.recoverDebugPort();
    const status = await this.readDhcsr();
    if (!(status & resetSeen))
      throw new Error('未确认目标复位', { cause:writeError });
    if (status & HALTED) throw new Error('已确认目标复位，目标当前处于暂停状态');
    return '软件复位（AIRCR.SYSRESETREQ）';
  }

  writeDhcsr(bits){
    const bytes = new Uint8Array(4);
    new DataView(bytes.buffer).setUint32(0, (DEBUG_KEY | bits) >>> 0, true);
    return this.writeMemDiagnostic(DHCSR, bytes);
  }
}
