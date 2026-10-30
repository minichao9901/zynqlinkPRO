// ETM 执行流的纯前端分析层：把 OpenCSD 的元素流还原成调用树、火焰图、调用统计、
// 可信区段和包问题。全部是纯函数，不碰 DOM，也不依赖任何本地桥或 Python 服务。
//
// 数据来源：`decodeTrace()` 返回的 records（kind === 'element' / 'packet'）。
// 元素与指令类型的编号来自本仓库 third_party/OpenCSD-1.8.3 的头文件，不要凭记忆改。

/** ocsd_gen_trc_elem_t（trc_gen_elem_types.h）。 */
export const ELEM=Object.freeze({UNKNOWN:0,NO_SYNC:1,TRACE_ON:2,EO_TRACE:3,PE_CONTEXT:4,INSTR_RANGE:5,
  I_RANGE_NOPATH:6,ADDR_NACC:7,ADDR_UNKNOWN:8,EXCEPTION:9,EXCEPTION_RET:10,TIMESTAMP:11,CYCLE_COUNT:12,
  EVENT:13,SWTRACE:14,SYNC_MARKER:15,MEMTRANS:16,INSTRUMENTATION:17,ITMTRACE:18,CUSTOM:19});
/** ocsd_instr_type（ocsd_if_types.h）。 */
export const INSTR=Object.freeze({OTHER:0,BR:1,BR_INDIRECT:2,ISB:3,DSB_DMB:4,WFI_WFE:5,TSTART:6});
/** ocsd_instr_subtype（ocsd_if_types.h）。 */
export const SUB=Object.freeze({NONE:0,BR_LINK:1,V8_RET:2,V8_ERET:3,V7_IMPLIED_RET:4});

export const BRANCH_LABEL=Object.freeze({none:'顺序',call:'调用',return:'返回',cond:'条件跳转',jump:'跳转',
  indirect:'间接跳转',wfi:'等待',barrier:'屏障',exception:'异常',unknown:'未知'});

const MAX_ISSUES=500;
const isRange=e=>!!e&&(e.type===ELEM.INSTR_RANGE||e.type===ELEM.I_RANGE_NOPATH);
const weightOf=e=>Math.max(0,((e.end>>>0)-(e.start>>>0))>>>1);   // 半字（2 字节）数

/**
 * 一个指令范围最后一条指令的分支性质。
 * Cortex-M3（v7 Thumb）：BL/BLX 是 BR+BR_LINK；BX LR / POP{PC} 是 BR_INDIRECT+V7_IMPLIED_RET。
 * 只有 BR_LINK 才算调用，只有在间接分支上带 RET 子类型才算返回——否则尾调用会被误判成返回。
 */
export function branchKind(element){
  if(!isRange(element))return element?.type===ELEM.EXCEPTION?'exception':'none';
  const type=element.lastType|0,sub=element.lastSubtype|0;
  if(sub===SUB.BR_LINK)return 'call';
  if(sub===SUB.V8_RET||sub===SUB.V8_ERET||sub===SUB.V7_IMPLIED_RET)return 'return';
  if(type===INSTR.BR_INDIRECT)return 'indirect';
  if(type===INSTR.BR)return element.lastConditional?'cond':'jump';
  if(type===INSTR.WFI_WFE)return 'wfi';
  if(type===INSTR.ISB||type===INSTR.DSB_DMB)return 'barrier';
  if(type===INSTR.OTHER)return 'none';
  return 'unknown';
}

const hex=value=>'0x'+(value>>>0).toString(16).padStart(8,'0');

/** 用 ELF 函数符号表建一个地址→函数名解析器（Thumb 地址末位为 1 时先抹掉）。 */
export function symbolResolver(symbols=[]){
  const table=symbols.filter(s=>s&&s.size>0).map(s=>({name:s.name,addr:(s.addr>>>1)*2,size:s.size}))
    .sort((a,b)=>a.addr-b.addr);
  const addrs=table.map(s=>s.addr);
  return function resolve(address){
    const pc=(address>>>0)&0xfffffffe;
    let lo=0,hi=addrs.length;
    while(lo<hi){const mid=(lo+hi)>>>1;if(addrs[mid]<=pc)lo=mid+1;else hi=mid;}
    const hit=table[lo-1];
    if(hit&&pc<hit.addr+hit.size)return hit.name;
    return hex(pc);
  };
}

