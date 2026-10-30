// STM32F103ZE ETMv3.5 recipe, ported from superlinkPRO's verified f103ze_etm.py.
export const REG={demcr:0xe000edfc,dbg_cr:0xe0042004,etmcr:0xe0041000,etmtrigger:0xe0041008,
  etmteevr:0xe0041020,etmtecr1:0xe0041024,etmfflr:0xe004102c,etmtraceidr:0xe0041200,
  cspsr:0xe0040004,sppr:0xe00400f0,ffcr:0xe0040304,acpr:0xe0040010};
export class EtmTarget{
  constructor(probe){this.probe=probe;this.saved=null;this.locks=new Map();}
  async read(addr){const b=await this.probe.readMemDiagnostic(addr,4);return new DataView(b.buffer,b.byteOffset,4).getUint32(0,true);}
  async write(addr,value){const b=new Uint8Array(4);new DataView(b.buffer).setUint32(0,value>>>0,true);await this.probe.writeMemDiagnostic(addr,b);await this.probe.flushWrites();}
  async waitProgram(value){for(let i=0;i<100;i++)if(((await this.read(0xe0041010))&2)===(value?2:0))return;throw Error('ETM 编程态握手超时');}
  async unlock(base){const lock=await this.read(base+0xfb4);if(!this.locks.has(base))this.locks.set(base,!!(lock&2));if((lock&3)===3)await this.write(base+0xfb0,0xc5acce55);if((await this.read(base+0xfb4))&2)throw Error('CoreSight 解锁失败');}
  /** @param {{divider?:number}} options TRACECLK 分频（1～4，TPIU ACPR）；实板语法见 README。 */
  async prepare({divider=3}={}){
    if(this.saved)throw Error('上一次目标 trace 配置尚未恢复');
    const cpuid=await this.read(0xe000ed00),device=(await this.read(0xe0042000))&0xfff;
    if(((cpuid>>>4)&0xfff)!==0xc23||device!==0x414)throw Error('当前自动配置仅支持 STM32F103ZE / Cortex-M3');
    // F103ZE can return zero from gated TPIU registers until TRCENA is set.
    // Preserve DEMCR before enabling access, then snapshot the real registers.
    const demcr=await this.read(REG.demcr);
    try{
      await this.write(REG.demcr,demcr|0x01000000);
      const saved={demcr};for(const [name,addr]of Object.entries(REG))if(name!=='demcr')saved[name]=await this.read(addr);
      if(!((await this.read(0xe0040000))&8))throw Error('TPIU 不支持四位 DDR');
      this.saved=saved;await this.unlock(0xe0041000);await this.unlock(0xe0040000);
      this.control=(this.saved.etmcr|0xc00)&~0x301;
      await this.write(REG.etmcr,this.control);await this.waitProgram(true);
      for(const [name,value]of Object.entries({etmtrigger:0,etmteevr:0x6f,etmtecr1:0,etmfflr:0,etmtraceidr:2,cspsr:8,sppr:0,ffcr:this.saved.ffcr|2,dbg_cr:(this.saved.dbg_cr&~0xe0)|0xe0}))await this.write(REG[name],value);
      this.divider=Math.min(4,Math.max(1,Math.round(Number(divider)||3)));
      await this.write(REG.acpr,this.divider-1);   // ACPR：TRACECLK = HCLK / divider
      this.config={protocol:'ETMv3',idr:await this.read(0xe00411e4),ctrl:(await this.read(REG.etmcr))&~0x400,ccer:await this.read(0xe00411e8),traceid:await this.read(REG.etmtraceidr),divider:this.divider};
      return this.config;
    }catch(e){try{if(this.saved)await this.restore();else await this.write(REG.demcr,demcr);}catch(cleanup){e.message+='；恢复失败：'+cleanup.message;}throw e;}
  }
  async start(){await this.write(REG.etmcr,this.control&~0x400);await this.waitProgram(false);}
  async stop(){if(this.saved){await this.write(REG.etmcr,this.control);await this.waitProgram(true);}}
  async restore(){
    if(!this.saved)return;
    await this.unlock(0xe0041000);await this.unlock(0xe0040000);
    await this.write(REG.etmcr,(this.control|0x400)&~1);await this.waitProgram(true);
    for(const name of ['etmtrigger','etmteevr','etmtecr1','etmfflr','etmtraceidr','cspsr','sppr','ffcr','acpr','dbg_cr'])await this.write(REG[name],this.saved[name]);
    await this.write(REG.etmcr,this.saved.etmcr);
    for(const [base,locked]of this.locks)if(locked)await this.write(base+0xfb0,0);
    await this.write(REG.demcr,this.saved.demcr);this.saved=null;this.locks.clear();
  }
}
