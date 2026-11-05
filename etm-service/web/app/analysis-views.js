import {wireFlameExport} from './flame-export-ui.js';
import {rangeFromPixels,wheelRange} from './execution-window.js';
import {createZoomControls} from './zoom-controls.js';
import {recordReport} from './record-report.js';
const make=(tag,text,className='')=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;e.className=className;if(className.split(/\s+/).includes('hint')&&text!==undefined)e.title=String(text);return e;};
const n=value=>Number(value).toLocaleString('zh-CN');

export function integrityView(result){
  const box=make('div',undefined,'integrity-panel'),nav=make('nav',undefined,'record-report-nav'),panels=[],buttons=[];
  nav.setAttribute('aria-label','报告分类');box.append(nav);
  const labels={'记录身份与配置':'概况','采集窗口与传输':'采集','解码完整性':'完整性','执行周期与耗时口径':'周期','处理性能 Profile':'Profile'};
  for(const group of recordReport(result)){
    const panel=make('section'),button=make('button',labels[group.title]||group.title);
    button.type='button';button.onclick=()=>{panels.forEach((p,i)=>{const selected=p===panel;p.hidden=!selected;buttons[i].setAttribute('aria-pressed',String(selected));});};
    buttons.push(button);panels.push(panel);nav.append(button);panel.append(make('h3',group.title));
    for(const [label,value]of group.rows){const row=make('div',undefined,'integrity-row');row.append(make('span',label),make('strong',String(value)));panel.append(row);}
    if(group.note)panel.append(make('p',group.note,'hint'));box.append(panel);
  }
  buttons[result.captureQuality?1:2].onclick();
  return box;
}

