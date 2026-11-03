/** Guided UI only. Hardware controls are never clicked by this module. */
export const TUTORIALS=[
  {id:'analysis',title:'离线分析 Demo',description:'无需硬件 · 用内置历史记录练习阅读执行轨迹',sample:true,steps:[
    {target:'#records',title:'这是保存的历史记录',text:'已打开 H743 历史参考示例，带有匹配 ELF、采集配置和源码位置，不代表当前板卡状态。选择其他历史记录也不会单步目标。'},
    {target:'#toggle-summary',title:'先看报告，再看结果',text:'点击「报告」，查看解码质量、捕获边界和未知区段。包问题为 0 也不能单独证明执行流完整。',done:'report'},
    {target:'#table-container',view:'instructions',title:'选中一条历史指令',text:'点击执行流中的一行。右侧会定位到该历史位置；灰色未成立路径与未知条件需要分别阅读。',observe:'#table-container tbody tr'},
    {target:'.source-pane',source:true,title:'理解源码定位与机器码',text:'示例保留了文件名、行号和机器码，未附源码正文。自己的记录带有配套源码快照时，这里会显示对应 C 代码；ETM 指令轨迹不提供变量值历史。'},
    {target:'#history-next',title:'沿历史前后移动',text:'点击箭头移动历史位置，或切换导航类型按调用、返回、中断查找。这些按钮浏览记录，不会让目标执行单步。',observe:'#history-next,#history-prev'},
    {target:'[data-view="flame"]',title:'换一个角度看调用路径',text:'点击「火焰图」，查看函数调用路径并尝试局部放大。默认横轴是执行序号，不是耗时；没有周期信息时不要把宽度当运行时间。',done:'flame'},
    {target:'[data-view="quality"]',title:'了解哪些区段可以信任',text:'点击「可信区段」查看边界与异常；可再回到执行流定位。教程结束后，示例仍保留在记录列表中供你自由探索。',done:'quality'}
  ]},
  {id:'capture',title:'第一次联动采集',description:'需要目标板与探针 · 一步一步熟悉真实录制流程',steps:[
    {target:'#choose-elf',panel:'target',title:'载入目标实际运行的 ELF',text:'点击载入与目标 Flash 一致的 ELF。它用于校验镜像、解析函数和重建执行流；载入文件本身不是烧录。',done:'elf'},
    {target:'#connect',panel:'target',title:'连接并确认芯片能力',text:'确认板卡空闲、Trace 接线和供电正确，再由你点击「连接探针」。检查识别型号和 ETM 支持情况，不能仅凭芯片系列推断支持。',done:'connected'},
    {target:'#symbol-search',panel:'target',title:'选择初始化后的业务函数',text:'搜索函数，点击函数前的 ＋ 添加断点，再用断点列表圆点选为采集起点。优先选择初始化后的业务函数，避免一开始就在启动代码中采集。',done:'entry'},
    {target:'#read-clock',panel:'clock',title:'核对板级输入与回读时钟',text:'按板卡填写真实 HSE，点击重新读取 RCC，再核对 CPU 与 TRACECLK。这里的预期值不会替你修改目标 PLL；不要直接照抄示例板频率。',observe:'#read-clock'},
    {target:'#panel-trace',panel:'trace',title:'从短窗口和默认配置开始',text:'核对 Trace ID、芯片支持的选项和接收端。首次可选择较短采集窗口，例如 10ms，再按需要加长；不必一次修改所有高级选项。'},
    {target:'#start',panel:'trace',title:'由你点击联动采集',text:'先看起点、复位和联动复选项，再点击「联动采集」。此操作可能暂停、复位并运行目标；教学不会替你点击。任务完成后再核对恢复状态。',done:'capture'},
    {target:'#toggle-summary',title:'采集成功还要检查记录',text:'打开报告检查实际窗口、接收/解码质量和捕获边界，再查看执行流。可以保存完整记录包，日后无需连接板卡也能分析。',done:'report'}
  ]},
  {id:'import',title:'导入自己的记录',description:'无需连接目标 · 区分记录包与原始 Trace 数据',steps:[
    {target:'#import',panel:'files',title:'完整记录包最省步骤',text:'如果有 .etmrecord，直接点击「导入记录」：它带有匹配 ELF、原始 Trace 和采集配置，不需要先连接硬件。',done:'record'},
    {target:'#choose-elf',panel:'target',title:'只有原始文件时，先准备 ELF',text:'若输入是 BIN、KVDAT 或波形 CSV，而不是完整记录包，先载入采集时实际使用的 firmware.elf。不能用后来重新编译的文件代替。'},
    {target:'#choose-offline-config',panel:'files',title:'载入采集时的配置',text:'原始文件还需要同次采集的 session.json，提供协议、Trace ID 和寄存器配置。完整 .etmrecord 已包含这些信息，可以跳过此步。'},
    {target:'#import',panel:'files',title:'导入原始 Trace 并等待解码',text:'现在选择原始采集文件。已导出的执行流 CSV 是分析结果，不是波形输入；解码失败时保留原记录并查看原因。',done:'record'},
    {target:'#toggle-summary',title:'从质量报告进入分析',text:'先确认协议、ELF、质量和边界，再选中历史指令查看源码。后续可以使用「离线分析 Demo」学习各个分析视图。',done:'report'}
  ]}
];

