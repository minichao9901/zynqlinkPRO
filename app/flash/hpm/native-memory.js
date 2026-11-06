/** Existing Zynq RISC-V virtual MEM-AP, restricted to flashloader RAM.
 * Standard DAP TransferBlock replaces thousands of raw DMI/HTTP round trips.
 * No fallback/replay after a native request may have touched target memory.
 */
export class HpmNativeMemory {
  constructor(dm,probe,port){
    this.dm=dm;this.probe=probe;this.port=port;
    this.stats={reads:0,writes:0,readBytes:0,writeBytes:0,blocks:0};
  }
  static eligible(probe,port){
    return port.id==='hpm6800evk'&&probe.device?.nativeService===true&&probe.device.dapSynchronized===true&&probe.requestedClockHz===10000000;
  }
  contains(addr,length){
    const area=this.port.memory.workArea;
    return Number.isInteger(addr)&&Number.isInteger(length)&&length>=64&&addr>=area.addr&&addr+length<=area.addr+area.size;
  }
  async command(code,payload,deadline){return await this.probe._ctrl(code,payload,{deadline});}
  async clockSnapshot(deadline){
    const reply=await this.command(0x80,Uint8Array.of(255),deadline);
    if(reply.length!==11||reply[0]!==0)throw new Error('无法读取实际探针时钟');
    const view=new DataView(reply.buffer,reply.byteOffset,reply.byteLength),fclk=view.getUint32(3,true),cfg=view.getUint32(7,true);
    const half=1+((cfg>>>13)&15)+(((cfg>>>28)&15)<<4);
    return {fclkHz:fclk,tckHz:fclk/(2*half),cfg,basis:'PS/PL register calculation, not external measurement'};
  }
  async transfer(kind,addr,value,timeoutMs=2000){
    const length=kind==='read'?value:value.length;
    if(!this.contains(addr,length)||addr%4||length%4)throw new Error('原生批量访问仅允许对齐的 flashloader RAM');
    const deadline=performance.now()+Math.max(timeoutMs,length),clock=this.probe.requestedClockHz;
    const le=value=>[value&255,(value>>>8)&255,(value>>>16)&255,(value>>>24)&255];
    let error,switched=false;
    try{
      const mode=await this.command(0x8b,Uint8Array.of(1),deadline);
      if(mode.length!==2||mode[0]!==0||mode[1]!==1)throw new Error('探针未确认 RISC-V 原生内存模式');
      switched=true;await this.probe.setClock(clock);
      const result=kind==='read'?new Uint8Array(length):null;
      const maxWords=Math.min(120,Math.floor(((this.probe.pkt||512)-(kind==='read'?4:5))/4));
      for(let offset=0;offset<length;offset+=maxWords*4){
        const count=Math.min(maxWords,(length-offset)/4);
        const address=await this.command(5,Uint8Array.of(0,3,8,...le(0),1,...le(0x23000052),5,...le(addr+offset)),deadline);
        if(address.length<2||address[0]!==3||address[1]!==1)throw new Error('原生 RAM 地址设置失败；未重放');
        if(!this.stats.nativeClock){
          this.stats.nativeClock=await this.clockSnapshot(deadline);
          if(Math.abs(this.stats.nativeClock.tckHz-clock)>10)throw new Error('原生批量通路实际时钟与请求不符，未开始数据搬运');
        }
        const payload=new Uint8Array(4+(kind==='write'?count*4:0));
        payload.set([0,count&255,count>>>8,kind==='read'?15:13]);
        if(kind==='write')payload.set(value.subarray(offset,offset+count*4),4);
        const reply=await this.command(6,payload,deadline);this.stats.blocks++;
        if(reply.length!==(kind==='read'?3+count*4:3)||reply[0]!==count%256||reply[1]!==(count>>>8)||reply[2]!==1)
          throw new Error('原生 RAM 批量结果不完整；未重放或退回逐字访问');
        if(result)result.set(reply.subarray(3),offset);
      }
      this.stats[kind==='read'?'reads':'writes']++;this.stats[kind==='read'?'readBytes':'writeBytes']+=length;
      return result;
    }catch(e){error=e;throw e;}
    finally{
      this.dm._sbcsCfg=null;this.dm._holdAddr=null;
      // A timed-out wire cannot safely accept cleanup commands.
      if(error&&/timeout|超时|短写|fetch/i.test(error.message)){this.dm._wireFault=error;}
      else if(switched){
        try{
          const raw=await this.command(0x8b,Uint8Array.of(0x0e),deadline);
          if(raw[0]!==0||raw[1]!==0x0e)throw new Error('未确认恢复原始 JTAG 模式');
          await this.probe.setClock(clock);
          await this.dm.dap.resetTapAndLoadIR(0x11);
          if(!this.stats.rawClock)this.stats.rawClock=await this.clockSnapshot(deadline);
          if(Math.abs(this.stats.rawClock.tckHz-clock)>10)throw new Error('原始 JTAG 实际时钟未恢复');
        }catch(cleanup){this.dm._wireFault=cleanup;if(error)throw new AggregateError([error,cleanup],'原生内存及收尾均失败');throw cleanup;}
      }
    }
  }
  install(){
    const dm=this.dm,read=dm.readMem.bind(dm),write=dm.writeMem.bind(dm);
    const run=(kind,addr,value,timeout)=>{
      const length=kind==='read'?value:value.length;
      if(!this.contains(addr,length)||addr%4||length%4)return kind==='read'?read(addr,value,timeout):write(addr,value,timeout);
      if(dm._wireFault)return Promise.reject(dm._wireFault);
      return dm._exclusive('_sbaQueue',()=>dm._exclusive('_dmiQueue',()=>this.transfer(kind,addr,value,timeout)));
    };
    dm.readMem=(addr,length,timeout)=>run('read',addr,length,timeout);
    dm.writeMem=(addr,bytes,timeout)=>run('write',addr,bytes,timeout);
    return this;
  }
}