function aggregateFlameView(result,onFunction,selectedFunction='',o={}){
  const box=make('div',undefined,'flame-panel');
  const timing=result.analysis?.timing;
  const cyclesReady=!!timing?.timeFlameAvailable&&(timing.totalCycles||0)>0;
  // 周期加权（Ozone 同款口径）：宽度 = 该节点累计的**周期数**，而不是指令记录数。
  // 没有周期数据时退回记录数加权，按钮禁用并说明原因。
  let weightMode=cyclesReady?'cycles':'records';
  const weightOf=node=>weightMode==='cycles'?(node.valueCycles||0):(node.value||0);
  const weightText=()=>weightMode==='cycles'?'宽度＝周期（耗时口径）':'宽度＝路径指令记录数';
  const tools=make('div',undefined,'row flame-tools'),reset=make('button','重置'),open=make('button','查看函数执行流'),exportSvg=make('button','导出当前火焰图 SVG'),exportHtml=make('button','导出交互火焰图 HTML','primary');
  const weightBtn=make('button',weightMode==='cycles'?'切换到记录数':'切换到周期');
  weightBtn.disabled=!cyclesReady;
  weightBtn.title=cyclesReady?'火焰图权重：周期数（Ozone 口径）↔ 路径指令记录数':'本记录没有周期计数数据（目标未启用，或 ETMv3/F103 不支持）';
  const label=make('span','全部路径','dim'),canvas=make('div');
  label.title='当前选择与权重口径';
  box.title='点击方块放大；可查看选中函数的执行流'+(selectedFunction?'；蓝框为当前光标所属函数':'');
  exportSvg.title='导出当前区间、当前权重和当前放大层级；SVG 宽度按函数名自动扩展，函数名完整显示';
  exportHtml.title='导出当前区间的Timeline和周期权重双标签HTML，默认Timeline；支持框选放大、Shift拖动平移及查找函数';
  tools.append(reset,open,weightBtn,exportHtml,exportSvg,label);box.append(tools,canvas);
  const namespace='http://www.w3.org/2000/svg',original=result.analysis.flame;let selected=original;
  const levels=node=>1+Math.max(0,...node.children.map(levels));
  function nodePath(target,node=original,path=[]){
    if(node===target)return path;
    for(let i=0;i<node.children.length;i++){const found=nodePath(target,node.children[i],path.concat(i));if(found)return found;}
    return null;
  }
  const exportFeedback=wireFlameExport(exportSvg,()=>o.onExport?.({mode:'aggregate',weight:weightMode,rootPath:(nodePath(selected)||[]).join('.'),format:'svg'}),o.onError);
  const htmlFeedback=wireFlameExport(exportHtml,()=>o.onExport?.({mode:'aggregate',weight:weightMode,rootPath:(nodePath(selected)||[]).join('.'),format:'html'}),o.onError);
  tools.after(htmlFeedback,exportFeedback);
  function repaint(root){selected=root;o.onExportOptions?.({mode:'aggregate',weight:weightMode,rootPath:(nodePath(root)||[]).join('.')});label.textContent=root.name+' · '+(weightMode==='cycles'?n(root.valueCycles||0)+' 周期':n(root.value)+' 条');open.disabled=root===original||/未知|中断/.test(root.name);const svg=document.createElementNS(namespace,'svg'),height=levels(root)*29+12;svg.setAttribute('viewBox',`0 0 1000 ${height}`);svg.setAttribute('role','img');svg.setAttribute('aria-label',`按${weightMode==='cycles'?'周期数':'路径指令记录数量'}加权的调用火焰图`);svg.style.width='100%';
    function draw(node,x,depth,width,path){const group=document.createElementNS(namespace,'g'),rect=document.createElementNS(namespace,'rect'),text=document.createElementNS(namespace,'text'),title=document.createElementNS(namespace,'title'),y=depth*29+2;   // 向下生长：根在顶部，子调用逐层向下
      rect.setAttribute('x',x);rect.setAttribute('y',y);rect.setAttribute('width',Math.max(.2,width-1));rect.setAttribute('height',26);let hash=0;for(const c of node.name)hash=(hash*31+c.charCodeAt(0))|0;rect.setAttribute('fill',node.name.includes('未知')?'#c4ccd8':`hsl(${25+Math.abs(hash)%40} 78% ${58+depth%3*5}%)`);rect.setAttribute('rx',2);if(selectedFunction&&node.name===selectedFunction){rect.setAttribute('stroke','#58a6ff');rect.setAttribute('stroke-width','2');}
      const cycleInfo=(node.valueCycles!==undefined)?`；周期 ${n(node.valueCycles)}（自身 ${n(node.selfCycles||0)}）`:'';
      title.textContent=path.concat(node.name).join(' → ')+'；包含 '+n(node.value)+' 条，自身 '+n(node.self)+' 条'+cycleInfo;text.setAttribute('x',x+5);text.setAttribute('y',y+17);text.setAttribute('fill','#403329');text.setAttribute('font-size',12);text.textContent=width>40?node.name.slice(0,Math.max(1,Math.floor((width-10)/7))):'';group.append(rect,text,title);group.setAttribute('role','button');group.setAttribute('tabindex','0');group.setAttribute('aria-label',`函数 ${node.name}，${node.value} 条路径记录${node.valueCycles!==undefined?'，'+node.valueCycles+' 周期':''}`);group.style.cursor='pointer';group.onclick=()=>repaint(node);group.onkeydown=e=>{if(e.key==='Enter')repaint(node);};svg.append(group);
      const total=weightOf(node)||1;let next=x;
      const children=[...node.children].filter(c=>weightOf(c)>0).sort((a,b)=>weightOf(b)-weightOf(a));
      for(const child of children){const w=width*weightOf(child)/total;if(w<.15)continue;draw(child,next,depth+1,w,path.concat(node.name));next+=w;}
    }
    if(weightOf(root))draw(root,0,0,1000,[]);else canvas.replaceChildren(make('p','当前权重下没有可绘制区间。','hint'));canvas.replaceChildren(svg);
  }
  weightBtn.onclick=()=>{weightMode=weightMode==='cycles'?'records':'cycles';weightBtn.textContent=weightMode==='cycles'?'切换到记录数':'切换到周期';repaint(original);};
  reset.onclick=()=>repaint(original);open.onclick=()=>onFunction(selected.name);repaint(original);return box;
}

