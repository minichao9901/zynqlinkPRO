"""Exercise the debugger RTT terminal using a browser and its built-in mock target."""
import argparse
import json
from urllib.parse import urljoin

from playwright.sync_api import expect, sync_playwright


def verify(page, url, version):
    response = page.goto(urljoin(url, './?demo=serial#dbg'), wait_until='domcontentloaded')
    assert response and response.ok
    expect(page.locator('#build-stamp')).to_have_text(f'v{version} 版')
    page.locator('[data-tab="dbg"]').click()
    page.locator('#d-dock-tabs [data-dock="rtt"]').click()
    page.evaluate('''async () => {
      window.dbg = window.__tools.dbg;
      document.querySelector('#d-backend').value = 'mock';
      await dbg._syncBackend();
      document.querySelector('#d-rtt-addr').value = '0x20000100';
      document.querySelector('#d-rtt-on').checked = true;
      await dbg.connect();
    }''')
    status = page.locator('#d-rtt-info')
    expect(status).to_contain_text('下行通道 0 不可用')
    assert page.evaluate('dbg.rttTerminal.options.disableStdin')
    page.evaluate('''() => {
      const probe = dbg.session.probe;
      const ram = new DataView(probe.ram.buffer);
      const offset = { signature: 0x100, downCount: 0x114, buffer: 0x134, size: 0x138, write: 0x13c,
        read: 0x140, flags: 0x144, data: 0x320 };
      const put = (key, value) => ram.setUint32(offset[key], value, true);
      const get = key => ram.getUint32(offset[key], true);
      const signature = get('signature');
      dbg.rttStop();
      put('signature', 0);
      put('downCount', 1);
      put('buffer', 0x20000000 + offset.data);
      put('size', 8);
      put('write', 6);
      put('read', 6);
      put('flags', 0);
      window.initRtt = () => put('signature', signature);
      window.sendUp = text => probe._pushRtt(text);
      window.downPointers = () => [get('write'), get('read')];
      window.consumeDown = () => {
        const bytes = [];
        let read = get('read');
        while (read !== get('write')) {
          bytes.push(probe.ram[offset.data + read]);
          read = (read + 1) % get('size');
        }
        put('read', read);
        return bytes;
      };
      window.pasteRtt = text => {
        const clipboardData = new DataTransfer();
        clipboardData.setData('text/plain', text);
        dbg.rttTerminal.textarea.dispatchEvent(new ClipboardEvent('paste', {clipboardData, bubbles: true}));
      };
      document.querySelector('#d-rtt-on').dispatchEvent(new Event('change'));
    }''')
    expect(status).to_contain_text('将自动重试')
    page.evaluate("initRtt(); sendUp('msh >');")
    expect(status).to_contain_text('点击终端输入')
    rows = page.locator('#d-rtt .xterm-rows')
    expect(rows).to_contain_text('msh >')
    assert page.evaluate('dbg.session.halted')
    page.evaluate('dbg.rttTerminal.focus()')
    page.wait_for_function('document.activeElement === dbg.rttTerminal.textarea')
    for key in ('h', 'Backspace', 'Enter'):
        page.keyboard.press(key)
    page.wait_for_function('!dbg.rttInput && downPointers()[0] === 1')
    assert page.evaluate('downPointers()') == [1, 6]
    assert page.evaluate('consumeDown()') == [0x68, 0x7f, 0x0d]

    page.evaluate('pasteRtt', 'help\nversion')
    page.wait_for_function('dbg.rttInput?.pending === 5')
    head = page.evaluate('consumeDown()')
    page.wait_for_function('!dbg.rttInput')
    assert bytes(head + page.evaluate('consumeDown()')) == b'help\rversion'
    page.evaluate('pasteRtt', '0123456789')
    expect(status).to_contain_text('3 B 未发送')
    assert bytes(page.evaluate('consumeDown()')) == b'0123456'

    page.evaluate('''async () => {
      let release;
      const held = dbg.session.exclusive(() => new Promise(resolve => {release = resolve;}));
      await new Promise(resolve => setTimeout(resolve, 0));
      pasteRtt('stale');
      document.querySelector('#d-rtt-stop').click();
      release();
      await held;
      await dbg.session.exclusive(() => {});
    }''')
    assert page.evaluate('consumeDown()') == []
    assert page.evaluate('dbg.rttTerminal.options.disableStdin')
    page.locator('#d-rtt-locate').click()
    expect(status).to_contain_text('点击终端输入')
    page.evaluate('sendUp', '\x1b[32m 中 OK\x1b[0m')
    expect(rows).to_contain_text('msh > 中 OK')
    page.locator('#d-rtt-clear').click()
    expect(rows).not_to_contain_text('msh >')
    page.evaluate('sendUp', 'new prompt')
    expect(rows).to_contain_text('new prompt')
    page.evaluate('dbg.disconnect()')
    assert page.evaluate('dbg.rttTerminal.options.disableStdin')
    return dict(version=version, verified=['read-only', 'late initialization', 'automatic refresh',
        'keyboard', 'paste', 'wrap', 'full ring', 'stop cancels queued input', 'restart', 'UTF-8 and ANSI', 'clear', 'disconnect'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--version', required=True)
    parser.add_argument('--browser', default=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
    args = parser.parse_args()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=args.browser, headless=True)
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 900})
            page.context.new_cdp_session(page).send('Network.setCacheDisabled', {'cacheDisabled': True})
            print(json.dumps(verify(page, args.url, args.version)))
        finally:
            browser.close()


if __name__ == '__main__':
    main()
