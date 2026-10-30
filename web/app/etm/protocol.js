// ZET1 packets from this project's PS USB EP2 IN. No ORBFlow or Kingst bridge.
export const TRACE_ENDPOINT=2;
export class TracePackets{
  constructor(){this.pending=new Uint8Array(0);this.sequence=null;this.captureId=null;this.records=0;this.chunks=[];this.loss=false;this.ended=false;this.fclk=0;this.synced=false;}
  feed(bytes){
    const input=new Uint8Array(this.pending.length+bytes.length);input.set(this.pending);input.set(bytes,this.pending.length);
    let offset=0;
    while(input.length-offset>=32){
      const v=new DataView(input.buffer,input.byteOffset+offset);
      if(v.getUint32(0,true)!==0x3154455a||v.getUint32(28,true)!==1)throw Error('不是 ZynqDAP ZET1 trace 数据');
      const seq=v.getUint32(4,true),flags=v.getUint32(8,true),count=v.getUint32(12,true),id=v.getUint32(24,true);
      if(count>240)throw Error('Trace 包记录数越界');
      const length=32+count*2;if(input.length-offset<length)break;
      if(this.ended)throw Error('捕获结束后仍有 trace 包');
      if(this.captureId!==null&&this.captureId!==id)throw Error('Trace 捕获会话在流中改变');
      if(this.sequence===null ? seq!==0 : seq!==((this.sequence+1)>>>0))this.loss=true;
      this.sequence=seq;this.captureId=id;this.loss||=!!(flags&4);this.synced||=!!(flags&2);this.ended=!!(flags&8);this.fclk=v.getUint32(20,true);this.tckKhz=flags>>>16;
      const records=input.slice(offset+32,offset+length);for(let n=1;n<records.length;n+=2)if(records[n]&0x80)throw Error('无效 trace source ID');
      this.chunks.push(records);this.records+=count;offset+=length;
    }
    this.pending=input.slice(offset);
    if(this.ended&&this.pending.length)throw Error('Trace 结束包后存在残留字节');
    return this.ended;
  }
  stream(id){
    const values=[];for(const b of this.chunks)for(let i=0;i<b.length;i+=2)if(b[i+1]===id)values.push(b[i]);
    return Uint8Array.from(values);
  }
  quality(){return {records:this.records,loss:this.loss,synced:this.synced,ended:this.ended,trailingBytes:this.pending.length,fclk:this.fclk,tckKhz:this.tckKhz||null,captureId:this.captureId};}
}
export function base64(bytes){let text='';for(let i=0;i<bytes.length;i+=0x4000)text+=String.fromCharCode(...bytes.subarray(i,i+0x4000));return btoa(text);}
export function unbase64(text){return Uint8Array.from(atob(text),c=>c.charCodeAt(0));}
export async function sha256(bytes){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(v=>v.toString(16).padStart(2,'0')).join('');}
