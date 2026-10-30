import {parseUvprojx,suggestFromDevice,buildOutputs,PARAM_DEFAULTS} from './model.js';
import {zipStore} from './zip.js';
import {toast} from '../ui/toast.js';
const save=(bytes,name)=>{const a=document.createElement('a'),url=URL.createObjectURL(new Blob([bytes]));a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
export class GenView{
  constructor(){this.files=[];}
  init(){
    const panel=document.getElementById('tab-gen');
    panel.innerHTML=`<div class="z-page"><div class="z-heading"><div><h1>工程生成</h1><p>从 Keil 工程生成构建、下载和调试配套文件。全部在浏览器中完成。</p></div><label class="btn">载入 .uvprojx<input id="zg-file" type="file" accept=".uvprojx" hidden></label></div>
    <div class="z-columns"><aside class="z-card"><h2>项目参数</h2><label>工程名<input id="zg-name" value="project"></label><label>器件<input id="zg-device" value="STM32F103ZE"></label><label>Flash 起点<input id="zg-flash" value="0x08000000"></label><label>RTT 地址<input id="zg-rtt" value="0x20002000"></label><label>SWD 速率 (kHz)<input id="zg-speed" value="10000" type="number" min="1" max="60000"></label><label><input id="zg-jlink" type="checkbox">额外生成 J-Link Makefile</label><button id="zg-zip">下载 ZIP</button><button id="zg-folder">写入所选目录</button><p id="zg-info" class="muted">默认生成 CMSIS-DAP / pyOCD / OpenOCD 文件。</p></aside>
    <div class="z-card"><h2>文件预览</h2><select id="zg-select"></select><pre id="zg-preview" class="z-code"></pre></div></div></div>`;
    const $=id=>document.getElementById(id);
    $('zg-file').onchange=async e=>{
      try{const f=e.target.files[0];if(!f)return;const p=parseUvprojx(await f.text());
        $('zg-name').value=p.targetName||f.name.replace(/\.uvprojx$/i,'');$('zg-device').value=p.device||'STM32F103ZE';
        if(p.flashStart)$('zg-flash').value=p.flashStart;if(p.ramStart)$('zg-rtt').value=p.ramStart;
        $('zg-info').textContent=`${p.device||'未标注器件'} · ${p.cpu||'内核未标注'}`;this.refresh();
      }catch(error){toast(error.message,'err');}
    };
    panel.addEventListener('input',()=>this.refresh());
    $('zg-select').onchange=()=>this.preview();
    $('zg-zip').onclick=()=>save(zipStore(this.files),'zynqdap-project.zip');
    $('zg-folder').onclick=async()=>{
      try{if(!window.showDirectoryPicker)throw Error('此浏览器不支持目录写入，请下载 ZIP');const dir=await window.showDirectoryPicker();
        for(const file of this.files){const handle=await dir.getFileHandle(file.name,{create:true}),writer=await handle.createWritable();await writer.write(file.data);await writer.close();}
        toast('已写入 '+this.files.length+' 个文件');
      }catch(error){if(error.name!=='AbortError')toast(error.message,'err');}
    };this.refresh();
  }
  refresh(){
    const $=id=>document.getElementById(id);if(!$('zg-name'))return;
    const target=suggestFromDevice($('zg-device').value),speed=$('zg-speed').value;
    this.files=buildOutputs({...PARAM_DEFAULTS,...target,projectName:$('zg-name').value,flashStart:$('zg-flash').value,rttAddress:$('zg-rtt').value,
      openocdFreq:speed,pyocdFreq:String(Number(speed)*1000),checks:{jlink:$('zg-jlink').checked,gdb:true,pyocd:true,openocd:true,testBin:true}});
    const selected=$('zg-select').value;$('zg-select').replaceChildren(...this.files.map((f,i)=>new Option(f.name,String(i))));
    if(Number(selected)<this.files.length)$('zg-select').value=selected;this.preview();
  }
  preview(){const f=this.files[Number(document.getElementById('zg-select').value)];document.getElementById('zg-preview').textContent=f?.text??`二进制文件：${f?.data.length||0} 字节`;}
  onShow(){this.refresh();}
}
