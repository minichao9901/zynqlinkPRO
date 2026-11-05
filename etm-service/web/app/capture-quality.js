/** Decode success cannot erase a known acquisition failure. Missing flags stay unknown. */
export function captureTransportFailed(quality){
  return !!quality&&(quality.loss===true||quality.synced===false||quality.ended===false||quality.captureComplete===false||quality.requestedWindowComplete===false);
}
export function captureTransportText(quality){
  if(!quality)return '';
  const parts=[quality.loss===true?'有丢失':quality.loss===false?'无丢失':'丢失状态未知',
    quality.synced===true?'已同步':quality.synced===false?'未同步':'同步状态未知',
    quality.ended===true?'完整结束':quality.ended===false?'未完整结束':'结束状态未知'];
  if(quality.bufferFull){
    const capacity=Number(quality.bufferCapacityBytes);
    parts.push(Number.isFinite(capacity)&&capacity>0?`缓冲区已满（${capacity/1048576} MiB）`:'缓冲区已满');
  }else if(quality.completionReason==='time')parts.push('采集时间到');
  if(quality.flight){
    parts.push(quality.completionReason==='trigger'&&quality.captureComplete===true&&quality.requestedWindowComplete===true?'触发后窗口完成':'飞行记录提前停止');
    if(quality.historyOverwritten)parts.push(`旧历史已移除 ${quality.discardedHistoryBytes??quality.overwrittenBytes} 字节（覆盖/帧对齐）`);
    parts.push('保留段起点需重新同步；未知执行不算已还原');
  }
  return parts.join(' / ');
}
