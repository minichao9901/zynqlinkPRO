/* Standalone export viewer: embedded data only; never connects to the workbench. */
(()=>{
  'use strict';
  const bundle=JSON.parse(document.getElementById('flame-data').textContent),$=id=>document.getElementById(id);
  const views=bundle.views||{timeline:bundle},states=new Map();let active=null,data;
  const canvas=$('chart'),ctx=canvas.getContext('2d'),viewport=$('viewport'),ROW=28,PAD=6;
  let timeline,full,frames,names,rows,events,colors,unit;
  let lo,hi,width=1,height=1,pending=false,selected=null,drag=null,history=[],matches=[],matchPosition=-1,query='';
  const number=n=>timeline?'#'+Math.round(n).toLocaleString('en-US'):Number(n.toFixed(3)).toLocaleString('en-US');
  function activate(key){
    cancelDrag();
    if(data)states.set(active,{lo,hi,selected,history,matches,matchPosition,query,scroll:viewport.scrollTop});
    active=key;data=views[key];$('tooltip').hidden=true;
    for(const name of ['timeline','cycles']){const tab=$('tab-'+name),chosen=name===key;tab.setAttribute('aria-selected',String(chosen));tab.tabIndex=chosen?0:-1;}
    $('flame-panel').setAttribute('aria-labelledby','tab-'+key);
    $('chart-content').hidden=!data;$('unavailable').hidden=!!data;
    $('title').textContent=bundle.recordName||'ETM 火焰图';
    if(!data){$('subtitle').textContent='周期权重火焰图 · 导出区间 #'+bundle.range[0]+'～#'+bundle.range[1];$('unavailable').textContent=bundle.cycleUnavailableReason||'该记录没有可用周期计数。';return;}
    timeline=data.mode==='timeline';full=data.domain;frames=data.frames;names=data.names;events=data.events||[];
    rows=Array.from({length:data.depth},()=>[]);frames.forEach((f,i)=>rows[f[1]].push(i));rows.forEach(row=>row.sort((a,b)=>frames[a][2]-frames[b][2]));
    colors=names.map(name=>Array.from({length:3},(_,depth)=>color(name,depth)));
    unit=timeline?'执行序号':data.weight==='cycles'?'周期':'路径指令记录数';
    const state=states.get(key)||{lo:full[0],hi:full[1],selected:null,history:[],matches:[],matchPosition:-1,query:'',scroll:0};
    ({lo,hi,selected,history,matches,matchPosition,query}=state);$('search').value=query;
    $('match-count').textContent=query?(matchPosition<0?matches.length+' 处':(matchPosition+1)+' / '+matches.length):'';
    $('detail').textContent=selected===null?'悬停查看完整函数名和区间；点击保留调用详情。':describe(selected);
    $('subtitle').textContent=(timeline?'按执行顺序 · 横轴为执行序号，不是逐指令时间':'按调用路径聚合 · 宽度＝周期计数 · '+(data.timingBasis||'不是逐指令精确时间戳'))+' · 导出区间 #'+data.range[0]+'～#'+data.range[1]+(data.elfSha256?' · ELF '+data.elfSha256.slice(0,12):'');
    $('stats').textContent=frames.length.toLocaleString()+' 个完整调用段 · '+data.depth+' 层'+(timeline?' · '+data.counts.instructions.toLocaleString()+' 条指令记录 · '+data.counts.events+' 个事件':' · 合计 '+Number(full[1]-full[0]).toLocaleString()+' 周期');
    layout();viewport.scrollTop=state.scroll;canvas.style.top=viewport.scrollTop+'px';schedule();
  }
  function color(name,depth){if(/未知|未证实/.test(name))return '#9ba9bb';let h=0;for(const c of name)h=(31*h+c.charCodeAt(0))|0;return `hsl(${25+Math.abs(h)%40} 78% ${58+depth%3*5}%)`;}
  function firstAfter(row,value){let a=0,b=row.length;while(a<b){const m=(a+b)>>>1;if(frames[row[m]][2]<=value)a=m+1;else b=m;}return a;}
  function describe(index){const f=frames[index],path=[];for(let at=index;at!==null;at=frames[at][4])path.push(names[frames[at][0]]);return names[f[0]]+'\n'+(timeline?number(f[2])+' ～ '+number(f[3]-1):unit+' '+number(f[3]-f[2]))+' · 第 '+(f[1]+1)+' 层\n'+path.reverse().join(' → ');}
  function schedule(){if(!pending){pending=true;requestAnimationFrame(draw);}}
  function draw(){pending=false;if(!data)return;ctx.clearRect(0,0,width,height);const scale=(width-2*PAD)/(hi-lo),top=viewport.scrollTop;
    const first=Math.max(0,Math.floor(top/ROW)),last=Math.min(data.depth,Math.ceil((top+height)/ROW));
    for(let depth=first;depth<last;depth++){
      const row=rows[depth],begin=Math.max(0,firstAfter(row,lo)-1),y=depth*ROW-top+2;
      for(let at=begin;at<row.length;at++){const index=row[at],f=frames[index];if(f[2]>=hi)break;if(f[3]<=lo)continue;
        const x=PAD+(f[2]-lo)*scale,right=PAD+(f[3]-lo)*scale,left=Math.max(PAD,x),edge=Math.min(width-PAD,right),w=edge-left;
        if(w<=0)continue;ctx.fillStyle=colors[f[0]][depth%3];ctx.fillRect(left,y,Math.max(0,w-.5),ROW-3);
        if(query&&names[f[0]].toLocaleLowerCase().includes(query)){ctx.strokeStyle='#67c9ff';ctx.lineWidth=1.5;ctx.strokeRect(left+.75,y+.75,Math.max(0,w-2),ROW-4.5);}
        if(index===selected){ctx.strokeStyle='#f5fbff';ctx.lineWidth=2;ctx.strokeRect(left+1,y+1,Math.max(0,w-2.5),ROW-5);}
        if(w>16){ctx.save();ctx.beginPath();ctx.rect(left+3,y,w-6,ROW-3);ctx.clip();ctx.fillStyle='#392918';ctx.font='12px Consolas,"Microsoft YaHei",monospace';ctx.fillText(names[f[0]],left+4,y+17);ctx.restore();}
      }
    }
    if(events.length){const y=data.depth*ROW-top+2;if(y<height&&y+ROW>0){ctx.fillStyle='#f2b85e';for(const e of events){if(e[0]<lo)continue;if(e[0]>=hi)break;ctx.fillRect(PAD+(e[0]-lo)*scale,y,1,ROW-4);}}}
    if(drag&&drag.moved&&!drag.pan){const left=Math.min(drag.x,drag.current),right=Math.max(drag.x,drag.current);ctx.fillStyle='#61baff33';ctx.fillRect(left,0,right-left,height);ctx.strokeStyle='#8accff';ctx.lineWidth=1;ctx.strokeRect(left+.5,.5,right-left,Math.max(0,height-1));}
    $('range-label').textContent=number(lo)+' → '+number(timeline?hi-1:hi)+' · '+unit;
    $('axis').replaceChildren();for(let i=0;i<=4;i++){const span=document.createElement('span');span.textContent=number(i===4&&timeline?hi-1:lo+(hi-lo)*i/4);span.style.left=(i*25)+'%';span.style.transform=i===4?'translateX(-100%)':i?'translateX(-50%)':'';$('axis').append(span);}
    $('back').disabled=!history.length;$('zoom-out').disabled=hi-lo>=full[1]-full[0];$('zoom-in').disabled=hi-lo<=(timeline?1:(full[1]-full[0])*1e-9);$('focus').disabled=selected===null;
  }
  function bounds(a,b,remember=true){const total=full[1]-full[0],minimum=timeline?1:Math.max(total*1e-9,Number.EPSILON),span=Math.min(total,Math.max(minimum,b-a));a=Math.max(full[0],Math.min(a,full[1]-span));if(remember&&history.length<500&&(a!==lo||a+span!==hi))history.push([lo,hi]);lo=a;hi=a+span;schedule();}
  function zoom(factor,ratio=.5){cancelDrag();const at=lo+ratio*(hi-lo),span=(hi-lo)*factor;bounds(at-span*ratio,at+span*(1-ratio));}
  function reset(){cancelDrag();bounds(full[0],full[1]);viewport.scrollTop=0;}
  function focus(index){cancelDrag();selected=index;const f=frames[index];bounds(f[2],f[3]);viewport.scrollTop=Math.max(0,(f[1]-2)*ROW);$('detail').textContent=describe(index);}
  function hit(event){const rect=canvas.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top,depth=Math.floor((y+viewport.scrollTop)/ROW),value=lo+(x-PAD)/(width-2*PAD)*(hi-lo);if(depth<0||depth>=rows.length)return null;const row=rows[depth],at=firstAfter(row,value)-1;if(at<0)return null;const index=row[at];return value<frames[index][3]?index:null;}
  function tooltip(event){const index=hit(event),tip=$('tooltip');if(index===null){tip.hidden=true;return;}tip.textContent=describe(index);tip.hidden=false;tip.style.left=Math.min(window.innerWidth-tip.offsetWidth-12,event.clientX+14)+'px';tip.style.top=Math.max(8,Math.min(window.innerHeight-tip.offsetHeight-12,event.clientY+16))+'px';}
  function layout(){const maxHeight=Math.max(240,window.innerHeight-300);viewport.style.height=Math.min((data.depth+(events.length?1:0))*ROW+8,maxHeight)+'px';height=viewport.clientHeight;$('spacer').style.height=(data.depth+(events.length?1:0))*ROW+8+'px';width=viewport.clientWidth;const dpr=window.devicePixelRatio||1;canvas.width=Math.ceil(width*dpr);canvas.height=Math.ceil(height*dpr);canvas.style.width=width+'px';canvas.style.height=height+'px';canvas.style.top=viewport.scrollTop+'px';ctx.setTransform(dpr,0,0,dpr,0,0);schedule();}
  $('zoom-in').onclick=()=>zoom(.5);$('zoom-out').onclick=()=>zoom(2);$('reset').onclick=reset;$('back').onclick=()=>{const previous=history.pop();if(previous)bounds(...previous,false);};$('focus').onclick=()=>{if(selected!==null)focus(selected);};
  canvas.addEventListener('wheel',event=>{event.preventDefault();const x=event.clientX-canvas.getBoundingClientRect().left;zoom(Math.exp(Math.max(-1,Math.min(1,event.deltaY*.002))),Math.max(0,Math.min(1,(x-PAD)/(width-2*PAD))));},{passive:false});
  const localX=event=>Math.max(PAD,Math.min(width-PAD,event.clientX-canvas.getBoundingClientRect().left));
  function cancelDrag(){if(!drag)return;const previous=drag;drag=null;canvas.classList.remove('panning');if(previous.pan)bounds(previous.lo,previous.hi,false);if(canvas.hasPointerCapture(previous.pointerId))canvas.releasePointerCapture(previous.pointerId);schedule();}
  canvas.addEventListener('pointerdown',event=>{if(event.button!==0||drag)return;event.preventDefault();canvas.focus();drag={x:localX(event),current:localX(event),lo,hi,pan:event.shiftKey,moved:false,pointerId:event.pointerId};canvas.setPointerCapture(event.pointerId);$('tooltip').hidden=true;canvas.classList.toggle('panning',drag.pan);});
  canvas.addEventListener('pointermove',event=>{if(!drag){tooltip(event);return;}if(event.pointerId!==drag.pointerId)return;drag.current=localX(event);const dx=drag.current-drag.x;if(Math.abs(dx)>4)drag.moved=true;if(drag.moved&&drag.pan){const shift=dx/(width-2*PAD)*(drag.hi-drag.lo);bounds(drag.lo-shift,drag.hi-shift,false);}else schedule();});
  canvas.addEventListener('pointerup',event=>{if(!drag||event.pointerId!==drag.pointerId)return;drag.current=localX(event);if(Math.abs(drag.current-drag.x)>4)drag.moved=true;const finished=drag;drag=null;canvas.classList.remove('panning');if(canvas.hasPointerCapture(event.pointerId))canvas.releasePointerCapture(event.pointerId);
    if(!finished.moved){selected=hit(event);if(selected!==null)$('detail').textContent=describe(selected);schedule();}
    else if(finished.pan){if(history.length<500&&(lo!==finished.lo||hi!==finished.hi))history.push([finished.lo,finished.hi]);schedule();}
    else{const toValue=x=>finished.lo+(x-PAD)/(width-2*PAD)*(finished.hi-finished.lo);let a=toValue(Math.min(finished.x,finished.current)),b=toValue(Math.max(finished.x,finished.current));if(timeline){a=Math.floor(a);b=Math.ceil(b);}bounds(a,b);}
  });
  canvas.addEventListener('pointercancel',cancelDrag);canvas.addEventListener('lostpointercapture',cancelDrag);canvas.addEventListener('pointerleave',()=>{$('tooltip').hidden=true;});
  canvas.addEventListener('dblclick',event=>{const index=hit(event);if(index===null)reset();else focus(index);});
  canvas.addEventListener('keydown',event=>{let handled=true;if(['+','='].includes(event.key))zoom(.5);else if(['-','_'].includes(event.key))zoom(2);else if(event.key==='Home')reset();else if(event.key==='ArrowLeft')bounds(lo-(hi-lo)*.2,hi-(hi-lo)*.2);else if(event.key==='ArrowRight')bounds(lo+(hi-lo)*.2,hi+(hi-lo)*.2);else if(event.key==='Escape'){cancelDrag();selected=null;$('tooltip').hidden=true;schedule();}else handled=false;if(handled)event.preventDefault();});
  $('search').addEventListener('input',()=>{query=$('search').value.toLocaleLowerCase().trim();matches=[];if(query)frames.forEach((f,i)=>{if(names[f[0]].toLocaleLowerCase().includes(query))matches.push(i);});matchPosition=-1;$('match-count').textContent=query?matches.length+' 处':'';schedule();});
  function match(direction){if(!matches.length)return;matchPosition=matchPosition<0?(direction>0?0:matches.length-1):(matchPosition+direction+matches.length)%matches.length;focus(matches[matchPosition]);$('match-count').textContent=(matchPosition+1)+' / '+matches.length;}
  $('next-match').onclick=()=>match(1);$('previous-match').onclick=()=>match(-1);$('search').addEventListener('keydown',e=>{if(e.key==='Enter')match(e.shiftKey?-1:1);});
  viewport.addEventListener('scroll',()=>{canvas.style.top=viewport.scrollTop+'px';$('tooltip').hidden=true;schedule();});window.addEventListener('resize',()=>{cancelDrag();if(data)layout();});
  for(const key of ['timeline','cycles']){const tab=$('tab-'+key);tab.onclick=()=>{if(active!==key)activate(key);};tab.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const next=event.key==='Home'?'timeline':event.key==='End'?'cycles':active==='timeline'?'cycles':'timeline';activate(next);$('tab-'+next).focus();});}
  activate('timeline');
  document.documentElement.dataset.flameReady='true';
})();
