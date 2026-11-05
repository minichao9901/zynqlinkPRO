import {captureTransportText} from './capture-quality.js';
import {traceSettingsText} from './trace-options.js';
const valid=v=>typeof v==='number'&&Number.isFinite(v);
const n=v=>valid(v)?v.toLocaleString('zh-CN'):'未记录';
const ms=v=>valid(v)?`${(v*1000).toFixed(3)} ms`:'未记录';
const flag=v=>v===true?'是':v===false?'否':'未记录';
/** Report only recorded evidence, never substitute the currently connected target. */
export function recordReport(result){
  const q=result.quality||{},c=result.captureQuality,t=result.analysis?.timing,p=result.physical,groups=[];
  const add=(title,rows,note='')=>groups.push({title,rows,note});
  add('记录身份与配置',[
    ['协议',result.protocol||result.config?.protocol||'未记录'],['目标 ELF SHA-256',result.elf?.sha256||'未记录'],
    ['采集时镜像已核对',flag(result.targetVerified)],['ETM 选项快照',traceSettingsText(result.config||result.targetSnapshot?.config)],
    ['存储 / 引擎',result.traceStore?`TraceStore · ${result.traceStore.engine?.name||'未记录'}`:'旧记录 / 未记录'],
  ],'以下为这份记录的快照，不代表当前板卡状态。');
  const rows=[];
  if(c){
    rows.push(['采集通路',c.transport||'未记录'],['传输状态',captureTransportText(c)],['结束原因',({time:'时间到',trigger:'触发',cancelled:'取消',timeout:'等待超时',capacity:'容量到限'})[c.completionReason]||c.completionReason||'未记录'],['请求窗口完整',flag(c.requestedWindowComplete)],['采集完成',flag(c.captureComplete)]);
    const duration=c.totalHardwareSeconds??c.hardwareSeconds;
    rows.push([c.flight?'硬件等待与后窗总时长':'硬件采集时长',ms(duration)],['硬件参考计时',`${n(c.totalHardwareTicks??c.hardwareTicks)} 拍 · ${n(c.refClockHz)} Hz`]);
    if(!c.flight)rows.push(['请求时长',ms(result.captureExtent?.requestedSeconds??(valid(c.requestedTicks)&&c.refClockHz>0?c.requestedTicks/c.refClockHz:undefined))]);
    if(c.flight){
      const f=c.flight,tr=c.flightTrigger||{};
      rows.push(['触发来源',({manual:'手动',fault:'Fault 主机轮询',after:'延时'})[tr.source]||tr.source||'未记录'],['触发位置（参考拍）',n(f.triggerTicks)],['请求触发后窗口',ms(valid(f.postTicks)&&c.refClockHz>0?f.postTicks/c.refClockHz:undefined)],['环容量',`${n(c.bufferCapacityBytes??f.capacityBytes)} B`],['累计采集 / 最终保留',`${n(f.totalBytes)} / ${n(c.retainedHistoryBytes??f.retainedBytes)} B`],['物理覆盖旧历史',`${n(c.overwrittenBytes)} B`],['帧对齐移除',`${n(c.alignmentDiscardedBytes)} B`],['旧历史合计移除',`${n(c.discardedHistoryBytes)} B`],['保留起点执行未知',flag(c.initialExecutionUnknown)]);
      if(tr.source==='fault')rows.push(['Fault 轮询请求间隔',ms(tr.requestedPollSeconds)],['触发时 ICSR',valid(tr.observedValue)?'0x'+tr.observedValue.toString(16):'未记录']);
    }
    if(valid(c.fclk))rows.push(['探针 FCLK（寄存器推算）',`${(c.fclk/1e6).toFixed(3)} MHz`]);
    if(valid(c.tckKhz))rows.push(['调试时钟（记录值）',`${(c.tckKhz/1000).toFixed(3)} MHz`]);
    if(c.diagnostics)rows.push(['帧丢失 / 解析错误 / 写入错误',`${n(c.diagnostics.frameDrops)} / ${n(c.diagnostics.parserErrors)} / ${n(c.diagnostics.writerError)}`]);
  }else rows.push(['硬件采集状态','未记录，不能由解码成功推断']);
  const clocks=result.targetSnapshot?.clocks;
  if(clocks)rows.push(['目标 CPU / TRACECLK（快照推算）',`${valid(clocks.coreHz)?(clocks.coreHz/1e6).toFixed(3):'未知'} / ${valid(clocks.physicalTraceHz)?(clocks.physicalTraceHz/1e6).toFixed(3):'未知'} MHz`]);
  add('采集窗口与传输',rows,c?.flight?'环容量限定保留字节数，不能据此保证触发前时长。历史覆盖与真实丢帧分开核算；Fault 主机轮询可能漏过短暂异常。':'硬件时长不包括配置、下载、解码或首屏。');
  add('解码完整性',[
    ['ETM 原始输入 / 已处理',`${n(q.inputBytes??q.processedBytes)} / ${n(q.processedBytes)} B`],['未处理输入',`${n(q.unprocessedBytes)} B`],
    ['包记录覆盖 / 重叠 / 遗漏',`${n(q.accountedBytes)} / ${n(q.overlapBytes)} / ${n(q.unaccountedBytes)} B`],['已识别包',n(q.validPackets)],
    ['未同步 ETM 数据',`${n(q.unsynchronizedBytes)} B / ${n(q.unsynchronizedRecords)} 条`],['TPIU 同步前 / 未知源 ID',`${n(q.initialPhysicalBytes)} / ${n(q.unknownSourceBytes)} B`],
    ['尾部不完整帧 / 同步标记残片',`${n(q.trailingFrameBytes)} / ${n(q.trailingSyncBytes)} B`],['执行状态未知',`${n(q.unknownExecution)} 条指令记录`],
    ['溢出 / 包问题',`${n(q.overflowPackets)} / ${n(q.packetIssues)}`],['解码器最后错误',result.status?.lastErrorCode??'未记录'],['首个恢复区间 ETM 偏移',q.firstPathOffset??'未记录'],
  ],[result.recordError?`记录错误：${result.recordError}`:'',q.basis||'','未同步、采集前调用栈与缺口保留为未知；包问题为 0 不等于完整执行流。'].filter(Boolean).join(' '));
  add('执行周期与耗时口径',[
    ['周期计数元素',n(q.timing?.cycleElements)],['有效周期总数',t?.timeFlameAvailable?n(t.totalCycles):'不可用'],
    ['CPI',t?.timeFlameAvailable&&valid(t.cpi)?t.cpi.toFixed(3):'不可用'],
    ['周期折算覆盖时长',t?.timeFlameAvailable&&valid(t.totalCycles)&&t.coreHz>0?ms(t.totalCycles/t.coreHz):'不可用'],
  ],'无周期数据时，执行流和火焰图按序号/记录数展示，不能当作耗时轴；F103 ETMv3 本项目路径不提供周期计数。');
  const perf=result.performance,pr=[];
  if(c){pr.push(['USB 下载',ms(c.usbSeconds)],['USB 有效负载速率',valid(c.usbPayloadMBps)?`${c.usbPayloadMBps.toFixed(3)} MB/s`:'未记录']);}
  if(perf){
    pr.push(['离线解码任务总耗时',ms(perf.jobSeconds)],['解码流水线',ms(perf.decodeSeconds)]);
    const labels={metadataPreparation:'元数据准备',decode:'任务解码阶段',captureStartAndMetadata:'起点分析与元数据',browsePreparation:'浏览数据准备'};
    for(const [k,v]of Object.entries(perf.jobPhasesSeconds||{}))pr.push([labels[k]||k,ms(v)]);
    const storeLabels={inputPreparation:'输入准备',nativeClosedBuild:'原生建库',verifyNativeStore:'校验存储',inputBindings:'输入身份绑定',publish:'发布',cleanup:'清理'};
    for(const [k,v]of Object.entries(perf.storePhasesSeconds||{}))pr.push(['建库细分 · '+(storeLabels[k]||k),ms(v)]);
  }else pr.push(['离线性能 Profile','本记录未保存']);
  add('处理性能 Profile',pr,'各阶段可能包含子阶段，不相加当作总耗时。离线解码不包括采集、上传和浏览器首屏；USB 下载速率不是 SRAM 读写速率。');
  if(p){
    const depth=p.sample_depth,rate=p.sample_rate,span=p.window_seconds;
    const seconds=depth>0&&rate>0?depth/rate:Array.isArray(span)&&span.length===2?span[1]-span[0]:undefined;
    add('旧 LA 波形记录',[
      ['波形窗口',ms(seconds)],['物理时钟段',n(p.clock_runs?.length)],['长时钟间隔',n(p.clock_gaps?.length)],['最小数据跳变距离',valid(p.min_data_transition_distance_ns)?`${p.min_data_transition_distance_ns.toFixed(3)} ns`:'未记录'],
    ],'仅对含物理波形的旧记录展示；Zynq DDR 直接 Trace 数据不提供逐线波形校准结果。');
  }
  if(result.laFilter?.channels){const active=result.laFilter.channels.filter(x=>x.enabled);add('历史滤波快照',[['LA 毛刺滤波',active.length?active.map(x=>`CH${x.channel} ≤${x.samples} 点`).join('；'):'全部关闭']]);}
  if(result.samplingValidation){const s=result.samplingValidation;add('历史采样相位检查',[['位置 / 数据流',`${n(s.phases?.length)} / ${n(s.distinctStreams)}`],['稳定窗',Array.isArray(s.stableWindow)?s.stableWindow.join('–'):'未记录'],['稳定窗宽度',valid(s.stableWindowNs)?`${s.stableWindowNs.toFixed(2)} ns`:'未记录'],['余量不足',flag(s.sensitive)]]);}
  if(result.spiValidation){const s=result.spiValidation;add('历史 SPI 对照',[['直接分支落点核对',n(s.branchTransitionsChecked)],['完整调用 / 每次字节',`${n(s.closedSpiCalls)} / ${n(s.bytesPerClosedTransfer)}`]]);}
  return groups;
}
