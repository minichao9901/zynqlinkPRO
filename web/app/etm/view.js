import {WebUsbDapProbe} from '../rtt/dap-webusb.js';
import {runProbeOperation} from '../core/probe-manager.js';
import {Elf} from '../elf/elf.js';
import {LineTable} from '../elf/lines.js';
import {elfImages} from './decode.js';
import {EtmTarget} from './target.js';
import {EtmTransport} from './transport.js';
import {base64,sha256} from './protocol.js';
import {toast} from '../ui/toast.js';
import {readRecord} from './record.js';
const hex=v=>'0x'+v.toString(16).padStart(8,'0');
const save=(bytes,name,type)=>{const url=URL.createObjectURL(new Blob([bytes],{type})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const esc=t=>String(t).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export class EtmView{
  constructor(){this.probe=null;this.busy=false;this.ranges=[];this.sources=new Map();this.symbols=[];this.images=[];}
  init(){
    const panel=document.getElementById('tab-etm');
    panel.innerHTML=`<div class="z-page"><div class="z-heading"><div><h1>ETM 执行轨迹</h1><p>ORBTrace 并行接收 · PS USB bulk-in · OpenCSD 浏览器解码</p></div><div class="z-actions"><button id="ze-full">打开完整 ETM 工作台</button><span class="z-badge">四位 DDR / source ID 2</span></div></div>
    <div class="z-columns"><aside class="z-card"><h2>采集</h2><div class="z-actions"><button id="ze-connect">连接 ZynqDAP</button><button id="ze-disconnect">断开</button></div><p id="ze-device" class="muted">USB 未连接</p>
    <p class="z-pinout">J7.16 TRACECLK<br>J7.15 / 17 / 18 / 19 → D0 / D1 / D2 / D3<br>J7.14 GND · 3.3 V · TRACECLK ≤ 50 MHz</p>
    <label class="btn">载入匹配的 ELF<input id="ze-elf" type="file" accept=".elf,.axf,.out" hidden></label><p id="ze-image" class="muted">尚未载入镜像</p>
    <label><input id="ze-auto" type="checkbox" checked>自动配置并恢复 F103ZE ETM</label><label>采集时长 (ms，0 为手动)<input id="ze-ms" type="number" min="0" max="60000" value="10"></label>
    <label>内存上限 (MiB)<input id="ze-limit" type="number" min="1" max="256" value="16"></label>
    <div class="z-actions"><button id="ze-start">开始采集</button><button id="ze-stop">停止</button></div>
    <details><summary>ETMv3 解码寄存器</summary><textarea id="ze-config" rows="6">{"protocol":"ETMv3","idr":1091891777,"ctrl":2320,"ccer":100352,"traceid":2}</textarea><p>自动配置会替换为目标实际读回值；手工配置时由目标工程启用 ETM。</p></details>
    <h2>本地记录</h2><div class="z-actions"><button id="ze-open">导入记录</button><button id="ze-save">保存记录</button></div><input id="ze-record" type="file" accept=".zetm,.json" hidden>
    <button id="ze-sample">载入真实 CM3 仿真样例</button><button id="ze-decode">解码 / 重新解码</button><button id="ze-export">导出指令范围 CSV</button>
    <label class="btn">载入源码文件<input id="ze-source" type="file" multiple hidden></label>
    <pre id="ze-log" class="z-log" aria-live="polite"></pre></aside>
    <div class="z-card z-trace"><div id="ze-status" class="z-stats">尚无捕获</div><canvas id="ze-timeline" height="110" aria-label="执行地址时间轴"></canvas>
    <div class="z-actions"><label>搜索函数 / 地址<input id="ze-filter" placeholder="函数名或 0x0800…"></label><button id="ze-prev">上一范围</button><button id="ze-next">下一范围</button></div>
    <input id="ze-cursor" type="range" min="0" max="0" value="0" aria-label="执行范围回放"><p id="ze-location"></p>
    <div class="z-trace-columns"><div><h2>函数热点</h2><div id="ze-hotspots"></div><h2>顺序执行范围</h2><div class="z-table-scroll"><table><thead><tr><th>#</th><th>PC</th><th>结束</th><th>执行</th><th>函数</th></tr></thead><tbody id="ze-rows"></tbody></table></div></div>
    <div><h2>源码 / 指令字节</h2><pre id="ze-code" class="z-code">载入记录后解码；可另选源码进行逐范围回放。</pre></div></div></div></div></div>`;
    this.$=id=>document.getElementById('ze-'+id);
    const action=fn=>async()=>{try{await fn();}catch(e){this.log(e.message);toast(e.message,'err');}finally{this.buttons();}};
    this.$('full').onclick=()=>window.open('/etm/index.html','_blank','noopener');
    this.$('connect').onclick=action(()=>this.connect());this.$('disconnect').onclick=action(()=>this.releaseProbe());
    this.$('start').onclick=action(()=>this.start());this.$('stop').onclick=action(()=>this.stop());
    this.$('elf').onchange=action(async()=>{const f=this.$('elf').files[0];if(f)await this.loadElf(new Uint8Array(await f.arrayBuffer()),f.name);});
    this.$('open').onclick=()=>this.$('record').click();this.$('record').onchange=action(async()=>{const f=this.$('record').files[0];if(f)await this.loadRecord(JSON.parse(await f.text()));});
    this.$('save').onclick=action(()=>this.saveRecord());this.$('sample').onclick=action(async()=>this.loadRecord(await(await fetch('samples/cm3-orbtrace.zetm')).json()));
    this.$('decode').onclick=action(()=>this.decode());this.$('export').onclick=()=>this.exportCsv();
    this.$('source').onchange=action(async()=>{for(const f of this.$('source').files)this.sources.set(f.name,await f.text());this.select(Number(this.$('cursor').value));});
    this.$('auto').onchange=()=>this.buttons();
    this.$('cursor').oninput=()=>this.select(Number(this.$('cursor').value));this.$('prev').onclick=()=>this.select(Number(this.$('cursor').value)-1);this.$('next').onclick=()=>this.select(Number(this.$('cursor').value)+1);
    this.$('filter').oninput=()=>this.renderRows();this.$('timeline').onclick=e=>{if(this.ranges.length)this.select(Math.floor((e.offsetX/this.$('timeline').clientWidth)*this.ranges.length));};
    this.buttons();
  }
  buttons(){if(!this.$)return;this.$('start').disabled=!this.probe||this.busy||!this.images.length||(this.$('auto').checked&&!this.elfBytes);this.$('stop').disabled=!this.transport?.running&&!this.worker;this.$('disconnect').disabled=!this.probe||this.busy&&!this.transport?.running;this.$('connect').disabled=!!this.probe||this.busy;this.$('decode').disabled=!this.etm?.length||this.busy;this.$('save').disabled=!this.etm?.length||this.busy;this.$('sample').disabled=this.busy;this.$('open').disabled=this.busy;this.$('elf').disabled=this.busy;}
  log(text){this.$('log').textContent+=(new Date().toLocaleTimeString())+' '+text+'\n';this.$('log').scrollTop=this.$('log').scrollHeight;}
  async connect(){return runProbeOperation(this,'etm',async()=>{
    const device=await navigator.usb.requestDevice({filters:[{vendorId:0x0d28,productId:0x0204}]});
    try{this.probe=await WebUsbDapProbe.open(device,{clockKhz:50000});this.target=new EtmTarget(this.probe);this.transport=new EtmTransport(this.probe.device,(p,e)=>{
      this.quality={...p.quality(),refClockHz:this.transport?.refClockHz};this.status();if(e)this.log(e.message);
      const limit=Number(this.$('limit').value)*1024*1024;if(p.records*2>=limit&&!this.stopping)this.stop().catch(e=>this.log(e.message));
    });await this.transport.open();this.$('device').textContent=this.probe.name;this.log('已连接，端点 0x82');}
    catch(e){if(this.transport)try{await this.transport.close();}catch{}if(this.probe)await this.probe.close();this.transport=null;this.probe=null;throw e;}
  });}
  async releaseProbe(){
    if(this.transport?.running)await this.stop();if(this.target?.saved)await this.target.restore();
    if(this.transport)await this.transport.close();if(this.probe)await this.probe.close();
    this.transport=null;this.probe=null;this.probeManager?.forget('etm');this.$('device').textContent='USB 未连接';this.buttons();
  }
  async loadElf(bytes,name){
    this.images=elfImages(bytes);this.flashImages=elfImages(bytes,{physical:true});this.elfBytes=bytes;this.elfName=name;this.elfSha=await sha256(bytes);
    const elf=new Elf(bytes);this.symbols=elf.symbols().filter(s=>s.isFunc&&s.size).sort((a,b)=>a.addr-b.addr);
    try{this.lines=LineTable.fromElf(elf);}catch{this.lines=null;}
    this.$('image').textContent=`${name} · SHA-256 ${this.elfSha.slice(0,16)}…`;this.log('镜像已载入');this.buttons();
  }
  async verifyFlash(){
    let verified=0;
    for(const image of this.flashImages||[]){
      if(image.addr<0x08000000||image.addr>=0x08080000)continue;
      for(let off=0;off<image.data.length;off+=512){
        const expected=image.data.subarray(off,off+512),actual=await this.probe.readMem(image.addr+off,expected.length);
        if(actual.length!==expected.length||expected.some((v,i)=>v!==actual[i]))throw Error(`目标 Flash 与 ELF 不符：${hex(image.addr+off)}`);verified+=expected.length;
      }
    }
    if(!verified)throw Error('F103ZE 自动采集需要 ELF 的 Flash 加载段');this.log(`已核对目标 Flash ${verified} 字节`);
  }
  async start(){
    if(!this.probe||!this.images.length)throw Error('请连接并载入匹配 ELF');this.busy=true;this.buttons();
    try{
      if(this.$('auto').checked){await this.verifyFlash();this.config=await this.target.prepare();this.$('config').value=JSON.stringify(this.config,null,2);}
      else this.config=JSON.parse(this.$('config').value);
      this.etm=null;this.ranges=[];this.decoded=null;this.recordKind='hardware';this.stopping=null;this.transport.byteLimit=Number(this.$('limit').value)*1024*1024;await this.transport.start();
      if(this.$('auto').checked)await this.target.start();
      this.log('开始采集');this.buttons();const ms=Number(this.$('ms').value);
      if(ms>0)this.timer=setTimeout(()=>this.stop().catch(e=>{this.log(e.message);toast(e.message,'err');}),ms);
    }catch(e){try{await this.transport?.stop();if(this.target?.saved)await this.target.restore();}catch(cleanup){e.message+='；收尾失败：'+cleanup.message;}this.busy=false;throw e;}
  }
  async stop(){
    if(this.worker){this.worker.terminate();this.cancelDecode?.(Error('已取消解码'));return;}
    if(this.stopping)return this.stopping;
    this.stopping=(async()=>{
      clearTimeout(this.timer);
      try{
        if(this.target?.saved){await this.target.stop();await sleep(5);}await this.transport.stop();
        this.etm=this.transport.parser.stream(this.config.traceid);this.quality={...this.transport.parser.quality(),refClockHz:this.transport.refClockHz};
        if(this.target?.saved)await this.target.restore();this.log(`停止：${this.etm.length} ETM 字节`);
        if(this.quality.loss)this.log('检测到 trace 丢失，捕获质量不通过');this.status();
      }finally{this.busy=false;this.buttons();}
    })();return this.stopping;
  }
  async loadRecord(record){
    if(this.busy)throw Error('请先停止采集');const parsed=await readRecord(record);
    if(parsed.elf)await this.loadElf(parsed.elf,parsed.elfName);
    else{this.elfBytes=null;this.elfName=null;this.elfSha=null;this.flashImages=[];this.symbols=parsed.symbols;this.lines=null;this.images=parsed.images;this.$('image').textContent=parsed.kind==='simulation'?'CM3 实际仿真指令镜像':'记录中的指令镜像';}
    this.etm=parsed.etm;this.config=parsed.config;this.quality=parsed.quality;this.recordKind=parsed.kind;this.ranges=[];this.decoded=null;
    this.$('config').value=JSON.stringify(this.config,null,2);this.status();this.log('已导入 '+(record.kind==='simulation'?'CM3 仿真':'设备')+'记录');await this.decode();
  }
  async saveRecord(){
    if(!this.etm?.length)throw Error('尚无捕获');
    const record={format:'zynqdap-etm-1',kind:this.recordKind||'hardware',created:new Date().toISOString(),config:this.config,quality:this.quality,
      etm:base64(this.etm),etmSha:await sha256(this.etm),elfName:this.elfName,elfSha:this.elfSha};
    if(this.elfBytes)record.elf=base64(this.elfBytes);else record.images=this.images.map(i=>({addr:i.addr,data:base64(i.data)}));
    save(JSON.stringify(record),'zynqdap-'+Date.now()+'.zetm','application/json');
  }
  async decode(){
    if(!this.etm?.length||!this.images.length)throw Error('需要捕获数据与匹配镜像');this.config=JSON.parse(this.$('config').value);
    this.busy=true;this.ranges=[];this.decoded=null;this.$('rows').replaceChildren();this.$('hotspots').replaceChildren();this.buttons();this.status();this.log('OpenCSD WASM 解码中…');
    const worker=new Worker(new URL('./worker.js',import.meta.url),{type:'module'});this.worker=worker;this.buttons();
    try{
      const result=await new Promise((resolve,reject)=>{this.cancelDecode=reject;worker.onmessage=e=>e.data.ok?resolve(e.data.value):reject(Error(e.data.error));worker.onerror=e=>reject(Error(e.message));worker.postMessage({etm:this.etm,config:this.config,images:this.images});});
      this.decoded=result;this.ranges=result.ranges;this.$('cursor').max=this.ranges.length-1;
      this.log(`恢复 ${this.ranges.length.toLocaleString()} 个指令范围 · OpenCSD ${result.status.library}`);this.renderRows();this.hotspots();this.timeline();this.select(0);this.status();
    }finally{worker.terminate();this.worker=null;this.cancelDecode=null;this.busy=false;this.buttons();}
  }
  func(addr){let lo=0,hi=this.symbols.length;while(lo<hi){const mid=(lo+hi)>>>1;if((this.symbols[mid].addr>>>1)*2<=addr)lo=mid+1;else hi=mid;}const s=this.symbols[lo-1];return s&&addr<(s.addr>>>1)*2+s.size?s.name:hex(addr);}
  status(){
    const q=this.quality||{};this.$('status').textContent=`${this.recordKind==='simulation'?'CM3 仿真 · ':''}${this.etm?.length||0} ETM 字节 · ${q.records||0} 传输记录 · ${this.ranges.length.toLocaleString()} 指令范围 · ${q.loss?'有丢失':q.ended&&q.synced?'同步 / 完整结束':'采集中或未验收'} · FCLK ${q.fclk?Math.round(q.fclk/1000000)+' MHz':'未知'}`;
    this.$('status').classList.toggle('z-loss',!!q.loss);
  }
  renderRows(){
    const filter=this.$('filter').value.toLowerCase(),start=Math.max(0,Number(this.$('cursor').value)-50);
    const rows=[];for(let i=filter?0:start;i<this.ranges.length&&rows.length<250;i++){const r=this.ranges[i],name=this.func(r.start);if(filter&&!name.toLowerCase().includes(filter)&&!hex(r.start).includes(filter))continue;
      rows.push(`<tr data-index="${i}"><td>${i}</td><td>${hex(r.start)}</td><td>${hex(r.end)}</td><td>${r.lastExecuted?'E':'N'}</td><td>${esc(name)}</td></tr>`);}
    this.$('rows').innerHTML=rows.join('');for(const row of this.$('rows').children)row.onclick=()=>this.select(Number(row.dataset.index));
  }
  select(index){
    if(!this.ranges.length)return;index=Math.max(0,Math.min(this.ranges.length-1,index));this.$('cursor').value=index;
    const r=this.ranges[index],line=this.lines?.at(r.start);this.$('location').textContent=`#${index} ${hex(r.start)} → ${hex(r.end)} · ${this.func(r.start)}${line?' · '+line.file+':'+line.line:''}`;
    const source=line?this.sources.get(line.file.replace(/\\/g,'/').split('/').pop()):null;
    if(source)this.$('code').textContent=source.split(/\r?\n/).slice(Math.max(0,line.line-10),line.line+10).map((s,i)=>`${Math.max(1,line.line-9)+i===line.line?'▶':' '} ${Math.max(1,line.line-9)+i} ${s}`).join('\n');
    else{const image=this.images.find(i=>i.addr<=r.start&&r.start<i.addr+i.data.length),data=image?.data.subarray(r.start-image.addr,Math.min(r.end-image.addr,r.start-image.addr+64));this.$('code').textContent=`${hex(r.start)}  ${data?[...data].map(x=>x.toString(16).padStart(2,'0')).join(' '):'镜像无可用指令字节'}\n${line?'源码：'+line.file+':'+line.line+'，请载入该文件。':'镜像没有可用的源码行信息。'}`;}
    this.renderRows();
  }
  hotspots(){const counts=new Map();for(const r of this.ranges){const n=this.func(r.start);counts.set(n,(counts.get(n)||0)+1);}const top=[...counts].sort((a,b)=>b[1]-a[1]).slice(0,12);this.$('hotspots').innerHTML=top.map(([name,n])=>`<div class="z-hot"><span>${esc(name)}</span><meter min="0" max="${this.ranges.length}" value="${n}"></meter><b>${n.toLocaleString()}</b></div>`).join('');}
  timeline(){const c=this.$('timeline'),ctx=c.getContext('2d');c.width=Math.max(400,c.clientWidth*devicePixelRatio);c.height=110*devicePixelRatio;const min=Math.min(...this.ranges.slice(0,100000).map(r=>r.start)),max=Math.max(...this.ranges.slice(0,100000).map(r=>r.start));ctx.fillStyle='#0d1420';ctx.fillRect(0,0,c.width,c.height);ctx.strokeStyle='#5ca8ff';ctx.beginPath();for(let x=0;x<c.width;x++){const r=this.ranges[Math.min(this.ranges.length-1,Math.floor(x/c.width*this.ranges.length))],y=10+(max-r.start)/(max-min||1)*(c.height-20);if(!x)ctx.moveTo(x,y);else ctx.lineTo(x,y);}ctx.stroke();}
  exportCsv(){if(!this.ranges.length)return;save('index,start,end,executed,function\n'+this.ranges.map((r,i)=>`${i},${hex(r.start)},${hex(r.end)},${r.lastExecuted},"${this.func(r.start).replaceAll('"','""')}"`).join('\n'),'zynqdap-etm.csv','text/csv');}
  onShow(){if(this.ranges.length)this.timeline();}
  summary(){return {connected:!!this.probe,running:!!this.transport?.running,busy:this.busy,bytes:this.etm?.length||0,ranges:this.ranges.length,quality:this.quality||null,fullEtmPath:'/etm/'};}
}
