import test from 'node:test';
import assert from 'node:assert/strict';
import {initCaptureLayout} from '../../../etm-service/web/app/capture-layout.js';

function fixture(saved, narrow=false){
  const classes=new Set(), values=new Map(saved===undefined?[]:[['etm.captureSettingsHidden',saved]]);
  const body={classList:{contains:k=>classes.has(k),toggle(k,on){if(on)classes.add(k);else classes.delete(k);}}};
  const attrs={},button={setAttribute:(k,v)=>attrs[k]=v};
  const layout=initCaptureLayout({body,button,storage:{getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v)},width:()=>narrow?720:1280});
  return {layout,button,attrs,classes,values};
}

test('history opens a wide analysis area while settings can be restored without session actions',()=>{
  const f=fixture();
  assert.equal(f.attrs['aria-expanded'],'true');
  f.layout.historyOpened();assert.ok(f.classes.has('side-hidden'));
  assert.equal(f.attrs['aria-expanded'],'false');
  f.button.onclick();assert.equal(f.attrs['aria-expanded'],'true');
  f.layout.historyOpened();assert.equal(f.attrs['aria-expanded'],'true');
});

test('explicit collapsed preference survives reload and source settings can be revealed temporarily',()=>{
  const f=fixture('true');
  assert.equal(f.attrs['aria-expanded'],'false');
  f.layout.show();assert.equal(f.attrs['aria-expanded'],'true');
  f.layout.historyOpened();assert.equal(f.attrs['aria-expanded'],'false');
  assert.equal(f.values.get('etm.captureSettingsHidden'),'true');
});

test('mobile history closes the settings overlay and the same control reopens it',()=>{
  const f=fixture(undefined,true);
  f.button.onclick();assert.ok(f.classes.has('settings-open'));
  f.button.onclick();f.layout.historyOpened();assert.ok(!f.classes.has('settings-open'));
  f.button.onclick();assert.ok(f.classes.has('settings-open'));
});
