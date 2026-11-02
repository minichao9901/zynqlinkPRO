import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {nativeUsbDevices,nativeHidDevices,nativeSerialPorts} from '../../app/core/native-probe.js';

test('delivery sequence survives reload and is shared with same-origin child pages',async t=>{
  const originalWindow=globalThis.window,originalFetch=globalThis.fetch;
  t.after(()=>{globalThis.window=originalWindow;globalThis.fetch=originalFetch;});
  const data=new Map(),storage={getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v)};
  const make=()=>({document:{body:{dataset:{nativeProbe:'1'}}},location:{origin:'http://127.0.0.1:8882',search:'?trace-cli='+'a'.repeat(64)},sessionStorage:storage});
  let root=make();root.parent=root;const firstRoot=root;globalThis.window=root;const ids=[];
  globalThis.fetch=async(url,opts)=>{ids.push(opts.headers['X-Trace-Delivery']);return {ok:true,json:async()=>({ok:true,value:[]})};};
  await nativeUsbDevices();const child=make();child.parent=root;globalThis.window=child;await nativeUsbDevices();
  root=make();root.parent=root;globalThis.window=root;await nativeUsbDevices();
  globalThis.window=firstRoot;await nativeUsbDevices();
  assert.deepEqual(ids.map(id=>id.split(':')[2]),['1','2','3','4']);
  assert.equal(new Set(ids.map(id=>id.split(':')[1])).size,1);
  assert.ok(ids.every(id=>/^v2:[0-9a-f]{32}:\d+$/.test(id)));
});

test('offline lists never fetch and existing native devices cannot be opened',async t=>{
  const originalWindow=globalThis.window,originalFetch=globalThis.fetch;
  t.after(()=>{globalThis.window=originalWindow;globalThis.fetch=originalFetch;});
  const dataset={nativeProbe:'1'};
  globalThis.window={document:{body:{dataset}},location:{origin:'http://127.0.0.1:8882',search:'?trace-cli='+'a'.repeat(64)}};
  globalThis.fetch=async()=>({ok:true,json:async()=>({ok:true,value:[{vendorId:1,productId:1,serialNumber:'offline-test'}]})});
  const [device]=await nativeUsbDevices();dataset.nativeOffline='1';
  globalThis.fetch=async()=>{throw Error('network forbidden');};
  assert.deepEqual(await nativeUsbDevices(),[]);assert.deepEqual(await nativeHidDevices(),[]);assert.deepEqual(await nativeSerialPorts(),[]);
  await assert.rejects(device.open(),/离线验收：硬件访问已禁用/);
});

test('native transport preserves real wire bytes, report IDs and serial reads after idle polls',async t=>{
  const originalWindow=globalThis.window,originalFetch=globalThis.fetch;
  t.after(()=>{globalThis.window=originalWindow;globalThis.fetch=originalFetch;});
  globalThis.window={document:{body:{dataset:{nativeProbe:'1'}}},location:{origin:'http://127.0.0.1:8882',search:'?trace-cli='+'a'.repeat(64)}};
  const requests=[];let empty=2;
  const encode=bytes=>Buffer.from(bytes).toString('base64');
  const descriptor={vendorId:0x0d28,productId:0x0204,serialNumber:'test-probe',productName:'wire device',configuration:{interfaces:[]}};
  globalThis.fetch=async(url,options)=>{
    assert.equal(options.headers['X-Trace-CLI'],'a'.repeat(64));
    const route=new URL(url).pathname,value=JSON.parse(options.body);requests.push({route,value});
    let reply={};
    if(route==='/native-probe/usb/list')reply=[descriptor];
    if(route==='/native-probe/usb/open')reply=descriptor;
    if(route==='/native-probe/usb/write')reply={bytesWritten:Buffer.from(value.data,'base64').length};
    if(route==='/native-probe/usb/read')reply={data:encode([0,128,255])};
    if(route==='/native-probe/hid/list')reply=[{...descriptor,collections:[{usagePage:0xff00}]}];
    if(route==='/native-probe/hid/report')reply={reportId:2,data:encode([1,0x31,0])};
    if(route==='/native-probe/serial/list')reply=[{path:'COM-test',usbVendorId:0x0d28,usbProductId:0x0204}];
    if(route==='/native-probe/serial/read')reply={data:empty-->0?'':encode([65,66])};
    return {ok:true,json:async()=>({ok:true,value:reply})};
  };
  const [usb]=await nativeUsbDevices();await usb.open();
  const buffer=vm.runInNewContext('new Uint8Array([0,128,255]).buffer');
  assert.equal((await usb.transferOut(2,buffer)).bytesWritten,3);
  assert.deepEqual([...new Uint8Array((await usb.transferIn(1,64)).data.buffer)],[0,128,255]);
  await usb.close();
  const [hid]=await nativeHidDevices();await hid.open();let report;
  hid.addEventListener('inputreport',event=>{report=event;});
  await hid.sendReport(1,new Uint8Array(63));assert.equal(report.reportId,2);
  assert.deepEqual([...new Uint8Array(report.data.buffer)],[1,0x31,0]);await hid.close();
  const [port]=await nativeSerialPorts();await port.open({baudRate:115200});
  const reader=port.readable.getReader();assert.deepEqual([...(await reader.read()).value],[65,66]);
  await reader.cancel();reader.releaseLock();await port.close();
  assert.equal(requests.filter(r=>r.route==='/native-probe/serial/read').length,3);
});

test('fatal native serial receive failure retires the readable stream for session cleanup',async t=>{
  const originalWindow=globalThis.window,originalFetch=globalThis.fetch;
  t.after(()=>{globalThis.window=originalWindow;globalThis.fetch=originalFetch;});
  globalThis.window={document:{body:{dataset:{nativeProbe:'1'}}},location:{origin:'http://127.0.0.1:8882',search:'?trace-cli='+'b'.repeat(64)}};
  globalThis.fetch=async(url)=>({ok:true,json:async()=>new URL(url).pathname.endsWith('/list')
    ?{ok:true,value:[{path:'COM-overflow'}]}:new URL(url).pathname.endsWith('/read')
      ?{ok:false,error:'本地串口接收队列溢出，数据不完整'}:{ok:true,value:{resourceEpoch:'overflow-test'}}});
  const [port]=await nativeSerialPorts();await port.open({baudRate:115200});
  const reader=port.readable.getReader();
  await assert.rejects(reader.read(),/数据不完整/);assert.equal(port.readable,null);
  reader.releaseLock();await port.close();
});
