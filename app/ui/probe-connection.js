import { authorizedOpenOcdDevices, openOcdUsbSupported, rememberOpenOcdDevice, selectOpenOcdDevice } from '../core/openocd-usb.js';
import { nativeProbeEnabled } from '../core/native-probe.js';
import { runProbeOperation } from '../core/probe-manager.js';
import { withTimeout } from '../core/pace.js';
import { AkaLinkHid, authorizedHidDevices, PID, rememberHidDevice, selectHidDevice, USAGE_PAGE, VID } from '../hid/probe.js';
import { toast } from './toast.js';

export function initProbeConnection(tools){
  const $ = id => document.getElementById(id);
  const connect = $('btn-probe-connect');
  const disconnect = $('btn-probe-disconnect');
  const usbButton = $('btn-probe-usb');
  const hidButton = $('btn-probe-hid');
  const menu = $('probe-connect-menu');
  const status = $('probe-connect-status');
  const native = nativeProbeEnabled();
  const offline = document.body.dataset.nativeOffline === '1';
  let usb = null, hid = null, busy = false, message = '';
  const connection = tools.probeConnection = { usb:false, hid:false };
  const usbSupported = openOcdUsbSupported();
  const hidSupported = AkaLinkHid.supported();
  let authorizedUsb = [], authorizedHid = [], usbScan = 0, hidScan = 0;
  let checkingGrants = !native && !offline;
  const updateUsb = async () => {
    const scan = ++usbScan;
    const devices = await authorizedOpenOcdDevices().catch(() => []);
    if (scan === usbScan) authorizedUsb = devices.filter(d => d.vendorId === VID || /CMSIS-DAP/i.test(d.productName));
  };
  const updateHid = async () => {
    const scan = ++hidScan;
    const devices = await withTimeout(authorizedHidDevices(), 5000, '枚举已授权 HID').catch(() => []);
    if (scan === hidScan) authorizedHid = devices.filter(d => d.vendorId === VID && d.productId === PID &&
      d.collections?.some(c => c.usagePage === USAGE_PAGE));
  };
  const activeTab = () => document.querySelector('#tabs [aria-current="page"]')?.dataset.tab;
  const mock = tab => tab === 'dbg' && $('d-backend').value === 'mock' ||
    tab === 'rtt' && tools.rtt.backend === 'mock' || tab === 'rttcdc' && !!tools.hid.mock;
  const awaitingHid = () => !native && hidSupported && !!usb && !hid && authorizedHid.length !== 1;

  function render(){
    const { owners, pending, failures } = tools.probeManager.summary();
    const hasSession = owners.some(owner => owner !== 'serial') || pending.some(ticket => ticket.owner !== 'serial') ||
      failures.some(failure => failure.owner !== 'serial') || !!(tools.rtt.probe || tools.dbg.session?.connected ||
        tools.hid.dev.connected || tools.scope.hid || tools.scope.transport || tools.etm.probe);
    const usable = !offline && (usbSupported || hidSupported);
    const mockTab = mock(activeTab());
    connect.disabled = busy || !mockTab && (!usable || checkingGrants);
    disconnect.disabled = busy || !(hasSession || usb || hid);
    usbButton.disabled = busy || offline || !usbSupported;
    hidButton.disabled = busy || offline || !hidSupported;
    const usbLabel = usb && !native ? '更换 USB 探针' : '连接 USB';
    const hidLabel = hid && !native ? '更换 HID 探针' : '连接 HID';
    if (usbButton.textContent !== usbLabel) usbButton.textContent = usbLabel;
    if (hidButton.textContent !== hidLabel) hidButton.textContent = hidLabel;
    connection.usb = !!usb;
    connection.hid = !!hid;
    const state = `USB ${usb ? '就绪' : '未连接'} · HID ${hid ? '就绪' : '未连接'}`;
    const detail = offline ? '离线验收模式，硬件访问已禁用'
      : checkingGrants ? '正在读取浏览器已授权的探针…' : [message, state].filter(Boolean).join('\n');
    if (status.textContent !== detail) status.textContent = detail;
    const finishHid = awaitingHid() && !mock(activeTab());
    const label = finishHid ? '连接 HID' : '连接探针';
    if (connect.textContent !== label) connect.textContent = label;
    connect.title = `${finishHid ? '继续完成 HID 授权' : '准备 USB 和 HID，并连接当前工具'}。\n${state}`;
  }

  async function attach(tab, dap, control){
    switch(tab){
      case 'rtt':
        if (dap || mock(tab)){
          await tools.rtt.connectProbe(dap);
          return !!tools.rtt.probe;
        }
        break;
      case 'dbg':
        if (dap || mock(tab)){
          await tools.dbg.connect(dap);
          return tools.dbg.session.connected;
        }
        break;
      case 'etm':
        if (dap) return await tools.etm.connect(dap);
        break;
      case 'rttcdc':
        if (tools.hid.mock) await tools.hid.connect();
        else if (control && !tools.hid.dev.connected)
          await runProbeOperation(tools.hid, 'hid', () => tools.hid.connect(control),
            { reason:'连接 RTT 转发的 HID', recovery:true });
        if (control || tools.hid.mock) return tools.hid.dev.connected;
        break;
      case 'scope':
        if (tools.scope.usingMock || tools.scope.usesWasmPolling()) break;
        if (control && !tools.scope.hid?.connected) await tools.scope.connectHid(false, control);
        if (dap && tools.scope.hid?.connected && !tools.scope.transport) await tools.scope.connectUsb(false, dap);
        if (control || dap) return !!tools.scope.hid?.connected && (!dap || !!tools.scope.transport);
    }
  }

  async function prepare(kind){
    if (busy) return;
    const tab = activeTab();
    busy = true;
    message = native || mock(tab) ? '正在连接…' : '请按浏览器提示选择探针';
    render();
    try {
      if (kind === 'both' && mock(tab)){
        await attach(tab, null, null);
        return;
      }
      const all = kind === 'both';
      const wantUsb = kind === 'usb' || all && usbSupported;
      // Chrome device choosers can dismiss each other. The second chooser
      // needs its own click when neither permission has been granted.
      const chooseUsb = !native && wantUsb && (kind === 'usb' || authorizedUsb.length !== 1);
      const wantHid = kind === 'hid' || all && hidSupported && (!chooseUsb || authorizedHid.length === 1);
      const useUsb = () => !wantUsb ? null : native ? selectOpenOcdDevice()
        : kind !== 'usb' && authorizedUsb.length === 1 ? authorizedUsb[0]
        : selectOpenOcdDevice({ all:tab === 'rtt' && $('r-usb-all').checked, forcePick:true });
      const useHid = () => !wantHid ? null : native ? selectHidDevice()
        : kind !== 'hid' && authorizedHid.length === 1 ? authorizedHid[0]
        : selectHidDevice({ forcePick:true });
      // Browser enumeration can outlast transient user activation. Start the
      // chooser from the original click. Local RPCs share a control queue.
      const settle = async task => {
        try { return { value:await task() }; }
        catch (error) { return { error }; }
      };
      const [dap, control] = native
        ? [await settle(useUsb), await settle(useHid)]
        : await Promise.all([settle(useUsb), settle(useHid)]);
      const errors = [];
      if (dap.error) errors.push('USB：' + dap.error.message);
      if (control.error) errors.push('HID：' + control.error.message);

      let nextUsb = dap.value || usb;
      let nextHid = control.value || hid;
      if (nextUsb && nextHid && (nextUsb.vendorId !== nextHid.vendorId || nextUsb.productId !== nextHid.productId ||
          (nextUsb.serialNumber && nextHid.serialNumber && nextUsb.serialNumber !== nextHid.serialNumber))){
        errors.push('USB 和 HID 对应不同设备，请选择同一只探针');
        if (kind === 'hid') nextUsb = null;
        else nextHid = null;
      }
      if (usb && nextUsb !== usb || hid && nextHid !== hid)
        await tools.probeManager.releaseOthers(null, '更换探针', { preserve:['serial'] });
      usb = nextUsb;
      hid = nextHid;
      rememberOpenOcdDevice(usb);
      rememberHidDevice(hid);
      if (!native && usb){ usbScan++; authorizedUsb = [usb]; }
      if (!native && hid){ hidScan++; authorizedHid = [hid]; }
      if (!native && !usb) updateUsb();
      if (!native && !hid) updateHid();
      if (activeTab() === tab && await attach(tab, usb, hid) === false)
        errors.push('当前工具未接通，请查看工具状态');
      message = errors.join('；');
      if (!message && all && awaitingHid()) message = 'USB 已授权，请点顶栏「连接 HID」完成第二步';
      if (message) toast(message, 'warn', 6000);
      else toast('探针通路已就绪', 'ok');
    } catch (error){
      message = error.message;
      toast(message, 'err', 6000);
    } finally {
      busy = false;
      render();
    }
  }

  connect.onclick = () => prepare('both');
  usbButton.onclick = () => prepare('usb');
  hidButton.onclick = () => prepare('hid');
  disconnect.onclick = async () => {
    if (busy) return;
    busy = true;
    render();
    try {
      await tools.probeManager.releaseOthers(null, '从顶栏断开探针', { preserve:['serial'] });
      if (tools.rtt._probeMock && tools.rtt.probe) await tools.rtt.disconnect();
      if (tools.dbg.session?.backendName === '模拟目标' && tools.dbg.session.connected) await tools.dbg.disconnect();
      if (tools.hid.mock?.connected && await tools.hid.disconnect() === false)
        throw Error('模拟 HID 连接未关闭');
      usb = hid = null;
      rememberOpenOcdDevice(null);
      rememberHidDevice(null);
      message = '';
      toast('已断开探针连接', 'ok');
    } catch (error){
      message = error.message;
      toast('断开失败：' + message, 'err', 6000);
    } finally {
      busy = false;
      render();
    }
  };
  if (!native && !offline){
    Promise.all([updateUsb(), updateHid()]).finally(() => {
      checkingGrants = false;
      render();
    });
    navigator.usb?.addEventListener('connect', updateUsb);
    navigator.hid?.addEventListener('connect', updateHid);
    navigator.usb?.addEventListener('disconnect', ({device}) => {
      authorizedUsb = authorizedUsb.filter(d => d !== device);
      if (usb === device){ usb = null; rememberOpenOcdDevice(null); }
      updateUsb();
      render();
    });
    navigator.hid?.addEventListener('disconnect', ({device}) => {
      authorizedHid = authorizedHid.filter(d => d !== device);
      if (hid === device){ hid = null; rememberHidDevice(null); }
      updateHid();
      render();
    });
  }
  document.addEventListener('click', event => { if (!menu.parentElement.contains(event.target)) menu.open = false; });
  menu.addEventListener('keydown', event => {
    if (event.key === 'Escape'){ menu.open = false; menu.querySelector('summary').focus(); }
  });
  render();
  const timer = setInterval(render, 500);
  window.addEventListener('pagehide', () => clearInterval(timer), { once:true });
  return render;
}
