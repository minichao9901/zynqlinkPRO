/** WebUSB RTT viewer; URL mock mode is reserved for offline checks. */
import { prepareProbeHandoff } from '../core/probe-users.js';
import { runProbeOperation } from '../core/probe-manager.js';
import { $, seg, setStatus, mhzLabel, ensureSelectOption } from '../ui/dom.js';
import { toast } from '../ui/toast.js';
import { store } from '../core/store.js';
import { webClockKhz,isHpmClockTarget } from '../core/target-clock.js';
import { constrainClockSelect } from '../ui/target-clock.js';
import { RxBuffer } from '../core/rxview.js';
import { AnsiDisplay, terminalBytes } from '../core/display-stream.js';
import { FileRecorder, recordButtonState } from '../core/recorder.js';
import { Rtt } from './protocol.js';
import { OpenOcdProbe } from '../core/openocd-probe.js';
import { OpenOcdEtmProbe } from '../core/openocd-etm.js';
import { isZynqDapDevice, openOcdUsbSupported, selectOpenOcdDevice } from '../core/openocd-usb.js';
import { makeOpenOcdProfile } from '../core/openocd-profile.js';
import { Hpm6800RttProbe } from './hpm6800-probe.js';
import { ArmMemApRttProbe } from './arm-mem-ap-probe.js';
import { hpmBoard } from '../targets/hpm/porting.js';
import { selectedHpmBoard } from '../targets/hpm/select.js';
import { MockProbe } from './mock.js';
import { findSymbol } from './elf.js';
import { parseHex, textToBytes } from '../core/hex.js';
import { waitMs,yieldTask } from '../core/pace.js';
import { rate as fRate, bytes as fBytes, fileStamp, download, stamp as stampOf } from '../core/format.js';

const EOL = { cr: '\r', crlf: '\r\n', lf: '\n', none: '' };
const MAX_RAW = 2 * 1024 * 1024;

export class RttView {
  constructor(){
    this.probe = null;
    this.rtt = null;
    this.mode = 'term';
    this.paused = false;
    this.running = false;
    this._sessionGen = 0;
    this.timer = null;
    this.interval = 5;
    this.records = [];
    this.recBytes = 0;
    this.truncated = false;
    this.term = null;
    this.fit = null;
    this.hist = [];
    this.histIdx = -1;
    this.rec = new FileRecorder();      // 高速采集落文件（见 core/recorder.js）
    this.lastWasCR = false;             // 终端模式补 CR 的跨包状态
    this.suppressed = false;            // 高速自动关显示（见 _highspeedGate）
    this.suppManual = false;            // 用户手动恢复过显示：暂不再自动关，速率回落后重新武装
    this.suppBytes = 0;                 // 关显示期间省略渲染的字节数
    this.stats = { bytes: 0, polls: 0, lost: 0, corrupt: 0, lastBytes: 0, lastPolls: 0, rate: 0, hz: 0 };
  }

