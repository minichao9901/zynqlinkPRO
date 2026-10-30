// toolbox CLI 的端到端自检：真起服务、真开无头浏览器、真跑 CLI 子进程。
//
//   node web/tools/toolbox-selftest.mjs
//
// 覆盖：catalog / ping / describe / click / wait / invoke / set / read / upload / batch。
// 不连接任何真实设备：用的是 ETM 记录样例、J-Scope 假探针、调试器模拟目标。
import {spawn, spawnSync} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const cli=path.join(here,'toolbox.mjs');
const runtime=fs.mkdtempSync(path.join(os.tmpdir(),'zynqdap-toolbox-'));
const port=8896+Math.floor(Math.random()*80);
const failures=[];
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));

function findBrowser(){
  return [process.env.ZYNQDAP_BROWSER,
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\chrome.exe',
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'].filter(Boolean)
    .find(candidate=>fs.existsSync(candidate));
}

function runCli(args,{expectOk=true}={}){
  const result=spawnSync(process.execPath,[cli,'--runtime',runtime,...args],{encoding:'utf8',timeout:180000});
  let json=null;
  try{json=JSON.parse(result.stdout.trim());}catch{}
  const line={args:args.join(' '),code:result.status,json,stderr:result.stderr.trim()};
  if(expectOk&&(result.status!==0||json?.ok===false)){
    failures.push(`${line.args} → 退出码 ${result.status}：${line.json?.error||line.stderr||'无输出'}`);
  }
  return line;
}
const check=(name,condition,detail='')=>{if(!condition)failures.push(`${name}${detail?'：'+detail:''}`);};

let browser=null,service=null;
try{
  service=spawn(process.execPath,[cli,'--runtime',runtime,'serve','--port',String(port)],{stdio:'ignore',windowsHide:true});
  let url=null;
  for(let attempt=0;attempt<80;attempt++){
    await sleep(250);
    const file=path.join(runtime,'port');
    if(fs.existsSync(file)){url='http://127.0.0.1:'+fs.readFileSync(file,'utf8').trim()+'/';break;}
  }
  if(!url)throw Error('服务没有起来');

  const executable=findBrowser();
  if(!executable)throw Error('找不到 Edge/Chrome');
  const profile=path.join(runtime,'browser');
  browser=spawn(executable,['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
    '--user-data-dir='+profile,url],{stdio:'ignore',windowsHide:true});

  let connected=false;
  for(let attempt=0;attempt<80;attempt++){
    await sleep(250);
    const ping=runCli(['ping'],{expectOk:false});
    if(ping.json?.connected){connected=true;break;}
  }
  if(!connected)throw Error('页面没有连上本机服务');
  console.log('  页面已连上 '+url);

  const catalog=runCli(['catalog'],{expectOk:false});
  check('catalog 列出九页',Array.isArray(catalog.json?.pages)&&catalog.json.pages.length===9,
    '实际 '+(catalog.json?.pages?.length??'?'));

  const describe=runCli(['page','etm','describe']);
  const controls=describe.json?.value?.controls||[];
  check('describe 枚举控件',controls.length>20,'只有 '+controls.length+' 个');
  check('describe 列出方法',(describe.json?.value?.methods||[]).includes('decode'));

  runCli(['page','etm','click','#ze-sample-f103']);
  const waited=runCli(['--timeout','90','page','etm','wait','#ze-log','--contains','调用树']);
  check('wait 等到解码完成',waited.json?.value?.matched===true,waited.json?.error||'');

  const summary=runCli(['page','etm','invoke','summary']);
  const functions=summary.json?.value?.value?.functions??0;
  check('invoke 拿到真实分析结果',functions>=8,'functions='+functions);

  const sample=path.join(here,'..','samples','cm3-orbtrace.zetm');
  runCli(['page','etm','upload','#ze-record',sample]);
  const uploaded=runCli(['--timeout','90','page','etm','wait','#ze-log','--contains','22,036']);
  check('upload 把文件放进真实 file input',uploaded.json?.value?.matched===true,uploaded.json?.error||'');

  runCli(['page','etm','invoke','exportCsv']);
  const listed=runCli(['page','etm','downloads']);
  const exports_=listed.json?.value||[];
  check('downloads 列出导出文件',exports_.some(item=>/\.csv$/.test(item.name||'')),'拿到 '+(exports_.length));
  if(exports_.length){
    const csvPath=path.join(runtime,'flow.csv');
    const saved=runCli(['page','etm','download',String(exports_[0].id),csvPath]);
    check('download 落盘并校验 SHA-256',saved.json?.ok===true&&saved.json.picked===true,saved.json?.error||'');
    check('下载的 CSV 内容正确',fs.existsSync(csvPath)&&
      fs.readFileSync(csvPath,'utf8').split('\n')[0]==='index,offset,start,end,weight,branch,executed,depth,function');
  }

  const setMock=runCli(['page','scope','set','#sc-mock','true']);
  check('set 勾选复选框',setMock.json?.value?.checked===true);
  const readBack=runCli(['page','scope','read','#sc-mock']);
  check('read 读回控件状态',readBack.json?.value?.checked===true);

  runCli(['page','dbg','set','#d-backend','"mock"'],{expectOk:false});
  runCli(['page','dbg','click','#d-connect']);
  const debugged=runCli(['--timeout','60','page','dbg','wait','#d-out','--contains','已连接：模拟目标']);
  check('模拟调试目标连上',debugged.json?.value?.matched===true,debugged.json?.error||'');

  const batchFile=path.join(runtime,'batch.json');
  fs.writeFileSync(batchFile,JSON.stringify([
    {page:'etm',op:'read',args:{selector:'#ze-status'}},
    {page:'etm',op:'invoke',args:{method:'summary'}},
  ]));
  const batch=runCli(['batch',batchFile]);
  check('batch 顺序执行',batch.json?.ok===true&&batch.json.count===2,'count='+batch.json?.count);

  const missing=runCli(['page','etm','read','#no-such-control'],{expectOk:false});
  check('缺失控件给出失败退出码',missing.code===1&&/找不到控件/.test(missing.json?.error||''));
}finally{
  if(browser){
    try{spawnSync('taskkill',['/PID',String(browser.pid),'/T','/F'],{stdio:'ignore'});}catch{}
  }
  if(service){
    try{service.kill();}catch{}
    try{spawnSync('taskkill',['/PID',String(service.pid),'/T','/F'],{stdio:'ignore'});}catch{}
  }
  await sleep(400);
  try{fs.rmSync(runtime,{recursive:true,force:true});}catch{}
}

if(failures.length){
  console.error('\n失败 '+failures.length+' 项：');
  for(const failure of failures)console.error('  - '+failure);
  process.exit(1);
}
console.log('\nPASS toolbox CLI 自检：目录/describe/click/wait/invoke/set/read/upload/batch/download 全部可用');