export function tutorialDone(step,state,observed=false){
  if(step.observe)return observed;
  return !!({report:state.reportOpen,elf:state.hasElf,connected:state.connected,entry:state.hasEntry,
    record:state.hasRecord&&state.freshRecord,capture:state.freshCapture,flame:state.view==='flame',quality:state.view==='quality'}[step.done]);
}

export function initTutorials({doc=document,win=window,busy,state,prepare,saveLayout,loadExample}){
  const opener=doc.getElementById('tutorials');if(!opener)return null;
  const make=(tag,text,cls)=>{const e=doc.createElement(tag);if(text)e.textContent=text;if(cls)e.className=cls;return e;};
  const chooser=make('dialog',null,'tutorial-chooser');chooser.setAttribute('aria-labelledby','tutorial-menu-title');
  const heading=make('h2','跟着 Demo 学 ETM');heading.id='tutorial-menu-title';
  const intro=make('p','选一条流程开始。高亮会指向实际控件；每一步都可以直接预览，硬件按钮始终由你操作。','hint');
  const status=make('p','','hint');status.setAttribute('role','status');
  const menu=make('div',null,'tutorial-choices'),cancel=make('button','关闭');cancel.type='button';cancel.onclick=()=>chooser.close();
  chooser.append(heading,intro,menu,status,cancel);doc.body.append(chooser);
  const ring=make('div',null,'tutorial-ring');ring.hidden=true;ring.setAttribute('aria-hidden','true');
  const card=make('section',null,'tutorial-card');card.hidden=true;card.setAttribute('role','dialog');card.setAttribute('aria-modal','false');card.setAttribute('aria-labelledby','tutorial-step-title');
  const top=make('div',null,'tutorial-top'),progress=make('span'),close=make('button','退出教学');close.type='button';top.append(progress,close);
  const title=make('h2');title.id='tutorial-step-title';title.tabIndex=-1;
  const text=make('p'),note=make('p',null,'tutorial-note');note.setAttribute('role','status');
  const footer=make('div',null,'tutorial-actions'),back=make('button','上一步'),next=make('button','下一步','primary');back.type=next.type='button';footer.append(back,next);
  card.append(top,title,text,note,footer);doc.body.append(ring,card);
  let flow=null,index=0,observed=false,restore=null,timer=null,version=0,preparing=false,returnFocus=null,issue='',menuError='',baselineRecord=null,baselineCapture=null;
  const stopTimer=()=>{if(timer){win.clearInterval(timer);timer=null;}};
  const position=()=>{
    if(!flow||card.hidden)return;
    const el=doc.querySelector(flow.steps[index].target),r=el?.getBoundingClientRect();
    const visible=r&&r.width>0&&r.height>0&&r.bottom>0&&r.top<win.innerHeight;
    ring.hidden=!visible;
    if(visible){Object.assign(ring.style,{left:Math.max(2,r.left-3)+'px',top:Math.max(2,r.top-3)+'px',width:Math.min(r.width+6,win.innerWidth-4)+'px',height:Math.min(r.height+6,win.innerHeight-4)+'px'});}
    const w=card.offsetWidth,h=card.offsetHeight,pad=10;
    let x=visible&&r.right+w+pad*2<win.innerWidth?r.right+pad:win.innerWidth-w-pad;
    let y=visible?(r.bottom+h+pad*2<win.innerHeight?r.bottom+pad:r.top-h-pad):pad;
    Object.assign(card.style,{left:Math.max(pad,Math.min(x,win.innerWidth-w-pad))+'px',top:Math.max(pad,Math.min(y,win.innerHeight-h-pad))+'px'});
  };
  const update=()=>{
    const locked=busy();next.disabled=back.disabled=locked||preparing;
    if(!locked&&!preparing)back.disabled=index===0;
    if(flow){const step=flow.steps[index],current=state();note.textContent=preparing?'正在定位操作区域…':locked?'当前操作进行中，请等待结果；引导不会代替执行。'
      :issue|| (tutorialDone(step,{...current,freshRecord:!!current.recordId&&current.recordId!==baselineRecord,freshCapture:!!current.captureId&&current.captureId!==baselineCapture},observed)?'已看到本步操作或状态。可以继续。':'请在高亮处操作；也可点下一步仅预览说明。');position();}
    else if(chooser.open&&!preparing){status.textContent=locked?'当前有任务进行中，完成后可开始教学。':menuError;for(const b of menu.children)b.disabled=locked;}
  };
  const end=()=>{version++;flow=null;preparing=false;ring.hidden=card.hidden=true;stopTimer();restore?.();restore=null;if(returnFocus?.isConnected)returnFocus.focus();};
  close.onclick=end;
  const show=async n=>{
    if(!flow)return;const ticket=++version;index=n;observed=false;issue='';preparing=true;update();
    progress.textContent=flow.title+' · '+(index+1)+' / '+flow.steps.length;
    title.textContent=flow.steps[index].title;text.textContent=flow.steps[index].text;
    next.textContent=index===flow.steps.length-1?'完成教学':'下一步';card.hidden=false;
    try{await prepare(flow.steps[index]);if(ticket!==version)return;
      doc.querySelector(flow.steps[index].target)?.scrollIntoView({block:'nearest',inline:'nearest'});
      win.requestAnimationFrame(()=>{if(ticket===version){position();title.focus();}});
    }catch(e){if(ticket===version){issue='此处暂不可用：'+e.message+'。可继续预览或退出。';card.hidden=false;}}
    finally{if(ticket===version){preparing=false;update();}}
  };
  next.onclick=()=>{if(flow&&!busy()&&!preparing){if(index+1===flow.steps.length)end();else show(index+1);}};
  back.onclick=()=>{if(flow&&!busy()&&!preparing&&index>0)show(index-1);};
  const start=async item=>{
    if(busy()||preparing)return;returnFocus=opener;preparing=true;menuError='';const ticket=++version;
    baselineRecord=state().recordId;baselineCapture=state().captureId;
    for(const b of menu.children)b.disabled=true;status.textContent=item.sample?'正在准备历史示例：导入、解码后开始引导…':'';
    const undo=saveLayout();
    try{if(item.sample)await loadExample();if(ticket!==version){undo();return;}
      chooser.close();restore=undo;flow=item;preparing=false;stopTimer();timer=win.setInterval(update,400);await show(0);
    }catch(e){undo();if(ticket===version){preparing=false;menuError='准备失败：'+e.message+'。可重试或选择其他教程。';update();}}
  };
  for(const item of TUTORIALS){const b=make('button',null,'tutorial-choice');b.type='button';b.dataset.tutorial=item.id;b.append(make('strong',item.title),make('span',item.description));b.onclick=()=>start(item);menu.append(b);}
  const open=()=>{if(flow)end();preparing=false;menuError='';chooser.showModal();stopTimer();timer=win.setInterval(update,400);update();};
  opener.onclick=open;const empty=doc.getElementById('tutorial-start');if(empty)empty.onclick=open;
  chooser.addEventListener('cancel',()=>{version++;preparing=false;});
  chooser.addEventListener('close',()=>{if(!flow)stopTimer();});
  cancel.onclick=()=>{version++;preparing=false;chooser.close();};
  doc.addEventListener('click',event=>{const step=flow?.steps[index];if(step?.observe&&event.target.closest(step.observe)){observed=true;update();}},true);
  doc.addEventListener('keydown',e=>{if(e.key==='Escape'&&flow){e.preventDefault();end();}});
  win.addEventListener('resize',position);doc.addEventListener('scroll',position,true);
  win.addEventListener('pagehide',()=>{version++;stopTimer();});
  return {open,close:end};
}