  init(){
    this.tx = new RxBuffer($('r-rx'), { mode: 'ascii', maxLines: 4000, maxRaw: MAX_RAW });

    // ---------- 设置 ----------
    store.bind($('r-poll'), 'rtt.poll');
    store.bind($('r-eol'), 'rtt.eol');
    this._chk($('r-ts'), 'rtt.ts', v => { this.ts = v; this.tx.setTimestamps(v, false); });
    this._chk($('r-autoscroll'), 'rtt.autoscroll', v => { this.tx.setAutoscroll(v); });
    this._chk($('r-hexsend'), 'rtt.hexsend', () => {});

    const mode = store.get('rtt.mode', 'term');
    this.mode = mode;
    this.modeSeg = seg(document.querySelector('[data-group=rttmode]'), mode, v => { store.set('rtt.mode', v); this._setMode(v); });
    this.interval = Math.max(1, Number($('r-poll').value) || 5);
    $('r-poll').addEventListener('input', () => { this.interval = Math.max(1, Number($('r-poll').value) || 5); });


    store.bind($('r-target'), 'rtt.target');
    $('r-target').addEventListener('change', () => {
      this.sessionTarget = null;
      this._clearElf();
      this._updateTargetUi();
      if (this.probe) this.disconnect();
    });

    $('r-elf').addEventListener('click', () => this._elfInput.click());
    $('r-pause').addEventListener('click', () => this._togglePause());
    $('r-clear').addEventListener('click', () => this._clear());
    $('r-save').addEventListener('click', () => this.save());
    store.bind($('r-usb-clock'), 'rtt.clockKhz');
    // 老版本这里是 select（0/1000/500/200/2000/4000/8000/12000/20000）：存过 8000/12000 的要能显示出来
    ensureSelectOption($('r-usb-clock'), store.get('rtt.clockKhz', ''), mhzLabel(store.get('rtt.clockKhz', '')));
    $('r-usb-clock').value=String(store.get('rtt.clockKhz','0'));
    this._updateTargetUi();
    store.bind($('r-record-ts'), 'rtt.recordTs', 'checked');
    store.bind($('r-record-auto'), 'rtt.recordAuto', 'checked');
    $('r-record').addEventListener('click', () => this._toggleRecord());
    $('r-err').addEventListener('click', () => {
      // 高速关显示时状态栏就是恢复入口（文字会提示"点此恢复显示"）
      if (this.suppressed){ this.suppManual = true; this._setSuppressed(false); }
    });
    this.rec.onChange = () => this._recordBtn();
    // 记录期间"本页被切到后台"这类提醒（见 core/recorder.js 里的说明）
    this.rec.onNote = s => toast(s, 'warn', 8000);
    this._recordBtn();
    $('r-send').addEventListener('click', () => this._sendInput());

    this._elfInput = document.createElement('input');
    this._elfInput.type = 'file';
    this._elfInput.accept = '.elf,.axf,.out';
    this._elfInput.style.display = 'none';
    this._elfInput.addEventListener('change', () => this._loadElf());
    document.body.appendChild(this._elfInput);

    // ---------- 下行输入 ----------
    $('r-tx').addEventListener('keydown', e => {
      if (e.key === 'Enter'){ e.preventDefault(); this._sendInput(); return; }
      if (e.key === 'ArrowUp' || e.key === 'ArrowDown'){
        if (!this.hist.length) return;
        e.preventDefault();
        this.histIdx = e.key === 'ArrowUp'
          ? (this.histIdx < 0 ? this.hist.length - 1 : Math.max(0, this.histIdx - 1))
          : (this.histIdx < 0 ? -1 : Math.min(this.hist.length - 1, this.histIdx + 1));
        $('r-tx').value = this.histIdx < 0 ? '' : this.hist[this.histIdx];
      }
    });

    setInterval(() => this._stats(), 500);
    // 页面切到后台时浏览器会限速定时器（RTT 轮询会明显变慢）—— 如实告诉用户，别让人以为工具卡了
    document.addEventListener('visibilitychange', () => {
      if (!this.running) return;
      if (document.hidden){
        this._wasRunning = true;
        setStatus($('r-err'), '页面在后台：浏览器会限速定时器，RTT 轮询会变慢（数据不丢，切回来会补上）', null);
      } else if (this._wasRunning){
        this._wasRunning = false;
        setStatus($('r-err'), '', null);
      }
    });
    if (!openOcdUsbSupported()) setStatus($('r-err'), '需要 WebUSB 或本机探针服务', 'err');

    // URL 参数：?backend=mock&auto=1 直接连上（做演示链接/自测用）
    const q = new URLSearchParams(location.search);
    const b = q.get('backend') === 'mock' ? 'mock' : 'webusb';
    this.backend = b;
    this._setMode(mode);                       // 起手就要应用显示模式（否则默认的终端模式没容器，数据看不见）
    // 只有当 URL **明确指定了后端**时才自动连接（否则会拿 localStorage 里上次的后端乱连）
    if (b === 'mock' && q.get('auto') === '1') setTimeout(() => this.connectProbe().catch(() => {}), 150);
  }

  _chk(el, key, apply){
    store.bind(el, key, 'checked');
    el.addEventListener('change', () => apply(el.checked));
    apply(el.checked);
  }


  _targetConfig(){
    const arch = $('r-target').value === 'riscv' ? 'riscv' : 'arm';
    return this.sessionTarget?.arch === arch ? this.sessionTarget : {
      id: arch, arch, label: arch === 'arm' ? 'ARM / SWD（未绑定板型）' : 'RISC-V / JTAG（未绑定板型）',
    };
  }

  _applySessionTarget(target){
    this.sessionTarget = target;
    $('r-target').value = target.arch === 'riscv' ? 'riscv' : 'swd';
    store.set('rtt.target', $('r-target').value);
    this._updateTargetUi();
  }

  _family(target){
    return target.id === 'riscv' ? selectedHpmBoard() : target.id;
  }

  _clearElf(){
    this.elfAddress = null;
    this._elfRevision = (this._elfRevision || 0) + 1;
    setStatus($('r-err'), '请载入与目标匹配的 ELF');
  }

  _updateTargetUi(){
    const config = this._targetConfig();
    const family = this._family(config);
    const clock = $('r-usb-clock');
    const label = clock.closest('label')?.querySelector('span');
    if (label) label.textContent = config.arch === 'riscv' ? 'JTAG TCK' : 'SWD 时钟';
    constrainClockSelect(clock, family, value => store.set('rtt.clockKhz', value));
    clock.disabled = !!config.cfg || !!this.probe;
    clock.title = config.cfg ? `沿用 CFG 的 ${config.cfg.clockKhz} kHz` :
      isHpmClockTarget(family) ? 'HPM JTAG TCK 最高 25 MHz；默认 10 MHz' : '调试时钟最高 60 MHz；默认 10 MHz';
  }

