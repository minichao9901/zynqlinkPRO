/** 导出错误留在页面；成功响应才交给浏览器保存，避免把错误 JSON 当下载。 */
export async function fetchExecutionExport(url,{fetchImpl=globalThis.fetch,timeout=45000}={}){
  const controller=new AbortController();let timer,response;
  // 45 秒约束服务端响应/生成，文件开始返回后的传输与浏览器普通下载一致。
  try{response=await Promise.race([
      fetchImpl(url,{signal:controller.signal}),
      new Promise((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(Error('导出等待超时；可先选择较小执行区间再导出'));},timeout);})
  ]);}finally{clearTimeout(timer);}
  if(!response.ok){
    let detail;try{detail=await response.json();}catch{}
    throw Error(detail?.error||'导出失败（HTTP '+response.status+'），请检查本地服务');
  }
  const type=response.headers.get('Content-Type')||'';
  if(type.includes('application/json')){
    const detail=await response.json();throw Error(detail.error||'服务未返回导出文件，请检查桥包版本');
  }
  const disposition=response.headers.get('Content-Disposition')||'';
  const encoded=disposition.match(/filename\*=UTF-8''([^;]+)/i),plain=disposition.match(/filename="([^"]+)"|filename=([^;]+)/i);
  let filename=plain?.[1]||plain?.[2]||'etm-export';
  if(encoded)try{filename=decodeURIComponent(encoded[1]);}catch{}
  return {blob:await response.blob(),filename};
}

export function saveExportFile({blob,filename},{retainUrl=false,captureOnly=false,windowImpl=globalThis}={}){
  // Embedded browsers may not support downloads initiated inside an iframe.
  // Use the same-origin workbench document for human downloads; the explicit
  // CLI path stays in the frame where its capture hook is installed.
  let owner=windowImpl;
  if(!captureOnly)try{if(windowImpl.parent?.document)owner=windowImpl.parent;}catch{}
  const a=owner.document.createElement('a');
  if(captureOnly&&!a.click._traceCliDownloadCapture)throw Error('CLI下载捕获未启用，请从统一工作台调用');
  const url=owner.URL.createObjectURL(blob);
  const activate=link=>{
    link.href=url;link.download=filename;
    if(captureOnly)link.dataset.cliDownloadOnly='1';
    owner.document.body.append(link);
    try{link.click();}finally{link.remove();}
  };
  let requested=false;
  try{
    activate(a);requested=true;
    return {downloadUrl:url,filename,bytes:blob.size,cliCaptured:a.dataset.cliCaptured==='1',browserDownloadRequested:!captureOnly,
      retryDownload:captureOnly?undefined:()=>activate(owner.document.createElement('a'))};
  }finally{
    if(!retainUrl||!requested)setTimeout(()=>owner.URL.revokeObjectURL(url),30000);
  }
}
