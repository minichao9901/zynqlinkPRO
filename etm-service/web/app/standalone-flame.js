/* Standalone export viewer: embedded data only; never connects to the workbench. */
(()=>{
  'use strict';
  const data=JSON.parse(document.getElementById('flame-data').textContent),$=id=>document.getElementById(id);
  const canvas=$('chart'),ctx=canvas.getContext('2d'),viewport=$('viewport'),ROW=28,PAD=6;
  const timeline=data.mode==='timeline',full=data.domain,frames=data.frames,names=data.names;
  const rows=Array.from({length:data.depth},()=>[]),events=data.events||[];
  frames.forEach((f,i)=>rows[f[1]].push(i));rows.forEach(row=>row.sort((a,b)=>frames[a][2]-frames[b][2]));
  let lo=full[0],hi=full[1],width=1,height=1,pending=false,selected=null,drag=null,history=[],matches=[],matchPosition=-1,query='';
  const number=n=>timeline?'#'+Math.round(n).toLocaleString('en-US'):Number(n.toFixed(3)).toLocaleString('en-US');
  const unit=timeline?'执行序号':data.weight==='cycles'?'周期':'路径指令记录数';
  $('title').textContent=data.recordName||'ETM 火焰图';
  $('subtitle').textContent=(timeline?'按执行顺序 · 横轴为执行序号，不是逐指令时间':'按调用权重 · '+unit)+' · 导出区间 #'+data.range[0]+'～#'+data.range[1]+(data.elfSha256?' · ELF '+data.elfSha256.slice(0,12):'');
  $('stats').textContent=frames.length.toLocaleString()+' 个完整调用段 · '+data.depth+' 层'+(timeline?' · '+data.counts.instructions.toLocaleString()+' 条指令记录 · '+data.counts.events+' 个事件':'');
  function color(name,depth){if(/未知|未证实/.test(name))return '#9ba9bb';let h=0;for(const c of name)h=(31*h+c.charCodeAt(0))|0;return `hsl(${25+Math.abs(h)%40} 78% ${58+depth%3*5}%)`;}
  const colors=names.map(name=>Array.from({length:3},(_,depth)=>color(name,depth)));
  function firstAfter(row,value){let a=0,b=row.length;while(a<b){const m=(a+b)>>>1;if(frames[row[m]][2]<=value)a=m+1;else b=m;}return a;}
  function describe(index){const f=frames[index],path=[];for(let at=index;at!==null;at=frames[at][4])path.push(names[frames[at][0]]);return names[f[0]]+'\n'+(timeline?number(f[2])+' ～ '+number(f[3]-1):unit+' '+number(f[3]-f[2]))+' · 第 '+(f[1]+1)+' 层\n'+path.reverse().join(' → ');}
  function schedule(){if(!pending){pending=true;requestAnimationFrame(draw);}}
  function draw(){pending=false;ctx.clearRect(0,0,width,height);const scale=(width-2*PAD)/(hi-lo),top=viewport.scrollTop;
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
    $('range-label').textContent=number(lo)+' → '+number(timeline?hi-1:hi)+' · '+unit;
    $('axis').replaceChildren();for(let i=0;i<=4;i++){const span=document.createElement('span');span.textContent=number(i===4&&timeline?hi-1:lo+(hi-lo)*i/4);span.style.left=(i*25)+'%';span.style.transform=i===4?'translateX(-100%)':i?'translateX(-50%)':'';$('axis').append(span);}
    $('back').disabled=!history.length;$('zoom-out').disabled=hi-lo>=full[1]-full[0];$('zoom-in').disabled=hi-lo<=(timeline?1:(full[1]-full[0])*1e-9);$('focus').disabled=selected===null;
  }
  function bounds(a,b,remember=true){const total=full[1]-full[0],minimum=timeline?1:Math.max(total*1e-9,Number.EPSILON),span=Math.min(total,Math.max(minimum,b-a));a=Math.max(full[0],Math.min(a,full[1]-span));if(remember&&history.length<500&&(a!==lo||a+span!==hi))history.push([lo,hi]);lo=a;hi=a+span;schedule();}
  function zoom(factor,ratio=.5){const at=lo+ratio*(hi-lo),span=(hi-lo)*factor;bounds(at-span*ratio,at+span*(1-ratio));}
  function reset(){bounds(full[0],full[1]);viewport.scrollTop=0;}
  function focus(index){selected=index;const f=frames[index];bounds(f[2],f[3]);viewport.scrollTop=Math.max(0,(f[1]-2)*ROW);$('detail').textContent=describe(index);}
  function hit(event){const rect=canvas.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top,depth=Math.floor((y+viewport.scrollTop)/ROW),value=lo+(x-PAD)/(width-2*PAD)*(hi-lo);if(depth<0||depth>=rows.length)return null;const row=rows[depth],at=firstAfter(row,value)-1;if(at<0)return null;const index=row[at];return value<frames[index][3]?index:null;}
  function tooltip(event){const index=hit(event),tip=$('tooltip');if(index===null){tip.hidden=true;return;}tip.textContent=describe(index);tip.hidden=false;tip.style.left=Math.min(window.innerWidth-tip.offsetWidth-12,event.clientX+14)+'px';tip.style.top=Math.max(8,Math.min(window.innerHeight-tip.offsetHeight-12,event.clientY+16))+'px';}
  function layout(){const maxHeight=Math.max(240,window.innerHeight-300);viewport.style.height=Math.min((data.depth+(events.length?1:0))*ROW+8,maxHeight)+'px';height=viewport.clientHeight;$('spacer').style.height=(data.depth+(events.length?1:0))*ROW+8+'px';width=viewport.clientWidth;const dpr=window.devicePixelRatio||1;canvas.width=Math.ceil(width*dpr);canvas.height=Math.ceil(height*dpr);canvas.style.width=width+'px';canvas.style.height=height+'px';canvas.style.top=viewport.scrollTop+'px';ctx.setTransform(dpr,0,0,dpr,0,0);schedule();}
  $('zoom-in').onclick=()=>zoom(.5);$('zoom-out').onclick=()=>zoom(2);$('reset').onclick=reset;$('back').onclick=()=>{const previous=history.pop();if(previous)bounds(...previous,false);};$('focus').onclick=()=>{if(selected!==null)focus(selected);};
  canvas.addEventListener('wheel',event=>{event.preventDefault();const x=event.clientX-canvas.getBoundingClientRect().left;zoom(Math.exp(Math.max(-1,Math.min(1,event.deltaY*.002))),Math.max(0,Math.min(1,(x-PAD)/(width-2*PAD))));},{passive:false});
  canvas.addEventListener('pointerdown',event=>{if(event.button!==0)return;canvas.focus();drag={x:event.clientX,y:event.clientY,lo,hi,moved:false};canvas.setPointerCapture(event.pointerId);$('tooltip').hidden=true;});
  canvas.addEventListener('pointermove',event=>{if(!drag){tooltip(event);return;}const dx=event.clientX-drag.x;if(Math.abs(dx)>3||Math.abs(event.clientY-drag.y)>3)drag.moved=true;if(drag.moved){const shift=dx/(width-2*PAD)*(drag.hi-drag.lo);bounds(drag.lo-shift,drag.hi-shift,false);}});
  canvas.addEventListener('pointerup',event=>{if(!drag)return;if(!drag.moved){selected=hit(event);if(selected!==null)$('detail').textContent=describe(selected);schedule();}else if(history.length<500)history.push([drag.lo,drag.hi]);drag=null;});canvas.addEventListener('pointercancel',()=>drag=null);canvas.addEventListener('pointerleave',()=>{$('tooltip').hidden=true;});
  canvas.addEventListener('dblclick',event=>{const index=hit(event);if(index===null)reset();else focus(index);});
  canvas.addEventListener('keydown',event=>{let handled=true;if(['+','='].includes(event.key))zoom(.5);else if(['-','_'].includes(event.key))zoom(2);else if(event.key==='Home')reset();else if(event.key==='ArrowLeft')bounds(lo-(hi-lo)*.2,hi-(hi-lo)*.2);else if(event.key==='ArrowRight')bounds(lo+(hi-lo)*.2,hi+(hi-lo)*.2);else if(event.key==='Escape'){selected=null;$('tooltip').hidden=true;schedule();}else handled=false;if(handled)event.preventDefault();});
  $('search').addEventListener('input',()=>{query=$('search').value.toLocaleLowerCase().trim();matches=[];if(query)frames.forEach((f,i)=>{if(names[f[0]].toLocaleLowerCase().includes(query))matches.push(i);});matchPosition=-1;$('match-count').textContent=query?matches.length+' 处':'';schedule();});
  function match(direction){if(!matches.length)return;matchPosition=matchPosition<0?(direction>0?0:matches.length-1):(matchPosition+direction+matches.length)%matches.length;focus(matches[matchPosition]);$('match-count').textContent=(matchPosition+1)+' / '+matches.length;}
  $('next-match').onclick=()=>match(1);$('previous-match').onclick=()=>match(-1);$('search').addEventListener('keydown',e=>{if(e.key==='Enter')match(e.shiftKey?-1:1);});
  viewport.addEventListener('scroll',()=>{canvas.style.top=viewport.scrollTop+'px';$('tooltip').hidden=true;schedule();});window.addEventListener('resize',layout);layout();
  document.documentElement.dataset.flameReady='true';
})();