  // ================= 连接 =================
  async connectProbe(device){
    if (this._connectPromise || this._disconnectPromise || this.probe) return;
    const g = this._sessionGen = (this._sessionGen || 0) + 1;
    const backend = this.backend || 'webusb';
    this._probeMock = backend === 'mock';
    this._connectPromise = runProbeOperation(this, 'rtt', () => this._connectProbe(g, backend, device), {
      mock: this._probeMock, reason: 'RTT Viewer 要使用探针', recovery: true,
    });
    try { return await this._connectPromise; }
    catch (e){ this._err(e); return false; }
    finally {
      if (g !== this._sessionGen && (this.probe)) await this.disconnect();
      this._connectPromise = null;
    }
  }

  async _connectProbe(g, b = this.backend || 'webusb', device){
    try {
      if (b !== 'mock'){
        await prepareProbeHandoff(this, 'rtt', 'RTT Viewer 要使用探针');
        if (g !== this._sessionGen) return;
      }
      if (b === 'webusb'){
        const target = this._targetConfig();
        const family = this._family(target);
        const {arch, cfg:imported} = target;
        const memoryAp = (imported?.arch ?? arch) === 'arm';
        const cfg = imported ? { ...imported, memoryAp } : makeOpenOcdProfile({ memoryAp,
          arch, family, port:hpmBoard(family), clockKhz:webClockKhz($('r-usb-clock').value, family, 10000),
        });
        device ??= await selectOpenOcdDevice({ all:$('r-usb-all').checked });
        if (g !== this._sessionGen) return;
        let Probe = memoryAp ? OpenOcdEtmProbe : OpenOcdProbe;
        if (isZynqDapDevice(device)){
          if (memoryAp) Probe = ArmMemApRttProbe;
          if (cfg.boardId === 'hpm6800evk' && !imported) Probe = Hpm6800RttProbe;
        }
        this.probe = new Probe(device, cfg, line => console.debug('[OpenOCD]', line), true);
        this._opening = this.probe.connect();
        try { await this._opening; }
        finally { this._opening = null; }
        toast('探针已连接：' + this.probe.name, 'ok');
      } else if (b === 'mock'){
        this.probe = new MockProbe();
        await this.probe.connect();
        toast('模拟目标已启动（内存里有个假 RTT 控制块）', 'ok');
      } else { throw new Error('仅支持 WebUSB 连接'); }
      if (g !== this._sessionGen) return;
      this._uiConnected(true);
      if ($('r-record-auto').checked && !this.rec.active) this._autoStartRecord();
      /**
       * 🚨 **探针连通 ≠ RTT 控制块就绪**，两者必须分开报错（用户 2026-10 现场质问：
       *    "连接探针以前不依赖 RTT 地址，只要 probe 可用就能连"）。
       *    这里的失败只说明"控制块没找到 / 那一格读不通"，探针本身是好的 ——
       *    所以**不断开探针、不写「连接失败」**，只把原因写进状态条并给出重试入口。
       *    （旧写法把 _startRtt 放在外层 try 里 → 它的异常会触发 disconnect() + "连接失败"，
       *      把"探针明明连上了"说成连接失败，还顺手把探针断掉。）
       */
      const probeNow = this.probe;
      {
        try { await this._startRtt(g); }
        catch (e){
          if (g === this._sessionGen && this.probe === probeNow){
            this._err(e);
            setStatus($('r-err'), '探针已连接 · RTT 控制块未就绪：' + (e?.message || e)
              + ' —— 探针保持连接；请载入与运行固件匹配的 ELF', 'warn');
          }
        }
      }
    } catch (e){
      /**
       * 🚨 收尾时**要把错误留在状态栏上**（2026-10 真机走查踩到）：
       *    `disconnect()` 最后一句是 `setStatus($('r-err'), '已断开')`，它会把 `_err(e)` 刚写上去的
       *    真正原因**覆盖掉** —— 用户看到的是"已断开"，而实际原因是"没找到 RTT 控制块 / 读失败"，
       *    等于把唯一的线索擦掉了（本机就因此白查了一轮：以为是探针没连上）。
       *    这里在断开之后再补一句，把原因留在界面上。
       */
      const why = e?.message || String(e);
      this._err(e);
      await this.disconnect();
      setStatus($('r-err'), '连接失败：' + why);
    }
  }

  async disconnect(){
    this.probeManager?.cancel('rtt');
    this._sessionGen = (this._sessionGen || 0) + 1;
    this.running = false;
    clearTimeout(this.timer);
    if (this._disconnectPromise) return await this._disconnectPromise;
    this._disconnectPromise = this._disconnectNow();
    try {
      const result = await this._disconnectPromise;
      this.probeManager?.forget('rtt');
      return result;
    } catch (e){
      this.probeManager?.fail('rtt', e);
      throw e;
    } finally { this._disconnectPromise = null; }
  }

