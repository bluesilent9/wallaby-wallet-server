const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path'),root=path.resolve(process.argv[2]);
const {N}=require('./dom_fixture.cjs');
const c={window:{},Node:N,document:{createElement:t=>new N(t),createElementNS:(_,t)=>new N(t),createTextNode:s=>String(s)},Date,setTimeout,clearTimeout,setInterval:()=>1,clearInterval:()=>{}};
vm.createContext(c);const app=fs.readFileSync(path.join(root,'app.js'),'utf8');vm.runInContext(app.slice(app.indexOf('const icons='),app.indexOf('function humanDate(')),c);vm.runInContext(fs.readFileSync(path.join(root,'vaults.js'),'utf8'),c);
const all=n=>n&&typeof n==='object'?[n,...n.children.flatMap(all)]:[],kinds=n=>all(n).filter(n=>n.attrs?.['data-resource-icon']).map(n=>n.attrs['data-resource-icon']);
(async()=>{
 const w={id:'v',name:'Example vault',state:'green',countdown:'2 Hours',issues:[],vault_sats:120000,outside_sats:0,balance_verified:true,balance_available:true,funding_status:'locked',signatures:[{required:3,total:5}],disc_only:true,smsf:true};
 let response={checked_utc:new Date().toISOString(),wallets:[w],loading:false};
 const ctx={el:c.el,icon:c.icon,resourceIcons:c.resourceIcons,active:()=>true,refresh:()=>{},api:async()=>({json:async()=>response})};
 async function render(){c.window.WallabyVaults.enter(ctx);await new Promise(r=>setImmediate(r));return all(c.window.WallabyVaults.view(ctx));}
 let nodes=await render(),card=nodes.find(n=>n.tag==='article');
 assert.deepEqual(kinds(card),kinds(c.resourceIcons({...w,has_vault:true,multisig:w.signatures,kind:'descriptor'})));
 assert.equal(kinds(card)[0],'wallet');assert.equal(kinds(card).at(-1),'disc');assert(kinds(card).includes('multisig'));assert(kinds(card).includes('smsf'));assert(card.className.includes('balance-card'));
 assert(nodes.find(n=>n.className==='balance-grid vault-grid'));
 w.vault_sats=0;w.state='amber';w.countdown='Not funded';w.funding_status='ready_to_fund';nodes=await render();assert(nodes.some(n=>n.tag==='article'),'Verified empty vault must remain visible');assert(nodes.find(n=>n.tag==='article').className.includes('vault-amber'));
 w.countdown='Unlocked';w.state='red';w.funding_status='unlocked';nodes=await render();assert(nodes.some(n=>n.tag==='article'),'Expired zero balance must remain visible');assert(nodes.find(n=>n.tag==='article').className.includes('vault-red'));assert(nodes.some(n=>n.children?.includes('Unlocked')));
 w.balance_verified=false;w.balance_available=false;w.issues=['Current balance unavailable'];nodes=await render();assert(nodes.some(n=>n.tag==='article'),'Unknown balance must remain visible');
 w.balance_available=true;w.balance_verified=true;w.outside_sats=900;nodes=await render();assert(nodes.some(n=>n.tag==='article'),'Outside-policy funds must remain visible');
 w.outside_sats=0;w.vault_sats=120000;w.state='red';w.funding_status='unlocked';w.issues=[];nodes=await render();assert(nodes.find(n=>n.tag==='article').className.includes('vault-red'));
 console.log('PASS: shared ordered icons, Wallets grid/cards, verified empty vault visibility and colours before/after expiry, unknown and partial protection retained, funded expiry red.');
})().catch(e=>{console.error(e);process.exitCode=1;});
