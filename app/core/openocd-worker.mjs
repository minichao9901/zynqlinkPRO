import createOpenOcd from './openocd-runtime/openocd-core.mjs';

export function createOpenOcdDispatcher({ post, select, wasmBinary, onExit }){
  const memoryFile = '/workbench-memory.bin';
  let core, next, startup, pending, closing, streamLogs, importedDevice, lines = [];
  const reply = (request, body) => post({ id:request.id, ...body });
  function log(line){
    const request = startup || pending || closing;
    if (request && streamLogs) reply(request, { log:line });
    lines.push(line);
    if (lines.length > 64) lines.shift();
  }

  async function open(request){
    startup = request;
    streamLogs = request.streamLogs === true;
    const raw = request.raw;
    const files = raw ? raw.files : [['workbench.cfg', request.script]];
    // Loading Tcl must not open USB. A checked configuration is attached only
    // when the workbench explicitly issues init for the selected target.
    importedDevice = request.device;
    select(null);
    core = await createOpenOcd({
      wasmBinary,
      noInitialRun:true,
      print:log,
      printErr:log,
      isArmMemoryImage(){
        return pending?.type === 'memoryImage' && pending.physical === false;
      },
      nextCommand(){
        return new Promise(resolve => {
          next = resolve;
          if (startup){
            reply(startup, { lines });
            startup = null;
            lines = [];
          }
        });
      },
      commandResult(code, value){
        try {
          const bytes = !code && pending.type === 'memoryImage' && !pending.input
            ? core.FS.readFile(memoryFile) : undefined;
          reply(pending, { code, value, lines, bytes });
        } catch (error){ reply(pending, { error:error.message, lines }); }
        if (pending.type === 'memoryImage' && core.FS.analyzePath(memoryFile).exists)
          core.FS.unlink(memoryFile);
        pending = null;
        lines = [];
      },
    });
    const hpmSdk = raw?.hpmSdk;
    const directory = hpmSdk ? '/sdk/boards/openocd' : '/cfg';
    core.FS.mkdirTree(directory + '/interface');
    core.FS.writeFile(directory + '/interface/cmsis-dap.cfg', 'adapter driver cmsis-dap\n');
    for (const [name, text] of files){
      if (raw && (name.split('/').some(part => !part || part === '.' || part === '..') || /[\\:\u0000-\u001f]/.test(name)))
        throw Error('CFG 路径必须位于所选目录');
      const path = directory + '/' + name;
      core.FS.mkdirTree(path.slice(0, path.lastIndexOf('/')));
      core.FS.writeFile(path, text);
    }
    const args = ['openocd', '-s', directory, '-c', 'noinit; adapter driver cmsis-dap',
      '-c', 'gdb port disabled; tcl port disabled; telnet port disabled'];
    if (raw) args.push('-c', 'adapter speed 1000');
    const connection = raw?.connection;
    if (connection){
      if (!['swd','jtag'].includes(connection.transport) || !Number.isInteger(connection.clockKhz) ||
          connection.clockKhz < 1 || connection.clockKhz > 60000)
        throw Error('OpenOCD 连接参数无效');
      args.push('-c', `transport select ${connection.transport}`);
    }
    if (hpmSdk) args.push('-c', 'set HPM_SDK_BASE /sdk; set PROBE cmsis_dap');
    if (connection?.board !== undefined){
      if (!hpmSdk || !/^hpm[a-z0-9]+$/.test(connection.board)) throw Error('HPM SDK 板卡参数无效');
      args.push('-c', `set BOARD ${connection.board}`);
    }
    args.push('-f', directory + '/' + (raw?.entry ?? 'workbench.cfg'),
      '-c', 'noinit; gdb port disabled; tcl port disabled; telnet port disabled; cmsis-dap backend usb_bulk');
    if (hpmSdk) args.push('-c', 'reset_config none');
    if (connection) args.push('-c', `adapter speed ${connection.clockKhz}`);
    const argv = core._malloc((args.length + 1) * 4);
    const strings = args.map(arg => core.stringToNewUTF8(arg));
    for (const [i, ptr] of strings.entries()) core.setValue(argv + i * 4, ptr, 'i32');
    core.setValue(argv + args.length * 4, 0, 'i32');
    try {
      const code = await core.ccall('main', 'number', ['number', 'number'], [args.length, argv], { async:true });
      if (closing) reply(closing, code === 0 ? { lines } : { error:'OpenOCD 断开失败', lines });
      else throw new Error('OpenOCD 会话意外结束，状态 ' + code);
    } finally {
      for (const ptr of strings) core._free(ptr);
      core._free(argv);
    }
  }

  return request => {
    if (request.type === 'open'){
      open(request).catch(error => reply(startup || pending || closing || request, { error:error.message, lines })).finally(onExit);
    } else if (!next){
      reply(request, { error:'OpenOCD 会话未就绪' });
    } else if (request.type === 'flashFile'){
      try {
        if (request.input instanceof Uint8Array){
          core.FS.writeFile('/flash-input.bin', request.input);
          reply(request, {});
        } else if (request.read === true){
          const bytes = core.FS.readFile('/flash-readback.bin');
          core.FS.unlink('/flash-readback.bin');
          reply(request, { bytes });
        } else {
          core.FS.unlink('/flash-input.bin');
          reply(request, {});
        }
      } catch (error){ reply(request, { error:error.message }); }
    } else {
      let command = request.command;
      if (command === 'init' && importedDevice) select(importedDevice);
      if (request.type === 'memoryImage'){
        const { address, length, input } = request;
        if (!Number.isInteger(address) || address < 0 || address % 4 || !Number.isInteger(length) ||
            length < 4 || length % 4 || length > 0x40000 || address + length > 0x100000000 ||
            input != null && (!(input instanceof Uint8Array) || input.length !== length)){
          reply(request, { error:'OpenOCD 二进制内存范围无效' });
          return;
        }
        try { if (input) core.FS.writeFile(memoryFile, input); }
        catch (error){ reply(request, { error:error.message }); return; }
        const operation = input ? `load_image ${memoryFile} ${address} bin` : `dump_image ${memoryFile} ${address} ${length}`;
        // Image commands lack a phys flag. Switch translation for this one
        // command while keeping the selected memory access method intact.
        command = request.physical === false ? operation :
          'set workbench_mode [riscv virt2phys_mode]; riscv virt2phys_mode off; ' +
          `set workbench_rc [catch {${operation}} workbench_result]; ` +
          'riscv virt2phys_mode $workbench_mode; if {$workbench_rc} {error $workbench_result}; set workbench_result';
      }
      const resume = next;
      next = null;
      if (request.type === 'close'){
        closing = request;
        resume(null);
      } else {
        pending = request;
        resume(command);
      }
    }
  };
}