  async _disconnectNow(){
    this.running = false;
    clearTimeout(this.timer);
    if (this._opening) await this._opening.catch(() => {});
    // A readUp transaction can still be reading/writing RdOff. Let it retire
    // before DAP_Disconnect and native USB close consume the same reply queue.
    await this._drainRtt();
    await this._rttStartTask?.catch(() => {});
    if (this.rec.active || this.rec.needsClose || this.rec.starting || this.rec.draining){
      const info = await this.rec.stop();
      this._recordBtn();
      if (info?.error) toast('记录落盘出错：' + (info.error.message || info.error), 'err', 8000);
      else if (info) toast(`记录已停止并保存：${info.name}（${fBytes(info.bytes)}）`, 'ok', 6000);
    }
    let failure = null;
    if (this.probe?.disconnect){
      try { await this.probe.disconnect(); this.probe = null; }
      catch (e){ failure = e; }
    }
    if (failure) throw failure;
    this.rtt = null;
    this._needsRttReconnect = false;
    this._ringBackpressure = false;
    this.suppManual = false;
    if (this.suppressed) this._setSuppressed(false);
    this._uiConnected(false);
    setStatus($('r-err'), '已断开');
  }

  _uiConnected(on){
    $('r-target').disabled = on;
    this._updateTargetUi();
    if (!on){ $('r-cb').textContent = '—'; $('r-up').textContent = '0'; $('r-down').textContent = '0'; }
  }

  async _drainRtt(){
    const rtt = this.rtt;
    this.rtt = null;
    await rtt?.drain();
    await this._pollTask?.catch(() => {});
    this._pollTask = null;
  }

  async _startRtt(g){
    if (!this.probe || this._disconnectPromise) return;
    if (this._rttStartTask) return await this._rttStartTask;
    this._rttStartTask = this._openRtt(g);
    try { return await this._rttStartTask; }
    finally { this._rttStartTask = null; }
  }

  async _openRtt(g){
    if (g === undefined) g = this._sessionGen = (this._sessionGen || 0) + 1;
    const probe = this.probe;
    const active = () => g === this._sessionGen && this.probe === probe;
    this.running = false;
    clearTimeout(this.timer);
    await this._drainRtt();
    if (!active()) return;
    if (this._needsRttReconnect || probe._faulted){
      if (typeof probe.recoverDebugPort !== 'function') throw Error('请断开并重新连接探针');
      setStatus($('r-err'), '正在重新连接原探针并检查 RTT 控制块…');
      await probe.recoverDebugPort();
      if (!active()) return;
    }
    const address = this._probeMock ? probe.cbAddr : this.elfAddress;
    if (!address){
      setStatus($('r-err'), '探针已连接 · 请载入含 _SEGGER_RTT 的 ELF', 'warn');
      return;
    }
    await probe.prepareRttScan?.();
    if (!active()) return;
    $('r-cb').textContent = '—';
    $('r-up').textContent = $('r-down').textContent = '0';
    setStatus($('r-err'), '正在验证 ELF 指定的 RTT 控制块…');
    const check = await Rtt.validate(probe, address);
    if (!active()) return;
    if (!check.ok) throw Error(`0x${address.toString(16)} 处的 RTT 控制块校验失败：${check.reason}`);
    const rtt = new Rtt(probe, {addr:address});
    await rtt.init();
    if (!active()) return;
    const inff = rtt.info();
    const nm = await rtt.name('up', 0);
    if (!active()) return;
    await probe.useRttMemory?.(inff);
    if (!active()) return;
    this.rtt = rtt;
    $('r-cb').textContent = '0x' + address.toString(16);
    $('r-up').textContent = inff.maxUp;
    $('r-down').textContent = inff.maxDown;
    this._needsRttReconnect = false;
    $('r-chlabel').textContent = `下行 ch0${nm ? ' · ' + nm : ''}`;
    const sz = inff.up[0]?.size || 0;
    setStatus($('r-err'), `控制块 0x${address.toString(16)}，上行缓冲 ${sz} B${inff.maxUp > 1 ? `（固件声明 ${inff.maxUp} 个上行通道，本页读 ch0）` : ''}`, 'ok');
    this._startPoll(g);
  }

