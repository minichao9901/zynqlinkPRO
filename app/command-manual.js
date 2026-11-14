const endpoint = '/command-manual';
const token = new URLSearchParams(location.search).get('trace-cli');
const root = document.getElementById('manual-document');
const references = {
  'dependencies.md': 'docs/dependencies.md',
  '../README.md#硬件与接线': 'README.md#硬件与接线',
  'toolbox-cli-ai.md': 'docs/toolbox-cli-ai.md',
  '../prebuilt/qspi-release/README.md': 'prebuilt/qspi-release/README.md',
};
let loading = false;
let loaded = false;
let running = false;
let firmware = '';
let firmwareInput;

function element(tag, text, className){
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function appendInline(parent, text){
  const pattern = /`([^`]+)`|\*\*([^*]+)\*\*|\[([^\]]+)\]\(([^)]+)\)/g;
  let offset = 0;
  for (const match of text.matchAll(pattern)){
    parent.append(text.slice(offset, match.index));
    if (match[1]) parent.append(element('code', match[1]));
    else if (match[2]) parent.append(element('strong', match[2]));
    else if (Object.hasOwn(references, match[4])){
      const link = element('a', match[3]);
      link.href = 'https://github.com/minichao9901/zynqlinkPRO/blob/main/' + references[match[4]];
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      parent.append(link);
    } else parent.append(match[3]);
    offset = match.index + match[0].length;
  }
  parent.append(text.slice(offset));
}

function appendProse(text){
  for (const paragraph of text.split(/\n\s*\n/)){
    if (!paragraph) continue;
    const heading = paragraph.match(/^(#{1,2})\s+(.+)$/);
    const instruction = /^\d+\.\s+/.test(paragraph);
    const node = element(heading ? (heading[1].length === 1 ? 'h2' : 'h3') : 'p', '',
      instruction ? 'manual-instruction' : '');
    appendInline(node, heading ? heading[2] : paragraph);
    root.append(node);
  }
}

async function request(path = '', body){
  const headers = { 'X-Trace-CLI': token };
  const options = { headers, cache:'no-store' };
  if (body){
    headers['Content-Type'] = 'application/json';
    options.method = 'POST';
    options.body = JSON.stringify(body);
  }
  const response = await fetch(endpoint + path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw Error(payload.error || `本机工作台返回 HTTP ${response.status}`);
  return payload;
}

function buttonsBusy(busy){
  for (const button of root.querySelectorAll('[data-command]'))
    button.disabled = busy || button.dataset.offline === 'true';
}

function appendCommand(row){
  const box = element('div', '', 'manual-step');
  const action = element('div', '', 'manual-action');
  const line = element('pre');
  line.append(element('code', row.line));
  const button = element('button', '执行', 'primary');
  button.type = 'button';
  button.dataset.command = row.id;
  button.dataset.offline = String(row.disabled);
  button.disabled = row.disabled;
  button.setAttribute('aria-label', '执行 ' + row.line);
  action.append(line, button);
  box.append(action);
  let input;
  if (row.id === 'firmware' || row.field === 'job'){
    const label = element('label', row.field === 'firmware' ? '固件绝对路径' : 'CLI job ID', 'manual-input');
    input = element('input');
    input.type = 'text';
    input.spellcheck = false;
    input.autocomplete = 'off';
    input.maxLength = 4096;
    if (row.id === 'firmware') firmwareInput = input;
    label.append(input);
    box.append(label);
    input.addEventListener('keydown', event => { if (event.key === 'Enter') button.click(); });
  }
  const status = element('div', row.disabled ? '离线模式已禁用硬件操作' : '', 'manual-status');
  status.setAttribute('role', 'status');
  const output = element('pre', '', 'manual-output');
  output.hidden = true;
  const log = element('div', '', 'manual-log');
  box.append(status, output, log);
  root.append(box);
  button.addEventListener('click', async () => {
    if (running) return;
    const value = input ? input.value.trim() : row.field === 'firmware' ? firmware : '';
    if (row.field && !value){
      status.textContent = row.field === 'firmware' ? '请先填写并确认 ELF 路径。' : '请输入 CLI job ID。';
      (input || firmwareInput)?.focus();
      return;
    }
    if (row.confirmation && !window.confirm(row.confirmation + (value ? '\n\n固件 ' + value : ''))) return;
    running = true;
    buttonsBusy(true);
    status.dataset.result = 'running';
    status.textContent = '正在运行…';
    output.hidden = false;
    output.textContent = '';
    log.textContent = '';
    let job;
    try {
      ({ job } = await request('/run', { id:row.id, value, confirmed:!!row.confirmation }));
      for (;;){
        const result = await request('/job/' + job);
        output.textContent = (result.truncated ? '…这里只显示末尾输出。\n' : '') + result.output;
        if (result.exitCode !== null){
          if (row.id === 'firmware' && result.exitCode === 0) firmware = value;
          status.dataset.result = result.exitCode === 0 ? 'ok' : 'error';
          status.textContent = (result.exitCode === 0 ? '完成' : '失败') + ` · 退出码 ${result.exitCode}`;
          log.textContent = '完整日志 ' + result.log;
          break;
        }
        await new Promise(resolve => setTimeout(resolve, 350));
      }
    } catch (error){
      status.dataset.result = 'error';
      status.textContent = error.message + (job ? '。命令可能仍在运行，请查本机日志。' : '');
    } finally {
      running = false;
      buttonsBusy(false);
    }
  });
}

export async function showManual(){
  if (loading || loaded) return;
  if (!token){
    root.textContent = '请从本机启动器打开带鉴权的工作台页面。';
    return;
  }
  loading = true;
  root.textContent = '正在读取手册…';
  try {
    const { rows } = await request();
    root.replaceChildren();
    root.append(element('p', '从上往下执行。接线、拨码和断电重上电请按说明操作。工作台会复用当前会话，并为每次操作保留日志。', 'manual-intro'));
    for (const row of rows){
      if (row.line) appendCommand(row);
      else appendProse(row.text);
    }
    loaded = true;
  } catch (error){
    root.textContent = error.message;
  } finally {
    loading = false;
  }
}