if (typeof WorkerGlobalScope !== 'undefined' && self instanceof WorkerGlobalScope){
  let selection;
  const pending = new Map();
  let serial = 0;
  function usbDevice(identity){
    const device = { ...identity, configuration:null };
    const call = (method, ...args) => new Promise((resolve, reject) => {
      const id = ++serial;
      pending.set(id, { resolve, reject });
      self.postMessage({ usbCall:{ id, method, args } });
    });
    for (const method of ['open','close','selectConfiguration','controlTransferIn',
      'claimInterface','releaseInterface','transferIn','transferOut']){
      device[method] = async (...args) => {
        const value = await call(method, ...args);
        if (value?.configurationValue) device.configuration = value;
        return value;
      };
    }
    return device;
  }
  Object.defineProperty(navigator, 'usb', { value:{
    async getDevices(){ return selection ? [selection] : []; },
  }});
  globalThis.WebSocket = class {
    constructor(){ throw Error('OpenOCD Worker 不提供 TCP 服务'); }
  };
  const dispatch = createOpenOcdDispatcher({
    post:message => self.postMessage(message),
    select:device => { selection = device ? usbDevice(device) : null; },
  });
  self.onmessage = ({ data }) => {
    const reply = data.usbReply;
    if (!reply){ dispatch(data); return; }
    const result = pending.get(reply.id);
    if (!result) return;
    pending.delete(reply.id);
    if (reply.error) result.reject(new DOMException(reply.error, 'NetworkError'));
    else result.resolve(reply.value);
  };
}