  _startPoll(g){
    if (g === undefined) g = this._sessionGen = (this._sessionGen || 0) + 1;
    const rtt = this.rtt, probe = this.probe;
    const active = () => this.running && g === this._sessionGen && this.rtt === rtt && this.probe === probe;
    clearTimeout(this.timer);
    this.running = true;

    this.stats.polls = 0; this.stats.bytes = 0; this.stats.lost = 0;
    this.stats.lastBytes=0;this.stats.lastPolls=0;this._lastStatsAt=performance.now();
    this._ringBackpressure = false;
    this.fullPolls = 0; this.highPolls = 0; this.peak = 0; this._faults = 0; this._corruptRun = 0;
    this._pollT0 = Date.now(); this._zeroHinted = false; this._zeroHintSet = false;   // 见 _stats 里的"零速率"诊断

    const minGap = 0;
    const loop = async () => {
      if (!active()) return;
      const t0 = performance.now();
      try {
        const { bytes, lost, high, level, corrupt } = await rtt.readUp(0);
        if (!active()) return;
        this._faults = 0;
        // Protect the polling loop before rendering can hide a high data rate.
        this._ringBackpressure = Boolean(probe.rttPollLimit && high && bytes.length >= probe.rttPollLimit / 2);
        if (this._ringBackpressure) this._highspeedGate(this.stats.rate);
        if (bytes.length) this._ingest(bytes, new Date());
        if (lost) this.stats.lost += lost;
        if (high) this.highPolls++;
        if (level > this.peak) this.peak = level;
        if (corrupt){
          this.stats.corrupt++;
          this._corruptRun = (this._corruptRun || 0) + 1;
          // 别刷屏：10 秒提醒一次。错位读常见原因：SWD 时钟过高、接线/共地不良
          //（拔插过 LA/杜邦线后特别常见）、或 USB 响应流错位
          if (!this._corruptAt || Date.now() - this._corruptAt > 10000){
            this._corruptAt = Date.now();
            if (!this.suppressed) setStatus($('r-err'),
              '检测到错位读（读回了控制块内容，已丢弃并重读）—— 查 SWD 时钟、接线与共地', 'err');
          }
          if (this._corruptRun >= 15){
            this._fail(new Error('连续读到错位数据'));
            return;
          }
        } else {
          this._corruptRun = 0;
        }
      } catch (e){
        if (!active()) return;
        const msg = String(e?.message || e);
        if (!/FAULT|NO ACK|不可信|不合理|没在运行/i.test(msg) || ++this._faults >= 3){
          this._fail(e);
          return;
        }
      }
      if (!active()) return;
      this.stats.polls++;
      const cost = performance.now() - t0;
      const gap=Math.max(minGap,this.interval-cost,0);
      await (gap>0?waitMs(gap):yieldTask());
      if(active())this._pollTask=loop();
    };
    this._pollTask = loop();
  }

  _fail(e){
    this.running = false;
    clearTimeout(this.timer);
    this._needsRttReconnect = true;
    setStatus($('r-err'), '读取失败：' + (e?.message || e) + '。请重新载入 ELF 或通过顶栏重新连接探针。', 'err');
  }

  _err(e){
    setStatus($('r-err'), String(e?.message || e), 'err');
    toast(String(e?.message || e), 'err', 6000);
  }

  // ================= 数据 =================
  _ingest(bytes, t){
    if (!bytes?.length) return;
    this.stats.bytes += bytes.length;
    this.rec.push(bytes, t);            // 落文件在"显示之前"：暂停/丢历史都不影响它
    this.records.push({ t, b: bytes });
    if (this.records.length === 1) this._updateEmptyHint();
    this.recBytes += bytes.length;
    while (this.recBytes > MAX_RAW && this.records.length > 1){
      this.recBytes -= this.records.shift().b.length;
      this.truncated = true;
    }
    if(this.suppressed){this.suppBytes+=bytes.length;return;}
    if (this.paused) return;
    if (this.mode === 'term') this._termWrite(bytes, t);
    else this.tx.push(bytes, t);
  }

  _termWrite(bytes, t){
    this.ansiDisplay?.push(bytes, t);
  }

  _formatTerminal(bytes, t){
    const body = terminalBytes(bytes, this);
    if (!this.ts) return body;
    const prefix = textToBytes(`\x1b[90m[${stampOf(t)}]\x1b[0m `);
    const out = new Uint8Array(prefix.length + body.length);
    out.set(prefix);
    out.set(body, prefix.length);
    return out;
  }

  _ensureTerm(){
    if (this.term || !window.Terminal) return;
    this.term = new Terminal({
      fontFamily: '"Cascadia Mono","JetBrains Mono",Consolas,monospace',
      fontSize: Number(store.get('rtt.font', 13)) || 13,
      lineHeight: 1.15, cursorBlink: true, scrollback: 3000,
      theme: { background: '#0a0f15', foreground: '#e6edf3', cursor: '#58a6ff', selectionBackground: '#264f78' },
    });
    try { this.fit = new FitAddon.FitAddon(); this.term.loadAddon(this.fit); } catch {}
    this._termStale = !$('tab-rtt').classList.contains('active');   // 在隐藏状态下创建的话，第一次显示时要重放
    this.term.open($('r-term'));
    this.ansiDisplay = new AnsiDisplay(this.term, {
      visible: () => this.mode === 'term' && !this.paused && $('tab-rtt').classList.contains('active'),
      format: (bytes, t) => this._formatTerminal(bytes, t),
      onSkip: () => { this.lastWasCR = false; },
      onError: e => setStatus($('r-err'), '终端显示失败，接收和记录继续：' + e.message, 'err'),
    });
    this.fit?.fit();
    // 允许直接在终端里敲（等价于下行 ch0），像 JLinkRTTViewer 的 Terminal 模式
    this.term.onData(d => {
      const eol = $('r-eol').value;
      if (d === '\r') this._sendBytes(textToBytes(EOL[eol] ?? '\r'));
      else this._sendBytes(textToBytes(d));
    });
    const ro = new ResizeObserver(() => { if (this.mode === 'term') { try { this.fit?.fit(); } catch {} } });
    ro.observe($('r-term'));
  }