export function flameView(result,onFunction,o={}){
  if(!o.window)return aggregateFlameView(result,onFunction,o.cursorFunction||'',o);
  const data=o.window,scope=data.range,box=make('div',null,'execution-chart'),toolbar=make('div',null,'row window-tools');
  const safe=fn=>{try{Promise.resolve(fn()).catch(o.onError);}catch(e){o.onError(e);}};
  const button=(text,fn)=>{const b=make('button',text);b.onclick=()=>safe(fn);return b;};
  const modes=make('div',null,'window-actions'),rangeTools=make('div',null,'window-range');
  const timeline=button('按执行顺序',()=>o.onMode('timeline')),aggregate=button('按调用权重',()=>o.onMode('aggregate'));
  timeline.classList.toggle('primary',o.mode!=='aggregate');aggregate.classList.toggle('primary',o.mode==='aggregate');
  const back=button('上一级',o.onBack);back.disabled=!o.canBack;
  const from=make('input'),to=make('input');from.type=to.type='number';from.value=scope.start;to.value=scope.end;
  from.setAttribute('aria-label','区间起点序号');to.setAttribute('aria-label','区间结束序号');from.min=to.min=scope.totalStart;from.max=to.max=scope.totalEnd;
  const width=scope.end-scope.start+1,totalWidth=scope.totalEnd-scope.totalStart+1;
  const zoom=createZoomControls({onZoomOut:()=>safe(()=>o.onZoom?.(false)),onZoomIn:()=>safe(()=>o.onZoom?.(true)),onFit:()=>safe(o.onReset)});
  zoom.setDisabled({zoomIn:o.zoomBusy||width<=2,zoomOut:o.zoomBusy||width>=totalWidth,fit:o.zoomBusy||width>=totalWidth});
  const sourceToggle=button(o.sourceCollapsed?'展开源码':'收起源码',o.onToggleSource);sourceToggle.setAttribute('aria-expanded',String(!o.sourceCollapsed));sourceToggle.title=o.sourceCollapsed?'展开源码对照窗格':'收起源码窗格，扩展火焰图';
  modes.append(timeline,aggregate,back);rangeTools.append(make('span','#'),from,make('span','～'),to,button('查看',()=>o.onRange({start:Number(from.value),end:Number(to.value)})));toolbar.append(modes,zoom.element,sourceToggle,rangeTools);
  box.zoomControls=zoom;box.append(toolbar);box.title='拖选放大；Ctrl＋滚轮缩放；纵向按调用深度向下延展。';
  if(o.mode==='aggregate'){box.append(aggregateFlameView({...result,analysis:data.analysis},onFunction,o.cursorFunction||'',o));return box;}
  if(!Array.isArray(data.timeline)||!data.timeline.length){
    // 全记录没有预计算的分桶时间轴：按调用权重显示（analysis 是解码时算好的，立即出图），
    // 要看执行顺序需先选一个区间（审查 P2：全记录 window() 实测 119.5 s，不能阻塞首屏）。
    box.append(make('p','没有执行序号分桶，先按调用权重显示；选一个区间可看执行顺序。','hint'));
    box.append(aggregateFlameView({...result,analysis:data.analysis},onFunction,o.cursorFunction||'',o));
    return box;
  }
  o.onExportOptions?.({mode:'timeline',weight:'records',rootPath:''});
  const exportSvg=make('button','导出当前火焰图 SVG'),exportHtml=make('button','导出交互火焰图 HTML','primary');
  const exportFeedback=wireFlameExport(exportSvg,()=>o.onExport?.({mode:'timeline',weight:'records',rootPath:'',format:'svg'}),o.onError);
  const htmlFeedback=wireFlameExport(exportHtml,()=>o.onExport?.({mode:'timeline',weight:'records',rootPath:'',format:'html'}),o.onError);
  exportSvg.title='读取当前区间的原始调用栈，完整深度、完整函数名；图宽按最小所需比例扩展';
  exportHtml.title='按原始执行顺序导出完整调用深度，可离线缩放、平移和查找函数';
  modes.append(exportHtml,exportSvg);box.append(htmlFeedback,exportFeedback);
  const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');
  const maxDepth=Math.max(1,...data.timeline.map(b=>b.path.length)),height=maxDepth*26+38;
  const unit=1000;svg.setAttribute('viewBox',`0 0 ${unit} ${height}`);svg.setAttribute('role','img');svg.setAttribute('aria-label','按执行先后排列的调用区间图，拖选缩放');svg.classList.add('execution-timeline');svg.style.touchAction='none';
  const span=scope.end-scope.start+1;
  const text=(x,y,value,color='#9aa4af')=>{const t=document.createElementNS(ns,'text');t.setAttribute('x',x);t.setAttribute('y',y);t.setAttribute('fill',color);t.setAttribute('font-size','11');t.textContent=value;svg.append(t);};
  for(let i=0;i<=4;i++){text(i*unit/4,height-7,'#'+Math.round(scope.start+(scope.end-scope.start)*i/4));svg.lastChild.setAttribute('text-anchor',i===4?'end':i===0?'start':'middle');}
  const frames=[],active=[];
  for(const b of data.timeline){
    let ancestorChanged=false;
    b.path.forEach((name,depth)=>{let frame=ancestorChanged?null:active[depth];
      if(frame&&frame.name===name&&frame.endSeq+1===b.startSeq&&!frame.cutAfter&&!b.events.length){frame.endSeq=b.endSeq;frame.records+=b.records;frame.unknown+=b.unknown;}
      else{ancestorChanged=true;frame={name,depth,startSeq:b.startSeq,endSeq:b.endSeq,records:b.records,unknown:b.unknown,firstSeq:b.firstSeq,cutAfter:!!b.events.length};frames.push(frame);active[depth]=frame;}
    });active.length=b.path.length;
    if(b.events.length){const x=(b.startSeq-scope.start)/span*unit,w=(b.endSeq-b.startSeq+1)/span*unit,marker=document.createElementNS(ns,'rect'),title=document.createElementNS(ns,'title');marker.setAttribute('x',x);marker.setAttribute('y',height-29);marker.setAttribute('width',Math.max(1,w));marker.setAttribute('height',7);marker.setAttribute('fill','#d29922');title.textContent=b.events.map(e=>'#'+e.seq+' '+e.text).join('；');marker.append(title);svg.append(marker);}
  }
  for(const b of frames){const x=(b.startSeq-scope.start)/span*unit,w=Math.max(.4,(b.endSeq-b.startSeq+1)/span*unit),name=b.name,depth=b.depth;
    const g=document.createElementNS(ns,'g'),r=document.createElementNS(ns,'rect'),title=document.createElementNS(ns,'title');
    r.setAttribute('x',x);r.setAttribute('y',depth*26+2);r.setAttribute('width',Math.max(.3,w-.4));r.setAttribute('height',23);let hash=0;for(const c of name)hash=(hash*31+c.charCodeAt(0))|0;
    r.setAttribute('fill',/未知|多段/.test(name)?'#667484':`hsl(${25+Math.abs(hash)%45} 76% ${56+depth%3*5}%)`);title.textContent=name+` · #${b.startSeq}～#${b.endSeq} · ${b.records} 条路径 / ${b.unknown} 条状态未知`;
    g.append(r,title);g.setAttribute('role','button');g.setAttribute('tabindex','0');g.setAttribute('aria-label',name+' 执行区间 '+b.startSeq+' 到 '+b.endSeq);g.onkeydown=e=>{if(e.key==='Enter')safe(()=>o.onSelect(b.firstSeq));};svg.append(g);
    if(w>40)text(x+3,depth*26+18,name.slice(0,Math.floor((w-6)/7)),'#302d25');
  }
  if(Number.isInteger(o.cursorSeq)&&o.cursorSeq>=scope.start&&o.cursorSeq<=scope.end){
    const x=(o.cursorSeq-scope.start)/span*unit,line=document.createElementNS(ns,'line'),marker=document.createElementNS(ns,'path'),title=document.createElementNS(ns,'title');
    line.setAttribute('x1',x);line.setAttribute('x2',x);line.setAttribute('y1','1');line.setAttribute('y2',height-20);line.setAttribute('class','execution-cursor');line.setAttribute('pointer-events','none');
    marker.setAttribute('d',`M${x-5} 1h10l-5 7z`);marker.setAttribute('class','execution-cursor-marker');marker.setAttribute('pointer-events','none');title.textContent='当前光标 · #'+o.cursorSeq;line.append(title);svg.append(line,marker);
  }
  let drag=null;
  const overlay=document.createElementNS(ns,'rect');overlay.setAttribute('fill','#58a6ff33');overlay.setAttribute('stroke','#58a6ff');overlay.setAttribute('height',height-20);overlay.setAttribute('pointer-events','none');
  svg.onpointerdown=e=>{if(e.button!==0)return;e.preventDefault();const r=svg.getBoundingClientRect();drag={start:e.clientX-r.left,width:r.width,left:r.left};svg.setPointerCapture(e.pointerId);overlay.setAttribute('x',drag.start/r.width*unit);overlay.setAttribute('width',0);svg.append(overlay);};
  svg.onpointermove=e=>{if(!drag)return;const end=Math.max(0,Math.min(drag.width,e.clientX-drag.left));overlay.setAttribute('x',Math.min(drag.start,end)/drag.width*unit);overlay.setAttribute('width',Math.abs(drag.start-end)/drag.width*unit);};
  svg.onpointerup=e=>{if(!drag)return;const d=drag;drag=null;overlay.remove();svg.releasePointerCapture(e.pointerId);const end=e.clientX-d.left,r=rangeFromPixels(d.start,end,d.width,scope.start,scope.end);if(Math.abs(end-d.start)>4)safe(()=>o.onRange(r));else safe(()=>o.onSelect(r.start));};
  svg.onpointercancel=()=>{drag=null;overlay.remove();};
  svg.addEventListener('wheel',e=>{if(!e.ctrlKey)return;e.preventDefault();const r=svg.getBoundingClientRect(),focus=Number.isInteger(o.cursorSeq)&&o.cursorSeq>=scope.start&&o.cursorSeq<=scope.end?(o.cursorSeq-scope.start)/span:(e.clientX-r.left)/r.width;safe(()=>o.onRange(wheelRange(scope,{start:scope.totalStart,end:scope.totalEnd},focus,e.deltaY<0)));},{passive:false});
  box.append(svg);return box;
}
