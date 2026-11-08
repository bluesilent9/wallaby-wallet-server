class N{
 constructor(tag,a={},...children){this.tag=tag;this.attrs={};this.children=[];this.events={};Object.assign(this,a);this.className=a.className||a.class||'';this.classList={add:(...names)=>{this.className=[...new Set([...(this.className||'').split(' '),...names])].join(' ')},remove:(...names)=>{this.className=(this.className||'').split(' ').filter(x=>!names.includes(x)).join(' ')}};this.append(...children.flat());}
 append(...values){for(const v of values.flat(Infinity)){if(v==null)continue;if(typeof v==='object')v.parent=this;this.children.push(v);}}
 replaceChildren(...v){this.children=[];this.append(...v);}
 setAttribute(k,v){this.attrs[k]=v;if(k==='class')this.className=v;}
 addEventListener(k,v){this.events[k]=v;}
 querySelector(s){return all(this).slice(1).find(n=>s.startsWith('.')?(n.className||'').split(' ').includes(s.slice(1)):n.tag===s)||null;}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(x=>x!==this);}
}
function all(n){return n&&typeof n==='object'?[n,...(n.children||[]).flatMap(all)]:[];}
function el(...args){return new N(...args);}
module.exports={N,el,all};