  /** 切到本标签时调用（隐藏状态下建的终端在这里补尺寸/重放） */
  onShow(){
    if (this.mode !== 'term' || !this.term) return;
    try { this.fit?.fit(); } catch {}
    if (this._termStale){ this._redrawAll(); this._termStale = false; }
    this.ansiDisplay?.flush();
  }

  _setMode(m){
    this.mode = m;
    $('r-term').hidden = m !== 'term';
    $('r-rx').hidden = m === 'term';
    this._updateEmptyHint();
    if (m === 'term'){ this._ensureTerm(); this._redrawAll(); try { this.fit?.fit(); } catch {} }
    else { this.tx.setMode(m === 'hex' ? 'hex' : 'ascii'); this._redrawAll(); }
  }

  _updateEmptyHint(){
    const hint = $('r-empty');
    if (hint) hint.hidden = this.mode !== 'term' || this.records.length > 0;
  }

  _redrawAll(){
    if (this.mode === 'term'){
      if (!this.term) return;
      this.ansiDisplay?.clear();
      this.lastWasCR = false;
      this.term.clear();
      for (const r of this.records) this._termWrite(r.b, r.t);
    } else {
      this.tx.clear();
      for (const r of this.records) this.tx.push(r.b, r.t);
    }
  }

  _togglePause(){
    this.paused = !this.paused;
    $('r-pause').textContent = this.paused ? '恢复显示' : '暂停显示';
    $('r-pause').classList.toggle('primary', this.paused);
    if (!this.paused) this._redrawAll();
  }

  _clear(){
    this.records = []; this.recBytes = 0; this.truncated = false;
    this.tx.clear();
    this.ansiDisplay?.clear();
    this.lastWasCR = false;
    this.term?.clear();
    this._updateEmptyHint();
  }

  // ================= 下行 =================
  _sendInput(){
    const raw = $('r-tx').value;
    if (!raw.trim()) return;
    const bytes = this._build(raw);
    if (!bytes) return;
    if (this.hist[this.hist.length - 1] !== raw) this.hist.push(raw);
    if (this.hist.length > 100) this.hist.shift();
    this.histIdx = -1;
    $('r-tx').value = '';
    this._sendBytes(bytes);
  }

  _build(text){
    let b;
    if ($('r-hexsend').checked){
      const r = parseHex(text);
      if (r.error){ setStatus($('r-err'), r.error, 'err'); return null; }
      b = r.bytes;
    } else {
      b = textToBytes(text);
    }
    const tail = EOL[$('r-eol').value] ?? '';
    if (tail) b = new Uint8Array([...b, ...textToBytes(tail)]);
    return b;
  }

  async _sendBytes(bytes){
    try {
      const rtt = this.rtt;
      if (!this.running || !rtt) throw new Error('RTT 还没就绪（先扫描控制块）');
      const n = await rtt.writeDown(0, bytes);
      if (this.rtt !== rtt || !this.running) return;
      if (n < bytes.length) toast(`下行缓冲只写进 ${n}/${bytes.length} 字节（固件没在取？）`, 'warn');
      setStatus($('r-err'), '', null);
    } catch (e){ this._err(e); }
  }

  // ================= ELF =================
  async _loadElf(){
    const file = this._elfInput.files?.[0];
    this._elfInput.value = '';
    return await this.loadElfFile(file);
  }

