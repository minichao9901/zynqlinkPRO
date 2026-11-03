import test from 'node:test';
import assert from 'node:assert/strict';
import {initTutorials,TUTORIALS,tutorialDone} from '../../../etm-service/web/app/tutorial.js';

function fixture({busy=()=>false,loadExample=async()=>{}}={}){
  const nodes=new Map(),listeners={},timers=new Set();let restored=0,hardware=0;
  class El{
    constructor(tag='DIV'){this.tagName=tag;this.children=[];this.style={};this.dataset={};this.handlers={};this.hidden=false;this.isConnected=true;this.offsetWidth=350;this.offsetHeight=240;}
    append(...children){this.children.push(...children);}setAttribute(){}
    addEventListener(type,fn){(this.handlers[type]??=[]).push(fn);}
    showModal(){this.open=true;}close(){this.open=false;for(const fn of this.handlers.close||[])fn();}
    getBoundingClientRect(){return {left:20,top:100,right:200,bottom:130,width:180,height:30};}
    scrollIntoView(){}focus(){}click(){hardware++;}
  }
  const get=id=>{if(!nodes.has(id))nodes.set(id,new El());return nodes.get(id);};
  const doc={body:new El(),createElement:tag=>new El(tag),getElementById:get,querySelector:s=>get(s),
    addEventListener:(type,fn)=>(listeners[type]??=[]).push(fn)};
  const win={innerWidth:1280,innerHeight:720,requestAnimationFrame:fn=>fn(),setInterval:fn=>{timers.add(fn);return fn;},clearInterval:fn=>timers.delete(fn),addEventListener(){}};
  const api=initTutorials({doc,win,busy,state:()=>({}),prepare:async()=>{},saveLayout:()=>()=>restored++,loadExample});
  const card=doc.body.children.find(e=>e.className==='tutorial-card'),chooser=doc.body.children.find(e=>e.className==='tutorial-chooser');
  return {api,card,chooser,menu:chooser.children.find(e=>e.className==='tutorial-choices'),
    next:card.children.find(e=>e.className==='tutorial-actions').children[1],listeners,timers,
    restored:()=>restored,hardware:()=>hardware};
}
const settle=async()=>{await Promise.resolve();await Promise.resolve();};

test('capture guide previews every step without invoking hardware and restores layout on finish',async()=>{
  const f=fixture();f.api.open();await f.menu.children.find(b=>b.dataset.tutorial==='capture').onclick();
  assert.equal(f.card.hidden,false);
  for(let n=0;n<TUTORIALS.find(t=>t.id==='capture').steps.length;n++){f.next.onclick();await settle();}
  assert.equal(f.hardware(),0);assert.equal(f.restored(),1);assert.equal(f.card.hidden,true);assert.equal(f.timers.size,0);
});
test('canceling while the offline sample loads never reopens an exited guide',async()=>{
  let resolve;const f=fixture({loadExample:()=>new Promise(r=>{resolve=r;})});f.api.open();
  const pending=f.menu.children[0].onclick();f.chooser.children.at(-1).onclick();resolve();await pending;
  assert.equal(f.card.hidden,true);assert.equal(f.restored(),1);assert.equal(f.hardware(),0);assert.equal(f.timers.size,0);
});
test('busy work blocks starting a tutorial, not the current operation',async()=>{
  let busy=true,loads=0;const f=fixture({busy:()=>busy,loadExample:async()=>loads++});f.api.open();
  await f.menu.children[0].onclick();assert.equal(loads,0);assert.equal(f.menu.children[0].disabled,true);
  busy=false;for(const update of f.timers)update();assert.equal(f.menu.children[0].disabled,false);f.chooser.children.at(-1).onclick();
});
test('failed example loading keeps the reason visible and allows retry',async()=>{
  let attempts=0;const f=fixture({loadExample:async()=>{if(++attempts===1)throw new Error('example missing');}});f.api.open();
  await f.menu.children[0].onclick();
  for(const update of f.timers)update();
  assert.match(f.chooser.children[3].textContent,/example missing/);
  assert.equal(f.menu.children[0].disabled,false);assert.equal(f.card.hidden,true);
  await f.menu.children[0].onclick();assert.equal(attempts,2);assert.equal(f.card.hidden,false);
  f.api.close();assert.equal(f.timers.size,0);
});
test('viewing teaching text is not reported as a hardware step completed',()=>{
  const steps=TUTORIALS.find(t=>t.id==='capture').steps;
  for(const step of steps)assert.equal(tutorialDone(step,{}),false);
  assert.equal(tutorialDone(steps[0],{hasElf:true}),true);
  const capture=steps.find(step=>step.done==='capture');
  assert.equal(tutorialDone(capture,{hasRecord:true,freshRecord:true}),false,'Opening a historical record is not a new hardware capture');
  assert.equal(tutorialDone(capture,{freshCapture:true}),true);
});
