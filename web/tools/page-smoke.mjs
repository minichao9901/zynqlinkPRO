// 九个页面的浏览器冒烟验收：用本机 Edge 的无头 CDP 打开工作台，逐页点进去，
// 收集控制台错误和每页的渲染结果；ETM 页再走一遍「载入 CM3 仿真样例 → WASM 解码 → 调用树分析」。
//
//   node web/tools/page-smoke.mjs
//   ZYNQDAP_WEB=http://127.0.0.1:8898/ node web/tools/page-smoke.mjs
//
// 需要一个静态服务在跑：node web/tools/serve.mjs
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BASE=process.env.ZYNQDAP_WEB||'http://127.0.0.1:8898/';
const PAGES=[['serial','串口助手'],['terminal','终端'],['rtt','RTT Viewer'],['rttcdc','RTT 转发'],
  ['scope','J-Scope 波形'],['flash','烧录器'],['dbg','调试器'],['etm','ETM 执行轨迹'],['gen','工程生成']];
const PORT=Number(process.env.ZYNQDAP_CDP_PORT||9333);

const CANDIDATES=[process.env.ZYNQDAP_BROWSER,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'].filter(Boolean);
const browser=CANDIDATES.find(candidate=>fs.existsSync(candidate));
if(!browser)throw Error('找不到 Edge/Chrome 可执行文件');

class Client{
  constructor(url){this.url=url;this.id=0;this.pending=new Map();this.events=[];}
  async open(){
    this.ws=new WebSocket(this.url);
    await new Promise((resolve,reject)=>{
      this.ws.addEventListener('open',resolve,{once:true});
      this.ws.addEventListener('error',()=>reject(Error('CDP 连接失败')),{once:true});
    });
    this.ws.addEventListener('message',event=>this.receive(JSON.parse(event.data)));
  }
  receive(message){
    if(message.id!==undefined){
      const pending=this.pending.get(message.id);
      if(!pending)return;
      this.pending.delete(message.id);
      if(message.error)pending.reject(Error(message.error.message));
      else pending.resolve(message.result);
      return;
    }
    this.events.push(message);
  }
  send(method,params={},sessionId){
    const id=++this.id;
    return new Promise((resolve,reject)=>{
      this.pending.set(id,{resolve,reject});
      this.ws.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));
    });
  }
  close(){try{this.ws.close();}catch{}}
}

const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const userDataDir=fs.mkdtempSync(path.join(os.tmpdir(),'zynqdap-smoke-'));
const child=spawn(browser,['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
  '--disable-extensions','--remote-debugging-port='+PORT,'--user-data-dir='+userDataDir,'about:blank'],
{stdio:'ignore',windowsHide:true});

let browserClient;
async function connect(){
  for(let attempt=0;attempt<60;attempt++){
    try{
      const response=await fetch('http://127.0.0.1:'+PORT+'/json/version');
      if(response.ok){
        const version=await response.json();
        browserClient=new Client(version.webSocketDebuggerUrl);
        await browserClient.open();
        return;
      }
    }catch{}
    await sleep(250);
  }
  throw Error('无头浏览器没有起来（端口 '+PORT+'）');
}

const failures=[];
function fail(page,message){failures.push(page+'：'+message);}

