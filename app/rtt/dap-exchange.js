import { withTimeout } from '../core/pace.js';

const USB_PACKET = 4096;

export async function exchangeRttDap(device, request, expected, length = expected.length){
  const bytes = Uint8Array.from(request);
  let result;
  if (device.atomicDapSupported) result = await device.exchangeDap(bytes, USB_PACKET);
  else {
    // These packets end short (block writes have a five-byte header).
    const out = await withTimeout(device.transferOut(2, bytes), 2000, 'RTT DAP 写请求');
    if (out.status !== 'ok' || out.bytesWritten !== bytes.length) throw Error('DAP 请求短写');
    result = await withTimeout(device.transferIn(1, USB_PACKET), 2000, 'RTT DAP 读响应');
  }
  const reply = result.data && new Uint8Array(result.data.buffer, result.data.byteOffset, result.data.byteLength);
  if (result.status !== 'ok' || reply?.length !== length || !expected.every((n, i) => n === reply[i])){
    const command = bytes[0].toString(16).padStart(2, '0');
    const header = Array.from(reply?.subarray(0, 4) ?? [], value => value.toString(16).padStart(2, '0')).join(' ');
    const error = Error(`RTT DAP 响应状态或长度错误（0x${command}，${reply?.length ?? 0}/${length} B，${header || result.status}）`);
    if (result.status === 'ok' && reply?.[0] === bytes[0]) error.dapReply = reply;
    throw error;
  }
  return reply.subarray(expected.length);
}
