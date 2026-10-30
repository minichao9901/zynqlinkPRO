import test from 'node:test';
import assert from 'node:assert/strict';
import {analyze,branchKind,callStats,executionCsv,flameLayout,flameSvg,packetSummary,sourceFlow,
  stackFrames,symbolResolver,summaryJson,BRANCH_LABEL,ELEM,INSTR,SUB} from '../app/etm/analysis.js';

// OpenCSD 元素的最小构造器：只填分析层真正读取的字段。
function element(type,{offset=0,start=0,end=0,lastType=INSTR.OTHER,lastSubtype=SUB.NONE,
  lastExecuted=1,lastConditional=0,payload=0,text=''}={}){
  return {kind:'element',type,offset,start,end,lastType,lastSubtype,lastExecuted,lastConditional,payload,text};
}
const range=(start,options={})=>element(ELEM.INSTR_RANGE,{start,end:start+2,...options});

const SYMBOLS=[{name:'main',addr:0x1001,size:0x20},{name:'helper',addr:0x2001,size:0x20}];

test('branchKind separates calls, returns, tail jumps and barriers',()=>{
  assert.equal(branchKind(range(0x1000,{lastType:INSTR.BR,lastSubtype:SUB.BR_LINK})),'call');
  assert.equal(branchKind(range(0x1000,{lastType:INSTR.BR_INDIRECT,lastSubtype:SUB.V7_IMPLIED_RET})),'return');
  assert.equal(branchKind(range(0x1000,{lastType:INSTR.BR_INDIRECT,lastSubtype:SUB.V8_RET})),'return');
  assert.equal(branchKind(range(0x1000,{lastType:INSTR.BR})),'jump');
  assert.equal(branchKind(range(0x1000,{lastType:INSTR.BR,lastConditional:1})),'cond');
  assert.equal(branchKind(range(0x1000,{lastType:INSTR.BR_INDIRECT})),'indirect');
  assert.equal(branchKind(range(0x1000,{lastType:INSTR.DSB_DMB})),'barrier');
  assert.equal(branchKind(range(0x1000)),'none');
  assert.equal(branchKind(element(ELEM.EXCEPTION)),'exception');
  for(const kind of Object.keys(BRANCH_LABEL))assert.equal(typeof BRANCH_LABEL[kind],'string');
});

test('symbolResolver maps Thumb addresses and falls back to hex',()=>{
  const resolve=symbolResolver(SYMBOLS);
  assert.equal(resolve(0x2000),'helper');
  assert.equal(resolve(0x2001),'helper');
  assert.equal(resolve(0x201f),'helper');
  assert.equal(resolve(0x3000),'0x00003000');
  assert.equal(symbolResolver([])(0x1234),'0x00001234');
});

test('analyze rebuilds the call tree from BL / BX LR pairs',()=>{
  const model=analyze({records:[
    element(ELEM.TRACE_ON,{offset:0}),
    range(0x1000,{offset:2,lastType:INSTR.BR,lastSubtype:SUB.BR_LINK}),   // bl helper
    range(0x2000,{offset:4}),                                            // helper 第一条
    range(0x2002,{offset:6,lastType:INSTR.BR_INDIRECT,lastSubtype:SUB.V7_IMPLIED_RET}), // bx lr
    range(0x1002,{offset:8}),                                            // main 续
    element(ELEM.EO_TRACE,{offset:10}),
  ],symbols:SYMBOLS});
  assert.equal(model.ranges.length,4);
  assert.equal(model.totals.halfwords,4);
  assert.equal(model.totals.calls,1);
  assert.equal(model.totals.returns,1);
  assert.equal(model.totals.maxDepth,2);
  assert.equal(model.totals.orphanReturns,0);
  assert.equal(model.totals.entryReturns,0);
  assert.deepEqual(model.frames.map(f=>f.name),['全部','main','helper']);
  assert.equal(model.frames[1].self,2);            // bl 与返回后的续跑都算 main 自身
  assert.equal(model.frames[2].self,2);            // helper 两条
  assert.equal(model.frames[1].total,2);           // main 只把 helper 的两条算进子树
  assert.deepEqual(stackFrames(model,0).map(f=>f.name),['main']);
  assert.deepEqual(stackFrames(model,2).map(f=>f.name),['main','helper']);
  const stats=callStats(model);
  assert.equal(stats[0].name,'main');
  assert.equal(stats[0].total,4);                  // 含 helper 的包含式权重
  assert.equal(stats[0].self,2);
  assert.equal(stats[0].share,1);                  // main 覆盖整段 trace
  assert.equal(stats[0].calls,0);                  // main 是 trace 入口，不是被调用进来的
  assert.equal(stats.find(r=>r.name==='helper').calls,1);
  assert.equal(stats.find(r=>r.name==='helper').total,2);
  assert.equal(model.sections.length,1);
  assert.equal(model.sections[0].reason,'trace-on');
  assert.equal(model.sections[0].ranges,4);
  assert.equal(model.sections[0].trusted,true);
  assert.equal(model.totals.issues,0);
});