  async loadElfFile(file, buffer){
    if (!file) return false;
    const revision = this._elfRevision = (this._elfRevision || 0) + 1;
    try {
      const bytes = buffer || await file.arrayBuffer();
      if (revision !== this._elfRevision) return false;
      if (this._connectPromise || this._disconnectPromise || this._rttStartTask)
        throw Error('探针操作尚未完成，请稍后载入 ELF');
      const symbol = findSymbol(bytes, '_SEGGER_RTT');
      if (!symbol?.addr || !Number.isInteger(symbol.addr) || symbol.addr > 0xffffffff)
        throw Error(`${file.name} 中没有可用的 _SEGGER_RTT 地址，请载入包含符号表的 ELF`);
      const data = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
      const header = new DataView(data.buffer, data.byteOffset, data.byteLength);
      const machine = header.getUint16(18, data[5] === 1);
      if (machine !== (this._targetConfig().arch === 'arm' ? 40 : 243))
        throw Error('ELF 架构与 Viewer 的目标类型不匹配');
      this.elfAddress = symbol.addr;
      this.onElfLoaded?.(bytes, file.name);
      setStatus($('r-err'), `${file.name} · _SEGGER_RTT 0x${symbol.addr.toString(16)}`, 'ok');
      if (this.probe && !this._probeMock){
        try { await this._startRtt(); }
        catch (error){ this._err(error); }
      }
      return true;
    } catch (error){
      this._err(error);
      return false;
    }
  }

  // ================= 统计 / 保存 =================
  summary(){
    return {connected:!!this.probe,running:this.running,backend:this.backend || 'webusb',
      transport:this.probe?.name ?? null,
      stats:{...this.stats},elfControlBlock:this.elfAddress??null,controlBlock:this.rtt?.addr??null,
      bufferedBytes:this.recBytes,displaySuppressed:this.suppressed,error:$('r-err').textContent};
  }
  _stats(){
    const s = this.stats;
    const now=performance.now(),elapsed=Math.max(.001,(now-(this._lastStatsAt??(now-500)))/1000);
    this._lastStatsAt=now;
    s.rate = Math.max(0, s.bytes - s.lastBytes) / elapsed;
    s.hz = Math.max(0, s.polls - s.lastPolls) / elapsed;
    s.lastBytes = s.bytes; s.lastPolls = s.polls;
    $('r-rate').textContent = fRate(s.rate);
    $('r-hz').textContent = Math.round(s.hz);
    $('r-lost').textContent = s.lost;
    $('r-corrupt').textContent = s.corrupt || 0;
    this._highspeedGate(s.rate);
    const peak = Math.round((this.peak || 0) * 100);
    $('r-full').textContent = `${this.highPolls || 0} 次 / 峰值 ${peak}%`;
    $('r-full').parentElement.title =
      '缓冲水位：RTT 不重传，水位打到 3/4 以上说明目标写速 ≥ 主机读速，可能已有覆盖/丢弃。\n' +
      '（缓冲水位和丢弃计数以实际目标及采集窗口为准）';
    if (peak >= 75) $('r-full').classList.add('err');
    if (this.paused) $('r-pause').title = '显示已暂停，接收和记录继续；恢复后显示当前缓冲';
    // 记录/落盘期间按钮要一直刷：字节数与"待落盘"量都得看得见（见 recorder.js 的说明）
    if (this.rec.active || this.rec.draining) this._recordBtn();
    /**
     * **零速率诊断**（2026-10 用户现场：报"我测 RTT Viewer，没有速率" —— 界面上只有 0 B/s，
     * 看不出该去查哪儿）。控制块找到了、轮询也在跑，却连着 4 秒一个字节都没有时，把可能的原因写出来；
     * 后来读到数据就自动把这句话收掉（只清自己写的那条，不覆盖别的错误）。
     */
    if (this.running && this.rtt && s.bytes === 0 && !this._zeroHinted && Date.now() - (this._pollT0 || 0) > 4000){
      this._zeroHinted = true;
      const errEl = $('r-err');
      if (errEl && !errEl.textContent){
        setStatus(errEl, '控制块在、轮询也在跑，但 4 秒没读到任何字节：' +
          '请检查目标是否正在输出，或是否有 RTT 转发等其他读取端在使用同一个环。', 'warn');
        this._zeroHintSet = true;
      }
    } else if (this._zeroHintSet && s.bytes > 0){
      this._zeroHintSet = false;
      setStatus($('r-err'), '', null);
    }
    if (!this.rtt && this.probe){
      const status = this._rttStartTask && (this.elfAddress || this._probeMock) ? '校验中…' : '—';
      if ($('r-cb').textContent !== status) $('r-cb').textContent = status;
    }
  }

  // ================= 高速自动关显示 =================
  /**
   * WebUSB 实测 330KB/s 时渲染必然掉队 —— 先崩的总是显示，字节本身不丢
   * （统计/落文件是全量，MicroLink 固件侧的 g_bytes 对账可以对出来）。
   * 速率 > 100KB/s 自动停渲染，降到 50KB/s 以下才恢复（回滞）；
   * 点状态栏提示可手动恢复（之后不再自动关，直到速率回落后重新武装）。
   */
  static HS_OFF = 100 * 1024;   // 超过 100KB/s 停渲染
  static HS_ON  = 50 * 1024;    // 降到 50KB/s 以下才自动恢复（回滞）

