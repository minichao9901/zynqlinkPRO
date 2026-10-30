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
import {analyze,callStats,executionCsv,flameSvg,packetSummary,sourceFlow,
  summaryJson,BRANCH_LABEL} from './analysis.js';const hex=v=>'0x'+(v>>>0).toString(16).padStart(8,'0');
const save=(bytes,name,type)=>{const url=URL.createObjectURL(new Blob([bytes],{type})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const esc=t=>String(t).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct=v=>(v*100).toFixed(1)+'%';
// 历史导航的过滤条件；和 superlink 的「指令 / 调用 / 返回 / 异常 / 未知」一一对应。
const NAV_KINDS={all:()=>true,call:r=>r.kind==='call',return:r=>r.kind==='return',cond:r=>r.kind==='cond',
  exception:(r,model)=>model.frames[model.order[r.index]]?.kind==='exception',
  nonexec:r=>!r.executed,indirect:r=>r.kind==='indirect'||r.kind==='unknown'};

export class EtmView{
  constructor(){this.probe=null;this.busy=false;this.ranges=[];this.sources=new Map();this.symbols=[];this.images=[];this.model=null;this.view='flow';}
  init(){
    const panel=document.getElementById('tab-etm');
    panel.innerHTML=`<div class="z-page"><div class="z-heading"><div><h1>ETM 执行轨迹</h1><p>FPGA 并行接收 · PS USB bulk-in · OpenCSD 浏览器解码 · 前端调用树分析</p></div><div class="z-actions"><span class="z-badge">四位 DDR / source ID 2</span></div></div>
    <div class="z-columns"><aside class="z-card"><h2>采集</h2><div class="z-actions"><button id="ze-connect">连接 ZynqDAP</button><button id="ze-pick">换设备…</button><button id="ze-disconnect">断开</button></div><p id="ze-device" class="muted">USB 未连接</p>
    <p class="z-pinout">J7.16 TRACECLK<br>J7.15 / 17 / 18 / 19 → D0 / D1 / D2 / D3<br>J7.14 GND · 3.3 V · TRACECLK ≤ 50 MHz</p>
    <label class="btn">载入匹配的 ELF<input id="ze-elf" type="file" accept=".elf,.axf,.out" hidden></label><p id="ze-image" class="muted">尚未载入镜像</p>
    <label><input id="ze-auto" type="checkbox" checked>自动配置并恢复 F103ZE ETM</label><label>TRACECLK 分频 (HCLK / N)<select id="ze-div"><option>1</option><option>2</option><option selected>3</option><option>4</option></select></label><label>采集时长 (ms，0 为手动)<input id="ze-ms" type="number" min="0" max="60000" value="10"></label>
    <label>内存上限 (MiB)<input id="ze-limit" type="number" min="1" max="256" value="16"></label>
    <div class="z-actions"><button id="ze-start">开始采集</button><button id="ze-stop">停止</button></div>
    <details><summary>ETMv3 解码寄存器</summary><textarea id="ze-config" rows="6">{"protocol":"ETMv3","idr":1091891777,"ctrl":2320,"ccer":100352,"traceid":2}</textarea><p>自动配置会替换为目标实际读回值；手工配置时由目标工程启用 ETM。</p></details>
    <h2>本地记录</h2><div class="z-actions"><button id="ze-open">导入记录</button><button id="ze-save">保存记录</button></div><input id="ze-record" type="file" accept=".zetm,.json" hidden>
    <button id="ze-sample">载入真实 CM3 仿真样例</button><button id="ze-sample-f103">载入 F103ZE 实板样例</button><button id="ze-decode">解码 / 重新解码</button>
    <label class="btn">载入源码文件<input id="ze-source" type="file" multiple hidden></label>
    <pre id="ze-log" class="z-log" aria-live="polite"></pre></aside>
    <div class="z-card z-trace"><div id="ze-status" class="z-stats">尚无捕获</div><canvas id="ze-timeline" height="110" aria-label="执行地址时间轴"></canvas>
    <div class="z-actions"><label>搜索函数 / 地址<input id="ze-filter" placeholder="函数名或 0x0800…"></label>
      <label>历史导航<select id="ze-nav"><option value="all">指令</option><option value="call">调用</option><option value="return">返回</option><option value="cond">条件跳转</option><option value="indirect">间接跳转 / 未知</option><option value="exception">异常</option><option value="nonexec">未执行</option></select></label>
      <button id="ze-prev">上一个</button><button id="ze-next">下一个</button></div>
    <input id="ze-cursor" type="range" min="0" max="0" value="0" aria-label="执行范围回放"><p id="ze-location"></p>
    <nav class="z-etm-tabs" id="ze-tabs" aria-label="分析视图"><button data-view="flow" class="active">执行流</button><button data-view="stats">调用统计</button><button data-view="flame">火焰图</button><button data-view="hot">热点</button><button data-view="packet">ETM 包</button><button data-view="section">可信区段</button></nav>
    <div id="ze-view-flow" class="z-etm-view"><div class="z-table-scroll"><table><thead><tr><th>#</th><th>PC</th><th>结束</th><th>分支</th><th>深度</th><th>函数</th></tr></thead><tbody id="ze-rows"></tbody></table></div></div>
    <div id="ze-view-stats" class="z-etm-view" hidden><div class="z-table-scroll"><table><thead><tr><th>函数</th><th>调用</th><th>自身半字</th><th>含子树</th><th>占比</th><th>深度</th></tr></thead><tbody id="ze-statrows"></tbody></table></div></div>
    <div id="ze-view-flame" class="z-etm-view" hidden><div class="z-actions"><span class="z-legend">列宽按执行半字数；颜色按函数名散列。</span></div><div id="ze-flame" class="z-flame"></div></div>
    <div id="ze-view-hot" class="z-etm-view" hidden><div id="ze-hotspots"></div></div>
    <div id="ze-view-packet" class="z-etm-view" hidden><h2>包类型统计</h2><div class="z-table-scroll"><table><thead><tr><th>包</th><th>条数</th><th>字节</th></tr></thead><tbody id="ze-packetgroups"></tbody></table></div><h2>最近的包</h2><div class="z-table-scroll"><table><thead><tr><th>偏移</th><th>长度</th><th>原始字节</th><th>说明</th></tr></thead><tbody id="ze-packets"></tbody></table></div></div>
    <div id="ze-view-section" class="z-etm-view" hidden><div class="z-actions"><span class="z-legend">区段按 TRACE_ON / 未同步事件切分；缺口或地址问题会让区段不可信。</span></div><div class="z-table-scroll"><table><thead><tr><th>#</th><th>起点</th><th>终点</th><th>来源</th><th>范围</th><th>半字</th><th>异常</th><th>问题</th><th>可信</th></tr></thead><tbody id="ze-sections"></tbody></table></div><h2>包问题</h2><div class="z-table-scroll"><table><thead><tr><th>类型</th><th>偏移</th><th>说明</th></tr></thead><tbody id="ze-issues"></tbody></table></div></div>
    <div class="z-actions z-exports"><button id="ze-csv">导出执行流 CSV</button><button id="ze-svg">导出火焰图 SVG</button><button id="ze-json">导出分析 JSON</button><button id="ze-srcflow">导出源码执行流</button></div>
    <div class="z-trace-columns"><div><h2>历史调用栈</h2><ol id="ze-stack" class="z-stack"></ol></div><div><h2>源码 / 指令字节</h2><pre id="ze-code" class="z-code">载入记录后解码；可另选源码进行逐范围回放。</pre></div></div></div></div></div>`;
    this.$=id=>document.getElementById('ze-'+id);
    const action=fn=>async()=>{try{await fn();}catch(e){this.log(e.message);toast(e.message,'err');}finally{this.buttons();}};
    this.$('connect').onclick=action(()=>this.connect());this.$('pick').onclick=action(()=>this.connectNew());this.$('disconnect').onclick=action(()=>this.releaseProbe());
    this.$('start').onclick=action(()=>this.start());this.$('stop').onclick=action(()=>this.stop());
    this.$('elf').onchange=action(async()=>{const f=this.$('elf').files[0];if(f)await this.loadElf(new Uint8Array(await f.arrayBuffer()),f.name);});
    this.$('open').onclick=()=>this.$('record').click();this.$('record').onchange=action(async()=>{const f=this.$('record').files[0];if(f)await this.loadRecord(JSON.parse(await f.text()));});
    this.$('save').onclick=action(()=>this.saveRecord());this.$('sample').onclick=action(async()=>this.loadRecord(await(await fetch('samples/cm3-orbtrace.zetm')).json()));
    this.$('sample-f103').onclick=action(async()=>this.loadRecord(await(await fetch('samples/f103ze-oversample.zetm')).json()));
    this.$('decode').onclick=action(()=>this.decode());
    this.$('csv').onclick=action(()=>this.exportCsv());this.$('svg').onclick=action(()=>this.exportSvg());
    this.$('json').onclick=action(()=>this.exportJson());this.$('srcflow').onclick=action(()=>this.exportSourceFlow());
    this.$('source').onchange=action(async()=>{for(const f of this.$('source').files)this.sources.set(f.name,await f.text());this.select(Number(this.$('cursor').value));});
    this.$('auto').onchange=()=>this.buttons();
    this.$('cursor').oninput=()=>this.select(Number(this.$('cursor').value));
    this.$('prev').onclick=()=>this.jump(-1);this.$('next').onclick=()=>this.jump(1);
    this.$('nav').onchange=()=>this.jump(1);
    for(const button of this.$('tabs').querySelectorAll('button'))button.onclick=()=>this.showView(button.dataset.view);
    // 板子重新上电/烧录会让 USB 重新枚举：旧句柄失效，界面必须跟着说实话。
    navigator.usb?.addEventListener?.('disconnect',event=>{
      if(!this.probe||event.device!==this.probe.device)return;
      this.probe=null;this.transport=null;this.$('device').textContent='USB 已断开（重新上电/烧录后点「连接」）';
      this.log('探针已断开');this.buttons();
    });
    this.$('filter').oninput=()=>this.renderFlow();this.$('timeline').onclick=e=>{if(this.ranges.length)this.select(Math.floor((e.offsetX/this.$('timeline').clientWidth)*this.ranges.length));};
    this.buttons();
  }
  buttons(){if(!this.$)return;this.$('start').disabled=!this.probe||this.busy||!this.images.length||(this.$('auto').checked&&!this.elfBytes);this.$('stop').disabled=!this.transport?.running&&!this.worker;this.$('disconnect').disabled=!this.probe||this.busy&&!this.transport?.running;this.$('connect').disabled=!!this.probe||this.busy;this.$('decode').disabled=!this.etm?.length||this.busy;this.$('save').disabled=!this.etm?.length||this.busy;this.$('sample').disabled=this.busy;this.$('sample-f103').disabled=this.busy;this.$('open').disabled=this.busy;this.$('elf').disabled=this.busy;this.$('csv').disabled=!this.model;this.$('svg').disabled=!this.model;this.$('json').disabled=!this.model;this.$('srcflow').disabled=!this.model||!this.lines;}
  log(text){this.$('log').textContent+=(new Date().toLocaleTimeString())+' '+text+'\n';this.$('log').scrollTop=this.$('log').scrollHeight;}
  /**
   * 连接：优先复用浏览器已经授权过的 ZynqDAP（`getDevices()` 不需要用户手势），
   * 没有授权过才弹设备选择框。板子重新烧录/断电后 USB 会重新枚举，旧句柄失效但授权还在，
   * 这条路径就是为那种场景准备的——CLI 因此可以在不弹框的情况下自己恢复连接。
   */
  async connect(){return runProbeOperation(this,'etm',async()=>{
    await this.openDevice(await this.pickDevice(false));
  });}
  /** 强制弹设备选择框（换设备、或授权过别的板子时用）。 */
  async connectNew(){return runProbeOperation(this,'etm',async()=>{
    await this.openDevice(await this.pickDevice(true));
  });}
  /**
   * 只走已授权设备的重连：CLI 造不出 `requestDevice` 需要的用户手势，所以这条不给弹框退路。
   * 第一次仍然要人点一次「连接 ZynqDAP」，之后 `page etm invoke reconnect` 就能自己恢复。
   */
  async reconnect(){return runProbeOperation(this,'etm',async()=>{
    const devices=(await WebUsbDapProbe.authorized().catch(()=>[]))
      .filter(device=>device.vendorId===0x0d28&&device.productId===0x0204);
    if(!devices.length)throw Error('没有已授权的 ZynqDAP：先在页面上点一次「连接 ZynqDAP」完成授权');
    await this.openDevice(devices[0]);
  });}
  async pickDevice(forcePick){
    if(!forcePick){
      const authorised=await WebUsbDapProbe.authorized().catch(()=>[]);
      const hit=authorised.find(device=>device.vendorId===0x0d28&&device.productId===0x0204);
      if(hit)return hit;
    }
    return navigator.usb.requestDevice({filters:[{vendorId:0x0d28,productId:0x0204}]});
  }
  async openDevice(device){
    // 同一个设备已经连着就不用重开：WebUSB 关闭后立刻重开会读到超时（端点还没复位）。
    // 同一个设备且句柄还开着才复用；USB 重新枚举后 device.opened 会变 false，必须重开。
    if(this.probe&&this.probe.device===device&&device.opened)return;
    if(this.probe){
      try{await this.releaseProbe();}catch(e){this.log('旧连接收尾失败：'+e.message);}
      await new Promise(resolve=>setTimeout(resolve,300));   // 给设备一点时间复位端点
    }
    try{this.probe=await WebUsbDapProbe.open(device,{clockKhz:50000});this.target=new EtmTarget(this.probe);this.transport=new EtmTransport(this.probe.device,(p,e)=>{
      this.quality={...p.quality(),refClockHz:this.transport?.refClockHz};this.status();if(e)this.log(e.message);
      const limit=Number(this.$('limit').value)*1024*1024;if(p.records*2>=limit&&!this.stopping)this.stop().catch(e=>this.log(e.message));
    });await this.transport.open();this.$('device').textContent=this.probe.name;this.log('已连接，端点 0x82');}
    catch(e){
      // 收尾失败不能顶掉原始错误，否则只剩一句 "xxx is not a function"。
      try{if(this.transport)await this.transport.close();}catch(cleanup){e.message+='；USB 端点收尾失败：'+cleanup.message;}
      try{if(this.probe)await this.probe.disconnect();}catch(cleanup){e.message+='；探针收尾失败：'+cleanup.message;}
      this.transport=null;this.probe=null;throw e;
    }
  }
  async releaseProbe(){
    if(this.transport?.running)await this.stop();if(this.target?.saved)await this.target.restore();
    if(this.transport)await this.transport.close();
    if(this.probe)await this.probe.disconnect();   // WebUsbDapProbe 的方法是 disconnect()，没有 close()
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
      if(this.$('auto').checked){await this.verifyFlash();this.config=await this.target.prepare({divider:Number(this.$('div').value)});this.$('config').value=JSON.stringify(this.config,null,2);}
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
    this.etm=parsed.etm;this.config=parsed.config;this.quality=parsed.quality;this.recordKind=parsed.kind;this.ranges=[];this.decoded=null;this.model=null;
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
    this.busy=true;this.ranges=[];this.decoded=null;this.model=null;this.$('rows').replaceChildren();this.$('hotspots').replaceChildren();this.buttons();this.status();this.log('OpenCSD WASM 解码中…');
    const worker=new Worker(new URL('./worker.js',import.meta.url),{type:'module'});this.worker=worker;this.buttons();
    try{
      const result=await new Promise((resolve,reject)=>{this.cancelDecode=reject;worker.onmessage=e=>e.data.ok?resolve(e.data.value):reject(Error(e.data.error));worker.onerror=e=>reject(Error(e.message));worker.postMessage({etm:this.etm,config:this.config,images:this.images});});
      this.decoded=result;this.ranges=result.ranges;this.$('cursor').max=Math.max(0,this.ranges.length-1);
      this.log(`恢复 ${this.ranges.length.toLocaleString()} 个指令范围 · OpenCSD ${result.status.library}`);
      const analysisStarted=performance.now();
      this.model=analyze({records:result.records,symbols:this.symbols});
      this.log(`调用树：${this.model.totals.functions} 个函数 · 深度 ${this.model.totals.maxDepth} · ${this.model.totals.calls} 次调用 · ${Math.round(performance.now()-analysisStarted)} ms`);
      this.renderAll();this.select(0);this.status();
    }finally{worker.terminate();this.worker=null;this.cancelDecode=null;this.busy=false;this.buttons();}
  }
  func(addr){let lo=0,hi=this.symbols.length;while(lo<hi){const mid=(lo+hi)>>>1;if((this.symbols[mid].addr>>>1)*2<=addr)lo=mid+1;else hi=mid;}const s=this.symbols[lo-1];return s&&addr<(s.addr>>>1)*2+s.size?s.name:hex(addr);}
  status(){
    const q=this.quality||{},t=this.model?.totals;
    this.$('status').textContent=`${this.recordKind==='simulation'?'CM3 仿真 · ':''}${this.etm?.length||0} ETM 字节 · ${q.records||0} 传输记录 · ${this.ranges.length.toLocaleString()} 指令范围 · ${q.loss?'有丢失':q.ended&&q.synced?'同步 / 完整结束':'采集中或未验收'} · FCLK ${q.fclk?Math.round(q.fclk/1000000)+' MHz':'未知'}${t?' · '+t.functions+' 函数 / 深度 '+t.maxDepth+' / '+t.calls+' 调用':''}`;
    this.$('status').classList.toggle('z-loss',!!q.loss);
  }
  showView(view){
    this.view=view;
    for(const button of this.$('tabs').querySelectorAll('button'))button.classList.toggle('active',button.dataset.view===view);
    for(const name of ['flow','stats','flame','hot','packet','section'])this.$('view-'+name).hidden=name!==view;
    if(view==='flame')this.renderFlame();
  }
  renderAll(){this.renderFlow();this.renderStats();this.renderFlame();this.renderHot();this.renderPackets();this.renderSections();this.renderStack();this.timeline();}
  renderFlow(){
    if(!this.model){this.$('rows').replaceChildren();return;}
    const filter=this.$('filter').value.toLowerCase(),start=Math.max(0,Number(this.$('cursor').value)-50),total=this.model.ranges.length;
    const cell=[];for(let i=filter?0:start;i<total&&cell.length<250;i++){
      const r=this.model.ranges[i],name=this.func(r.start),branch=BRANCH_LABEL[r.kind]||r.kind;
      if(filter&&!name.toLowerCase().includes(filter)&&!hex(r.start).includes(filter)&&!branch.includes(filter))continue;
      cell.push(`<tr data-index="${i}"${i===Number(this.$('cursor').value)?' class="z-row-current"':''}><td>${i}</td><td>${hex(r.start)}</td><td>${hex(r.end)}</td><td>${branch}${r.executed?'':'（未执行）'}</td><td>${r.depth}</td><td>${esc(name)}</td></tr>`);
    }
    this.$('rows').innerHTML=cell.join('');
    for(const row of this.$('rows').children)row.onclick=()=>this.select(Number(row.dataset.index));
  }
  renderStats(){
    if(!this.model){this.$('statrows').replaceChildren();return;}
    const rows=callStats(this.model,{limit:400}).map(row=>`<tr><td>${esc(row.name)}</td><td>${row.calls}</td><td>${row.self.toLocaleString()}</td><td>${row.total.toLocaleString()}</td><td>${pct(row.share)}</td><td>${row.maxDepth}</td></tr>`);
    this.$('statrows').innerHTML=rows.join('');
  }
  renderFlame(){
    if(!this.model||this.view!=='flame')return;
    const width=Math.max(480,this.$('flame').clientWidth||960);
    this.$('flame').innerHTML=flameSvg(this.model,{width:Math.round(width)});
  }
  renderHot(){
    if(!this.model){this.$('hotspots').replaceChildren();return;}
    const top=callStats(this.model,{limit:12});
    const max=top.length?top[0].total:1;
    this.$('hotspots').innerHTML=top.map(row=>`<div class="z-hot"><span>${esc(row.name)}</span><meter min="0" max="${max}" value="${row.total}"></meter><b>${row.total.toLocaleString()}</b></div>`).join('');
  }
  renderPackets(){
    if(!this.model){this.$('packetgroups').replaceChildren();this.$('packets').replaceChildren();return;}
    this.$('packetgroups').innerHTML=packetSummary(this.model).map(row=>`<tr><td>${esc(row.label)}</td><td>${row.count.toLocaleString()}</td><td>${row.bytes.toLocaleString()}</td></tr>`).join('');
    const recent=this.model.packets.slice(-400);
    this.$('packets').innerHTML=recent.map(packet=>`<tr><td>${packet.offset}</td><td>${packet.size}</td><td>${esc(packet.hex||'')}</td><td>${esc(packet.text||'')}</td></tr>`).join('');
  }
  renderSections(){
    if(!this.model){this.$('sections').replaceChildren();this.$('issues').replaceChildren();return;}
    this.$('sections').innerHTML=this.model.sections.map(part=>`<tr><td>${part.index}</td><td>${part.startOffset??'—'}</td><td>${part.endOffset??'—'}</td><td>${esc(part.reason)}</td><td>${part.ranges.toLocaleString()}</td><td>${part.halfwords.toLocaleString()}</td><td>${part.exception}</td><td>${part.issues}</td><td>${part.trusted?'可信':'不可信'}</td></tr>`).join('');
    const issues=this.model.issues.slice(0,300).map(issue=>`<tr><td>${esc(issue.kind)}</td><td>${issue.offset}</td><td>${esc(issue.detail||'')}</td></tr>`);
    if(this.model.totals.issuesTruncated)issues.push('<tr><td colspan="3">问题超出显示上限，完整的 500 条已记录在分析 JSON 中</td></tr>');
    this.$('issues').innerHTML=issues.join('');
  }
  renderStack(){
    if(!this.model){this.$('stack').replaceChildren();return;}
    const frames=this.model.stackAt(Number(this.$('cursor').value));
    this.$('stack').innerHTML=frames.map((frame,depth)=>`<li><b>${esc(frame.name)}</b> <span>深度 ${depth} · ${hex(frame.addr)}</span></li>`).join('')||'<li><span>调用栈为空（trace 起点之前没有可恢复的调用者）</span></li>';
  }
  select(index){
    if(!this.ranges.length)return;index=Math.max(0,Math.min(this.ranges.length-1,index));this.$('cursor').value=index;
    const r=this.ranges[index],line=this.lines?.at(r.start);
    const branch=BRANCH_LABEL[this.model?.ranges?.[index]?.kind]||'';
    this.$('location').textContent=`#${index} ${hex(r.start)} → ${hex(r.end)} · ${this.func(r.start)}${branch?' · '+branch:''}${line?' · '+line.file+':'+line.line:''}`;
    const source=line?this.sources.get(line.file.replace(/\\/g,'/').split('/').pop()):null;
    if(source)this.$('code').textContent=source.split(/\r?\n/).slice(Math.max(0,line.line-10),line.line+10).map((s,i)=>`${Math.max(1,line.line-9)+i===line.line?'▶':' '} ${Math.max(1,line.line-9)+i} ${s}`).join('\n');
    else{const image=this.images.find(i=>i.addr<=r.start&&r.start<i.addr+i.data.length),data=image?.data.subarray(r.start-image.addr,Math.min(r.end-image.addr,r.start-image.addr+64));this.$('code').textContent=`${hex(r.start)}  ${data?[...data].map(x=>x.toString(16).padStart(2,'0')).join(' '):'镜像无可用指令字节'}\n${line?'源码：'+line.file+':'+line.line+'，请载入该文件。':'镜像没有可用的源码行信息。'}`;}
    this.renderStack();this.renderFlow();
  }
  jump(direction){
    if(!this.model?.ranges.length)return;
    const kind=this.$('nav').value,predicate=NAV_KINDS[kind]||NAV_KINDS.all;
    const current=Number(this.$('cursor').value);
    for(let i=current+direction;i>=0&&i<this.model.ranges.length;i+=direction){
      if(predicate(this.model.ranges[i],this.model)){this.select(i);return;}
    }
    toast('这个方向上没有更多「'+this.$('nav').selectedOptions[0].textContent+'」范围','warn');
  }
  // 执行地址时间轴。用循环取极值：几十万范围展开成 Math.min(...array) 会直接爆栈。
  timeline(){
    const canvas=this.$('timeline');if(!canvas||!this.ranges.length)return;
    const ctx=canvas.getContext('2d');canvas.width=Math.max(400,canvas.clientWidth*devicePixelRatio);canvas.height=110*devicePixelRatio;
    const limit=Math.min(this.ranges.length,200000);let low=Infinity,high=-Infinity;
    for(let i=0;i<limit;i++){const start=this.ranges[i].start;if(start<low)low=start;if(start>high)high=start;}
    ctx.fillStyle='#0d1420';ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.strokeStyle='#5ca8ff';ctx.lineWidth=devicePixelRatio;ctx.beginPath();
    for(let x=0;x<canvas.width;x++){
      const range=this.ranges[Math.min(this.ranges.length-1,Math.floor(x/canvas.width*this.ranges.length))];
      const y=10+(high-range.start)/((high-low)||1)*(canvas.height-20);
      if(!x)ctx.moveTo(x,y);else ctx.lineTo(x,y);
    }
    ctx.stroke();
  }
  exportCsv(){if(!this.model)throw Error('先解码再导出');save(executionCsv(this.model),'zynqdap-etm-flow.csv','text/csv');}
  exportSvg(){if(!this.model)throw Error('先解码再导出');save(flameSvg(this.model,{width:1600}),'zynqdap-etm-flame.svg','image/svg+xml');}
  async exportJson(){
    if(!this.model)throw Error('先解码再导出');
    const etmSha=this.etm?.length?await sha256(this.etm):null;
    save(JSON.stringify(summaryJson(this.model,{elf:this.elfName,elfSha:this.elfSha,etmSha,
      config:this.config,quality:this.quality}),null,2),'zynqdap-etm-analysis.json','application/json');
  }
  exportSourceFlow(){
    if(!this.model)throw Error('先解码再导出');const rows=sourceFlow(this.model,this.lines);
    if(!rows.length)throw Error('ELF 里没有可用的源码行信息');
    save('file,line,halfwords,ranges\n'+rows.map(r=>`"${r.file.replaceAll('"','""')}",${r.line},${r.weight},${r.ranges}`).join('\n'),'zynqdap-etm-source-flow.csv','text/csv');
  }
  /**
   * 排查用：这次捕获里各 source ID 各有多少字节。
   * 收不到 ETM 数据时先看这里——「0 字节但传输记录很多」说明流是通的，只是 ID 对不上。
   */
  /**
   * 排查用：把和并行 trace 直接相关的寄存器读回来。
   * DBGMCU_CR 的 bit5=TRACE_IOEN、bit6-7=TRACE_MODE（11=4 位同步）；GPIOE_CRL 里 PE2~PE7
   * 应该是 0x4 开头的 AF 推挽。任何一项不对，四根数据线就不会被驱动，FPGA 只能采到空闲电平。
   */
  async traceRegisters(){
    if(!this.probe)throw Error('没有连接探针');
    const read=async address=>{
      const bytes=await this.probe.readMemDiagnostic(address,4);
      return '0x'+(new DataView(bytes.buffer,bytes.byteOffset,4).getUint32(0,true)>>>0).toString(16).padStart(8,'0');
    };
    const map={demcr:0xe000edfc,dbg_cr:0xe0042004,etmcr:0xe0041000,etmtraceidr:0xe0041200,
      tpiu_cspsr:0xe0040004,tpiu_acpr:0xe0040010,tpiu_ffcr:0xe0040304,gpioe_crl:0x40011800};
    const out={};
    for(const [name,address] of Object.entries(map))out[name]=await read(address);
    return out;
  }
  streamIds(){
    const counts=new Map();
    for(const chunk of this.transport?.parser?.chunks||[]){
      for(let i=0;i+1<chunk.length;i+=2)counts.set(chunk[i+1],(counts.get(chunk[i+1])||0)+1);
    }
    const total=[...counts.values()].reduce((sum,n)=>sum+n,0);
    const sample=[];
    for(const chunk of this.transport?.parser?.chunks||[]){
      for(let i=0;i+1<chunk.length&&sample.length<24;i+=2)
        sample.push(chunk[i].toString(16).padStart(2,'0')+'/'+chunk[i+1].toString(16).padStart(2,'0'));
      if(sample.length>=24)break;
    }
    return {total,expecting:this.config?.traceid??null,sample,
      ids:[...counts].sort((a,b)=>b[1]-a[1]).slice(0,8).map(([sourceId,bytes])=>({sourceId,bytes}))};
  }
  onShow(){if(this.ranges.length)this.timeline();if(this.view==='flame')this.renderFlame();}
  summary(){return {connected:!!this.probe,running:!!this.transport?.running,busy:this.busy,bytes:this.etm?.length||0,ranges:this.ranges.length,
    quality:this.quality||null,functions:this.model?.totals.functions||0,calls:this.model?.totals.calls||0,
    sections:this.model?.sections.length||0,view:this.view};}
}
