/** Read-only counters for completed DAP requests. Never logs register values. */
export class DapProfile {
  constructor(now=()=>performance.now()){this.now=now;this.state={};this.reset();this.enabled=false;}
  reset(){this.commands={};this.accesses={};this.regions={};this.stages={};this.unknownWords=0;this.stage=null;this.stageStart=null;this.enabled=true;}
  setStage(name){
    if(!this.enabled)return;
    const time=this.now();
    if(this.stage!==null)this.stages[this.stage].wallMs+=time-this.stageStart;
    this.stage=typeof name==='string'&&name.length<=100?name:null;this.stageStart=time;
    if(this.stage!==null)this.stages[this.stage]??={wallMs:0,commands:0};
  }
  open(){this.state={};}
  word(read){
    const {select,tar,csw}=this.state;
    if(select===undefined || (select&0xf0)!==0 || tar===undefined || csw===undefined){if(this.enabled)this.unknownWords++;return;}
    const size=1<<(csw&7),region=tar>=0x08000000&&tar<0x08100000?'flash':tar>=0x20000000&&tar<0x40000000?'ram':tar>=0xe0000000?'core-debug':tar>=0x40000000&&tar<0x60000000?'peripheral':'other';
    const key=read?'reads':'writes';
    if(this.enabled)(this.regions[region]??={reads:0,writes:0})[key]++;
    if(this.enabled && (region==='core-debug'||region==='peripheral')){
      const address='0x'+tar.toString(16).padStart(8,'0');
      if(this.accesses[address]||Object.keys(this.accesses).length<512)(this.accesses[address]??={reads:0,writes:0})[key]++;
    }
    if(((csw>>>4)&3)===1)this.state.tar=((tar&~0x3ff)|((tar+size)&0x3ff))>>>0;
  }
  record(req,reply){
    if(!req?.length||!reply?.length||req[0]!==reply[0])return;
    const cmd=req[0],key='0x'+cmd.toString(16).padStart(2,'0');if(this.enabled)this.commands[key]=(this.commands[key]||0)+1;
    if(this.enabled&&this.stage!==null)this.stages[this.stage].commands++;
    const u32=(b,i)=>(b[i]|b[i+1]<<8|b[i+2]<<16|b[i+3]<<24)>>>0;
    if(cmd===5 && req.length>=3 && reply.length>=3){
      const n=Math.min(req[2],reply[1]);let offset=3,data=3;
      for(let i=0;i<n&&offset<req.length;i++){
        const op=req[offset++],ap=!!(op&1),read=!!(op&2),address=op&12;
        if(!read&&offset+4>req.length)return;
        const value=read?(data+4<=reply.length?u32(reply,data):undefined):u32(req,offset);
        if(read)data+=4;else offset+=4;
        if(!ap&&!read&&address===8)this.state.select=value;
        if(ap && this.state.select!==undefined && !(this.state.select&0xf0)){
          if(address===0&&value!==undefined)this.state.csw=value;
          if(address===4&&!read)this.state.tar=value;
          if(address===12)this.word(read);
        }
      }
    }else if(cmd===6&&req.length>=5&&reply.length>=4){
      const count=Math.min(req[2]|req[3]<<8,reply[1]|reply[2]<<8),op=req[4];
      if((op&13)===13)for(let i=0;i<count;i++)this.word(!!(op&2));
    }
  }
  snapshot(){
    const result=structuredClone({commands:this.commands,regions:this.regions,registers:this.accesses,stages:this.stages,unknownWords:this.unknownWords});
    if(this.stage!==null)result.stages[this.stage].wallMs+=this.now()-this.stageStart;
    result.basis='completed DAP requests and AP word accesses; SWD retry cycles are not counted';return result;
  }
}
