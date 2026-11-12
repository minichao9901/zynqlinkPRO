import { buildData, buildDef, HOST_POLL, planReads, SCOPE_FLAG } from './protocol.js';

// 100 Hz is the routing threshold, not a promised sampling rate.
export const WASM_POLL_MIN_US = 10000;

export class WasmScopePoll {
  constructor(probe, vars, periodUs){
    this.probe = probe;
    this.vars = vars;
    this.periodMs = periodUs / 1000;
    // Read selected variables and their overlaps, without touching gaps.
    this.plan = planReads(vars, { maxGapBytes:0 });
    this.skipped = 0;
  }

  start(onChunk, onError){
    this.running = true;
    this.next = this.origin = performance.now();
    this.seq = 0;
    onChunk(buildDef({ seq:this.seq++, vars:this.vars, periodUs:this.periodMs * 1000,
      flags:HOST_POLL | (this.probe.isRiscv ? SCOPE_FLAG.RISCV : 0) }));
    const tick = async () => {
      if (!this.running) return;
      const stamp = performance.now();
      // Sample once after a delayed timer, then schedule the next slot.
      const skipped = Math.max(0, Math.floor((stamp - this.next) / this.periodMs));
      this.skipped += skipped;
      this.next += (skipped + 1) * this.periodMs;
      const frame = new Uint8Array(this.plan.frameBytes);
      let offset = 0;
      for (const span of this.plan.spans){
        const bytes = await this.probe.readMem(span.start, span.len);
        if (!this.running) return;
        if (bytes.length !== span.len) throw Error('OpenOCD Wasm 波形内存短读');
        for (const v of span.vars){
          frame.set(bytes.subarray(v.addr - span.start, v.addr - span.start + v.size), offset);
          offset += v.size;
        }
      }
      onChunk(buildData({ seq:this.seq++, tUs:Math.round((stamp-this.origin)*1000), n:1, payload:frame }));
      if (this.running) this.timer = setTimeout(schedule, Math.max(0, this.next - performance.now()));
    };
    const schedule = () => {
      this.task = tick().catch(error => {
        if (this.running){
          this.running = false;
          onError(error);
        }
      });
    };
    this.timer = setTimeout(schedule, 0);
  }

  async close(){
    this.running = false;
    clearTimeout(this.timer);
    await this.task;
    await this.probe.disconnect();
  }
}
