import { OpenOcdTargetSession } from '../core/openocd-session.js';

export function cfgPath(path){
  if (/[\u0000-\u001f\\:\[\]{}$;'"<>|?*]/.test(path) || path.split('/').some(part => !part || part === '..'))
    throw new Error(`CFG 路径必须位于所选脚本目录内（${path}）`);
  const normalized = path.split('/').filter(part => part !== '.').join('/');
  if (!normalized) throw new Error('CFG 路径缺少文件名');
  return normalized;
}

export async function readCfgDirectory(files){
  const scripts = new Map();
  let root, bytes = 0;
  for (const file of files){
    if (!/\.(?:cfg|tcl)$/i.test(file.name)) continue;
    const relative = file.webkitRelativePath;
    const split = relative?.indexOf('/') ?? -1;
    if (split <= 0) throw new Error('请选择包含 CFG 的目录');
    root ??= relative.slice(0, split);
    if (relative.slice(0, split) !== root) throw new Error('CFG 文件必须来自同一目录');
    const path = cfgPath(relative.slice(split + 1));
    if (scripts.has(path)) throw new Error(`CFG 路径重复（${path}）`);
    scripts.set(path, file);
    bytes += file.size;
    if (scripts.size > 4096 || bytes > 8 * 1024 * 1024)
      throw new Error('CFG 目录最多支持 4096 个脚本和 8 MiB 文件内容');
  }
  if (![...scripts.keys()].some(path => /\.cfg$/i.test(path))) throw new Error('所选目录没有入口 CFG');
  return new Map(await Promise.all([...scripts].map(async ([path, file]) => [path, await file.text()])));
}


const targetName = /^[A-Za-z0-9_.-]{1,100}$/;

/** Ask OpenOCD to interpret the uploaded files with USB disconnected. */
export async function inspectOpenOcdCfg(text, entry, directory, connection){
  entry = cfgPath(entry);
  const scripts = directory || new Map([[entry,text]]);
  if (!scripts.has(entry)) throw Error('CFG 目录缺少入口：' + entry);
  const files = [...scripts].map(([path, body]) => [cfgPath(path),body.replace(/^\uFEFF/, '')])
    .sort(([a], [b]) => a < b ? -1 : Number(a > b));
  if (files.length > 4096 || new TextEncoder().encode(files.map(([, body]) => body).join('')).length > 8 * 1024 * 1024)
    throw Error('CFG 内容超过限制');
  const hpmSdk = /^hpm\w+_all_in_one\.cfg$/i.test(entry) && scripts.has('probes/cmsis_dap.cfg');
  const raw = { entry, files, hpmSdk, ...(connection && {connection}) };
  const session = new OpenOcdTargetSession();
  try {
    await session.open({raw});
    if (await session.command('command mode') !== 'config')
      throw Error('CFG 在加载时调用了 init；请在工作台连接目标时初始化');
    if (await session.command('capture {adapter name}') !== 'cmsis-dap')
      throw Error('工作台仅支持 CMSIS-DAP / WebUSB 适配器');
    const transport = await session.command('transport select');
    const names = (await session.command('target names')).split(/\s+/).filter(Boolean);
    if (!names.length || names.length > 64 || names.some(name => !targetName.test(name)))
      throw Error('CFG 未定义可选的 OpenOCD 核');
    const cores = [];
    for (const target of names){
      const type = await session.command(`capture {${target} cget -type}`);
      if (['swd','jtag'].includes(transport) && type === 'cortex_m') cores.push({target,arch:'arm'});
      if (transport === 'jtag' && type === 'riscv') cores.push({target,arch:'riscv'});
    }
    if (!cores.length) throw Error('CFG 没有 Cortex-M / SWD、Cortex-M / JTAG 或 RISC-V / JTAG 核');
    const clock = await session.command('capture {adapter speed}');
    const clockKhz = Number(clock.match(/(\d+)\s*kHz/i)?.[1]);
    const maxClock = hpmSdk || cores.some(core => /^hpm\d+[.]cpu/i.test(core.target)) ? 25000 : 60000;
    if (!(clockKhz >= 1 && clockKhz <= maxClock)) throw Error(`CFG 时钟须在 1–${maxClock} kHz`);
    const bankText = await session.command('capture {flash banks}');
    const banks = [...bankText.matchAll(/^#\d+\s*:\s*[^\n]+?\(([^)]+)\)\s+at\s+(0x[\da-f]+),/gim)];
    const [, driver, address] = banks[0] ?? [];
    // The STM32 drivers infer the main bank location when probing. For BIN
    // display use its conventional address, and validate it live at write time.
    const flashBase = Number(address) === 0 && driver.startsWith('stm32') ? '0x08000000' : address;
    const digest = new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(raw))));
    const hash = Array.from(digest,b=>b.toString(16).padStart(2,'0')).join('');
    return { raw, hash, name:entry, transport, clockKhz, cores,
      hasFlash:!!banks.length, flashBase, hpmFlash:banks.some(([, name]) => name === 'hpm_xpi'), ...cores[0] };
  } finally { await session.close(); }
}
