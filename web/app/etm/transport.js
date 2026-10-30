import {UsbLease} from '../core/usb-device.js';
import {TracePackets,TRACE_ENDPOINT} from './protocol.js';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
export class EtmTransport{
  constructor(device,onChange=()=>{}){this.lease=new UsbLease(device,'etm');this.onChange=onChange;this.parser=null;this.running=false;this.inFlight=16;this.chunkBytes=8192;}
  async open(){
    await this.lease.open();this.device=this.lease.device;
    const iface=this.device.configuration.interfaces.find(i=>i.alternates.some(a=>a.endpoints.some(e=>e.direction==='in'&&e.type==='bulk'&&e.endpointNumber===TRACE_ENDPOINT)));
    if(!iface)throw Error('当前固件没有 ETM bulk-in 0x82，请加载配套 bit/ELF');
    this.interface=iface.interfaceNumber;await this.lease.claim(this.interface,[TRACE_ENDPOINT|0x80]);
    const info=await this.control();if(info[0]!==0x45544d31)throw Error('ETM PL 签名不匹配，请核对 bit/ELF 配对');
    const ref=await this.device.controlTransferIn({requestType:'vendor',recipient:'device',request:0x61,value:0,index:0x4554},16);
    if(ref.status!=='ok'||ref.data?.byteLength!==16)throw Error('ETM 时钟信息不匹配，请加载配套 ELF');
    this.refClockHz=ref.data.getUint32(0,true);
    if(this.refClockHz<190000000||this.refClockHz>210000000)throw Error('独立采样参考时钟未初始化到 200 MHz 范围');
  }
  async control(action=0){
    const r=await this.device.controlTransferIn({requestType:'vendor',recipient:'device',request:0x60,value:action,index:0x4554},32);
    if(r.status!=='ok'||r.data?.byteLength!==32)throw Error('ETM 控制请求失败');
    return Array.from({length:8},(_,i)=>r.data.getUint32(4*i,true));
  }
  async start(){
    if(this.running)throw Error('ETM 已在采集');
    if(this.error)throw this.error;
    this.parser=new TracePackets();await this.control(0x301);
    for(let i=0;i<100;i++){const s=await this.control();if((s[1]&1)&&(s[1]&16)&&!s[7])break;if(i===99)throw Error('ETM 采样延时校准未就绪，请核对配套 bit/ELF 和 PS 初始化文件');await sleep(5);}
    this.running=true;
    this.readLoop=this.receive().finally(()=>{this.running=false;this.onChange(this.parser);});
    // Attach a handler immediately, while preserving rejection for stop().
    this.readLoop.catch(e=>{this.error=e;this.onChange(this.parser,e);});
  }
  async receive(){
    const pending=[];
    const read=()=>{const p=this.device.transferIn(TRACE_ENDPOINT,this.chunkBytes);p.catch(()=>{});return p;};
    for(let i=0;i<this.inFlight;i++)pending.push(read());
    let notified=0,limitNotified=false;
    for(;;){
      const r=await pending.shift();
      if(r.status!=='ok'||!r.data)throw Error('ETM bulk-in 传输失败');
      const done=this.parser.feed(new Uint8Array(r.data.buffer,r.data.byteOffset,r.data.byteLength));
      const limit=!limitNotified&&this.byteLimit&&this.parser.records*2>=this.byteLimit;
      if(limit)limitNotified=true;
      const stamp=Date.now();
      if(done||limit||stamp-notified>=80){this.onChange(this.parser);notified=stamp;}
      if(done){
        // Firmware sends retirement ZLPs after END. Drain every issued read
        // before releasing a shared interface; no device-wide reset is needed.
        for(const request of pending){const tail=await request;if(tail.status!=='ok'||tail.data?.byteLength)throw Error('ETM 结束后仍有数据或 USB 读取失败');}
        return;
      }
      pending.push(read());
    }
  }
  async stop(){
    if(!this.running){if(this.error)throw this.error;return;}
    await this.control(2);
    let timer;
    try{await Promise.race([this.readLoop,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('ETM 结束包未到达，USB 读取仍待完成')),5000);})]);}
    finally{clearTimeout(timer);}
  }
  async close(){await this.stop();await this.lease.close();}
}
