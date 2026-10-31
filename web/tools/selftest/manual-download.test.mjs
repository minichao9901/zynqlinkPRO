import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkbenchAutomation} from '../../app/automation/workbench.js';
import {wireFlameExport} from '../../../etm-service/web/app/flame-export-ui.js';
import {saveExportFile} from '../../../etm-service/web/app/export.js';

function downloadRig(){
  let nativeClicks=0,next=0;
  class Anchor{constructor(){this.dataset={};}click(){nativeClicks++;}}
  const root={querySelectorAll:()=>[],textContent:''};
  const child={Object,Map,Set,ArrayBuffer,__etm:{},document:{getElementById:()=>root},
    URL:{createObjectURL:()=>`blob:${++next}`,revokeObjectURL:()=>{}},HTMLAnchorElement:Anchor};
  const automation=createWorkbenchAutomation({etm:{onShow:async()=>{},frame:{contentWindow:child}},errors:[]},
    {document:{getElementById:()=>null},CSS:{escape:s=>s}});
  return {child,automation,nativeClicks:()=>nativeClicks};
}

test('CLI download bookkeeping never suppresses ordinary browser downloads',async()=>{
  const r=downloadRig();await r.automation.dispatch({page:'etm',op:'describe'});
  const link=new r.child.HTMLAnchorElement();link.href=r.child.URL.createObjectURL(new Blob(['<svg/>']));link.download='manual.svg';link.click();
  assert.equal(r.nativeClicks(),1);
  const files=await r.automation.dispatch({page:'etm',op:'downloads'});
  assert.equal(files.length,1);assert.equal(files[0].browserDownloadRequested,true);
  link.dataset.cliDownloadOnly='1';link.click();
  assert.equal(r.nativeClicks(),1);assert.equal(link.dataset.cliCaptured,'1');
});

test('a full CLI download cache cannot break a manual download',async()=>{
  const r=downloadRig();await r.automation.dispatch({page:'etm',op:'describe'});
  for(let i=0;i<40;i++){
    const link=new r.child.HTMLAnchorElement();link.href=r.child.URL.createObjectURL(new Blob(['x']));link.download=`${i}.svg`;link.click();
  }
  assert.equal(r.nativeClicks(),40);
  assert.equal((await r.automation.dispatch({page:'etm',op:'downloads'})).length,32);
});

test('embedded manual export and retry download through the outer document; CLI stays in its frame',()=>{
  function windowRig(){
    const links=[];const w={URL:{createObjectURL:()=> 'blob:outer',revokeObjectURL:()=>{}},links};
    const click=function(){this.clicked=true;if(this.dataset.cliDownloadOnly)this.dataset.cliCaptured='1';};
    click._traceCliDownloadCapture=true;
    w.document={body:{append:link=>links.push(link)},createElement:()=>({dataset:{},click,remove(){this.removed=true;}})};
    return w;
  }
  const frame=windowRig(),outer=windowRig();frame.parent=outer;
  const file=saveExportFile({blob:new Blob(['<svg/>']),filename:'flame.svg'},{windowImpl:frame,retainUrl:true});
  assert.equal(frame.links.length,0);assert.equal(outer.links.length,1);assert.equal(outer.links[0].clicked,true);
  file.retryDownload();assert.equal(outer.links.length,2);assert.equal(outer.links[1].download,'flame.svg');
  // Revoke asynchronously in production; the test keeps ownership explicit.
  const captured=saveExportFile({blob:new Blob(['<svg/>']),filename:'cli.svg'},{windowImpl:frame,retainUrl:true,captureOnly:true});
  assert.equal(frame.links.length,1);assert.equal(captured.cliCaptured,true);assert.equal(captured.browserDownloadRequested,false);
});

class Element{
  constructor(document){this.ownerDocument=document;this.children=[];this.dataset={};this._text='';}
  set textContent(value){this._text=value;this.children=[];}
  get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
  setAttribute(key,value){this[key]=value;}
  append(child){this.children.push(child);}
}
function ui(){const document={createElement:()=>new Element(document)};const button=new Element(document);button.textContent='导出当前火焰图 SVG';return {document,button};}

test('manual flame export shows progress, requested filename, size and a real retry link',async()=>{
  const {button}=ui();let resolve,retries=0;
  const status=wireFlameExport(button,()=>new Promise(r=>{resolve=r;}));
  const completion=button.onclick();assert.equal(button.disabled,true);assert.match(status.textContent,/正在生成/);
  resolve({filename:'flame.svg',bytes:2531,downloadUrl:'blob:result',cliCaptured:false,retryDownload:()=>{retries++;}});await completion;
  assert.equal(button.disabled,false);assert.match(status.textContent,/flame.svg/);assert.match(status.textContent,/浏览器下载/);
  assert.equal(status.children[0].href,'blob:result');assert.equal(status.children[0].download,'flame.svg');
  let prevented=false;status.children[0].onclick({preventDefault:()=>{prevented=true;}});
  assert.equal(retries,1);assert.equal(prevented,true);
});

test('export failure remains visible and makes the button usable again',async()=>{
  const {button}=ui();let reported=0;
  const status=wireFlameExport(button,async()=>{throw Error('frame limit');},()=>{reported++;});
  await button.onclick();assert.equal(button.disabled,false);assert.match(status.textContent,/导出失败：frame limit/);
  assert.equal(status.children.length,0);assert.equal(reported,1);
});