/**
 * 把元素流还原成调用树。
 *
 * - 调用：BR_LINK 范围之后压栈；帧名在下一段范围到达时用它的起始地址解析，
 *   因为调用目标只有在下一条执行范围里才看得到。
 * - 返回：带 RET 子类型的间接分支范围之后弹栈；栈空时记一条「孤立返回」问题。
 * - 异常：异常入口压一帧，EXCEPTION_RET 弹栈。
 * - NO_SYNC / TRACE_ON：视为不连续边界，清空调用栈并切出一个新区段。
 *
 * 每个范围只累加所在帧的 self 权重（半字），total 在收尾时按子节点求和，
 * 这样百万级范围也只是一次线性扫描加一次树遍历。
 */
export function analyze({records=[], symbols=[], nameOf, resolve, maxIssues=MAX_ISSUES}={}){
  const resolveName=nameOf||resolve||symbolResolver(symbols);
  const nameOfAddr=addr=>{try{return resolveName(addr)||hex(addr);}catch{return hex(addr);}};
  const frames=[{id:0,name:'全部',addr:0,parent:-1,depth:0,self:0,total:0,calls:0,kind:'root'}];
  const stack=[0];
  const topFrames=new Map();   // 顶层函数名 → 帧号；入口函数被重复进入时复用同一个帧
  const order=[];
  const ranges=[];
  const sections=[];
  const issues=[];
  const packets=[];
  const stats={orphanReturns:0,entryReturns:0,nonExecuted:0,gaps:0,exceptions:0,calls:0,returns:0};
  let section=null, maxDepth=0, pendingCall=-1, truncated=false;
  const warn=(kind,offset,detail)=>{
    if(issues.length<maxIssues)issues.push({kind,offset,detail,index:issues.length});
    else truncated=true;
  };
  const openSection=(reason,gap=false)=>{
    // 还没有任何执行数据的空区段直接改写，避免在流开头留下一个空壳区段。
    if(section&&section.ranges===0&&section.exception===0){
      section.reason=reason;section.gap=gap;section.trusted=!gap;section.issues=0;
      return;
    }
    section={index:sections.length,reason,startOffset:null,endOffset:null,ranges:0,halfwords:0,
      exception:0,gap,issues:0,trusted:!gap};
    sections.push(section);
  };
  const touch=e=>{
    if(!section)openSection('start');
    const offset=e.offset??0;
    if(section.startOffset===null)section.startOffset=offset;
    section.endOffset=offset;
  };
  // calls 记「这个帧被调用了几次」：BL_LINK 建的帧是 1，trace 入口的顶层帧是 0。
  const pushFrame=(addr,parentId,kind,calls=1)=>{
    const frameId=frames.length;
    const parent=frames[parentId];
    frames.push({id:frameId,name:hex(addr),addr,parent:parentId,depth:parent.depth+1,self:0,total:0,calls,kind});
    if(parent.depth+1>maxDepth)maxDepth=parent.depth+1;
    return frameId;
  };

  for(const e of records){
    if(!e)continue;
    if(e.kind==='packet'){
      if(packets.length<60000)packets.push({offset:e.offset,size:e.size,hex:e.hex,text:e.text});
      continue;
    }
    if(e.kind!=='element')continue;
    if(e.type===ELEM.NO_SYNC){
      // payload 是 unsync_info_t：0 UNKNOWN / 1 INIT_DECODER / 2 RESET / 3 OVERFLOW /
      // 4 DISCARD / 5 BAD_PACKET / 6 BAD_IMAGE / 7 EOT。只有 3～6 是真的数据缺口。
      const unsync=e.payload|0, realGap=unsync>=3&&unsync<=6;
      openSection(realGap?'no-sync':'sync',realGap);
      if(realGap){
        stats.gaps++;section.issues++;
        warn('未同步',e.offset??0,(e.text||'').trim()||('UNSYNC 原因 '+unsync));
      }
      stack.length=1;pendingCall=-1;continue;
    }
    if(e.type===ELEM.TRACE_ON){openSection('trace-on');stack.length=1;pendingCall=-1;continue;}
    if(e.type===ELEM.EO_TRACE){if(section)section.endOffset=e.offset??section.endOffset;continue;}
    if(e.type===ELEM.ADDR_NACC||e.type===ELEM.ADDR_UNKNOWN){
      touch(e);if(section)section.issues++;
      warn(e.type===ELEM.ADDR_NACC?'地址不可访问':'地址未知',e.offset??0,
        (e.text||'').trim()||hex(e.start));
      continue;
    }
    if(e.type===ELEM.EXCEPTION_RET){if(stack.length>1)stack.pop();pendingCall=-1;continue;}
    if(e.type===ELEM.EXCEPTION){
      touch(e);stats.exceptions++;
      // 异常入口不占指令范围数，单独记在区段的 exception 上，免得和 ranges 口径对不上。
      if(section)section.exception++;
      // 异常目标本身就是被调用帧的入口：上一条 BL_LINK 帧在这里落地。
      if(pendingCall>=0){
        const pending=frames[pendingCall];
        pending.addr=e.start>>>0;pending.name=nameOfAddr(e.start);
        pendingCall=-1;
      }
      const frameId=pushFrame(e.start>>>0,stack[stack.length-1],'exception');
      frames[frameId].name='异常 '+hex(e.start);
      frames[frameId].self+=weightOf(e);
      stack.push(frameId);
      continue;
    }
    if(!isRange(e))continue;

    touch(e);
    const start=e.start>>>0;
    // 上一条范围是调用：此刻才知道被调函数的入口地址。
    if(pendingCall>=0){
      const frame=frames[pendingCall];
      frame.addr=start;frame.name=nameOfAddr(start);
      pendingCall=-1;
    }
    // 顶层函数：trace 开始时没有调用者，只能按地址归属。尾跳转（没有 BL_LINK 就换了函数）
    // 也在这里换帧，否则后面的执行会全部记到上一个函数头上。
    const topName=nameOfAddr(start);
    const unknownName=topName.startsWith('0x');
    if(stack.length===2&&!unknownName&&frames[stack[1]].name!==topName)stack.pop();
    if(stack.length===1){
      let frameId=topFrames.get(topName);
      if(frameId===undefined){
        frameId=pushFrame(start,0,'top',0);
        frames[frameId].name=topName;
        topFrames.set(topName,frameId);
      }
      stack.push(frameId);
    }
    const w=weightOf(e);
    const kind=branchKind(e);
    const node=frames[stack[stack.length-1]];
    node.self+=w;
    const index=ranges.length;
    ranges.push({index,offset:e.offset??0,start,end:e.end>>>0,weight:w,kind,
      executed:!!e.lastExecuted,conditional:!!e.lastConditional,branchType:e.lastType|0,
      branchSubtype:e.lastSubtype|0,isa:e.isa|0,cycleCount:e.cycleCount|0,timestamp:e.timestamp??0,
      text:e.text||'',depth:node.depth,frame:node.id});
    order.push(node.id);
    if(!e.lastExecuted)stats.nonExecuted++;
    if(section){section.ranges++;section.halfwords+=w;}

    if(kind==='call'){
      const frameId=pushFrame(e.end>>>0,node.id,'call');
      stack.push(frameId);
      pendingCall=frameId;
      stats.calls++;
    }else if(kind==='return'){
      if(stack.length>1){
        const callee=frames[stack[stack.length-1]];
        stack.pop();stats.returns++;
        // 入口函数返回给「trace 之外」的调用者，这是正常现象，不算问题，只做统计。
        if(callee.kind==='top')stats.entryReturns++;
      }else{stats.orphanReturns++;warn('孤立返回',e.offset??0,hex(start));}
    }
  }
  if(!sections.length)openSection('empty');
  // 可信区段：没有数据缺口、并且真的解出了执行数据。地址类问题按条数暴露在 issues 里，
  // 不直接否定整个区段——实板上 ADDR_UNKNOWN 在 trace 起点之后出现是常见现象。
  for(const part of sections)part.trusted=!part.gap&&part.ranges+part.exception>0;
  // 收尾：从后往前把「self + 子树 total」加到父节点，得到每帧的 total。
  for(let i=frames.length-1;i>0;i--){
    const frame=frames[i];
    if(frame.parent>=0)frames[frame.parent].total+=frame.self+frame.total;
  }
  // 没有后续范围的调用帧：保留地址命名的占位名，避免显示成 0x00000000。
  for(const frame of frames)if(frame.kind==='call'&&frame.addr===0)frame.name='未知调用';

  const halfwords=frames[0].self+frames[0].total;
  const functions=new Map();
  const rangesOfName=new Map();
  for(let i=0;i<order.length;i++){
    const frame=frames[order[i]];
    rangesOfName.set(frame.name,(rangesOfName.get(frame.name)||0)+1);
  }
  for(const frame of frames){
    if(frame.kind==='root')continue;
    let row=functions.get(frame.name);
    if(!row){
      row={name:frame.name,addr:frame.addr,ranges:0,self:0,total:0,calls:0,returns:0,
        maxDepth:frame.depth,instances:0,share:0,executed:rangesOfName.get(frame.name)||0};
      functions.set(frame.name,row);
    }
    if(!row.addr&&frame.addr)row.addr=frame.addr;
    row.self+=frame.self;row.total+=frame.self+frame.total;row.calls+=frame.calls;
    row.instances++;
    if(frame.depth>row.maxDepth)row.maxDepth=frame.depth;
  }
  for(const row of functions.values())row.share=halfwords?row.total/halfwords:0;

  const model={frames,order:Int32Array.from(order),ranges,sections,issues,packets,
    functions:[...functions.values()],
    totals:{ranges:ranges.length,packets:packets.length,halfwords,maxDepth,
      functions:functions.size,orphanReturns:stats.orphanReturns,entryReturns:stats.entryReturns,
      nonExecuted:stats.nonExecuted,gaps:stats.gaps,exceptions:stats.exceptions,
      calls:stats.calls,returns:stats.returns,issues:issues.length,issuesTruncated:truncated},
    stackAt(index){return stackFrames(this,index);}};
  model.tree=foldTree(model);      // 火焰图用的合并调用树，布局和导出共用同一棵
  return model;
}