test('unbalanced returns and resync boundaries become reported issues',()=>{
  const model=analyze({records:[
    element(ELEM.TRACE_ON,{offset:0}),
    range(0x1000,{offset:2,lastType:INSTR.BR_INDIRECT,lastSubtype:SUB.V7_IMPLIED_RET}), // 入口函数返回给 trace 之外
    element(ELEM.NO_SYNC,{offset:4,payload:4,text:'UNSYNC_OVERFLOW'}),
    element(ELEM.ADDR_UNKNOWN,{offset:6}),
    range(0x1000,{offset:8,lastExecuted:0}),
  ],symbols:SYMBOLS});
  assert.equal(model.totals.orphanReturns,0);
  assert.equal(model.totals.entryReturns,1);      // 入口函数直接返回，属于正常收尾
  assert.equal(model.totals.returns,1);
  assert.equal(model.totals.gaps,1);
  assert.equal(model.totals.nonExecuted,1);
  assert.equal(model.sections.length,2);
  assert.equal(model.sections[1].reason,'no-sync');
  assert.equal(model.sections[1].gap,true);
  assert.equal(model.sections[1].trusted,false);
  assert.deepEqual(model.issues.map(i=>i.kind),['未同步','地址未知']);
  assert.equal(model.ranges[0].executed,true);
  assert.equal(model.ranges[1].executed,false);
});

test('repeated calls fold into one flame-graph node per call path',()=>{
  const records=[element(ELEM.TRACE_ON,{offset:0})];
  for(let i=0;i<3;i++){
    records.push(range(0x1000,{offset:2+i*3,lastType:INSTR.BR,lastSubtype:SUB.BR_LINK}));
    records.push(range(0x2000,{offset:3+i*3}));
    records.push(range(0x2002,{offset:4+i*3,lastType:INSTR.BR_INDIRECT,lastSubtype:SUB.V7_IMPLIED_RET}));
  }
  const model=analyze({records,symbols:SYMBOLS});
  assert.equal(model.totals.calls,3);
  const tree=model.tree;
  assert.equal(tree.children.length,1);                 // 只有 main 一个入口
  assert.equal(tree.children[0].name,'main');
  assert.equal(tree.children[0].self,3);
  assert.equal(tree.children[0].children.length,1);     // 三次 helper 合成一个节点
  const helper=tree.children[0].children[0];
  assert.equal(helper.name,'helper');
  assert.equal(helper.instances,3);
  assert.equal(helper.self,6);
  assert.equal(helper.total,0);
  assert.equal(tree.total,tree.self+9);                 // 3 次 bl + 3×2 条 helper
  const {rows,total}=flameLayout(model);
  assert.equal(total,9);
  assert.equal(rows.length,3);                          // 全部 / main / helper
});

