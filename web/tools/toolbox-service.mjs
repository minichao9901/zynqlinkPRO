// toolbox 本机服务：静态托管工作台 + 给 CLI 和页面之间递条子的队列。
//
//   CLI ──POST /toolbox/request──▶ 队列 ──GET /toolbox/next（长轮询）──▶ 页面
//   CLI ◀─GET /toolbox/job/<id>── 结果 ◀─POST /toolbox/result────────── 页面
//
// 页面必须由这个服务托管（它会注入 toolbox-bridge.js 和令牌），这样 WebUSB / 串口 / HID
// 这些只有真浏览器能给的能力仍然留在页面上，CLI 只是借用，不去碰设备。
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';

const WEB_ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const TYPES={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8',
  '.mjs':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json',
  '.wasm':'application/wasm','.svg':'image/svg+xml','.png':'image/png','.ico':'image/x-icon'};
const JOB_TTL_MS=60*60*1000;
const PAGE_GRACE_MS=15000;

const json=(res,status,body)=>{
  const text=JSON.stringify(body);
  res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});
  res.end(text);
};
const readBody=req=>new Promise((resolve,reject)=>{
  const chunks=[];let size=0;
  req.on('data',chunk=>{size+=chunk.length;if(size>48*1024*1024)req.destroy();chunks.push(chunk);});
  req.on('end',()=>{try{resolve(chunks.length?JSON.parse(Buffer.concat(chunks).toString('utf8')):{});}catch(error){reject(error);}});
  req.on('error',reject);
});

/**
 * @param {{port?:number, token:string, host?:string, root?:string}} options
 */
