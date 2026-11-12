import { inspectOpenOcdCfg } from '../dbg/openocd-cfg.js';
import { upstreamFlashConfigs } from './openocd-cfgs/catalog.js';

export const hasUpstreamFlashCfg = family => Object.hasOwn(upstreamFlashConfigs, family);

const scripts = new Map();

async function loadScript(path){
  if (!scripts.has(path)){
    const response = await fetch(new URL(`./openocd-cfgs/${path}`, import.meta.url));
    if (!response.ok) throw Error(`无法加载 OpenOCD 脚本 ${path}（HTTP ${response.status}）`);
    scripts.set(path, await response.text());
  }
  return scripts.get(path);
}

export async function loadUpstreamFlashCfg(family, clockKhz){
  const paths = upstreamFlashConfigs[family];
  if (!paths) throw Error('没有可用的 OpenOCD 官方 Flash CFG');
  const [entry] = paths;
  const hpm = entry.startsWith('board/hpmicro/');
  const files = new Map(await Promise.all(paths.map(async path => [path, await loadScript(path)])));
  if (hpm){
    // The unchanged upstream board script includes its FTDI adapter. Bind
    // that include to the official CMSIS-DAP script for this probe.
    files.set('interface/hpmicro/hpmicro_evk.cfg', files.get('interface/cmsis-dap.cfg'));
  }
  const cfg = await inspectOpenOcdCfg(files.get(entry), entry, files, {
    transport:hpm ? 'jtag' : 'swd', clockKhz,
  });
  if (!cfg.hasFlash) throw Error('OpenOCD 官方 CFG 没有定义 Flash bank：' + entry);
  return cfg;
}
