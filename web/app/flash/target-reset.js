import { sleep } from '../core/pace.js';
import { OpenOcdTargetSession } from '../core/openocd-session.js';

/** Send a genuine hardware pulse, even if the target SWD port is unresponsive.
 * SWJ_Pins.wait is a wait-until-pin-matches timeout, NOT a pulse duration. */
export class OpenOcdResetSession extends OpenOcdTargetSession {
  async connect(device){
    // Initialize only the adapter. A target may be unreachable until NRST.
    await this.open({ script:'transport select swd\nadapter speed 1000\nreset_config none\n' }, device);
    await this.command('init');
  }

  async swjResetPin(value){
    if (value !== 0 && value !== 0x80) throw Error('无效的 nRESET 引脚电平');
    const result = await this.command(`capture {cmsis-dap cmd 0x10 ${value} 0x80 ${value ? '0x50 0xc3' : '0 0'} 0 0}`);
    const byte = /Returned data ([\da-f]{2})\b/i.exec(result)?.[1];
    if (byte === undefined) throw Error('OpenOCD 未返回 nRESET 引脚状态');
    return !!(parseInt(byte, 16) & 0x80);
  }

  disconnect(){ return this.close(); }
}

export async function pulseTargetReset(probe){
  // On release allow 50ms for the target RC network / another reset source.
  let assertError;
  try {
    if (await probe.swjResetPin(0)) throw new Error('探针未确认 nRESET 已拉低');
    await sleep(20);
  } catch (e){ assertError = e; }
  try {
    if (!await probe.swjResetPin(0x80)) throw new Error('探针未确认 nRESET 已释放');
  } catch (e){
    if (assertError) throw new AggregateError([assertError, e], '复位输出失败，且无法确认已释放');
    throw e;
  }
  if (assertError) throw assertError;
  await sleep(150);
}
