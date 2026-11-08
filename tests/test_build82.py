"""Saved ownership, nonblocking planning history, and durable linked refreshes."""
import copy,json,threading,unittest,http.client
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
import test_build8 as fixtures
from launch_wallaby_wallet_server import Session,create_server
from descriptor_store import DescriptorStore,clean_wallet
from descriptor_snapshot import publish_history,exclusive
from ownership_workspace import save_workspace
from builder_workspace import BuilderWorkspace
from builder_history import planning_history
from transaction_builder import builder_catalog
from storage import data_directory
from preferences import resource_id

class SavedOwnership(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.Setup();self.f.setUp();self.addCleanup(self.f.doCleanups);self.config=self.f.config;self.user=self.f.user
  catalog=DescriptorStore(self.config).read();self.chain=copy.deepcopy(self.f.history);self.chain.update(catalog_fingerprint=DescriptorStore.fingerprint(catalog),coverage=[],timestamp_basis='blocktime',source='fixture',scanned_utc=datetime.now(timezone.utc).isoformat())
  for wallet in self.chain['wallets']:
   for row in wallet['records']:row.update(fee_only=False,fee_sats=0)
  publish_history(self.config,catalog,self.chain)
  inputs=Path(self.f.tmp.name)/'saved-inputs';inputs.mkdir();(inputs/'exchanges.ods').write_bytes(b'fixture');(inputs/'chain.json').write_text(json.dumps(self.chain));inventory=[{'id':self.f.rid,'source':self.f.wallet['id'],'kind':'descriptor','name':'Example Wallet'}]
  save_workspace(self.config,self.user,{'exchanges':inputs/'exchanges.ods','chain':inputs/'chain.json'},inventory,{'entries':[]},{},metadata={'descriptor_fingerprint':self.chain['catalog_fingerprint'],'family_accounts':{self.user:False}})
  wallet=copy.deepcopy(self.f.wallet);wallet['raw']['descriptors'][0]['next_index']+=1;DescriptorStore(self.config).replace_node_wallets([wallet])
  self.session=Session(Path(self.f.tmp.name)/'browser',self.config);self.addCleanup(self.session.close);self.session.node_registry=self.f.registry;self.session.select_user(self.user)
 def test_history_mismatch_does_not_revoke_saved_assignment_or_template_access(self):
  access=self.session.access();self.assertFalse(access['ownership_ready']);self.assertFalse(access['descriptor_history_ready']);self.assertTrue(access['ownership_assignments_ready']);self.assertTrue(access['templates_ready']);self.assertTrue(access['ownership_available']);self.assertTrue(access['builder_history_refreshing']);self.assertEqual(builder_catalog(self.session)['wallets'][0]['btc'],'0.001')
 def test_starting_or_failed_inventory_reload_keeps_previous_assignments(self):
  self.session.inventory_ready=False;self.session.status='running';self.session.mode='inventory';self.assertTrue(self.session.access()['templates_ready']);self.session.inventory=[];self.assertTrue(self.session.access()['templates_ready']);self.session.status='error';self.assertTrue(self.session.access()['templates_ready'])
 def test_genuine_new_wallet_still_requires_an_owner(self):
  raw=copy.deepcopy(self.f.wallet['raw']);raw['wallet_name']='New';body=raw['descriptors'][0]['desc'].split('#')[0].replace('/0/*','/1/*');from vendor.embit.descriptor.checksum import checksum
  raw['descriptors'][0]['desc']=body+'#'+checksum(body);other=clean_wallet(raw);DescriptorStore(self.config).replace_node_wallets([self.f.wallet,other]);self.assertFalse(self.session.access()['templates_ready']);self.assertFalse(self.session.access()['ownership_assignments_ready'])
 def test_saved_planning_history_never_waits_for_background_scan_lock(self):
  path=data_directory(self.config)/'descriptor-history/scan.lock';started=threading.Event();release=threading.Event()
  def scan():
   with exclusive(path):started.set();release.wait(3)
  t=threading.Thread(target=scan);t.start();self.assertTrue(started.wait(1))
  try:
   with patch('descriptor_snapshot.shared_history',side_effect=AssertionError('planning must not wait on the scan')):value=planning_history(self.session,DescriptorStore(self.config).read())
   self.assertTrue(value['planning_saved']);self.assertEqual(value['wallets'][0]['records'],self.chain['wallets'][0]['records'])
  finally:release.set();t.join(3)
 def test_corrupt_saved_cache_is_not_silently_used(self):
  p=data_directory(self.config)/'descriptor-history'/(self.chain['catalog_fingerprint']+'.json');p.write_text('{}');self.session.uploads={}
  with self.assertRaisesRegex(ValueError,'Saved Bitcoin history'):planning_history(self.session,DescriptorStore(self.config).read())
 def test_restored_linked_builder_drafts_survive_stale_history_and_inventory_reload(self):
  from test_build80 import GroupedApproval
  f=GroupedApproval();f.setUp();self.addCleanup(f.doCleanups);f.begin();saved=f.work.read();restored=BuilderWorkspace(f.f.f.config);self.assertEqual(restored.owned(f.user,'wallet')['renewal']['approval'],saved['workspaces']['wallet']['renewal']['approval']);self.assertEqual(restored.owned(f.user,'transaction')['draft'],saved['workspaces']['transaction']['draft'])
 def test_http_start_allows_saved_assignments_without_current_history(self):
  server,pool=create_server(Path(self.f.tmp.name)/'web',0,self.config);pool.nodes.health.closed=True;pool.nodes=self.f.registry;t=threading.Thread(target=server.serve_forever,daemon=True);t.start();session=pool.create();session.select_user(self.user)
  try:
   c=http.client.HTTPConnection('::1',server.server_port,timeout=5);c.request('POST','/api/builders/transaction/start','{}',{'X-Session-Token':session.token,'Content-Type':'application/json'});r=c.getresponse();data=json.loads(r.read());c.close();self.assertEqual(r.status,200,data);self.assertTrue(data['workspace']);self.assertEqual(data['workspace']['owner_id'],self.user)
  finally:server.shutdown();server.server_close();t.join(3)
 def test_worker_history_requests_are_lower_priority_than_builder_requests(self):
  from node_bridge import NodeBridge,WorkerRPC
  calls=[];self.f.registry.rpc.call=lambda *args,**kw:(calls.append(kw) or {'state':'succeeded','result':100})
  bridge=NodeBridge(self.f.registry,priority=lambda:100);self.addCleanup(bridge.close);self.assertEqual(WorkerRPC(bridge.settings()).call(self.f.a['node_id'],'getblockcount'),100);self.assertEqual(calls[0]['priority'],100)
 def test_saved_history_never_substitutes_for_live_coin_or_transaction_checks(self):
  from fee_planner import live_coins
  f=self.f;coin={'txid':f.prev.txid().hex(),'vout':0,'amount':'0.001','confirmations':100,'safe':True,'solvable':True,'scriptPubKey':f.prev.vout[0].script_pubkey.data.hex()};reads=[]
  class Chain:
   def __init__(self,*a):self.hints={}
   def wallet_unspent(self,wallet):reads.append(wallet['id']);return [dict(coin)]
   def transaction(self,txid):return f.prev
  with patch('node_chain.NodeChain',Chain):
   result=live_coins(self.session,builder_catalog(self.session),{f.rid},force=True);self.assertEqual(result[f.rid][0]['value'],100000);self.assertTrue(reads)
   coin['amount']='0.002'
   with self.assertRaisesRegex(ValueError,'did not match its raw transaction'):live_coins(self.session,builder_catalog(self.session),{f.rid},force=True)
 def test_saved_chain_fallback_requires_its_manifest_hash(self):
  path=data_directory(self.config)/'descriptor-history'/(self.chain['catalog_fingerprint']+'.json');path.unlink();self.assertTrue(planning_history(self.session,DescriptorStore(self.config).read())['planning_saved']);self.session.uploads['chain'].write_text(json.dumps(dict(self.chain,transactions={})))
  with self.assertRaisesRegex(ValueError,'Saved Bitcoin history'):planning_history(self.session,DescriptorStore(self.config).read())
