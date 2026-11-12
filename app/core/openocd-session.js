import { OpenOcdUsb } from './openocd-usb.js';

// One Worker owns the OpenOCD instance. ProbeManager owns the target lease.
export class OpenOcdTargetSession {
  static createWorker(){
    return new Worker(new URL('./openocd-worker.mjs', import.meta.url), { type:'module' });
  }

  constructor(onLog){
    this.onLog = onLog;
    this.worker = null;
    this.sequence = 0;
    this.queue = Promise.resolve();
  }

  async open(cfg, device){
    if (this.worker) throw new Error('OpenOCD 会话已经打开');
    const worker = this.worker = OpenOcdTargetSession.createWorker();
    this.usb = device && new OpenOcdUsb(device);
    this.usbQueue = Promise.resolve();
    worker.onmessage = ({ data }) => {
      if (data.usbCall){
        const { id, method, args } = data.usbCall;
        const invoke = async () => {
          if (this.worker !== worker || !this.usb) return;
          let reply;
          try { reply = { value:await this.usb.invoke(method, args) }; }
          catch (error){ reply = { error:error.message }; }
          if (this.worker === worker) worker.postMessage({ usbReply:{ id, ...reply } });
        };
        // Preserve the order of DAP replies over the native HTTP transport.
        this.usbQueue = this.usbQueue.then(invoke, invoke);
        return;
      }
      if (data.id !== this.pending?.id) return;
      if (typeof data.log === 'string') {
        this.pending.lastLog = data.log;
        if (this.pending.type === 'open' || this.pending.command === 'init') this.onLog?.(data.log);
        return;
      }
      const error = data.error || (data.code ? [data.value, ...data.lines || []].filter(Boolean).join('\n') || 'OpenOCD 命令失败' : '');
      this.finish(error ? new Error(error) : null, data);
    };
    worker.onerror = event => {
      worker.terminate();
      this.worker = null;
      this.finish(new Error(event.message || 'OpenOCD Wasm 无法加载'));
    };
    const usb = device && { vendorId:device.vendorId, productId:device.productId,
      productName:device.productName, serialNumber:device.serialNumber };
    try {
      await this.request('open', { script:cfg.script, raw:cfg.raw, streamLogs:true, device:usb });
    } catch (error){
      try { await this.close(); }
      catch (cleanup){ throw new AggregateError([error, cleanup], `${error.message}；USB 清理失败：${cleanup.message}`); }
      throw error;
    }
  }

  request(type, payload, timeoutMs = 15000){
    const task = this.queue.then(() => new Promise((resolve, reject) => {
      if (!this.worker) throw new Error('OpenOCD 会话已关闭');
      const id = ++this.sequence;
      const timer = setTimeout(() => {
        const lastLog = this.pending?.lastLog;
        this.finish(new Error('OpenOCD 操作超时' + (lastLog ? '：' + lastLog : '')));
        this.worker?.terminate();
        this.worker = null;
      }, timeoutMs);
      this.pending = { id, type, command:payload?.command, timer, resolve, reject };
      this.worker.postMessage({ id, type, ...payload });
    }));
    this.queue = task.catch(() => {});
    return task;
  }

  finish(error, result){
    const pending = this.pending;
    this.pending = null;
    if (!pending) return;
    clearTimeout(pending.timer);
    if (error) pending.reject(error);
    else pending.resolve(result);
  }

  async command(command, timeoutMs){
    const response = await this.request('command', { command }, timeoutMs);
    return response.value.trim();
  }

  async close(){
    try { if (this.worker) await this.request('close'); }
    finally {
      this.worker?.terminate();
      this.worker = null;
      // Native calls already submitted to the service have bounded timeouts.
      // Await them before releasing its owner and epoch. WebUSB close retires
      // an outstanding transfer on the claimed interface.
      if (this.usb?.device.nativeService) await this.usbQueue;
      await this.usb?.close();
      this.usb = null;
    }
  }
}
