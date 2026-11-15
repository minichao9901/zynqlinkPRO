import test from 'node:test';
import assert from 'node:assert/strict';
import {RttCdcView} from '../../app/hid/view.js';
import {RttCdcStreamView} from '../../app/hid/stream.js';
import {SerialSession} from '../../app/serial/session.js';

test('RTT forwarding uses a single exact-address control-block header window',t=>{
  const fields = {'h-addr':{value:'0x24000014'},'h-chan':{value:'0'},'h-clock':{value:'50000000'},'h-target':{value:'swd'}};
  globalThis.document={getElementById:id=>fields[id]};
  t.after(()=>{delete globalThis.document;});
  const params = new RttCdcView().params();
  assert.equal(params.addr,0x24000014);
  assert.equal(params.size,24);
});

test('RTT forwarding prefers the native probe CDC and rejects an unrelated COM port',async t=>{
  const uart = {path:'COM5',nativeService:true,getInfo:()=>({usbVendorId:0x1a86,usbProductId:0x7523})};
  const cdc = {path:'COM33',nativeService:true,getInfo:()=>({usbVendorId:0x0d28,usbProductId:0x0204})};
  t.mock.method(SerialSession,'listPorts',async()=>[uart,cdc]);
  globalThis.Option = class { constructor(text,value){Object.assign(this,{text,value});} };
  t.after(()=>{delete globalThis.Option;});
  const select = {value:'0',appendChild(){}};
  const message = {className:'hint',textContent:'',classList:{remove(){},add(){}}};
  const controls = {'c-port':select,'c-note':message,'c-err':message,'c-baud':{value:'115200'}};
  let opened;
  const view = Object.assign(Object.create(RttCdcStreamView.prototype),{
    owner:'rtt',ports:[uart],$:name=>controls[name],s:{open:async(port,opts)=>{opened={port,opts};}},
  });
  await view.refreshPorts();
  assert.equal(select.value,'1');
  select.value = '0';
  await view.connect();
  assert.match(message.textContent,/接收口选错.*COM5/);
  assert.equal(opened,undefined);
  select.value = '1';
  await view.connect();
  assert.equal(opened.port,cdc);
  assert.equal(opened.opts.rts,true);
});

test('RTT STOP waits for the probe to drain and re-enables the start controls',async t=>{
  globalThis.document={getElementById:()=>null};
  globalThis.window={};
  t.after(()=>{delete globalThis.document;delete globalThis.window;});
  const view=Object.create(RttCdcView.prototype);
  const replies=[{rc:-7,status:{running:true}}, {rc:0,status:{running:false}}];
  const rendered=[];
  Object.assign(view,{
    dev:{stop:async()=>replies.shift()},
    _bridgeRequested:true,
    render(){rendered.push(!!this._stopPromise);},
  });
  await view.stop();
  assert.equal(replies.length,0);
  assert.equal(view._bridgeRequested,false);
  assert.equal(view.last.running,false);
  assert.equal(rendered.at(-1),false);
});
