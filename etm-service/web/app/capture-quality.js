/** Decode success cannot erase a known acquisition failure. Missing flags stay unknown. */
export function captureTransportFailed(quality){
  return !!quality&&(quality.loss===true||quality.synced===false||quality.ended===false);
}
export function captureTransportText(quality){
  if(!quality)return '';
  return [quality.loss===true?'有丢失':quality.loss===false?'无丢失':'丢失状态未知',
    quality.synced===true?'已同步':quality.synced===false?'未同步':'同步状态未知',
    quality.ended===true?'完整结束':quality.ended===false?'未完整结束':'结束状态未知'].join(' / ');
}
