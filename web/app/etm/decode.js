import createDecoder from './opencsd.mjs';
// A fresh instance per capture isolates OpenCSD's global logger/decoder state.
export async function decodeTrace({etm,config,images,maxRecords=2000000}){
  if(config.protocol!=='ETMv3')throw Error('当前接收链路解码配置需要 ETMv3');
  const records=[],errors=[];
  let recordLimit=false;
  const module=await createDecoder({noInitialRun:true,
    print:line=>{if(line.startsWith('{')){if(records.length>=maxRecords)recordLimit=true;else records.push(JSON.parse(line));}},
    printErr:line=>errors.push(line)});
  module.FS.writeFile('/trace.bin',etm);
  let manifest='ETMv3\n'+['idr','ctrl','ccer','traceid'].map(k=>{
    const v=config[k];if(!Number.isInteger(v)||v<0||v>0xffffffff)throw Error('无效的 ETM 配置 '+k);return '0x'+v.toString(16)+'\n';
  }).join('');
  for(const [i,image]of images.entries()){
    const path='/image-'+i+'.bin';module.FS.writeFile(path,image.data);manifest+='0x'+image.addr.toString(16)+' '+path+'\n';
  }
  module.FS.writeFile('/config.txt',manifest);
  const rc=module.callMain(['/trace.bin','/config.txt']);
  if(rc)throw Error('OpenCSD 解码失败：'+errors.join('\n'));
  if(recordLimit)throw Error('解码记录超过当前内存限制，请缩短采集或提高限制');
  const status=records.find(r=>r.kind==='status');
  if(!status||status.lastErrorCode)throw Error('OpenCSD: '+(status?.lastError||errors.join('\n')||'缺少结束状态'));
  const ranges=records.filter(r=>r.kind==='element'&&r.type===5);
  if(!ranges.length)throw Error('没有恢复到指令范围，请核对 ETM 配置、同步和 ELF');
  return {records,ranges,status,errors};
}
// Instruction image addresses are VMA: trace PCs refer to execution addresses,
// not the LMA used by a flash programmer for copied RAM functions.
export function elfImages(bytes,{physical=false}={}){
  if(bytes.length<52||bytes[0]!==0x7f||bytes[1]!==69||bytes[2]!==76||bytes[3]!==70||bytes[4]!==1||bytes[5]!==1)throw Error('需要 ELF32 小端 ARM 镜像');
  const v=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  if(v.getUint16(18,true)!==40)throw Error('ETM 指令解码需要 ARM ELF');
  const offset=v.getUint32(28,true),size=v.getUint16(42,true),count=v.getUint16(44,true),images=[];
  if(size<32||offset+size*count>bytes.length)throw Error('ELF 程序头表越界');
  for(let i=0;i<count;i++){
    const p=offset+i*size;if(v.getUint32(p,true)!==1)continue;
    const start=v.getUint32(p+4,true),length=v.getUint32(p+16,true),addr=v.getUint32(p+(physical?12:8),true);
    if(start+length>bytes.length||addr+length>0x100000000)throw Error('ELF 镜像段越界');
    if(length)images.push({addr,data:bytes.slice(start,start+length)});
  }
  if(!images.length)throw Error('ELF 没有可解码的加载段');
  return images;
}