/** 某个范围索引处的调用栈（根在前，最深帧在后）。 */
export function stackFrames(model,index){
  if(!model?.frames||!model.order||index<0||index>=model.order.length)return [];
  const chain=[];
  let id=model.order[index];
  while(id>0&&chain.length<4096){const frame=model.frames[id];chain.push(frame);id=frame.parent;}
  return chain.reverse();
}

/**
 * 把调用树按「同名兄弟合并」压成火焰图用的树。
 *
 * 一段 trace 里同一个函数会被调用几百次，逐个实例画出来只会得到几百个一像素的条。
 * 火焰图的标准做法是按调用路径聚合：每个节点代表一条「函数路径」，同名路径的 self 相加、
 * 子孙继续合并。这样宽度才等于这条路径实际执行的量。
 */
export function foldTree(model){
  const frames=model?.frames||[];
  if(!frames.length)return {name:'全部',kind:'root',self:0,total:0,children:[],instances:0};
  const root={name:'全部',kind:'root',self:frames[0].self,children:new Map(),instances:1};
  for(const frame of frames){
    if(frame.parent<0)continue;
    const parts=[];                       // 自底向上收集路径，再反过来
    for(let current=frame;current&&current.parent>=0;current=frames[current.parent])parts.push(current.name);
    parts.reverse();
    let node=root;
    for(const part of parts){
      let child=node.children.get(part);
      if(!child){child={name:part,kind:frame.kind,self:0,total:0,children:new Map(),instances:0};node.children.set(part,child);}
      node=child;
    }
    node.self+=frame.self;node.instances++;
  }
  // 自底向上定 total，并把子节点按权重降序排好（宽条在左）。
  const finish=node=>{
    const list=[];
    for(const child of node.children.values()){finish(child);list.push(child);}
    list.sort((a,b)=>(b.self+b.total)-(a.self+a.total)||a.name.localeCompare(b.name));
    node.children=list;
    node.total=list.reduce((sum,child)=>sum+child.self+child.total,0);
    return node.total;
  };
  finish(root);
  return root;
}

