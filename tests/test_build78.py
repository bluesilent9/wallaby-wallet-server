"""Visible-page identity checks use explicit priority; status reads are passive."""
import sys,unittest,time,threading,tempfile,http.client,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_build72 as fixtures
from vault_refresh import signers

class Priorities(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.Refresh();self.f.setUp();self.addCleanup(self.f.doCleanups);self.checks=self.f.checks
 def test_background_scans_use_lowest_supported_rpc_priority(self):
  with patch.object(self.checks,'scan'):self.checks.ensure('visible-builder',force=True,private_accounts=True,priority=100)
  self.f.calls.clear()
  for node,row in self.checks.rows.items():self.checks.scan(node,row['token'])
  self.assertTrue(self.f.calls);self.assertEqual({r[2] for r in self.f.calls},{100});self.assertTrue(signers(self.f.hub,self.f.w)['complete'])
 def test_foreground_request_upgrades_active_check_without_second_worker(self):
  with patch.object(self.checks,'scan') as scan:
   self.checks.ensure('visible-builder',force=True,private_accounts=True,priority=100)
   count=scan.call_count;self.checks.ensure('visible-builder',force=True,private_accounts=True,priority=0)
   self.assertEqual(scan.call_count,count);self.assertTrue(all(r['priority']==0 for r in self.checks.rows.values()))
 def test_passive_status_does_not_start_checks(self):
  with patch.object(self.checks,'ensure',side_effect=AssertionError('Passive status started network work')):
   self.assertTrue(signers(self.f.hub,self.f.w)['complete'])
 def test_retained_locations_never_override_fresh_verification(self):
  for row in self.checks.rows.values():row['verified_at']=time.monotonic()-20
  state=signers(self.f.hub,self.f.w);self.assertTrue(all(r['detected'] for r in state['roles']));self.assertFalse(state['complete'])

class Endpoints(unittest.TestCase):
 def test_status_is_passive_and_visible_checks_use_requested_priority(self):
  from preferences import FamilyStore
  from launch_wallaby_wallet_server import create_server
  with tempfile.TemporaryDirectory() as folder:
   cfg=Path(folder)/'config.cfg';family=FamilyStore(cfg);family.save_user('Example','green',revision=0);server,pool=create_server(Path(folder)/'browser',0,cfg);pool.nodes.health.closed=True;thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();session=pool.create();session.user_id=family.snapshot()['users'][0]['id'];session.access=lambda:{}
   work={'id':'refresh-work','owner_id':session.user_id,'renewal':{'roles':[]}}
   def request(method,path,body=None):
    c=http.client.HTTPConnection('::1',server.server_port,timeout=5);c.request(method,path,json.dumps(body) if body is not None else None,{'X-Session-Token':session.token,'Content-Type':'application/json'});r=c.getresponse();data=json.loads(r.read());c.close();self.assertEqual(r.status,200,data);return data
   try:
    with patch('launch_wallaby_wallet_server.BuilderWorkspace') as workspace,patch.object(pool.nodes,'ready_for_builders',return_value=True),patch.object(pool.nodes.hub.wallet_builder,'snapshot',return_value={'nodes':[],'sessions':[]}) as snapshot,patch.object(pool.nodes.hub.wallet_builder,'discover',return_value={'nodes':[],'sessions':[]}) as discover,patch.object(pool.nodes.hub.disc_signers,'ensure') as ensure,patch('vault_refresh.signers',return_value={'complete':False}) as signer_state:
     workspace.return_value.snapshot.return_value={'workspace':work};workspace.return_value.owned.return_value=work
     request('GET','/api/wallet-builder');ensure.assert_not_called();discover.assert_not_called();signer_state.assert_called_with(pool.nodes.hub,work)
     request('POST','/api/wallet-builder/discover',{'foreground':True,'identities':True});discover.assert_not_called();ensure.assert_called_with('renewal-refresh-work',force=True,private_accounts=True,priority=0)
     discover.reset_mock();request('POST','/api/wallet-builder/discover',{'foreground':False,'identities':True});discover.assert_not_called();ensure.assert_called_with('renewal-refresh-work',force=True,private_accounts=True,priority=100)
     discover.reset_mock();request('POST','/api/wallet-builder/discover',{'foreground':False,'identities':False});discover.assert_not_called();ensure.assert_called_with('renewal-refresh-work',force=True,private_accounts=True,priority=100)
     work.pop('renewal');ensure.reset_mock();request('POST','/api/wallet-builder/discover',{'foreground':True,'identities':True});discover.assert_called_once_with(foreground=True);ensure.assert_not_called()
   finally:server.shutdown();server.server_close();thread.join(3)