try{
  await connect();
  const {targetId}=await browserClient.send('Target.createTarget',{url:'about:blank'});
  const {sessionId}=await browserClient.send('Target.attachToTarget',{targetId,flatten:true});
  const call=(method,params)=>browserClient.send(method,params,sessionId);
  const evaluate=async expression=>{
    const result=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true,timeout:60000});
    if(result.exceptionDetails)throw Error(result.exceptionDetails.text+' '+(result.exceptionDetails.exception?.description||''));
    return result.result.value;
  };
  await call('Runtime.enable');
  await call('Log.enable');
  await call('Page.enable');
  browserClient.events.length=0;
  await call('Page.navigate',{url:BASE});
  for(let attempt=0;attempt<80;attempt++){
    await sleep(250);
    try{if(await evaluate('!!document.getElementById("boot-mask")===false&&!!document.getElementById("tabs")'))break;}catch{}
  }
  const errorText=()=>browserClient.events.filter(event=>event.sessionId===sessionId&&
    (event.method==='Runtime.exceptionThrown'||((event.method==='Log.entryAdded')&&event.params.entry.level==='error')))
    .map(event=>event.method==='Runtime.exceptionThrown'
      ?(event.params.exceptionDetails.exception?.description||event.params.exceptionDetails.text)
      :event.params.entry.text);

  console.log('页面：'+BASE);
  for(const [id,label] of PAGES){
    await evaluate('document.querySelector(\'[data-tab="'+id+'"]\').click()');
    await sleep(350);
    const state=await evaluate('(()=>{const panel=document.getElementById("tab-'+id+'");if(!panel)return {missing:true};'+
      'const text=(panel.innerText||"").trim();return {missing:false,length:text.length,head:text.slice(0,80),hidden:panel.hidden};})()');
    if(state.missing){fail(label,'页面容器不存在');continue;}
    if(state.hidden)fail(label,'切换后仍然隐藏');
    if(state.length<20)fail(label,'渲染内容过少：'+JSON.stringify(state.head));
    console.log('  '+(failures.some(f=>f.startsWith(label))?'✖':'✔')+' '+label+' · '+state.length+' 字符 · '+state.head.replace(/\s+/g,' '));
  }

  // ETM 端到端：CM3 仿真样例 → OpenCSD WASM 解码 → 前端调用树/火焰图/包视图。
  await evaluate('document.querySelector(\'[data-tab="etm"]\').click()');
  await sleep(200);
  await evaluate('document.getElementById("ze-sample").click()');
  let status='';
  for(let attempt=0;attempt<160;attempt++){
    await sleep(250);
    const progress=await evaluate('({max:Number(document.getElementById("ze-cursor").max)||0,'+
      'status:document.getElementById("ze-status").innerText,'+
      'log:document.getElementById("ze-log").innerText.slice(-200)})');
    status=progress.status;
    // 解码结束的标志：滑杆上限被写成指令范围数，并且日志里出现了调用树统计。
    if(progress.max>0&&/调用树/.test(progress.log))break;
    if(/解码失败|OpenCSD/.test(progress.log)&&/Error|失败/.test(progress.log)&&attempt>8)break;
  }
  const etm=await evaluate(`(()=>{
    const rows=document.querySelectorAll('#ze-rows tr').length;
    const stats=document.querySelectorAll('#ze-statrows tr').length;
    const sections=document.querySelectorAll('#ze-sections tr').length;
    const packets=document.querySelectorAll('#ze-packetgroups tr').length;
    const stack=document.querySelectorAll('#ze-stack li').length;
    document.querySelector('[data-view="flame"]').click();
    const svg=document.querySelector('#ze-flame svg');
    return {rows,stats,sections,packets,stack,flameNodes:svg?svg.querySelectorAll('rect').length:0,
      status:document.getElementById('ze-status').innerText,
      log:document.getElementById('ze-log').innerText.slice(-500)};
  })()`);
  console.log('  ETM 样例：'+etm.status.replace(/\s+/g,' '));
  if(!etm.rows)fail('ETM 执行流','样例解码后没有执行流行；日志：'+etm.log.replace(/\s+/g,' '));
  if(!etm.stats)fail('ETM 调用统计','调用统计为空');
  if(!etm.sections)fail('ETM 可信区段','可信区段为空');
  if(!etm.packets)fail('ETM 包视图','包类型统计为空');
  if(!etm.stack)fail('ETM 调用栈','历史调用栈为空');
  if(etm.flameNodes<2)fail('ETM 火焰图','SVG 没有生成节点');
  console.log('  ETM 视图：执行流 '+etm.rows+' 行 · 调用统计 '+etm.stats+' 行 · 区段 '+etm.sections+
    ' · 包类型 '+etm.packets+' · 栈深 '+etm.stack+' · 火焰节点 '+etm.flameNodes);

  // RTT Viewer 的模拟目标端到端：页面用 ?backend=mock&auto=1 自动连上内置模拟探针，
  // 走完「连接 → 扫描控制块 → 上行缓冲」这条真实路径，不需要接板子。
  const mockUrl=BASE+(BASE.includes('?')?'&':'?')+'backend=mock&auto=1';
  await call('Page.navigate',{url:mockUrl});
  let rtt='';
  for(let attempt=0;attempt<60;attempt++){
    await sleep(250);
    try{rtt=await evaluate('(document.getElementById("r-err")||{}).innerText||""');}catch{}
    if(/控制块/.test(rtt)||/失败|错误|不支持/.test(rtt))break;
  }
  const rttState=await evaluate('({backend:(document.getElementById("r-backend")||{}).value||null})');
  if(rttState.backend!=='mock')fail('RTT Viewer','模拟后端没有被选中');
  if(/控制块/.test(rtt)){
    console.log('  RTT 模拟目标：已连接 · '+rtt.replace(/\s+/g,' '));
  }else fail('RTT Viewer','模拟目标没有连上：'+(rtt||'(无状态文本)'));

  const consoleErrors=errorText();
  if(consoleErrors.length){for(const text of consoleErrors.slice(0,10))fail('控制台',text.split('\n')[0]);}
  else console.log('  控制台：无错误');
}finally{
  try{await browserClient?.send('Browser.close');}catch{}
  browserClient?.close();
  await sleep(300);
  try{child.kill();}catch{}
  try{fs.rmSync(userDataDir,{recursive:true,force:true});}catch{}
}

if(failures.length){
  console.error('\n失败 '+failures.length+' 项：');
  for(const failure of failures)console.error('  - '+failure);
  process.exit(1);
}
console.log('\nPASS 九个页面渲染正常，ETM 样例解码与分析视图可用');
