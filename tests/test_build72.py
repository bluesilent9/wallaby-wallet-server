"""Refresh requires all immutable signer accounts, not merely a signing quorum."""
import copy,sys,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_build27 as fixture
from vendor.embit import bip32
from vendor.embit.descriptor.checksum import checksum
from descriptor_store import clean_wallet,DescriptorStore
from preferences import resource_id,FamilyStore
from vault_refresh import start,signers,cancel
from refresh_handoff_fixture import finish
from builder_destinations import Destinations

class Refresh(unittest.TestCase):
 def setUp(self):
  self.f=fixture.DestinationsTest();self.f.setUp();self.addCleanup(self.f.doCleanups);self.hub=self.f.hub;self.checks=self.hub.disc_signers;self.addCleanup(self.checks.close)
  self.accounts={self.f.a['node_id']:[],self.f.b['node_id']:[]};self.calls=[];self.busy=False
  masters=[bip32.HDKey.from_seed(('Build72 invented key '+str(i)).encode()).to_public().to_base58() for i in range(5)]
  def raw(name,bodies):return {'wallet_name':name,'descriptors':[{'desc':body+'#'+checksum(body),'range':[0,99],'next_index':1,'active':True,'internal':i==1,'timestamp':1} for i,body in enumerate(bodies)]}
  monitor=raw('Logical vault',['wsh(and_v(v:after(1000000),multi(3,'+','.join(k+'/'+str(branch)+'/*' for k in masters)+')))' for branch in (0,1)])
  self.f.wallet=clean_wallet(monitor);self.f.wallet['setup_name']='Logical vault';self.f.wallet['node_sources']=[{'node_id':self.f.a['node_id'],'hostname':'first','wallet_name':'Logical vault'}];self.f.rid=resource_id('descriptor',self.f.wallet['id']);DescriptorStore(self.f.config).replace_node_wallets([self.f.wallet])
  for i,key in enumerate(masters):
   node=list(self.accounts)[i%2];name='Role '+str(i+1);w=clean_wallet(raw(name,['wpkh('+key+'/'+str(branch)+'/*)' for branch in (0,1)]));self.accounts[node].append({'name':name,'id':w['id'],'raw':w['raw'],'private_keys_enabled':True,'scanning':False,**({'archive_id':str(i)*64,'signing_only':True} if i>=3 else {})})
  for node,accounts in self.accounts.items():
   self.hub.caps[node]={'partial_signing','wallet_relay_v1','wallet_policy_refresh_relay_v1'};self.hub.inventories[node]['wallets']=copy.deepcopy(accounts)+[{'name':'Logical vault','raw':monitor,'private_keys_enabled':True}]
  self.hub.registry.rpc.call=self.rpc
  self.work,self.dest=self.f.transaction()
  with patch.object(self.checks,'ensure',return_value={}):start(self.hub,self.f.user,self.f.rid,self.dest['id'])
  self.w=self.work.owned(self.f.user,'wallet');self.scan()
  from relay_fixtures import signed_mesh
  signed_mesh(self.f)
 def rpc(self,node,method,params=None,wallet=None,**kw):
  self.calls.append((method,wallet,kw.get('priority')))
  if self.busy:return {'state':'error'}
  if wallet=='Logical vault' and method in ('listdescriptors','listreceivedbyaddress'):return {'state':'succeeded','result':self.f.wallet['raw'] if method=='listdescriptors' else []}
  if method=='listwallets':value=[a['name'] for a in self.accounts[node]]
  else:
   a=next(a for a in self.accounts[node] if a['name']==wallet)
   if method=='getwalletinfo':value={'walletname':a['raw']['wallet_name'],'private_keys_enabled':a['private_keys_enabled'],'scanning':a['scanning'],**({'wallaby_storage':'disc','wallaby_archive_id':a['archive_id']} if a.get('archive_id') else {})}
   elif method=='listdescriptors':value=a['raw']
   else:raise AssertionError(method)
  return {'state':'succeeded','result':value}
 def scan(self):
  for node,c in self.checks.connections().items():
   self.checks.rows[node]={'state':'checking','private_accounts':True,'token':c['token'],'hostname':c['hostname'],'active':True,'wallets':[]};self.checks.scan(node,c['token'])
 def test_all_five_signers_and_both_storage_modes_are_detected(self):
  state=signers(self.hub,self.w);self.assertTrue(state['complete']);self.assertEqual(len(state['roles']),5);self.assertEqual(sorted(r['storage'] for r in state['roles']),['disc','disc','node','node','node']);self.assertTrue(all(r['detected'] and r['hostname'] in ('first','second') for r in state['roles']));self.assertTrue(all(c[2]==0 for c in self.calls))
 def test_missing_one_disc_blocks_even_with_four_available_keys(self):
  node=next(n for n,aa in self.accounts.items() if any(a['name']=='Role 5' for a in aa));self.accounts[node]=[a for a in self.accounts[node] if a['name']!='Role 5'];self.scan();s=signers(self.hub,self.w);self.assertFalse(s['complete']);missing=[r for r in s['roles'] if not r['detected']];self.assertEqual(len(missing),1);self.assertEqual(missing[0]['hostname'],'Signer not detected');self.assertEqual(missing[0]['storage'],'');before=self.work.read();dest=Destinations(self.f.config).read();requests=self.hub.read()
  with self.assertRaisesRegex(ValueError,'Every existing signer'):finish(self.hub,self.f.user,1000100)
  self.assertEqual(self.work.read(),before);self.assertEqual(Destinations(self.f.config).read(),dest);self.assertEqual(self.hub.read(),requests)
 def test_watch_only_disc_does_not_count(self):
  self.accounts[self.f.b['node_id']][-1]['private_keys_enabled']=False;self.scan();self.assertFalse(signers(self.hub,self.w)['complete'])
 def test_public_monitor_with_private_wallet_flag_cannot_supply_all_keys(self):
  for node in self.accounts:self.accounts[node]=[{'name':'Logical vault','raw':self.f.wallet['raw'],'private_keys_enabled':True,'scanning':False}]
  self.scan();self.assertFalse(any(r['detected'] for r in signers(self.hub,self.w)['roles']))
 def test_disconnect_and_busy_never_reuse_stale_signer_proof(self):
  self.busy=True;self.scan();self.assertFalse(signers(self.hub,self.w)['complete']);self.busy=False;self.scan();self.assertTrue(signers(self.hub,self.w)['complete']);self.f.registry.connections.pop(self.f.b['connection_token']);self.assertFalse(signers(self.hub,self.w)['complete'])
 def test_expired_scan_is_not_ready(self):
  for row in self.checks.rows.values():row['verified_at']=time.monotonic()-16
  self.assertFalse(signers(self.hub,self.w)['complete'])
 def test_both_agent_and_storage_changes_are_rejected_by_save(self):
  for field,value in (('node_id',self.f.a['node_id']),('storage','disc'),('name','Other signer')):
   draft=copy.deepcopy(self.w['draft']);draft['roles'][0][field]=value
   with self.assertRaisesRegex(ValueError,'cannot be replaced'):self.work.save(self.f.user,'wallet',{'id':self.w['id'],'revision':self.w['revision'],'draft':draft})
 def test_vault_estimator_changes_can_still_be_saved(self):
  draft=copy.deepcopy(self.w['draft']);draft['vault']={'height':1000100};saved=self.work.save(self.f.user,'wallet',{'id':self.w['id'],'revision':self.w['revision'],'draft':draft});self.assertEqual(saved['draft']['vault'],draft['vault']);self.assertEqual(saved['draft']['roles'],self.w['draft']['roles'])
 def test_success_preserves_all_keys_and_names_and_does_not_create_new_keys(self):
  sessions=copy.deepcopy(self.hub.wallet_builder.read()['sessions'])
  result=finish(self.hub,self.f.user,1000100)
  dest=Destinations(self.f.config).get(result['destination']);from policy_accounts import keys
  self.assertEqual(keys({'descriptors':dest['descriptors']}),keys(self.f.wallet['raw']));self.assertEqual(self.hub.wallet_builder.read()['sessions'],sessions);self.assertNotIn('wallet',self.work.read()['workspaces']);self.assertEqual(dest['archive_roles'],[])
 def test_cancel_with_missing_signer_leaves_transaction_unchanged(self):
  before=copy.deepcopy(self.work.read()['workspaces']['transaction']);self.accounts[self.f.a['node_id']]=[];self.scan();cancel(self.hub,self.f.user);self.assertEqual(self.work.read()['workspaces']['transaction'],before)

 def test_three_refreshes_keep_same_signers_and_return_only_new_destination(self):
  from vendor.embit.descriptor import Descriptor
  from multisig_psbt import witness_policy
  from policy_accounts import keys
  original_keys=keys(self.f.wallet['raw']);original_sessions=copy.deepcopy(self.hub.wallet_builder.read());addresses=set()
  for step in range(3):
   before=copy.deepcopy(self.work.read()['workspaces']['transaction']['draft']);result=finish(self.hub,self.f.user,1000100+step*100)
   self.assertEqual(result['return_to'],'builder');dest=Destinations(self.f.config).get(result['destination']);addresses.add(dest['address']);self.assertEqual(keys({'descriptors':dest['descriptors']}),original_keys)
   policy=witness_policy(Descriptor.from_string(dest['descriptors'][0]['desc']).derive(dest['index']).witness_script().data);self.assertEqual(policy['threshold'],3);self.assertEqual(policy['height'],1000100+step*100)
   tx=self.work.read()['workspaces']['transaction'];self.assertEqual(tx['draft']['edges'][0]['from'],before['edges'][0]['from']);self.assertEqual(tx['draft']['edges'][0]['to'],dest['id']);self.assertEqual(tx['draft']['edges'][0]['amount_sats'],before['edges'][0]['amount_sats']);self.assertEqual(tx['operations'],[]);self.assertEqual(dest['base'],self.f.rid)
   self.assertEqual(self.hub.wallet_builder.read(),original_sessions);self.assertTrue(all(r['kind']=='wallet_policy_refresh' for r in self.hub.read()['requests'].values()))
   self.work.finish(self.f.user,'transaction')
   if step<2:
    raw=copy.deepcopy(self.f.wallet['raw']);raw['descriptors'].extend(dest['descriptors']);self.f.wallet=clean_wallet(raw);self.f.wallet['setup_name']='Logical vault';self.f.wallet['node_sources']=[{'node_id':self.f.a['node_id'],'hostname':'first','wallet_name':'Logical vault'}];self.f.rid=resource_id('descriptor',self.f.wallet['id']);DescriptorStore(self.f.config).replace_node_wallets([self.f.wallet])
    for inv in self.hub.inventories.values():
     for account in inv['wallets']:
      if account['name']=='Logical vault':account['raw']=raw
    self.work,self.dest=self.f.transaction()
    with patch.object(self.checks,'ensure',return_value={}):start(self.hub,self.f.user,self.f.rid,self.dest['id'])
    self.w=self.work.owned(self.f.user,'wallet');self.scan()
  from relay_fixtures import signed_mesh
  signed_mesh(self.f);self.assertEqual(self.w['draft']['name'],'Logical vault')
  self.assertEqual(len(addresses),3)

 def test_http_poll_reports_detected_roles_and_finish_rejects_missing_signer(self):
  import threading,http.client,json
  from launch_wallaby_wallet_server import create_server
  server,pool=create_server(Path(self.f.tmp.name)/'browser',0,self.f.config);pool.nodes.health.closed=True;pool.nodes=self.f.registry;thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();session=pool.create();session.user_id=self.f.user
  def request(method,path,body=None):
   c=http.client.HTTPConnection('::1',server.server_port,timeout=5);c.request(method,path,json.dumps(body) if body is not None else None,{'X-Session-Token':session.token,'Content-Type':'application/json'});r=c.getresponse();data=json.loads(r.read());c.close();return r.status,data
  try:
   with patch.object(self.checks,'ensure',return_value={}) as ensure:
    code,data=request('GET','/api/wallet-builder');self.assertEqual(code,200);self.assertTrue(data['renewal_signers']['complete']);self.assertEqual(len(data['renewal_signers']['roles']),5);ensure.assert_not_called()  # Status is passive; visible-page discovery starts checks.
    self.accounts[self.f.a['node_id']]=[];self.scan();code,data=request('GET','/api/wallet-builder');self.assertFalse(data['renewal_signers']['complete'])
    code,data=request('POST','/api/wallet-builder/renewal-finish',{'height':1000100});self.assertEqual(code,400);self.assertIn('Every existing signer',data['error']);self.assertTrue(self.work.owned(self.f.user,'wallet')['renewal'])
  finally:server.shutdown();server.server_close();thread.join(3)

 def test_fresh_public_keys_override_old_cached_wallet_with_same_name(self):
  # A loaded wallet with the same filename but different keys cannot inherit
  # private-signer availability from the old inventory entry.
  node=self.f.a['node_id'];a=self.accounts[node][0];a['raw']=copy.deepcopy(self.accounts[self.f.b['node_id']][0]['raw']);a['raw']['wallet_name']=a['name'];self.scan();state=signers(self.hub,self.w);self.assertFalse(state['complete']);self.assertEqual(sum(r['detected'] for r in state['roles']),4)
 def test_refresh_does_not_depend_on_full_inventory_for_loaded_accounts(self):
  self.hub.inventories.clear();self.scan();self.assertTrue(signers(self.hub,self.w)['complete'])