export function startService({port=8896,token,host='127.0.0.1',root=WEB_ROOT}={}){
  if(!token||typeof token!=='string')throw Error('缺少服务令牌');
  const jobs=new Map();
  const queue=[];
  let inFlight=null;
  let lastPoll=0;
  let activePolls=0;      // 页面保持一条长轮询；只要还有挂着的轮询就算在线，别被 25 s 的挂起饿死
  let waiter=null;

  const authorised=req=>{
    const header=req.headers['x-toolbox-token'];
    if(typeof header!=='string'||header.length!==token.length)return false;
    return crypto.timingSafeEqual(Buffer.from(header),Buffer.from(token));
  };
  const connected=()=>activePolls>0||Date.now()-lastPoll<PAGE_GRACE_MS;
  const prune=()=>{
    const now=Date.now();
    for(const [id,job] of jobs)if(now-job.createdAt>JOB_TTL_MS)jobs.delete(id);
  };
  const wake=()=>{if(waiter){const resolve=waiter;waiter=null;resolve();}};
  const finish=(job,state,payload)=>{
    job.state=state;job.finishedAt=Date.now();
    Object.assign(job,payload);
    if(inFlight===job)inFlight=null;
    wake();
  };
  const takeNext=()=>{
    if(inFlight||!queue.length)return null;
    const job=jobs.get(queue.shift());
    if(!job)return null;
    inFlight=job;job.state='running';job.startedAt=Date.now();
    return job;
  };

  const server=http.createServer(async (req,res)=>{
    let url;
    try{url=new URL(req.url,'http://127.0.0.1');}catch{res.writeHead(400).end();return;}
    const pathname=url.pathname;

    // ---- 页面与 CLI 共用的队列接口 ----
    if(pathname==='/toolbox/ping'){
      if(!authorised(req))return json(res,403,{ok:false,error:'令牌无效'});
      return json(res,200,{ok:true,connected:connected(),
        lastPollAgoMs:lastPoll?Date.now()-lastPoll:null,queued:queue.length,inFlight:!!inFlight,
        jobs:jobs.size,root});
    }
    if(pathname==='/toolbox/next'){
      if(!authorised(req))return json(res,403,{ok:false,error:'令牌无效'});
      lastPoll=Date.now();
      activePolls++;
      res.on('close',()=>{activePolls--;});
      const job=takeNext();
      if(job){
        return json(res,200,{request:{id:job.id,page:job.request.page,op:job.request.op,
          args:job.request.args||{}}});
      }
      const wait=Math.min(Math.max(Number(url.searchParams.get('wait'))||25000,200),60000);
      let settled=false;
      const deliver=()=>{
        if(settled)return;settled=true;
        const next=takeNext();
        json(res,200,{request:next?{id:next.id,page:next.request.page,op:next.request.op,
          args:next.request.args||{}}:null});
      };
      if(waiter){waiter=null;return json(res,200,{request:null,busy:true});}
      waiter=deliver;
      const timer=setTimeout(()=>{if(!settled){waiter=null;deliver();}},wait);
      res.on('close',()=>{clearTimeout(timer);if(!settled){settled=true;if(waiter===deliver)waiter=null;}});
      return;
    }
    if(pathname==='/toolbox/result'&&req.method==='POST'){
      if(!authorised(req))return json(res,403,{ok:false,error:'令牌无效'});
      let body;try{body=await readBody(req);}catch{return json(res,400,{ok:false,error:'请求体不是 JSON'});}
      lastPoll=Date.now();
      const job=jobs.get(body.id);
      if(!job)return json(res,404,{ok:false,error:'没有这个 job：'+body.id});
      if(body.ok)finish(job,'done',{value:body.value});
      else finish(job,'error',{error:String(body.error||'页面执行失败')});
      return json(res,200,{ok:true});
    }
    if(pathname==='/toolbox/request'&&req.method==='POST'){
      if(!authorised(req))return json(res,403,{ok:false,error:'令牌无效'});
      if(!connected())
        return json(res,409,{ok:false,error:'浏览器页面没有连上：先打开 serve 输出的 browserUrl 并保持页面'});
      let body;try{body=await readBody(req);}catch{return json(res,400,{ok:false,error:'请求体不是 JSON'});}
      if(!body.page||!body.op)return json(res,400,{ok:false,error:'请求需要 page 和 op'});
      prune();
      const id=crypto.randomBytes(16).toString('hex');
      const job={id,state:'queued',createdAt:Date.now(),request:body};
      jobs.set(id,job);queue.push(id);wake();
      // 页面没在等的时候（比如刚提交）主动唤醒一次长轮询。
      if(waiter){const resolve=waiter;waiter=null;resolve();}
      return json(res,200,{ok:true,id});
    }
    if(pathname.startsWith('/toolbox/job/')){
      if(!authorised(req))return json(res,403,{ok:false,error:'令牌无效'});
      const job=jobs.get(pathname.slice('/toolbox/job/'.length));
      if(!job)return json(res,404,{ok:false,error:'没有这个 job'});
      return json(res,200,{ok:true,id:job.id,state:job.state,createdAt:job.createdAt,
        finishedAt:job.finishedAt||null,value:job.value??null,error:job.error??null});
    }

    // ---- 静态文件（带注入） ----
    if(req.method!=='GET'&&req.method!=='HEAD')return json(res,405,{ok:false,error:'只支持 GET'});
    let decoded;
    try{decoded=decodeURIComponent(pathname);}catch{res.writeHead(400).end();return;}
    const file=path.resolve(root,'.'+(decoded.endsWith('/')?decoded+'index.html':decoded));
    if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
    if(!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404).end('Not found');return;}
    const type=TYPES[path.extname(file)]||'application/octet-stream';
    if(path.extname(file)==='.html'){
      let html=fs.readFileSync(file,'utf8');
      const injection='<script>window.__toolboxToken='+JSON.stringify(token)+';</script>\n'+
        '<script type="module" src="/app/toolbox-bridge.js"></script>\n</body>';
      html=html.includes('</body>')?html.replace('</body>',injection):html+injection;
      res.writeHead(200,{'Content-Type':type,'Cache-Control':'no-store'});
      res.end(html);
      return;
    }
    res.writeHead(200,{'Content-Type':type,'Cache-Control':'no-store'});
    fs.createReadStream(file).pipe(res);
  });

  return new Promise((resolve,reject)=>{
    server.once('error',reject);
    server.listen(port,host,()=>{
      const actual=server.address().port;
      resolve({
        port:actual,
        url:`http://${host}:${actual}/`,
        close:()=>new Promise(done=>server.close(()=>done())),
        stats:()=>({connected:connected(),queued:queue.length,
          inFlight:!!inFlight,jobs:jobs.size}),
      });
    });
  });
}
