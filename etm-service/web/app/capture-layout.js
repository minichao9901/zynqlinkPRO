/** Presentation only: opening history never touches the target session. */
export function initCaptureLayout({body, button, storage, width, onOpen=()=>{}}){
  const key='etm.captureSettingsHidden';
  let preference=null;
  try { const value=storage?.getItem(key); if(value==='true'||value==='false')preference=value==='true'; } catch {}
  const refresh=()=>{
    const hidden=width()<=780?!body.classList.contains('settings-open'):body.classList.contains('side-hidden');
    button.textContent=hidden?'采集设置':'收起设置';
    button.setAttribute('aria-expanded',String(!hidden));
  };
  const setHidden=hidden=>{
    body.classList.toggle('side-hidden',hidden);
    body.classList.toggle('settings-open',!hidden);
    refresh();
  };
  button.onclick=()=>{
    const hidden=width()<=780?body.classList.contains('settings-open'):!body.classList.contains('side-hidden');
    preference=hidden;
    try { storage?.setItem(key,String(hidden)); } catch {}
    setHidden(hidden); if(!hidden)onOpen();
  };
  if(preference!==null)setHidden(preference);else refresh();
  return {refresh, show:()=>setHidden(false), historyOpened:()=>setHidden(preference??true)};
}
