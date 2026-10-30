/** Explicit local-service transport. Existing DAP/HID/serial/scope logic is reused. */
function host(){
  try{
    const w=globalThis.window;
    if(w?.document?.body?.dataset?.nativeProbe==='1')return w;
    if(w?.parent!==w&&w?.parent?.document?.body?.dataset?.nativeProbe==='1')return w.parent;
  }catch{}
  return null;
}
export function nativeProbeEnabled(){return !!host();}
const identity=()=>crypto.randomUUID().replaceAll('-','');
function encoded(value){
  const bytes=ArrayBuffer.isView(value)?new Uint8Array(value.buffer,value.byteOffset,value.byteLength):new Uint8Array(value);
  let text='';for(let i=0;i<bytes.length;i+=8192)text+=String.fromCharCode(...bytes.subarray(i,i+8192));
  return btoa(text);
}
const decoded=text=>Uint8Array.from(atob(text||''),c=>c.charCodeAt(0));
async function call(kind,action,value={}){
  const w=host();if(!w)throw Error('本地探针服务未启用');
  const token=new URLSearchParams(w.location.search).get('trace-cli');
  if(!/^[0-9a-f]{64}$/.test(token||''))throw Error('本地探针服务需要CLI运行时地址');
  const response=await fetch(w.location.origin+'/native-probe/'+kind+'/'+action,{method:'POST',
    headers:{'Content-Type':'application/json','X-Trace-CLI':token},body:JSON.stringify(value)});
  const result=await response.json();
  if(!response.ok||!result.ok)throw Error(result.error||'本地探针服务HTTP '+response.status);
  return result.value;
}

const usbCache=new Map(),hidCache=new Map(),serialCache=new Map();
export async function nativeUsbDevices(){
  const devices=await call('usb','list');
  return devices.map(info=>{
    const key=info.vendorId+':'+info.productId+':'+info.serialNumber;
    let device=usbCache.get(key);if(!device){device=new NativeUsbDevice(info);usbCache.set(key,device);}return device;
  });
}
class NativeUsbDevice extends EventTarget{
  constructor(info){super();Object.assign(this,info);this.nativeService=true;this.opened=false;this.owner=identity();this.reads=new Map();this.commandPending=0;}
  rpc(action,value={}){return call('usb',action,{owner:this.owner,...value});}
  async open(){Object.assign(this,await this.rpc('open'));this.opened=true;}
  async close(){await this.rpc('close');this.opened=false;this.commandPending=0;}
  async selectConfiguration(number){Object.assign(this,await this.rpc('configuration',{number}));}
  async claimInterface(number){await this.rpc('claim',{number});const i=this.configuration.interfaces.find(i=>i.interfaceNumber===number);if(i)i.claimed=true;}
  async releaseInterface(number){await this.rpc('release',{number});const i=this.configuration.interfaces.find(i=>i.interfaceNumber===number);if(i)i.claimed=false;}
  async selectAlternateInterface(number,alternate){await this.rpc('alternate',{number,alternate});const i=this.configuration.interfaces.find(i=>i.interfaceNumber===number);if(i)i.alternate=i.alternates.find(a=>a.alternateSetting===alternate);}
  async clearHalt(direction,endpoint){await this.rpc('clear',{endpoint:endpoint|(direction==='in'?128:0)});}
  async reset(){await this.rpc('reset');this.commandPending=0;}
  async transferOut(endpoint,data){
    const result=await this.rpc('write',{endpoint,data:encoded(data)});
    if(data.byteLength)this.commandPending++;
    return {status:'ok',bytesWritten:result.bytesWritten};
  }
  transferIn(endpoint,length){
    // Keep packet order across HTTP response scheduling. Native HSS uses one
    // batched reader instead of concurrent browser USB URBs.
    const previous=this.reads.get(endpoint)||Promise.resolve();
    const next=previous.catch(()=>{}).then(async()=>{
      const pending=endpoint===1&&this.commandPending>0;
      const result=await this.rpc('read',{endpoint:endpoint|128,length,commandPending:pending});
      if(pending)this.commandPending--;
      if(pending&&result.timedOut)throw Error('本地DAP响应超时；未重放命令');
      const bytes=decoded(result.data);return {status:'ok',data:new DataView(bytes.buffer)};
    });
    this.reads.set(endpoint,next);return next;
  }
}

export async function nativeHidDevices(){
  return (await call('hid','list')).map(info=>{
    const key=info.serialNumber;
    let device=hidCache.get(key);if(!device){device=new NativeHidDevice(info);hidCache.set(key,device);}return device;
  });
}
class NativeHidDevice extends EventTarget{
  constructor(info){super();Object.assign(this,info);this.nativeService=true;this.opened=false;this.owner=identity();}
  rpc(action,value={}){return call('hid',action,{owner:this.owner,...value});}
  async open(){await this.rpc('open');this.opened=true;}
  async close(){await this.rpc('close');this.opened=false;}
  async sendReport(reportId,data){
    const result=await this.rpc('report',{reportId,data:encoded(data)});
    const bytes=decoded(result.data),event=new Event('inputreport');
    Object.assign(event,{device:this,reportId:result.reportId,data:new DataView(bytes.buffer)});this.dispatchEvent(event);
  }
}

export async function nativeSerialPorts(){
  return (await call('serial','list')).map(info=>{
    let port=serialCache.get(info.path);if(!port){port=new NativeSerialPort(info);serialCache.set(info.path,port);}return port;
  });
}
class NativeSerialPort{
  constructor(info){Object.assign(this,info);this.nativeService=true;this.owner=identity();this.readable=this.writable=null;}
  getInfo(){return {usbVendorId:this.usbVendorId,usbProductId:this.usbProductId,portName:this.path};}
  rpc(action,value={}){return call('serial',action,{owner:this.owner,path:this.path,...value});}
  async open(options){
    await this.rpc('open',{options});this.cancelled=false;
    this.readable=new ReadableStream({pull:async controller=>{
      try{while(!this.cancelled){const result=await this.rpc('read');if(this.cancelled)return;const bytes=decoded(result.data);if(bytes.length){controller.enqueue(bytes);return;}}}
      catch(error){if(!this.cancelled)controller.error(error);}
    },cancel:()=>{this.cancelled=true;}});
    this.writable=new WritableStream({write:async bytes=>{await this.rpc('write',{data:encoded(bytes)});}});
  }
  async close(){this.cancelled=true;await this.rpc('close');this.readable=this.writable=null;}
  async setSignals(signals){await this.rpc('signals',{signals});}
  getSignals(){return this.rpc('get-signals');}
}
