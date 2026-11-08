"""Focused loaded-disc discovery, reconnect guards and signer eligibility."""
import copy,sys,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_build8 as fixtures
from agent_transactions import eligible,signing_state
from disc_signers import inventory

class Discs(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.Setup();self.f.setUp();self.addCleanup(self.f.doCleanups);self.checks=self.f.hub.disc_signers;self.addCleanup(self.checks.close);self.node=self.f.a['node_id'];self.token=self.f.a['connection_token'];self.calls=[];self.mounted=True;self.busy=False;self.mismatch=False;self.f.hub.caps[self.node]={'partial_signing'};self.disc=copy.deepcopy(self.f.wallet['raw']);self.disc['wallet_name']='archive-key';self.f.registry.rpc.call=self.rpc
 def rpc(self,node,method,params=None,wallet=None,**kw):
  self.calls.append((node,method,wallet,params,kw.get('priority')))
  if self.busy:return {'state':'error','error':{'code':'protected_workspace_busy'}}
  if method=='listwallets':value=['local']+(['Disc role'] if self.mounted else [])
  elif method=='getwalletinfo':value={'walletname':'archive-key' if wallet=='Disc role' else self.f.wallet['name'],'private_keys_enabled':True,'scanning':False,**({'wallaby_storage':'disc','wallaby_archive_id':'a'*64} if wallet=='Disc role' else {})}
  elif method=='listdescriptors':value={**self.disc,**({'wallet_name':'changed'} if self.mismatch else {})}
  else:raise AssertionError('Unrelated discovery '+method)
  return {'state':'succeeded','result':value}
 def check(self):
  self.checks.rows[self.node]={'state':'checking','token':self.token,'hostname':'fixture','active':True,'wallets':[]};self.checks.scan(self.node,self.token)
 def test_loaded_disc_plus_local_signer_remain_separate(self):
  self.check();choices=eligible(self.f.hub,self.f.rid);self.assertEqual({r['wallet'] for r in choices},{self.f.wallet['name'],'Disc role'});self.assertEqual(len({r['signer_id'] for r in choices}),2);self.assertEqual(self.checks.rows[self.node]['state'],'ready')
 def test_only_loaded_disc_descriptors_are_read_at_high_priority(self):
  self.check();self.assertEqual({c[1] for c in self.calls},{'listwallets','getwalletinfo','listdescriptors'});self.assertEqual([c[2] for c in self.calls if c[1]=='listdescriptors'],['Disc role']);self.assertTrue(all(c[-1]==0 for c in self.calls))
 def test_busy_does_not_publish_empty_success_and_retries(self):
  self.check();self.busy=True;self.checks.scan(self.node,self.token);row=self.checks.rows[self.node];self.assertEqual(row['state'],'busy');self.assertTrue(row['wallets']);self.assertTrue(self.checks.snapshot()['active']);self.assertEqual([r['wallet'] for r in eligible(self.f.hub,self.f.rid)],[self.f.wallet['name']]);self.busy=False;self.checks.scan(self.node,self.token);self.assertEqual(len(eligible(self.f.hub,self.f.rid)),2)
 def test_unload_removes_cached_disc_even_if_full_inventory_still_lists_it(self):
  self.check();self.f.hub.inventories[self.node]['wallets']+=copy.deepcopy(self.checks.rows[self.node]['wallets']);self.mounted=False;self.checks.scan(self.node,self.token);self.assertEqual(self.checks.rows[self.node]['wallets'],[]);self.assertEqual([r['wallet'] for r in eligible(self.f.hub,self.f.rid)],[self.f.wallet['name']])
 def test_missing_full_inventory_does_not_hide_targeted_disc(self):
  self.check();self.f.hub.inventories.pop(self.node);self.assertEqual([r['wallet'] for r in eligible(self.f.hub,self.f.rid)],['Disc role'])
 def test_identity_change_rejects_partial_scan(self):
  self.mismatch=True;self.check();self.assertEqual(self.checks.rows[self.node]['state'],'busy');self.assertEqual(self.checks.rows[self.node]['wallets'],[])
 def test_disconnect_discards_late_scan(self):
  self.check();self.f.registry.connections.pop(self.token);self.checks.scan(self.node,self.token);self.assertEqual(inventory(self.f.hub,self.node)['wallets'],self.f.hub.inventories[self.node]['wallets'])
 def test_force_check_and_automatic_checks_are_nonblocking(self):
  started=time.monotonic();self.checks.ensure('job',force=True);self.assertLess(time.monotonic()-started,.5)
  until=time.monotonic()+2
  while self.checks.rows[self.node].get('active') and time.monotonic()<until:time.sleep(.01)
  self.assertEqual(self.checks.rows[self.node]['state'],'ready');count=len(self.calls);self.checks.ensure('job');self.assertEqual(len(self.calls),count)
 def test_checking_state_is_in_transaction_status_without_changing_psbt(self):
  job=self.f.job();self.check();before=self.f.hub.read();row=signing_state(self.f.hub,self.f.user,job);self.assertFalse(row['signer_check']['active']);self.assertEqual(len(row['signing_wallets'][0]['nodes']),2);self.assertEqual(self.f.hub.read(),before)
 def test_profile_reset_drops_disc_cache(self):
  self.check();old=self.checks;self.f.hub.reset_live();self.assertTrue(old.closed);self.assertFalse(self.f.hub.disc_signers.rows)

 def test_temporarily_busy_health_still_checks_connected_agent(self):
  self.f.registry.health.values[self.token]={'state':'error','checked_at':time.monotonic()};self.assertIn(self.node,self.checks.connections())
 def test_partial_or_private_descriptor_failure_never_publishes_discs(self):
  self.disc['descriptors'][0]['desc']='wpkh(xprv-not-public)#bad';self.check();self.assertEqual(self.checks.rows[self.node]['state'],'busy');self.assertFalse(self.checks.rows[self.node]['wallets'])
 def test_reset_or_disconnect_does_not_mutate_pending_transaction_or_psbt(self):
  from transaction_workflows import WorkflowStore
  job=self.f.job();before=WorkflowStore(self.f.config)._read();self.check();self.checks.close();self.assertEqual(WorkflowStore(self.f.config)._read(),before)

class Endpoint(Discs):
 def test_targeted_endpoint_checks_active_creator_and_job_and_get_starts_check(self):
  import threading,http.client,json
  from unittest.mock import patch
  from launch_wallaby_wallet_server import create_server
  from builder_workspace import BuilderWorkspace
  job=self.f.job();w=BuilderWorkspace(self.f.config);w.start(self.f.user,'transaction');w.attach(self.f.user,'transaction',job)
  server,pool=create_server(Path(self.f.tmp.name)/'browser',0,self.f.config);pool.nodes.health.closed=True;pool.nodes=self.f.registry;thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();session=pool.create();session.user_id=self.f.user
  def request(method,path,body=None):
   c=http.client.HTTPConnection('::1',server.server_port,timeout=5);c.request(method,path,json.dumps(body) if body is not None else None,{'X-Session-Token':session.token,'Content-Type':'application/json'});r=c.getresponse();data=json.loads(r.read());c.close();return r.status,data
  try:
   with patch.object(self.checks,'ensure',return_value={'active':True,'nodes':[]}) as ensure:
    self.assertEqual(request('POST','/api/transaction/disc-check',{'id':job})[0],200);ensure.assert_called_with(job,force=True)
    self.assertEqual(request('GET','/api/transaction/status?id='+job)[0],200);ensure.assert_called_with(job)
    ensure.reset_mock();self.assertEqual(request('POST','/api/transaction/disc-check',{'id':'f'*32})[0],400);ensure.assert_not_called()
  finally:server.shutdown();server.server_close();thread.join(3)
# Run common tests once; Endpoint reuses only the isolated fixture helpers.
for name in Discs.__dict__:
 if name.startswith('test_'):setattr(Endpoint,name,None)
