/* AGPL-3.0. Adapted from Mempool's blockchain-blocks.component.ts and
 * component template; copyright 2019-2026 Mempool contributors.
 * Angular StateService/CacheService are replaced by Wallaby node snapshots.
 * Corresponding source and original component: /source.zip. */
(function(root){'use strict';
// Compact display only; the node's full rate remains in data and the hover text.
function displayRate(value){const fees=typeof module!=='undefined'&&module.exports?require('./fees.js'):root.WallabyFees;return fees.displayRate(value);}
function blockStyle(block,index,width=125){
 const padding=.24*width,offset=width+padding;
 // Upstream getStyleForBlock's weight-driven fill and placement.
 const free=100-(Number(block.weight||0)/4000000)*100;
 return {left:offset*index+'px',background:`linear-gradient(var(--secondary) ${Math.max(0,free)}%,var(--mainnet-alt) ${Math.max(0,free)}%,var(--primary) 100%)`};
}
function volumeGeometry(weight){
 const fraction=weight===null||weight===undefined?null:Math.max(0,Math.min(1,Number(weight)/4000000));
 const y=164-120*(fraction||0),back=y-24;
 return {fraction,front:`28,${y} 148,${y} 148,164 28,164`,side:`8,${back} 28,${y} 28,164 8,140`,top:`8,${back} 128,${back} 148,${y} 28,${y}`};
}
function volume(el,weight){
 const make=(tag,attrs)=>{if(typeof document==='undefined')return el(tag,attrs);const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);return n;};
 const g=volumeGeometry(weight),svg=make('svg',{viewBox:'0 0 160 174',class:'block-volume','aria-hidden':'true',style:'animation-delay:-'+(Date.now()%2000)/1000+'s'});
 const poly=(points,cls)=>make('polygon',{points,class:cls});
 svg.append(poly('8,20 128,20 148,44 28,44','cube-shell'),poly('8,20 28,44 28,164 8,140','cube-shell'),poly('28,44 148,44 148,164 28,164','cube-shell'));
 if(g.fraction>0){const fill=make('g',{class:'cube-fill'});fill.append(poly(g.side,'cube-fill-side'),poly(g.front,'cube-fill-front'),poly(g.top,'cube-fill-top'));svg.append(fill);}
 svg.append(make('path',{d:'M8 20H128L148 44V164H28L8 140V20L28 44H148M28 44V164',class:'cube-outline'}));return svg;
}
function markerIndex(blocks,height){return blocks.findIndex(b=>b.height===height);}
function confirmations(data,state){
 const known=state.tracked;if(!known||known.status!=='confirmed')return 0;
 if(Number.isSafeInteger(known.confirmations)&&known.confirmations>0)return known.confirmations;
 const tip=Number(data.recent_blocks?.[0]?.height),height=Number(known.block_height);return Number.isSafeInteger(tip)&&Number.isSafeInteger(height)?Math.max(0,tip-height+1):0;
}
function confirmationClock(el,data,state){
 const count=confirmations(data,state),entered=/^[0-9a-f]{64}$/i.test((state.input||state.tracked?.txid||'').trim()),label=count.toLocaleString('en-AU')+' Confirmation'+(count===1?'':'s'),tone=count>=6?'green':count>=3?'amber':count>0?'red':'empty';
 const face=el('div',{class:'confirmation-clock clock-'+tone,role:'img',tabindex:0,'aria-label':entered?label:'Transaction confirmation clock','data-confirmations':count,style:'--confirmation-sweep:'+Math.min(6,count)*60+'deg'});
 const make=(tag,attrs)=>{if(typeof document==='undefined')return el(tag,attrs);const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);return n;};
 const ticks=make('svg',{viewBox:'0 0 100 100','aria-hidden':'true',class:'confirmation-ticks'});ticks.append(make('circle',{cx:50,cy:50,r:48,fill:'none'}));
 for(let i=0;i<12;i++){const a=i*Math.PI/6;ticks.append(make('path',{d:'M'+(50+42*Math.sin(a))+','+(50-42*Math.cos(a))+'L'+(50+47*Math.sin(a))+','+(50-47*Math.cos(a))}));}face.append(ticks);
 if(entered)face.append(el('span',{class:'confirmation-tip',role:'tooltip'},label));return face;
}
function view({el,button,data,state,changed}){
 const section=el('section',{class:'node-block-panel','aria-label':'Pending and mined blocks'}),empty=data.mempool_transactions===0,pending=Array.from({length:3},(_,i)=>(data.projected_blocks||[])[i]||{weight:empty?0:null,tx_count:empty?0:null,median_rate:null,estimated_minutes:(i+1)*10}),mined=(data.recent_blocks||[]).slice(0,3);
 const top=el('div',{class:'node-block-title'},el('h2',{},'Your node’s block view'),el('span',{class:'subtle'},data.source||'Waiting for a connected node'));
 const content=el('div',{class:'node-block-track'}),future=el('div',{class:'node-block-half pending-blocks'}),past=el('div',{class:'node-block-half mined-blocks'});
 const create=(b,i,isPending)=>{
  const rate=b.median_rate,known=state.tracked,marked=known&&(isPending?(known.status==='mempool'||known.status==='confirmed'&&known.block_height>Number(mined[0]?.height))&&i===0:known.status==='confirmed'&&known.block_height===b.height);
  const cube=el('div',{class:'bitcoin-block '+(isPending?'projected-block':'mined-block'),'data-block-height':isPending?'pending-'+i:b.height,tabindex:0},el('strong',{class:'node-block-number'},isPending?'Next '+(i+1):Number(b.height).toLocaleString('en-AU')),el('span',{class:'node-block-main'},state.mode==='size'?(b.vsize?Math.round(b.vsize/1000)+' kvB':b.size?Math.round(b.size/1000)+' kB':'Size unavailable'):isPending?el('span',{class:'node-block-rate'},displayRate(rate)):new Date(b.timestamp*1000).toLocaleTimeString('en-AU',{hour:'2-digit',minute:'2-digit',hour12:false})),isPending&&state.mode!=='size'?el('span',{class:'node-block-rate-unit'},'sats/vB'):null,el('span',{class:'transaction-count'},b.tx_count!==null&&b.tx_count!==undefined?Number(b.tx_count).toLocaleString('en-AU')+' transactions':''),el('span',{class:'time-difference'},isPending?'~'+b.estimated_minutes+' minutes':new Date(b.timestamp*1000).toLocaleDateString('en-AU')));
  cube.append(volume(el,b.weight));
  if(marked)cube.append(el('span',{class:'node-track-marker',title:known.txid,'aria-label':'Tracked transaction'},'▼'));
  cube.title=isPending?'Estimated rate: '+(rate??'unavailable')+' sats/vB. Projected from ancestor packages in the local mempool; confirmation timing is uncertain.':b.hash;
  return cube;
 };
 future.append(el('div',{class:'block-half-label'},'PENDING · ESTIMATED'),...pending.map((b,i)=>create(b,i,true)));
 past.append(el('div',{class:'block-half-label'},'MINED LOCAL TIME'),...mined.map((b,i)=>create(b,i,false)));
 const mode=button(state.mode==='size'?'Show time / fees':'Show sizes','outline',()=>{state.mode=state.mode==='size'?'fees':'size';changed();});
 const centre=el('div',{class:'node-block-divider'},el('div',{class:'block-controls'},confirmationClock(el,data,state),mode));content.append(future,centre,past);section.append(top,content);
 if(state.tracked?.status==='mempool')section.append(el('p',{class:'subtle'},'Tracked transaction is in the local mempool. The marker indicates the next block; inclusion in that block is not guaranteed.'));
 if(!(data.projected_blocks||[]).length&&!data.projection_error)section.append(el('p',{class:'subtle'},data.loading?(data.projection_progress?'Reading local mempool: '+Number(data.projection_progress.received).toLocaleString()+' of '+Number(data.projection_progress.total).toLocaleString()+' transactions…':'Waiting for the local mempool…'):empty?'The local mempool is empty.':'Mempool projection unavailable. Select Refresh estimates to retry.'));
 if(data.projection_error)section.append(el('p',{class:'subtle'},data.projection_error));
 section._blockSnapshot=snapshot(data,state);section._blockData=data;return section;
}
function snapshot(data,state){return JSON.stringify([data.projected_blocks,data.recent_blocks,data.source,data.loading,data.projection_error,data.mempool_transactions,state.mode,state.tracked,state.input]);}
function place(parent,node,before){if(node===before)return;if(typeof parent.moveBefore==='function'&&node.isConnected&&parent.isConnected)parent.moveBefore(node,before);else parent.insertBefore(node,before);}
function syncTree(old,fresh){
 for(const a of [...old.attributes])if(!fresh.hasAttribute(a.name))old.removeAttribute(a.name);
 for(const a of [...fresh.attributes])if(!(a.name==='style'&&old.classList.contains('block-volume')))old.setAttribute(a.name,a.value);
 const candidates=[...old.childNodes],used=new Set();
 for(const [i,next]of [...fresh.childNodes].entries()){
  const key=n=>n.nodeType===1?n.nodeName+':'+(n.getAttribute('class')||''):'#text';let prior=candidates.find(n=>!used.has(n)&&key(n)===key(next));
  if(!prior)prior=next.cloneNode(true);else if(next.nodeType===3){if(prior.textContent!==next.textContent)prior.textContent=next.textContent;}else syncTree(prior,next);
  used.add(prior);if(old.childNodes[i]!==prior)place(old,prior,old.childNodes[i]||null);
 }
 for(const child of [...old.childNodes])if(!used.has(child))child.remove();
}
function update(section,options){
 let {data,state}=options;
 // A partial or failed snapshot cannot erase the last known block display.
 if(!data.projected_blocks?.length&&section._blockData?.projected_blocks?.length)data={...data,projected_blocks:section._blockData.projected_blocks};
 if(section._blockData?.recent_blocks?.length){const recent=new Map((data.recent_blocks||[]).map(b=>[b.height,b]));for(const b of section._blockData.recent_blocks)if(!recent.has(b.height))recent.set(b.height,b);data={...data,recent_blocks:[...recent.values()].sort((a,b)=>b.height-a.height).slice(0,3)};}
 if(section._blockSnapshot===snapshot(data,state))return section;
 const fresh=view({...options,data}),track=section.querySelector('.node-block-track'),nextTrack=fresh.querySelector('.node-block-track'),future=track.querySelector('.pending-blocks'),past=track.querySelector('.mined-blocks');
 const old=[...track.querySelectorAll('.bitcoin-block')],rects=new Map(old.map(n=>[n,n.getBoundingClientRect()])),pending=old.filter(n=>n.classList.contains('projected-block')),mined=old.filter(n=>n.classList.contains('mined-block'));
 const newCards=[...nextTrack.querySelectorAll('.bitcoin-block')],nextMined=newCards.filter(n=>n.classList.contains('mined-block')),tip=Number(mined[0]?.dataset.blockHeight),nextTip=Number(nextMined[0]?.dataset.blockHeight),advance=nextTip>tip?Math.min(3,nextTip-tip):0,used=new Set(),futureCards=[],pastCards=[];
 for(const next of newCards){
  const projected=next.classList.contains('projected-block'),index=Number(next.dataset.blockHeight?.replace('pending-',''));let prior=projected?pending[index+advance]:mined.find(n=>n.dataset.blockHeight===next.dataset.blockHeight&&n.title===next.title)||(advance?pending[Number(next.dataset.blockHeight)-tip-1]:null);
  if(prior&&used.has(prior))prior=null;
  if(prior){used.add(prior);for(const a of prior.getAnimations?.()||[])a.cancel();syncTree(prior,next);}
  (projected?futureCards:pastCards).push(prior||next);
 }
 const motion=typeof matchMedia==='function'&&!matchMedia('(prefers-reduced-motion: reduce)').matches&&typeof section.animate==='function',exiting=old.filter(n=>!used.has(n));
 if(motion&&advance&&exiting.length){const layer=options.el('div',{class:'node-block-half block-exit-layer','aria-hidden':'true'}),bounds=section.getBoundingClientRect();section.append(layer);for(const cube of exiting){const r=rects.get(cube);cube.style.position='absolute';cube.style.left=(r.left-bounds.left+section.scrollLeft)+'px';cube.style.top=(r.top-bounds.top+section.scrollTop)+'px';place(layer,cube,null);const a=cube.animate([{transform:'translateX(0)',opacity:1},{transform:'translateX(160px)',opacity:0}],{duration:800,easing:'ease-in',fill:'forwards'});a.onfinish=()=>{cube.remove();if(!layer.children.length)layer.remove();};}}
 // Place survivors directly between connected parents. Never detach or clear
 // the track, cubes, their SVG faces, or their transaction markers on refresh.
 for(const [parent,cards]of [[future,futureCards],[past,pastCards]])for(const [i,cube]of cards.entries())if(parent.children[i+1]!==cube)place(parent,cube,parent.children[i+1]||null);
 for(const [parent,cards]of [[future,futureCards],[past,pastCards]])for(const cube of [...parent.querySelectorAll('.bitcoin-block')])if(!cards.includes(cube))cube.remove();
 syncTree(section.querySelector('.node-block-title'),fresh.querySelector('.node-block-title'));
 syncTree(track.querySelector('.confirmation-clock'),nextTrack.querySelector('.confirmation-clock'));
 const mode=track.querySelector('.block-controls .button');mode.replaceWith(nextTrack.querySelector('.block-controls .button'));
 const notes=[...section.children].filter(n=>n!==track&&!n.classList.contains('node-block-title')&&!n.classList.contains('block-exit-layer'));for(const n of notes)n.remove();for(const n of [...fresh.children])if(!n.classList.contains('node-block-track')&&!n.classList.contains('node-block-title'))section.append(n);
 if(motion)for(const cube of [...futureCards,...pastCards]){const before=rects.get(cube),after=cube.getBoundingClientRect();if(before){const dx=before.left-after.left,dy=before.top-after.top;if(Math.abs(dx)+Math.abs(dy)>1)cube.animate([{transform:`translate(${dx}px,${dy}px)`},{transform:'translate(0,0)'}],{duration:800,easing:'cubic-bezier(.2,.7,.2,1)'});}else cube.animate([{transform:'translateX(-100px)',opacity:0},{transform:'translateX(0)',opacity:1}],{duration:800,easing:'ease-out'});}
 section._blockSnapshot=snapshot(data,state);section._blockData=data;return section;
}
const api={view,update,blockStyle,markerIndex,displayRate,volumeGeometry,confirmations,confirmationClock};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.WallabyNodeBlocks=api;
})(typeof globalThis!=='undefined'?globalThis:this);
