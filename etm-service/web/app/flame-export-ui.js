/** Visible outcome for both timeline and weighted flame exports. */
export function wireFlameExport(button,exporter,onError=()=>{}){
  const document=button.ownerDocument||globalThis.document,status=document.createElement('div');
  status.className='flame-export-status';status.hidden=true;
  status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  const original=button.textContent;
  button.onclick=async()=>{
    button.disabled=true;button.textContent='正在导出…';status.hidden=false;
    status.className='flame-export-status';status.textContent='正在生成 SVG…';
    try{
      const file=await exporter();
      if(!file?.downloadUrl||!file.filename)throw Error('服务未返回可下载的SVG文件');
      status.textContent=`已生成 ${file.filename}（${Number(file.bytes??file.blob?.size??0).toLocaleString('zh-CN')} B），`+
        (file.cliCaptured?'已交给 CLI 保存。':'已请求浏览器下载。');
      const link=document.createElement('a');link.href=file.downloadUrl;link.download=file.filename;
      if(file.retryDownload)link.onclick=event=>{event.preventDefault();file.retryDownload();};
      link.textContent='再次下载 SVG';status.append(link);
      return file;
    }catch(error){
      status.className='flame-export-status bad';status.textContent='导出失败：'+(error?.message||String(error));
      onError?.(error);
    }finally{button.disabled=false;button.textContent=original;}
  };
  return status;
}
