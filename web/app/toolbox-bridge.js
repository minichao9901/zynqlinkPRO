/**
 * toolbox 页面端桥：由 `web/tools/toolbox-service.mjs` 注入到工作台页面里。
 *
 * 它只做两件事：
 *   1. 长轮询本机 `/toolbox/next`，取一条请求；
 *   2. 把请求变成页面上的真实操作（DOM 控件或视图公开方法），把结果发回去。
 *
 * 这样 AI/CLI 不需要自己开浏览器、也不用猜控件：人（或脚本）把浏览器停在页面上，
 * 设备授权、WebUSB/串口句柄、会话都属于那个页面，请求只是借用它们。
 *
 * 安全边界：只有带服务注入的 `window.__toolboxToken` 才会启动；方法调用只允许视图对象上
 * 不以 `_` 开头的函数，不执行 eval、不接受任意对象路径。
 */
(() => {
  const token = window.__toolboxToken;
  if (!token) return;
  if (window.__toolboxBridge) return;
  window.__toolboxBridge = { ready: false, requests: 0, lastError: null };

  const FORBIDDEN = new Set(['constructor', 'init', 'onShow']);
  const MAX_TEXT = 20000;
  const MAX_UPLOAD = 24 * 1024 * 1024;

  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

  // ---- 导出接管 -------------------------------------------------------------
  // 页面导出走的是 Blob + <a download>。把两者记下来，CLI 就能取回字节并核对 SHA-256，
  // 而不是只看到浏览器把它存进了某个下载目录。
  const captured = new Map();
  let captureSeq = 0;
  try {
    const nativeCreate = URL.createObjectURL.bind(URL);
    URL.createObjectURL = value => {
      const url = nativeCreate(value);
      try {
        if (value instanceof Blob) {
          captured.set(url, {id: ++captureSeq, url, blob: value, name: 'export-' + captureSeq, size: value.size});
        }
      } catch {}
      return url;
    };
    const nativeClick = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = function () {
      try {
        if (this.download) {
          const entry = captured.get(this.href);
          if (entry) entry.name = this.download;
        }
      } catch {}
      return nativeClick.apply(this, arguments);
    };
  } catch {}
  const MAX_DOWNLOAD = 16 * 1024 * 1024;

  function viewFor(page) {
    const pages = window.__tools?.pages;
    return pages?.[page] || null;
  }

  function panelFor(page) {
    return document.getElementById('tab-' + page);
  }

  function usableSelector(element, page) {
    if (element.id) return '#' + element.id;
    const parts = [];
    let node = element;
    const root = panelFor(page);
    while (node && node !== root && node.nodeType === 1) {
      if (node.id) { parts.unshift('#' + node.id); break; }
      const parent = node.parentElement;
      if (!parent) break;
      const tag = node.tagName.toLowerCase();
      const siblings = [...parent.children].filter(child => child.tagName === node.tagName);
      parts.unshift(siblings.length > 1 ? `${tag}:nth-of-type(${siblings.indexOf(node) + 1})` : tag);
      node = parent;
    }
    const path = parts.join(' > ');
    return path.startsWith('#') ? path : `#tab-${page} > ${path}`;
  }

  function labelFor(element) {
    const label = element.closest('label');
    if (label) return (label.innerText || '').trim().slice(0, 80);
    const previous = element.previousElementSibling;
    if (previous && previous.tagName === 'LABEL') return (previous.innerText || '').trim().slice(0, 80);
    const aria = element.getAttribute('aria-label') || element.getAttribute('title');
    return aria ? String(aria).slice(0, 80) : '';
  }

  function describe(page) {
    const panel = panelFor(page);
    if (!panel) throw new Error('没有这个页面：' + page);
    const controls = [];
    for (const element of panel.querySelectorAll('input,select,textarea,button')) {
      if (element.type === 'hidden' || element.closest('[hidden]')) continue;
      const control = {
        selector: usableSelector(element, page),
        tag: element.tagName.toLowerCase(),
        type: element.type || '',
        disabled: !!element.disabled,
        label: labelFor(element),
      };
      if (element.tagName === 'SELECT') {
        control.value = element.value;
        control.options = [...element.options].map(option => ({value: option.value, text: option.textContent}));
      } else if (element.type === 'checkbox' || element.type === 'radio') {
        control.checked = !!element.checked;
      } else if (element.tagName === 'BUTTON') {
        control.text = (element.innerText || '').trim().slice(0, 40);
      } else {
        control.value = element.value;
      }
      controls.push(control);
    }
    const view = viewFor(page);
    // 页面外挂的 file input 也要能被 describe 找到，否则 CLI 只能靠猜。
    if (view) {
      for (const [name, value] of Object.entries(view)) {
        if (!name.startsWith('_')) continue;
        if (value instanceof HTMLInputElement && value.type === 'file')
          controls.push({selector: `@file:${page}.${name}`, tag: 'input', type: 'file',
            disabled: !!value.disabled, label: '页面外的文件入口'});
      }
    }
    const methods = new Set();
    if (view) {
      for (let object = view; object && object !== Object.prototype; object = Object.getPrototypeOf(object)) {
        for (const name of Object.getOwnPropertyNames(object)) {
          if (name === 'constructor' || name.startsWith('_') || FORBIDDEN.has(name)) continue;
          try { if (typeof view[name] === 'function') methods.add(name); } catch {}
        }
      }
    }
    return {
      page, hidden: !!panel.hidden, controls,
      methods: [...methods].sort(),
      targets: view ? ['view'] : [],
    };
  }

  function stateFor(page) {
    const panel = panelFor(page);
    if (!panel) throw new Error('没有这个页面：' + page);
    const errors = (window.__tools?.errors || []).slice(-20);
    return {
      page, hidden: !!panel.hidden,
      text: (panel.innerText || '').slice(0, MAX_TEXT),
      errors,
      summary: (() => { try { return window.__tools?.summary?.() || null; } catch (error) { return {error: String(error)}; } })(),
    };
  }

  function resolve(selector, page) {
    const found = document.querySelectorAll(selector);
    if (!found.length) throw new Error('找不到控件：' + selector);
    if (found.length > 1) throw new Error(`控件不唯一（${found.length} 个）：${selector}`);
    return found[0];
  }

  function readControl(selector) {
    const element = resolve(selector);
    return {
      selector,
      value: 'value' in element ? element.value : null,
      checked: 'checked' in element ? element.checked : null,
      text: (element.innerText || element.textContent || '').slice(0, MAX_TEXT),
      disabled: !!element.disabled,
    };
  }

  function setControl(selector, value) {
    const element = resolve(selector);
    if (element.type === 'checkbox' || element.type === 'radio') {
      element.checked = !!value;
    } else if (element.tagName === 'SELECT' || element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') {
      element.value = value === null || value === undefined ? '' : String(value);
    } else {
      throw new Error('这个控件不能赋值：' + selector);
    }
    element.dispatchEvent(new Event('input', {bubbles: true}));
    element.dispatchEvent(new Event('change', {bubbles: true}));
    return readControl(selector);
  }

  function clickControl(selector) {
    const element = resolve(selector);
    if (element.disabled) throw new Error('控件是禁用状态：' + selector);
    element.click();
    return {dispatched: true, completed: false};
  }

  function dispatchEvent(selector, type, data = {}) {
    const element = resolve(selector);
    const options = {bubbles: true, cancelable: true, composed: true, ...data};
    let event;
    if (type.startsWith('key')) event = new KeyboardEvent(type, options);
    else if (type.startsWith('mouse')) event = new MouseEvent(type, options);
    else if (type.startsWith('pointer')) event = new PointerEvent(type, options);
    else if (type === 'wheel') event = new WheelEvent(type, options);
    else if (type === 'input' || type === 'change') event = new Event(type, options);
    else event = new CustomEvent(type, options);
    element.dispatchEvent(event);
    return {dispatched: true};
  }

  // 有些页面把 file input 建在 body 上（比如烧录器的 _fileInput），它不在页面容器里，
  // 普通选择器找不到。用 `@file:<页面>.<属性>` 指过去，属性必须是页面对象上真实存在的
  // file input，不接受任意对象路径。
  function resolveFileInput(selector, page) {
    const match = /^@file:([a-z]+)\.(_[A-Za-z0-9_]+)$/.exec(selector);
    if (!match) throw new Error('虚拟文件选择器格式应为 @file:<页面>._属性：' + selector);
    const view = viewFor(match[1]);
    const element = view?.[match[2]];
    if (!(element instanceof HTMLInputElement) || element.type !== 'file')
      throw new Error('不是文件输入控件：' + selector);
    void page;
    return element;
  }

  function attachFiles(selector, files, page) {
    const element = selector.startsWith('@file:') ? resolveFileInput(selector, page) : resolve(selector);
    if (element.type !== 'file') throw new Error('不是文件控件：' + selector);
    const transfer = new DataTransfer();
    for (const file of files) {
      const bytes = Uint8Array.from(atob(file.base64), character => character.charCodeAt(0));
      if (bytes.length > MAX_UPLOAD) throw new Error('文件超过 24 MiB：' + file.name);
      transfer.items.add(new File([bytes], file.name, {type: file.type || 'application/octet-stream'}));
    }
    element.files = transfer.files;
    element.dispatchEvent(new Event('change', {bubbles: true}));
    return {count: files.length, names: files.map(file => file.name)};
  }

  function jsonSafe(value, depth = 0) {
    if (value === undefined) return null;
    if (value === null || typeof value === 'number' || typeof value === 'string' || typeof value === 'boolean') {
      return typeof value === 'string' ? value.slice(0, MAX_TEXT) : value;
    }
    if (depth > 4) return '[深层对象]';
    if (Array.isArray(value)) return value.slice(0, 200).map(item => jsonSafe(item, depth + 1));
    if (value instanceof Map) return [...value.entries()].slice(0, 200).map(([key, item]) => [jsonSafe(key, depth + 1), jsonSafe(item, depth + 1)]);
    if (typeof value === 'object') {
      const out = {};
      for (const [key, item] of Object.entries(value).slice(0, 100)) out[key] = jsonSafe(item, depth + 1);
      return out;
    }
    return String(value);
  }

  // 页面内轮询一个结果区域，避免 CLI 用「反复建 job」去刷（那会把队列灌满）。
  async function waitFor(selector, contains, timeoutMs) {
    const deadline = Date.now() + Math.min(Number(timeoutMs) || 60000, 300000);
    const needle = String(contains ?? '');
    for (;;) {
      const control = readControl(selector);
      const text = String((control.value ?? '') + ' ' + control.text);
      if (text.includes(needle)) return {matched: true, value: control};
      if (Date.now() > deadline) return {matched: false, timeout: true, last: control};
      await sleep(150);
    }
  }

  async function exportBlob(id, maxBytes) {
    const entry = [...captured.values()].find(item => item.id === Number(id));
    if (!entry) throw new Error('没有这个导出：' + id);
    const limit = Math.min(Number(maxBytes) || MAX_DOWNLOAD, MAX_DOWNLOAD);
    if (entry.size > limit) throw new Error(`导出 ${entry.size} 字节，超过单次上限 ${limit}`);
    const bytes = new Uint8Array(await entry.blob.arrayBuffer());
    let binary = '';
    for (let offset = 0; offset < bytes.length; offset += 0x8000)
      binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
    const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
      .map(value => value.toString(16).padStart(2, '0')).join('');
    return {id: entry.id, name: entry.name, size: bytes.length, sha256: digest, base64: btoa(binary)};
  }

  async function invoke(page, method, args = []) {
    const view = viewFor(page);
    if (!view) throw new Error('页面没有对应视图：' + page);
    if (typeof method !== 'string' || method.startsWith('_') || FORBIDDEN.has(method)) throw new Error('拒绝调用：' + method);
    const fn = view[method];
    if (typeof fn !== 'function') throw new Error(`页面 ${page} 没有方法 ${method}`);
    const value = await fn.apply(view, Array.isArray(args) ? args : [args]);
    return {returned: true, value: jsonSafe(value)};
  }

  async function run(request) {
    const {page, op, args = {}} = request;
    if (op === 'describe') return describe(page);
    if (op === 'state') return stateFor(page);
    if (op === 'reload') {
      // 改完前端代码后让页面重新加载；结果先回，再刷新。
      setTimeout(() => location.reload(), 300);
      return {reloading: true};
    }
    if (op === 'show') {
      const tab = document.querySelector(`[data-tab="${page}"]`);
      if (!tab) throw new Error('没有这个页面标签：' + page);
      tab.click();
      await sleep(120);
      return {page, shown: true};
    }
    if (op === 'read') return readControl(args.selector);
    if (op === 'set') return setControl(args.selector, args.value);
    if (op === 'click') return clickControl(args.selector);
    if (op === 'event') return dispatchEvent(args.selector, args.type, args.data || {});
    if (op === 'upload') return attachFiles(args.selector, args.files || [], page);
    if (op === 'invoke') return invoke(page, args.method, args.args || []);
    if (op === 'wait') return waitFor(args.selector, args.contains, args.timeoutMs);
    if (op === 'summary') return jsonSafe(window.__tools?.summary?.() || null);
    if (op === 'downloads') {
      return [...captured.values()].map(entry => ({id: entry.id, name: entry.name, size: entry.size}));
    }
    if (op === 'download') return exportBlob(args.id, args.maxBytes);
    throw new Error('未知操作：' + op);
  }

  async function post(path, body) {
    const response = await fetch(path, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'x-toolbox-token': token},
      body: JSON.stringify(body),
    });
    if (!response.ok) throw new Error('HTTP ' + response.status);
    return response.json();
  }

  async function loop() {
    await sleep(300);
    for (;;) {
      try {
        const response = await fetch('/toolbox/next?wait=25000', {headers: {'x-toolbox-token': token}});
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const body = await response.json();
        window.__toolboxBridge.ready = true;
        if (!body.request) { if (body.busy) await sleep(200); continue; }
        window.__toolboxBridge.requests++;
        let result;
        try {
          result = {ok: true, value: await run(body.request)};
        } catch (error) {
          result = {ok: false, error: String(error?.message || error)};
          window.__toolboxBridge.lastError = result.error;
        }
        await post('/toolbox/result', {id: body.request.id, ...result});
      } catch (error) {
        window.__toolboxBridge.lastError = String(error?.message || error);
        await sleep(1000);
      }
    }
  }

  loop();
})();
