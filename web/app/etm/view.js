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
  const saved = String(store.get('etm.service', '') || '').trim();
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
  get busy(){ return false; }
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
        this.load(true);
      };
    }
    if (this.retry) this.retry.onclick = () => this.load(true);
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
        const target = `${this.origin}/`;
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
  releaseProbe(){}
  summary(){ return {ready: this.ready, origin: this.origin, health: this.info}; }
}

