import {store} from '../core/store.js';

/**
 * ETM 执行轨迹页 = superlinkPRO 原始 ETM 工作台，由本地 Zynq 服务直接托管。
 *
 * 页面本身不再由工具箱重新实现：工具箱只负责 iframe、服务探测和错误提示。
 * 本地服务（etm-service/server.py）负责 ZynqDAP 的 SWD/USB 仲裁、FPGA ETM
 * 采集和 OpenCSD 解码；ETM 页内的「逻辑分析仪」已经换成「Zynq ETM 接收」。
 */
export const DEFAULT_ETM_ORIGIN = 'http://127.0.0.1:8766';

export function etmOrigin(){
  // toolbox.py hosts the workbench, ETM and authenticated queue on one origin.
  if (globalThis.location && new URLSearchParams(location.search).has('trace-cli')) return location.origin + '/etm';
  let saved = String(store.get('etm.service', '') || '').trim();
  if (saved && !/^https?:\/\//i.test(saved)) saved = 'http://' + saved;
  return (saved || DEFAULT_ETM_ORIGIN).replace(/\/+$/, '');
}

export async function probeEtmService(origin = etmOrigin(), timeoutMs = 2500){
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${origin}/api/health`, {cache: 'no-store', signal: controller.signal});
    if (!response.ok) throw Error(`HTTP ${response.status}`);
    const info = await response.json();
    return {origin, info};
  } finally {
    clearTimeout(timer);
  }
}

export class EtmView {
  constructor(){
    this.ready = false;
    this.info = null;
    this.origin = etmOrigin();
  }
  get probe(){ return this.bridge?.probe() || null; }
  get busy(){ return !!this.bridge?.busy(); }
  init(){
    this.frame = document.getElementById('etm-frame');
    this.notice = document.getElementById('etm-notice');
    this.status = document.getElementById('etm-status');
    this.retry = document.getElementById('etm-retry');
    this.open = document.getElementById('etm-open');
    const input = document.getElementById('etm-service');
    if (input){
      input.value = store.get('etm.service', '') || '';
      input.onchange = () => {
        const value = String(input.value || '').trim();
        store.set('etm.service', value);
        this.retryLoad();
      };
    }
    if (this.retry) this.retry.onclick = () => this.retryLoad();
    this.load(false);
  }
  async onShow(){
    if (!this.ready) await this.load(false);
  }
  async load(force = false){
    this.origin = etmOrigin();
    if (this.status) this.status.textContent = `正在检测本地 ETM 服务 ${this.origin} …`;
    try {
      const {info} = await probeEtmService(this.origin);
      this.info = info;
      this.ready = true;
      if (this.notice) this.notice.hidden = true;
      if (this.frame){
        this.frame.hidden = false;
        const sameOrigin = new URL(this.origin).origin === location.origin;
        const target = `${this.origin}/${sameOrigin ? '?embedded=1' : ''}`;
        if (force || this.frame.src !== target) this.frame.src = target;
      }
      if (this.open) this.open.href = this.origin + '/';
      return true;
    } catch (error){
      this.ready = false;
      if (this.frame) this.frame.hidden = true;
      if (this.notice) this.notice.hidden = false;
      if (this.status){
        this.status.textContent = `没有找到本地 ETM 服务（${this.origin}）：${error.message}。` +
          '请先运行 etm-service/start-etm.bat，或在下面填入服务地址。';
      }
      return false;
    }
  }
  async retryLoad(){
    try {
      if (this.bridge) {
        if (this.busy) await this.bridge.requestStop();
        await this.run(() => this.releaseProbe());
        this.bridge = null;
      }
      return await this.load(true);
    } catch(error) { this.status.textContent = error.message; return false; }
  }
  attach(bridge, child){
    if (this.bridge && this.bridge !== bridge) throw Error('请先释放原 ETM 连接再刷新');
    this.bridge = bridge;
    child.addEventListener('pagehide', () => {
      if (this.bridge !== bridge) return;
      this.ready = false;
      this.status.textContent = 'ETM 子页面已卸载，请重新检测并释放旧连接';
    }, {once:true});
    return this;
  }
  run(fn){ return this.probeManager ? this.probeManager.run('etm', fn, {reason:'ETM 执行轨迹使用探针'}) : fn(); }
  async releaseProbe(){
    if (this.busy) throw Error('ETM 正在操作目标或采集，请先停止');
    if (this.bridge) await this.bridge.release();
    if (this.probe) throw Error('ETM 探针尚未断开');
    this.probeManager?.forget('etm');
  }
  summary(){ return {ready: this.ready, origin: this.origin, health: this.info, connected:!!this.probe,
    busy:this.busy, ...this.bridge?.summary()}; }
}

