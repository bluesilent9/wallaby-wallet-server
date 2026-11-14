const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
class N{constructor(tag,a={},...children){this.tag=tag;Object.assign(this,a);this.children=children.flat(Infinity).filter(x=>x!=null)}append(...c){this.children.push(...c.filter(x=>x!=null))}}
const el=(...a)=>new N(...a),all=n=>typeof n==='object'&&n?[n,...(n.children||[]).flatMap(all)]:[],text=n=>typeof n==='object'&&n?(n.children||[]).map(text).join(' '):String(n);
const c={window:{},document:{body:{append:()=>{}}}};vm.createContext(c);vm.runInContext(fs.readFileSync(path.resolve(process.argv[2],'wallet_processes.js'),'utf8'),c);
const base={el,button:(t,cls,onclick)=>el('button',{onclick},t),cancelExtinction:()=>{}},a={node_id:'done',hostname:'Verified node',state:'complete',verified:true,colour:'green'},b={node_id:'wait',hostname:'Pending node',state:'pending',verified:false,colour:'amber'};
const render=(archives,holders=[])=>c.window.WallabyProcesses.view({...base,retirements:[{name:'Old wallet',state:'pending',archives,holders,can_restore:true}]});
let p=render([a,b]);const rows=all(p).filter(n=>n.tag==='tr');assert.equal(rows.length,2);assert(text(p).includes('Pending node'));assert(!text(p).includes('Verified node'));assert.equal(all(p).filter(n=>n.tag==='button'&&text(n)==='Restore Wallet').length,1);
p=render([{...a,verified:false}]);assert(text(p).includes('Preserve extinct history'));p=render([{...a,state:'pending'}]);assert(text(p).includes('Preserve extinct history'));
p=render([a],[{node_id:'other',hostname:'Other node',state:'pending',message:'Waiting for local deletion approval',colour:'red'}]);assert(!text(p).includes('Preserve extinct history'));assert(text(p).includes('Delete empty original wallet'));assert(text(p).includes('Other node'));
console.log('PASS: verified completed preservation disappears, unverified/pending work and other-node deletion remain visible; actions remain attached.');
