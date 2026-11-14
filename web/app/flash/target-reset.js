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
    return readResetPin(this, value);
  }

  disconnect(){ return this.close(); }
}

export async function readResetPin(probe, value){
  if (value !== undefined && value !== 0 && value !== 0x80) throw Error('无效的 nRESET 引脚电平');
  const result = await probe.command(`capture {cmsis-dap cmd 0x10 ${value ?? 0} ${value === undefined ? 0 : 0x80} ${value ? '0x50 0xc3' : '0 0'} 0 0}`);
  const byte = /Returned data ([\da-f]{2})\b/i.exec(result)?.[1];
  if (byte === undefined) throw Error('OpenOCD 未返回 nRESET 引脚状态');
  return !!(parseInt(byte, 16) & 0x80);
}

export async function pulseTargetReset(probe, { holdMs = 20, settleMs = 150 } = {}){
  // On release allow 50ms for the target RC network / another reset source.
  let assertError;
  try {
    if (await probe.swjResetPin(0)) throw new Error('探针未确认 nRESET 已拉低');
    await sleep(holdMs);
  } catch (e){ assertError = e; }
  try {
    if (!await probe.swjResetPin(0x80)) throw new Error('探针未确认 nRESET 已释放');
  } catch (e){
    if (assertError) throw new AggregateError([assertError, e], '复位输出失败，且无法确认已释放');
    throw e;
  }
  if (assertError) throw assertError;
  if (settleMs) await sleep(settleMs);
}

export async function confirmF103ResetRun(probe){
  const resetSeen = 1 << 25, retired = 1 << 24, halted = 1 << 17, locked = 1 << 19;
  if (!await readResetPin(probe)) throw Error('复位前 J7 NRST 未释放');
  await probe.readDhcsr();
  if (await probe.readDhcsr() & resetSeen) throw Error('旧的核心复位标志未清除');
  await pulseTargetReset({swjResetPin:value => readResetPin(probe, value)}, {holdMs:45, settleMs:0});
  const deadline = performance.now() + 2000;
  let resetStatus;
  do {
    const status = await probe.readDhcsr();
    if (status & resetSeen) resetStatus = status;
    if (resetStatus !== undefined && status & retired && !(status & (halted | locked)))
      return { method:'J7 NRST', resetDhcsr:resetStatus, runningDhcsr:status };
    await sleep(25);
  } while (performance.now() < deadline);
  throw Error('未确认 J7 NRST 触发新的核心复位并运行，请检查目标 NRST 接线');
}
