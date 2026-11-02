import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const root=process.argv[2];
class El {
 constructor(tag='DIV'){this.tagName=tag;this.children=[];this.handlers={};this.value='';this.options=['stm32f103','stm32h743'].map(value=>({value}));}
 get selectedOptions(){return [{textContent:this.value}];}
 append(...xs){this.children.push(...xs);} prepend(...xs){this.children.unshift(...xs);} after(){} replaceChildren(...xs){this.children=xs;} setAttribute(){}
 addEventListener(ev,fn){(this.handlers[ev]??=[]).push(fn);} change(){for(const fn of this.handlers.change||[])fn();}
 querySelector(){return this.side??=new El();}
 get parentElement(){return this.parent??=new El('FIELDSET');}
}
const nodes=new Map(),get=id=>{if(!nodes.has(id))nodes.set(id,new El());return nodes.get(id);};
globalThis.document={getElementById:get,createElement:tag=>new El(tag.toUpperCase())};
globalThis.window={addEventListener(){}};globalThis.setInterval=()=>0;
get('f-chip').value=get('r-chip').value='stm32f103';get('r-target').value=get('sc-target').value='swd';get('d-backend').value='webusb';
const view=()=>({session:{bps:[],bpNotes:new Map(),regs:[]},watch:{items:[]},renderVars(){},updatePlan(){},renderElfInfo(){},renderBps(){},renderWatch(){},_fileInfo(){},_applyChip(){},_applyTargetUi(){},_applyBackendUi(){},async _syncBackend(){}});
const tools={flash:view(),rtt:view(),dbg:view(),scope:view()};
const {initSessionContext}=await import(pathToFileURL(root+'/web/app/ui/session-context.js'));
const context=initSessionContext(tools);
const adopt=page=>(page==='scope'?get('sc-side-capture-panel'):get('tab-'+page).side).children[0].children[2];
// F103 local symbols remain after the global selection switches to H743.
tools.scope.elf={name:'f103.elf'};tools.scope.selected=[{addr:0x20000000}];
get('r-chip').value='stm32h743';get('r-chip').change();context.notify();
assert.equal(context.target.id,'stm32h743');assert.equal(adopt('scope').disabled,true);assert.equal(tools.scope.elf.name,'f103.elf');
console.log('A: H743 session target, scope adopt disabled as already matching, F103 ELF and selected address retained.');
// Explicit adoption does not update the local previous-target closure.
await adopt('flash').onclick();assert.equal(get('f-chip').value,'stm32h743');
tools.flash.file={name:'h743.elf'};
get('f-chip').value='stm32f103';get('f-chip').change();
assert.equal(tools.flash.file.name,'h743.elf');assert.equal(context.target.id,'stm32f103');
console.log('B: F103 -> adopt H743 -> choose F103 retains h743.elf in flash.file.');
