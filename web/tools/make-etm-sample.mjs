// 用一次真实采集（原始 ETM 字节 + 目标 ELF + 验收 JSON）生成可提交的 .zetm 样例记录。
//
//   node web/tools/make-etm-sample.mjs \
//     --record docs/validation/orbtrace-oversample-parser-20261030/acceptance.json \
//     --etm    docs/validation/orbtrace-oversample-parser-20261030/etm.bin \
//     --elf    E:/superlinkPRO/etm/firmware/stm32f103_cdc_trace/fw-ze.elf \
//     --out    web/samples/f103ze-oversample.zetm
//
// 样例只带 ELF 的加载段（VMA）和函数符号，不带 DWARF，所以体积小但函数名完整。
// ELF 与 ETM 的 SHA-256 都按验收 JSON 核对，核不过直接失败。
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {elfImages} from '../app/etm/decode.js';
import {Elf} from '../app/elf/elf.js';

const args={};
for(let i=2;i<process.argv.length;i+=2)args[process.argv[i].replace(/^--/,'')]=process.argv[i+1];
for(const required of ['record','etm','elf','out'])if(!args[required])throw Error('缺少参数 --'+required);

const acceptance=JSON.parse(fs.readFileSync(args.record,'utf8'));
const etm=fs.readFileSync(args.etm);
const elfBytes=fs.readFileSync(args.elf);
const digest=buffer=>createHash('sha256').update(buffer).digest('hex');

const etmSha=digest(etm), elfSha=digest(elfBytes);
if(acceptance.etm_sha256&&acceptance.etm_sha256!==etmSha)throw Error('ETM SHA-256 与验收记录不一致');
if(acceptance.target_elf_sha256&&acceptance.target_elf_sha256!==elfSha)throw Error('目标 ELF SHA-256 与验收记录不一致');

const elf=new Uint8Array(elfBytes.buffer,elfBytes.byteOffset,elfBytes.byteLength);
const images=elfImages(elf);
const symbols=new Elf(elf).symbols().filter(symbol=>symbol.isFunc&&symbol.size>0)
  .map(symbol=>({name:symbol.name,addr:symbol.addr,size:symbol.size}));

const record={format:'zynqdap-etm-1',kind:'hardware',created:new Date().toISOString(),
  config:acceptance.config,quality:acceptance.quality,
  etm:etm.toString('base64'),etmSha,
  images:images.map(image=>({addr:image.addr,data:Buffer.from(image.data).toString('base64')})),
  symbols,
  provenance:{acceptance:args.record.replace(/\\/g,'/'),targetElf:args.elf.replace(/\\/g,'/'),
    targetElfSha256:elfSha,bitSha256:acceptance.artifacts?.bit?.sha256??null,
    sourceCommit:acceptance.artifacts?.git_head??null,
    traceclkHz:24000,fclkHz:acceptance.quality?.fclk??null}};

fs.mkdirSync(path.dirname(args.out),{recursive:true});
fs.writeFileSync(args.out,JSON.stringify(record));
console.log(args.out+' · '+etm.length+' ETM 字节 · '+images.length+' 个镜像段 · '+symbols.length+' 个函数符号 · '+
  (fs.statSync(args.out).size/1024).toFixed(1)+' KiB');