const foldedWeight=node=>node.self+node.total;

/** 火焰图布局：先序遍历合并后的调用树，按 self+子树 的宽度铺开。 */
export function flameLayout(model,{maxDepth=96,maxNodes=20000,minWidth=0}={}){
  const rows=[];
  const tree=model?.tree||foldTree(model);
  const total=tree?foldedWeight(tree):0;
  if(!tree||!total)return {rows,total:0,omitted:0,tree};
  let omitted=0;
  const walk=(node,depth,x)=>{
    if(depth>maxDepth||rows.length>=maxNodes){omitted++;return;}
    const width=foldedWeight(node)||1;
    if(minWidth&&width<minWidth&&depth>0){omitted++;return;}
    rows.push({depth,x,width,name:node.name,kind:node.kind,self:node.self,instances:node.instances});
    let cursor=x;
    for(const child of node.children){
      walk(child,depth+1,cursor);
      cursor+=foldedWeight(child);
    }
  };
  walk(tree,0,0);
  return {rows,total,omitted,tree};
}

const hue=name=>{let h=0;for(let i=0;i<name.length;i++)h=(h*33+name.charCodeAt(i))>>>0;return h%360;};
const xmlEscape=text=>String(text).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

/** 火焰图 SVG（无外部依赖，可直接另存为 .svg 打开）。 */
export function flameSvg(model,{width=1200,rowHeight=18,maxDepth=96,maxNodes=20000,minWidth=0}={}){
  const {rows,total,omitted}=flameLayout(model,{maxDepth,maxNodes,minWidth});
  if(!rows.length||!total)return '<svg xmlns="http://www.w3.org/2000/svg" width="'+width+'" height="40"><text x="8" y="24" fill="#eaf2ff">没有可绘制的调用树</text></svg>';
  const scale=total?width/total:0;
  const height=(rows.reduce((m,r)=>Math.max(m,r.depth),0)+1)*rowHeight+24;
  const parts=['<svg xmlns="http://www.w3.org/2000/svg" width="'+width+'" height="'+height+'" font-family="ui-monospace,Consolas,monospace" font-size="11">',
    '<rect width="100%" height="100%" fill="#0d1420"/>'];
  for(const row of rows){
    const x=row.x*scale,w=Math.max(row.width*scale,0.6),y=row.depth*rowHeight+4;
    const color=row.kind==='root'?'#1f3550':row.kind==='exception'?'#7a2b2b':'hsl('+hue(row.name)+' 58% 42%)';
    parts.push('<g><rect x="'+x.toFixed(2)+'" y="'+y+'" width="'+w.toFixed(2)+'" height="'+(rowHeight-2)+'" fill="'+color+'" rx="2"/>');
    if(w>46){
      const room=Math.max(1,Math.floor(w/6.4)-1);
      const label=row.name.length>room?row.name.slice(0,room)+'…':row.name;
      parts.push('<text x="'+(x+3).toFixed(2)+'" y="'+(y+12)+'" fill="#eaf2ff" pointer-events="none">'+xmlEscape(label)+'</text>');
    }
    parts.push('</g>');
  }
  if(omitted)parts.push('<text x="8" y="'+(height-6)+'" fill="#f0a">已裁剪 '+omitted+' 个节点（超过渲染上限）</text>');
  parts.push('</svg>');
  return parts.join('');
}

