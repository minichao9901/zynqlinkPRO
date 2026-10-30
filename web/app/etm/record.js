import {unbase64,sha256} from './protocol.js';
import {elfImages} from './decode.js';
export async function readRecord(record){
  if(record?.format!=='zynqdap-etm-1')throw Error('不是 ZynqDAP ETM 记录');
  const config=record.config;
  if(config?.protocol!=='ETMv3')throw Error('需要 ETMv3 解码配置');
  for(const key of ['idr','ctrl','ccer','traceid'])if(!Number.isInteger(config[key])||config[key]<0||config[key]>0xffffffff)throw Error('无效的 ETM 配置 '+key);
  if(!config.traceid||config.traceid>0x6f||((config.idr>>>8)&15)!==2)throw Error('ETMv3 架构或 source ID 不匹配');
  const etm=unbase64(record.etm);
  if(!etm.length||etm.length>64*1024*1024)throw Error('ETM 记录为空或超过 64 MiB');
  if(record.etmSha&&await sha256(etm)!==record.etmSha)throw Error('记录 ETM SHA-256 不匹配');
  const elf=record.elf?unbase64(record.elf):null;
  if(elf&&record.elfSha&&await sha256(elf)!==record.elfSha)throw Error('记录 ELF SHA-256 不匹配');
  const images=elf?elfImages(elf):(record.images||[]).map(i=>({addr:i.addr,data:unbase64(i.data)}));
  if(!images.length||images.length>128)throw Error('记录缺少可解码的指令镜像');
  let imageBytes=0;
  for(const image of images){
    imageBytes+=image.data.length;
    if(!Number.isInteger(image.addr)||image.addr<0||image.addr+image.data.length>0x100000000||!image.data.length)throw Error('指令镜像地址无效');
  }
  if(imageBytes>64*1024*1024)throw Error('指令镜像超过 64 MiB');
  const symbols=(record.symbols||[]).filter(s=>Number.isInteger(s.addr)&&Number.isInteger(s.size)&&s.addr>=0&&s.size>0&&typeof s.name==='string').sort((a,b)=>a.addr-b.addr);
  return {etm,elf,images,config,symbols,quality:record.quality||{},kind:record.kind==='simulation'?'simulation':'hardware',elfName:record.elfName||'record.elf'};
}
