#!/usr/bin/env node
/**
 * ZynqDAP toolbox CLI —— 让 AI / 脚本驱动正在运行的工作台页面。
 *
 *   node web/tools/toolbox.mjs catalog
 *   node web/tools/toolbox.mjs --runtime <目录> serve --port 8896 --open
 *   node web/tools/toolbox.mjs --runtime <目录> page etm describe
 *   node web/tools/toolbox.mjs --runtime <目录> page scope invoke start
 *
 * CLI 自己不碰设备：它把请求投给本机服务，服务再交给已经打开的页面执行。
 * WebUSB / 串口 / HID 的授权和句柄仍然属于那个浏览器页面。
 *
 * 退出码：0 请求处理成功；1 失败；2 参数错误。
 * ⚠️ `ok:true` 只代表请求被处理，不代表硬件任务成功——要接着读 state / read / 计数。
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawn} from 'node:child_process';
import {startService} from './toolbox-service.mjs';

const CATALOG=[
  {page:'serial',title:'串口助手',range:'端口与参数、ASCII/HEX/ANSI、时间戳、定时/快捷发送、DTR/RTS、接收与记录',
    methods:['sendText','save','clear']},
  {page:'terminal',title:'终端',range:'与串口助手共用一个会话；交互输入、ANSI、回显、粘贴、清屏、保存',
    methods:['clear','save']},
  {page:'rtt',title:'RTT Viewer',range:'探针/本地桥/模拟目标、RTT 控制块扫描、上下行通道、ELF 符号、接收记录',
    methods:['connectProbe','disconnect','save']},
  {page:'rttcdc',title:'RTT 转发',range:'HID 目标与时钟、转发启停与状态、CDC 数据面',
    methods:['connect','disconnect','start','stop']},
  {page:'scope',title:'J-Scope 波形',range:'ELF/DWARF 变量、1–8 通道、速率标定、采样、触发与游标、分道缩放、CSV/原始包/质量',
    methods:['start','stop','exportCsv','saveRaw','openRaw','calibrate']},
  {page:'flash',title:'烧录器',range:'ELF/HEX/BIN、芯片与算法、基地址、擦除/编程/校验、复位、IDCODE',
    methods:['connect','disconnect','program','erase','verify','reset']},
  {page:'dbg',title:'调试器',range:'ARM/RISC-V、断点、暂停/继续/单步、寄存器/内存、调用栈、异常诊断、命令行',
    methods:['connect','disconnect','exec','reset','halt','resume']},
  {page:'etm',title:'ETM 执行轨迹',range:'目标 ELF 与 ETM 配置、FPGA 并行采集、OpenCSD 解码、执行流/调用统计/火焰图/热点/包/可信区段、四类导出',
    methods:['decode','loadRecord','saveRecord','exportCsv','exportSvg','exportJson','exportSourceFlow','connect','connectNew','reconnect','start','stop']},
  {page:'gen',title:'工程生成',range:'解析 Keil .uvprojx、参数、生成 Makefile/脚本、预览、单文件/ZIP',
    methods:['loadUvprojx','build','save']},
];

const USAGE=`用法：node web/tools/toolbox.mjs [--runtime <目录>] [--timeout 秒] [--out 文件] <命令>

命令：
  catalog                                列出页面与功能范围（不需要服务）
  serve --port 8896 [--open] [--headless] 创建运行时并前台运行本机服务
  ping | status                          页面是否就绪 / 工作台摘要
  page <页面> describe                   当前控件、可选值、公开方法
  page <页面> state                      页面文字、最近异常、摘要
  page <页面> show                       切到该页面
  page <页面> reload                     让页面重新加载（改完前端代码后用）
  page <页面> read <选择器>              读一个控件/结果区域
  page <页面> set <选择器> <JSON值>      写参数并触发 input/change
  page <页面> click <选择器>             点一个未禁用的控件（只投递，不等异步完成）
  page <页面> invoke <方法> [--args JSON] 调用页面公开方法并等它返回
  page <页面> event <选择器> <类型> [--data JSON]  键盘/鼠标/pointer/wheel/input/change
  page <页面> upload <选择器> <文件...>  放进真实 file input 并触发 change
  page <页面> wait <选择器> --contains 文字    轮询直到匹配或超时
  page <页面> downloads                  列出这次会话里被页面导出的文件（Blob）
  page <页面> download <ID> <目标文件>   取回导出文件并校验 SHA-256（16 MiB 上限）
  request <文件.json>                    提交一条完整请求
  batch <文件.json>                      顺序执行 [{page,op,args},…]
  job <ID>                               查询任务状态，不重做操作`;

function fail(message,code=1){const error=Error(message);error.exitCode=code;throw error;}

function parseArgs(argv){
  const flags={};const positional=[];
  for(let i=0;i<argv.length;i++){
    const arg=argv[i];
    if(arg.startsWith('--')){
      const name=arg.slice(2);const next=argv[i+1];
      if(next===undefined||next.startsWith('--'))flags[name]=true;
      else{flags[name]=next;i++;}
    }else positional.push(arg);
  }
  return {flags,positional};
}

const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));

function runtimeDir(flags){
  if(!flags.runtime)fail('需要 --runtime <目录>（serve 创建的运行时目录）',2);
  const dir=path.resolve(String(flags.runtime));
  if(!fs.existsSync(dir))fail('运行时目录不存在：'+dir+'（先跑 serve）',2);
  return dir;
}
function readToken(flags){
  const file=path.join(runtimeDir(flags),'cli-token');
  if(!fs.existsSync(file))fail('运行时目录里没有 cli-token：'+file,2);
  return fs.readFileSync(file,'utf8').trim();
}
function baseUrl(flags){
  const file=path.join(runtimeDir(flags),'port');
  if(!fs.existsSync(file))fail('运行时目录里没有 port：'+file,2);
  return 'http://127.0.0.1:'+fs.readFileSync(file,'utf8').trim()+'/';
}

async function call(flags,route,init={}){
  const response=await fetch(baseUrl(flags)+route,{
    ...init,
    headers:{'x-toolbox-token':readToken(flags),'content-type':'application/json',...(init.headers||{})},
  });
  let body=null;
  try{body=await response.json();}catch{}
  if(!response.ok)throw Error((body&&body.error)||('HTTP '+response.status));
  return body;
}

async function request(flags,page,op,args={}){
  const body=await call(flags,'toolbox/request',{method:'POST',body:JSON.stringify({page,op,args})});
  return body.id;
}

async function waitJob(flags,id,timeoutSeconds){
  const deadline=Date.now()+timeoutSeconds*1000;
  for(;;){
    const body=await call(flags,'toolbox/job/'+id);
    if(body.state==='done')return {job:id,ok:true,value:body.value};
    if(body.state==='error')return {job:id,ok:false,error:body.error};
    if(Date.now()>deadline)return {job:id,ok:false,timeout:true,
      error:`超时（${timeoutSeconds}s）：任务可能仍在执行，用 job ${id} 查询，不要重试硬件写入`};
    await sleep(120);
  }
}

async function runOp(flags,page,op,args){
  const id=await request(flags,page,op,args);
  return waitJob(flags,id,Number(flags.timeout||60));
}

function findBrowser(){
  const candidates=[process.env.ZYNQDAP_BROWSER,
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'].filter(Boolean);
  return candidates.find(candidate=>fs.existsSync(candidate))||null;
}

async function commandServe(flags){
  if(!flags.runtime)fail('serve 需要 --runtime <目录>',2);
  const runtime=path.resolve(String(flags.runtime));
  // 目录里已经有 cli-token 时复用（服务崩溃/机器重启后，仍然开着的页面不必重新授权就能接回来）。
  const tokenFile=path.join(runtime,'cli-token');
  let token=null,reused=false;
  if(fs.existsSync(runtime)&&fs.readdirSync(runtime).length){
    if(!fs.existsSync(tokenFile))fail('运行时目录不是空的，也没有 cli-token：'+runtime,2);
    token=fs.readFileSync(tokenFile,'utf8').trim();
    if(!/^[0-9a-f]{64}$/.test(token))fail('cli-token 内容无效：'+tokenFile,2);
    reused=true;
  }else{
    fs.mkdirSync(runtime,{recursive:true});
    token=crypto.randomBytes(32).toString('hex');
    fs.writeFileSync(tokenFile,token,{encoding:'utf8',mode:0o600});
  }
  const service=await startService({port:Number(flags.port||8896),token});
  fs.writeFileSync(path.join(runtime,'port'),String(service.port),'utf8');
  const browserUrl=service.url;
  const payload={ok:true,browserUrl,port:service.port,runtime,reusedToken:reused};
  console.log(JSON.stringify(payload,null,2));
  if(flags.open){
    const browser=findBrowser();
    if(!browser)console.error('[warn] 找不到 Edge/Chrome，请手动打开 '+browserUrl);
    else{
      const args=flags.headless
        ?['--headless=new','--disable-gpu','--no-first-run','--remote-debugging-port=0',
          '--user-data-dir='+path.join(runtime,'browser'),browserUrl]
        :[browserUrl];
      spawn(browser,args,{detached:true,stdio:'ignore',windowsHide:false}).unref();
    }
  }
  const stop=async()=>{await service.close();process.exit(0);};
  process.on('SIGINT',stop);process.on('SIGTERM',stop);
  await new Promise(()=>{});
}

async function commandPage(flags,positional){
  const [,page,op,...rest]=positional;
  if(!page||!op)fail('用法：page <页面> <操作> …\n\n'+USAGE,2);
  const timeout=Number(flags.timeout||60);
  if(op==='wait'){
    const selector=rest[0];const contains=flags.contains;
    if(!selector||contains===undefined)fail('wait 需要 <选择器> 和 --contains 文字',2);
    const result=await runOp(flags,page,'wait',{selector,contains,timeoutMs:timeout*1000});
    if(result.ok&&result.value?.matched===false)
      return {ok:false,timeout:true,error:`${timeout}s 内没有等到「${contains}」`,last:result.value.last};
    return result;
  }
  let args={};
  if(op==='read'){args={selector:rest[0]};}
  else if(op==='click'){args={selector:rest[0]};}
  else if(op==='set'){
    const selector=rest[0];
    let value;
    if(flags['value-file'])value=JSON.parse(fs.readFileSync(String(flags['value-file']),'utf8'));
    else{
      const raw=rest[1];
      try{value=raw===undefined?null:JSON.parse(raw);}catch{value=raw;}
    }
    args={selector,value};
  }
  else if(op==='event'){
    const [selector,type]=rest;
    args={selector,type,data:flags.data?JSON.parse(String(flags.data)):{}};
  }
  else if(op==='upload'){
    const selector=rest[0];
    const files=rest.slice(1).map(file=>{
      const bytes=fs.readFileSync(file);
      return {name:path.basename(file),base64:bytes.toString('base64')};
    });
    if(!files.length)fail('upload 需要至少一个文件',2);
    args={selector,files};
  }
  else if(op==='invoke'){
    const method=rest[0];
    let list=[];
    if(flags['args-file'])list=JSON.parse(fs.readFileSync(String(flags['args-file']),'utf8'));
    else if(flags.args!==undefined)list=JSON.parse(String(flags.args));
    args={method,args:Array.isArray(list)?list:[list]};
  }
  else if(op==='downloads'){args={};}
  else if(op==='download'){
    const id=rest[0];const destination=rest[1];
    if(!id||!destination)fail('download 需要 <导出ID> <目标文件>',2);
    const result=await runOp(flags,page,'download',{id:Number(id)});
    if(!result.ok)return result;
    const value=result.value;
    const target=path.resolve(destination);
    if(fs.existsSync(target))fail('目标文件已存在，拒绝覆盖：'+target);
    const bytes=Buffer.from(value.base64,'base64');
    fs.writeFileSync(target,bytes);
    return {ok:true,file:target,size:bytes.length,sha256:value.sha256,picked:value.sha256===
      crypto.createHash('sha256').update(bytes).digest('hex')};
  }
  else if(op==='describe'||op==='state'||op==='show'||op==='summary'||op==='reload'){args={};}
  else fail('未知操作：'+op+'\n\n'+USAGE,2);
  const result=await runOp(flags,page,op,args);
  return result;
}

async function commandBatch(flags,file){
  const list=JSON.parse(fs.readFileSync(file,'utf8'));
  if(!Array.isArray(list)||!list.length)fail('batch 文件必须是 1～1000 条请求的数组',2);
  const results=[];
  for(const item of list){
    const {page,op,args={}}=item;
    const result=await runOp(flags,page,op,args);
    results.push({page,op,ok:result.ok,...(result.ok?{value:result.value}:{error:result.error})});
    if(!result.ok)return {ok:false,stoppedAt:results.length-1,results};
  }
  return {ok:true,count:results.length,results};
}

async function main(){
  const {flags,positional}=parseArgs(process.argv.slice(2));
  const command=positional[0];
  if(!command||flags.help){console.log(USAGE);return 0;}
  if(command==='catalog')return {pages:CATALOG};
  if(command==='serve'){await commandServe(flags);return null;}
  if(command==='ping')return await call(flags,'toolbox/ping');
  if(command==='status')return await runOp(flags,'serial','summary',{});
  if(command==='job')return await call(flags,'toolbox/job/'+positional[1]);
  if(command==='request'){
    const body=JSON.parse(fs.readFileSync(positional[1],'utf8'));
    return await runOp(flags,body.page,body.op,body.args||{});
  }
  if(command==='batch')return await commandBatch(flags,positional[1]);
  if(command==='page')return await commandPage(flags,positional);
  fail('未知命令：'+command+'\n\n'+USAGE,2);
}

try{
  const {flags}=parseArgs(process.argv.slice(2));
  const result=await main();
  if(result!==null){
    const text=JSON.stringify(result,null,2);
    if(flags.out){
      const target=path.resolve(String(flags.out));
      if(fs.existsSync(target))fail('--out 文件已存在，拒绝覆盖：'+target);
      fs.writeFileSync(target,text+'\n','utf8');
      console.log(JSON.stringify({ok:result.ok!==false,out:target}));
    }else console.log(text);
    if(result&&result.ok===false)process.exitCode=1;
  }
}catch(error){
  console.error(JSON.stringify({ok:false,error:String(error.message||error)}));
  process.exitCode=error.exitCode||1;
}
