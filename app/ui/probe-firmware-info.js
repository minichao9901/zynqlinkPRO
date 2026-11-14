import { AkaLinkHid } from '../hid/probe.js';
import { nativeHidDevices, nativeProbeEnabled } from '../core/native-probe.js';
import { BUILD, WEB_BUILT_AT } from '../core/build.js';

export function initProbeFirmwareInfo(tools){
  const button = document.getElementById('btn-probe-info');
  const dialog = document.getElementById('probe-info-dialog');
  const result = document.getElementById('probe-info-result');
  const webBuildTime = WEB_BUILT_AT
    ? WEB_BUILT_AT.replace('T', ' ').replace('+00:00', ' UTC')
    : '源码模式，未打包';
  document.getElementById('web-build-info').textContent = `版本　${BUILD}\n构建时间　${webBuildTime}`;
  button.addEventListener('click', async () => {
    button.disabled = true;
    dialog.showModal();
    result.textContent = '正在读取探针…';
    const client = new AkaLinkHid();
    try {
      if (!AkaLinkHid.supported()) throw Error('当前浏览器需要 WebHID 或本机工作台。');
      if (nativeProbeEnabled()){
        const devices = await nativeHidDevices();
        if (devices.length !== 1) throw Error('请连接一只探针后重试。');
        await client.open(devices[0]);
      } else {
        const current = tools.hid?.dev;
        if (current?.connected && !tools.hid.mock && current.isProbe) await client.open(current.device);
        else await client.connect();
      }
      const { model, fw, sn, buildTime } = await client.firmwareInfo();
      result.textContent = [
        `型号　${model || '未提供'}`,
        `序列号　${sn || '未提供'}`,
        `固件版本　${fw || '未提供'}`,
        `编译时间　${buildTime || '当前固件未提供'}`,
      ].join('\n');
    } catch (error){
      result.textContent = error.message;
    } finally {
      try { await client.close(); }
      catch (error){ result.textContent += '\n关闭读取会话失败：' + error.message; }
      button.disabled = false;
    }
  });
}