  _highspeedGate(r){
    if (!this.probe || (this.probe.rttLivePreview && this.mode === 'term')){
      if (this.suppressed) this._setSuppressed(false);
      this.suppManual = false;
      return;
    }
    if (!this.suppressed && !this.suppManual && (this._ringBackpressure || r > RttView.HS_OFF)) this._setSuppressed(true, r);
    else if (!this._ringBackpressure && r < RttView.HS_ON){
      if (this.suppressed) this._setSuppressed(false);
      this.suppManual = false;
    }
  }

  _setSuppressed(on, r = 0){
    if (this.suppressed === on) return;
    this.suppressed = on;
    if (on){
      const reason = this._ringBackpressure ? 'RTT 缓冲积压' : `高速 ${fRate(r)}`;
      setStatus($('r-err'), `${reason}：渲染已停，继续接收和记录 · 点此恢复显示`, 'warn');
      $('r-err').title = '点击恢复显示。若速率仍高于阈值会再次自动关闭';

      const note = `\r\n[${reason}：已暂停渲染，继续接收和记录 · 点状态栏可恢复显示]\r\n`;
      if (this.mode === 'term' && this.term) this._termWrite(new TextEncoder().encode(note), new Date());
      else this.tx.push(new TextEncoder().encode(note), new Date());
    } else {
      setStatus($('r-err'), '', null);
      $('r-err').title = '';
      if (this.suppBytes > 0){
        const note = `（高速期间省略了 ${fBytes(this.suppBytes)} 的渲染；完整数据用「记录到文件」拿）`;
        this.suppBytes = 0;
        if (this.mode === 'term' && this.term) this._termWrite(new TextEncoder().encode(note + '\r\n'), new Date());
        else this.tx.push(new TextEncoder().encode('\r\n' + note + '\r\n'), new Date());
      }
    }
  }

  async _autoStartRecord(){
    try {
      const name = await this.rec.start({ name: 'rtt', timestamps: $('r-record-ts').checked });
      this._recordBtn();
      toast(`已自动开始记录 → ${name}`, 'ok', 5000);
    } catch (e){
      const why = e?.name === 'NotAllowedError' ? '浏览器要求弹保存框时页面正在响应用户点击' : (e?.message || e);
      toast(`自动记录没启动（${why}）。手动点「记录到文件」即可`, 'warn', 6000);
    }
  }

  // ================= 记录到文件 =================
  /**
   * 高速采集时接收区（raw 上限 2MB）存不下 —— 实测 WebUSB 330 KB/s 只要 6 秒就撑爆，
   * 之后「保存数据」只能保存剩下那段。落文件把字节直接写盘，采集多久都不丢。
   */
  async _toggleRecord(){
    if (this.rec.starting || this.rec.draining) return;
    if (this.rec.active || this.rec.needsClose){
      const info = await this.rec.stop();
      this._recordBtn();
      if (info?.error) toast('记录落盘出错：' + (info.error.message || info.error), 'err', 8000);
      else if (info) toast(`已落盘 ${info.name}：${fBytes(info.bytes)} / ${info.frames} 段 / ${info.seconds.toFixed(1)} s —— .crswap 已改名成正式文件`, 'ok', 7000);
      return;
    }
    try {
      const name = await this.rec.start({ name: 'rtt', timestamps: $('r-record-ts').checked });
      this._recordBtn();
      toast(`记录中 → ${name}：Chrome 先写成 ${name}.crswap，点「停止记录」才改名成正式文件（记录中别关页面/刷新）`, 'ok', 8000);
    } catch (e){
      if (e?.name !== 'AbortError') toast('开始记录失败：' + (e?.message || e), 'err', 6000);
    }
  }

  _recordBtn(){
    const b = $('r-record');
    if (!b) return;
    const s = recordButtonState(this.rec);
    b.disabled = this.rec.starting || this.rec.draining;
    b.textContent = s.text;
    b.title = s.title.replace('收到的字节', '读到的 RTT 上行字节');
    b.classList.toggle('primary', s.primary);
  }

  saveRaw(){
    if(!this.records.length)throw Error('还没有原始数据');
    const name=`rtt-raw-${fileStamp()}.bin`;
    download(name,new Blob(this.records.map(r=>r.b),{type:'application/octet-stream'}));
    return {name,bytes:this.recBytes,truncated:!!this.truncated};
  }

  save(){
    let out = '';
    if (this.mode === 'term' && this.term){
      const buf = this.term.buffer.active;
      for (let i = 0; i < buf.length; i++){
        const line = buf.getLine(i);
        out += (line ? line.translateToString(true) : '') + '\n';
      }
    } else {
      out = (this.truncated ? '（较早的数据已因超出上限被丢弃）\n' : '') + this.tx.render(this.records);
    }
    if (!out.trim()){ toast('还没有数据', 'warn'); return; }
    const name = `rtt-${fileStamp()}.txt`;
    download(name, out);
    toast(`已保存 ${name}`, 'ok');
  }
}
