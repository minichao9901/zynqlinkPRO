import { ProbeManager } from './probe-manager.js';
import { CdcMode, isProbeCdcPort } from './cdc-mode.js';
import { setUsbResetGuard, usbResourceConflict } from './usb-device.js';

// One declaration owns resource policy, teardown, injection and USB reset identity.
// EVKLite: SPI2 PB10..15 and debug PA04..08 are independent. SPI auxiliary
// pads may use I2C PA28/29, so keep SPI/I2C pin exclusion until configuration-aware leases exist.
export const PROBE_FEATURES = Object.freeze([
  {
    id: 'flash', label: '烧录器', client: t => t.flash, usbKind: 'dap',
    resources: ['target-engine', 'debug-pins', 'rtt-ring', 'dap-bulk', 'cdc-mode'],
    active: t => !!(t.flash?.busy || t.flash?.probe),
    release: t => t.flash?._closeProbe(), guarded: t => !!t.flash?.busy,
  },
  {
    id: 'dbg', label: '调试器', client: t => t.dbg, usbKind: 'dap',
    resources: ['target-engine', 'debug-pins', 'dap-bulk'],
    active: t => !!t.dbg?.session?.connected && t.dbg?.session?.backendName !== '模拟目标',
    release: t => t.dbg.disconnect(),
  },

  {
    id: 'rtt', label: 'RTT Viewer', client: t => t.rtt, usbKind: 'dap',
    resources: ['target-engine', 'debug-pins', 'rtt-ring', 'dap-bulk'],
    active: t => !!(t.rtt?.probe || t.rtt?.bridge) && !t.rtt?._probeMock,
    release: async t => {
      const pending = t.rtt?._connectPromise;
      await t.rtt.disconnect();
      if (pending) await pending.catch(() => {});
    },
  },
  {
    id:'etm',label:'ETM 执行轨迹',client:t=>t.etm,usbKind:'dap',
    resources:['target-engine','debug-pins','dap-bulk','probe-clock'],
    active:t=>!!t.etm?.probe,release:t=>t.etm?.releaseProbe(),guarded:t=>!!t.etm?.busy,
  },
  {
    id: 'scope', label: 'J-Scope', client: t => t.scope, usbKind: 'scope',
    resources: ['target-engine', 'debug-pins', 'scope-stream'],
    active: t => !!(t.scope && !t.scope.usingMock &&
      (t.scope.running || t.scope.transport || (t.scope.hid && t.scope.hid !== t.scope.mockProbe))),
    release: (t, why) => t.scope.releaseProbe(why),
  },
  {
    id: 'hid', label: 'RTT 转发', client: t => t.hid,
    resources: ['target-engine', 'debug-pins', 'rtt-ring', 'cdc-mode'],
    active: t => !t.hid?.mock && !!(t.hid?.last?.running || t.hid?._bridgeRequested),
    release: async t => { await t.hid.stop({ fromManager: true }); await t.hid.dev?.close?.(); },
  },




  {
    id: 'serial', label: 'CDC 串口', client: t => t.session,
    resources: ['cdc-port'],
    active: t => !!t.session?.isOpen && isProbeCdcPort(t.session.port),
    release: t => t.session?.close(),
  },
]);

/** Construct without injecting, so standalone handoff adapters stay independent. */
export function createProbeManager(t, { bus = null, locks, features = PROBE_FEATURES } = {}){
  const manager = new ProbeManager({ locks, beforeAcquire: async reason => {
    if (bus?.supported) await bus.requestRelease({ why: reason });
  } });
  for (const feature of features){
    manager.register(feature.id, {
      resources: feature.resources, label: feature.label,
      active: () => feature.active(t), release: why => feature.release(t, why),
      protected: () => !!feature.guarded?.(t),
    });
  }
  manager.cdcMode = new CdcMode(t, manager);
  manager.assertUsbResetAllowed = (kind, device) => {
    const own = features.filter(f => f.usbKind === kind).map(f => f.id);
    const peers = [...manager.clients].filter(([id, c]) => !own.includes(id) &&
      (manager.leases.has(id) || c.active())).map(([id]) => id);
    let info = {};
    try { info = t.session?.port?.getInfo?.() || {}; } catch {}
    if (t.session?.isOpen && info.usbVendorId === device.vendorId && info.usbProductId === device.productId)
      peers.push('CDC 串口');
    if (peers.length) throw usbResourceConflict(`USB 整设备复位需要先断开 ${[...new Set(peers)].join('、')}`);
  };
  return manager;
}

/** Application wiring before any feature init()/automatic reconnect. */
export function installProbeManager(t, { features = PROBE_FEATURES, ...options } = {}){
  const manager = createProbeManager(t, { ...options, features });
  t.probeManager = manager;
  for (const feature of features){
    const client = feature.client(t);
    if (client) client.probeManager = manager;
    const view = feature.view ? feature.view(t) : client;
    if (view){
      view.probeManager = manager;
      view.bus = options.bus || null;
    }
  }
  setUsbResetGuard((kind, device) => manager.assertUsbResetAllowed(kind, device));
  return manager;
}

/** Compatibility for standalone clients; the application uses its persistent manager. */
export async function releaseLocalProbeUsers(keep, why = '另一个功能要使用探针'){
  const t = globalThis.__tools || globalThis.window?.__tools;
  if (!t) return;
  return await (t.probeManager || createProbeManager(t)).releaseOthers(keep, why);
}

/** Standalone views share one fallback handoff; managed views already acquired in run(). */
export async function prepareProbeHandoff(view, owner, why){
  if (view.probeManager) return;
  await releaseLocalProbeUsers(owner, why);
  if (view.bus?.supported) return await view.bus.requestRelease({ why });
}
