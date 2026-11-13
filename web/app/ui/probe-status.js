import { PROBE_FEATURES } from '../core/probe-users.js';
import { setFlag } from './dom.js';
import { nativeProbeEnabled, nativeProbeStatus, nativeProbeCancel } from '../core/native-probe.js';

/** Only inspect local connection/lease state; never query hardware from the header. */
export function probeStatus(tools){
  const manager = tools.probeManager;
  const { pending = [], failures = [] } = manager?.summary() || {};
  const name = id => PROBE_FEATURES.find(f => f.id === id)?.label || id;
  const service=tools.nativeControl;
  if(service?.transport?.usbError)return {text:'探针：需重连',kind:'err',title:service.transport.usbError};
  const failed=Object.entries(service?.resources||{}).filter(([,v])=>v.error);
  if(failed.length)return {text:'探针：需恢复',kind:'err',title:failed.map(([k,v])=>`${k}：${v.error}`).join('\n')};
  if(service?.current || service?.pending?.length)return {text:'探针：操作中',kind:'warn',
    title:`当前：${service.current?.operation||'等待'}；排队：${service.pending.length}`};
  if (failures.length) return { text:'探针：需恢复', kind:'err', title:failures.map(f => `${name(f.owner)}：${f.error}`).join('\n') };
  if (pending.length) return { text:'探针：切换中', kind:'warn', title:pending.map(p => name(p.owner)).join('、') };
  const active = PROBE_FEATURES.filter(f => f.active(tools)).map(f => f.label);
  if(!active.length && Object.keys(service?.resources||{}).length)return {text:'探针：服务已占用',kind:'on',
    title:'当前资源：'+Object.keys(service.resources).join('、')+'；先断开原功能再交接'};
  if(active.length)
    return {text:`探针：${active.length === 1 ? active[0] : `${active.length} 项连接`}`, kind:'on', title:`当前连接：${active.join('、')}`};
  const { usb, hid } = tools.probeConnection || {};
  if(usb || hid)
    return {text:usb && hid ? 'USB + HID 就绪' : usb ? 'USB 就绪' : 'HID 就绪', kind:'on', title:'探针通路已准备，由工具按需打开'};
  return {text:'探针：未使用', kind:'off', title:'当前页面没有功能连接实体探针；串口连接状态单独显示。'};
}

export function initProbeStatus(tools){
  const summaryViews = [
    ['scope', () => `探针${tools.scope.hid?.connected||tools.scope.usingMock?'已连接':'未连接'} · 数据${tools.scope.transport||tools.scope.usingMock?'已连接':'未连接'}`],
    ['rttcdc', () => `转发${tools.hid.last?.running?'运行中':tools.probeManager?.failures.has('hid')?'状态未确认':'未启动'} · 接收口${tools.session.isOpen?'已打开':'未打开'}`],
  ].map(([name, read]) => {
    const side=document.querySelector(`#tab-${name} .side`);
    if(!side)return null;
    const el=document.createElement('div');el.className='connection-summary';el.setAttribute('role','status');
    side.prepend(el);return {el,read};
  }).filter(Boolean);
  const serial = document.getElementById('conn-flag');
  setFlag(serial, tools.session.isOpen ? '串口：已连接' : '串口：未连接', tools.session.isOpen ? 'on' : 'off');
  tools.session.on('open', ({ info, opts }) => {
    setFlag(serial, '串口：已连接', 'on'); serial.title = `${info} @${opts.baudRate}`;
  });
  tools.session.on('close', () => { setFlag(serial, '串口：未连接'); serial.title = ''; });
  const el = document.getElementById('probe-flag');
  let previous = '';
  const update = () => {
    for(const {el,read} of summaryViews){const text=read();if(el.textContent!==text)el.textContent=text;}
    const state = probeStatus(tools), key = JSON.stringify(state);
    if (key === previous) return;
    previous = key;
    el.textContent = state.text; el.title = state.title; el.className = `flag flag-${state.kind}`;
  };
  update();
  if(nativeProbeEnabled()){
    const cancel=document.createElement('button');cancel.textContent='取消当前操作';cancel.disabled=true;
    el.after(cancel);
    cancel.addEventListener('click',async()=>{
      const status=tools.nativeControl;
      const owner=status?.current?.owner||status?.resources?.capture?.restoreOwner;if(!owner)return;
      cancel.disabled=true;
      try{await nativeProbeCancel(owner);}
      catch(error){cancel.title=error.message;}
    });
    let reading=false;
    const refresh=async()=>{
      if(reading)return;reading=true;
      try{
        tools.nativeControl=await nativeProbeStatus();
        const capture=tools.nativeControl.resources?.capture;
        const capturing=capture?.restoreOwner&&!capture.restoring;
        cancel.disabled=!tools.nativeControl.current&&!capturing;
        cancel.textContent=capturing?'停止当前采集':'取消当前操作';update();
      }
      catch(error){cancel.title=error.message;}
      finally{reading=false;}
    };
    refresh();setInterval(refresh,2000);
  }
  // No DOM writes while unchanged, including during high-rate capture.
  setInterval(update, 1000);
}