test('flame layout covers the whole tree and the SVG escapes source text',()=>{
  const model=analyze({records:[
    element(ELEM.TRACE_ON,{offset:0}),
    range(0x1000,{offset:2,lastType:INSTR.BR,lastSubtype:SUB.BR_LINK}),
    range(0x2000,{offset:4}),
    range(0x2002,{offset:6,lastType:INSTR.BR_INDIRECT,lastSubtype:SUB.V7_IMPLIED_RET}),
  ],symbols:[{name:'main',addr:0x1001,size:0x10},{name:'a<b>&c',addr:0x2001,size:0x10}]});
  const {rows,total,omitted}=flameLayout(model);
  assert.equal(total,3);
  assert.equal(omitted,0);
  assert.equal(rows.reduce((m,r)=>Math.max(m,r.depth),0),2);
  const svg=flameSvg(model,{width:800});
  assert.match(svg,/^<svg xmlns/);
  assert.match(svg,/a&lt;b&gt;&amp;c/);
  assert.equal(flameSvg(analyze({records:[]})).includes('没有可绘制的调用树'),true);
  const clipped=flameLayout(model,{maxNodes:1});
  assert.equal(clipped.rows.length,1);
  assert(clipped.omitted>0);
});

test('execution CSV, packet view and JSON summary stay exportable',()=>{
  const model=analyze({records:[
    element(ELEM.TRACE_ON,{offset:0}),
    range(0x1000,{offset:2,lastType:INSTR.BR,lastSubtype:SUB.BR_LINK}),
    range(0x2000,{offset:4}),
    {kind:'packet',offset:0,size:2,hex:'0000',text:'I-Sync 0x00000000'},
    {kind:'packet',offset:2,size:1,hex:'04',text:'Address 0x00001000'},
  ],symbols:SYMBOLS});
  const csv=executionCsv(model).split('\n');
  assert.equal(csv[0],'index,offset,start,end,weight,branch,executed,depth,function');
  assert.equal(csv.length,3);
  assert.match(csv[1], /^0,2,0x00001000,0x00001002,1,call,1,1,"main"$/);
  const packets=packetSummary(model);
  assert.deepEqual(packets.map(p=>[p.label,p.count]),[['I-Sync',1],['Address',1]]);
  const summary=summaryJson(model,{record:'demo'});
  assert.equal(summary.record,'demo');
  assert.equal(summary.totals.ranges,2);
  assert.equal(summary.packets.count,2);
  assert.deepEqual(summary.sections.map(s=>s.reason),['trace-on']);
});

test('source flow aggregates hit weights per file and line',()=>{
  const model=analyze({records:[element(ELEM.TRACE_ON,{offset:0}),range(0x1000),range(0x1002)],symbols:SYMBOLS});
  const lines={at:address=>address===0x1000?{file:'Src\\main.c',line:10}:{file:'Src/main.c',line:10}};
  const rows=sourceFlow(model,lines);
  assert.equal(rows.length,1);
  assert.equal(rows[0].file,'Src/main.c');
  assert.equal(rows[0].ranges,2);
  assert.equal(rows[0].weight,2);
  assert.deepEqual(sourceFlow(model,null),[]);
});

test('a million-range stream stays linear and is not materialised per frame',()=>{
  const records=[element(ELEM.TRACE_ON,{offset:0})];
  for(let i=0;i<200000;i++){
    records.push(range(0x1000,{offset:2+i}));
    records.push(range(0x2000,{offset:2+i,lastType:INSTR.BR,lastSubtype:SUB.BR_LINK}));
    records.push(range(0x3000,{offset:2+i,lastType:INSTR.BR_INDIRECT,lastSubtype:SUB.V7_IMPLIED_RET}));
  }
  const started=Date.now();
  const model=analyze({records,symbols:SYMBOLS});
  const elapsed=Date.now()-started;
  assert.equal(model.ranges.length,600000);
  assert.equal(model.totals.calls,200000);
  assert(elapsed<20000,`analysis took ${elapsed} ms`);
  assert.equal(model.order.length,600000);
});