/** 调用统计表数据：按 total 降序。 */
export function callStats(model,{limit=0}={}){
  if(!model?.functions)return [];
  const rows=[...model.functions].sort((a,b)=>b.total-a.total||a.name.localeCompare(b.name));
  return limit>0?rows.slice(0,limit):rows;
}

/** 执行流 CSV：序号、偏移、起止、权重、分支性质、是否执行、深度、函数名。 */
export function executionCsv(model){
  const lines=new Array(model.ranges.length);
  for(let i=0;i<model.ranges.length;i++){
    const r=model.ranges[i],frame=model.frames[model.order[i]];
    lines[i]=[i,r.offset,'0x'+r.start.toString(16).padStart(8,'0'),'0x'+r.end.toString(16).padStart(8,'0'),
      r.weight,r.kind,r.executed?1:0,frame?frame.depth:0,'"'+(frame?frame.name:'').replaceAll('"','""')+'"'].join(',');
  }
  return 'index,offset,start,end,weight,branch,executed,depth,function\n'+lines.join('\n');
}

/** 源码执行流：按「文件:行」汇总命中的半字数。lines 是 LineTable。 */
export function sourceFlow(model,lines){
  if(!lines?.at)return [];
  const hits=new Map();
  for(const r of model.ranges){
    const line=lines.at(r.start);
    if(!line)continue;
    const file=line.file.replace(/\\/g,'/');
    const key=file+':'+line.line;
    const row=hits.get(key)||{file,line:line.line,weight:0,ranges:0};
    row.weight+=r.weight;row.ranges++;
    hits.set(key,row);
  }
  return [...hits.values()].sort((a,b)=>b.weight-a.weight||a.file.localeCompare(b.file)||a.line-b.line);
}

/** 分析模型的可序列化摘要（JSON 导出用，不含逐条范围明细）。 */
export function summaryJson(model,meta={}){
  return {...meta,generated:new Date().toISOString(),totals:model.totals,
    sections:model.sections.map(s=>({index:s.index,reason:s.reason,startOffset:s.startOffset,
      endOffset:s.endOffset,ranges:s.ranges,halfwords:s.halfwords,exception:s.exception,gap:s.gap,
      issues:s.issues,trusted:s.trusted})),
    issues:model.issues.slice(0,500),functions:callStats(model).slice(0,2000),
    packets:{count:model.packets.length,sample:model.packets.slice(0,200)}};
}

/** 包视图：按包说明文字的首词归类。 */
export function packetSummary(model){
  const groups=new Map();
  for(const packet of model.packets||[]){
    const label=(packet.text||'').trim().split(/\s+/)[0]||'未知包';
    const row=groups.get(label)||{label,count:0,bytes:0};
    row.count++;row.bytes+=packet.size||0;
    groups.set(label,row);
  }
  return [...groups.values()].sort((a,b)=>b.count-a.count);
}
