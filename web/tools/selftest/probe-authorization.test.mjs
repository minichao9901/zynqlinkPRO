import test from 'node:test';
import assert from 'node:assert/strict';

import {initProbeConnection} from '../../app/ui/probe-connection.js';

test('connect waits for saved grants before deciding whether to open a chooser',async t=>{
  const elements = new Map();
  const button = id => {
    if (id === 'toasts') return null;
    if (!elements.has(id)) elements.set(id,{parentElement:{},addEventListener(){}});
    return elements.get(id);
  };
  let usbReady, hidReady, chooserCalls=0;
  const usb = {vendorId:0x0d28,productId:0x0204};
  const hid = {...usb,collections:[{usagePage:0xff00}]};
  const api = callback => ({
    getDevices:()=>new Promise(resolve=>callback(resolve)),
    requestDevice(){chooserCalls++;throw Error('unexpected chooser');},
    addEventListener(){},
  });
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{
    usb:api(resolve=>{usbReady=resolve;}),hid:api(resolve=>{hidReady=resolve;}),
  }});
  globalThis.document={getElementById:button,querySelector:()=>({dataset:{tab:'flash'}}),
    body:{dataset:{}},addEventListener(){}};
  let timerCleanup;
  globalThis.window={addEventListener(event,fn){if(event==='pagehide')timerCleanup=fn;}};
  t.after(()=>{timerCleanup?.();delete globalThis.document;delete globalThis.window;});
  const tools={probeManager:{summary:()=>({owners:[],pending:[],failures:[]})},
    rtt:{},dbg:{},hid:{dev:{}},scope:{},etm:{}};
  initProbeConnection(tools);
  assert.equal(button('btn-probe-connect').disabled,true);
  usbReady([usb]);
  hidReady([hid]);
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(button('btn-probe-connect').disabled,false);
  await button('btn-probe-connect').onclick();
  assert.deepEqual(tools.probeConnection,{usb:true,hid:true});
  assert.equal(chooserCalls,0);
});
