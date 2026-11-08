"""Stable presentation across rechecks, with fresh verification still mandatory."""
import copy,sys,time,unittest,threading
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_build74 as fixtures
from vault_refresh import signers,finish

class Stable(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.Combined();self.f.setUp();self.addCleanup(self.f.doCleanups);self.checks=self.f.checks;self.hub=self.f.hub;self.w=self.f.f.w
 def state(self):return signers(self.hub,self.w)
 def begin(self):
  # Hold the network worker so a status poll observes an in-flight recheck.
  with patch.object(self.checks,'scan'):
   self.checks.ensure('recheck',force=True,private_accounts=True)
 def test_periodic_check_keeps_all_locations_and_disc_modes_but_blocks_handoff(self):
  before=self.state();self.assertTrue(before['complete']);self.begin();during=self.state();self.assertTrue(all(r['detected'] for r in during['roles']));self.assertFalse(during['complete']);self.assertTrue(during['checking']);self.assertEqual([(r['hostname'],r['storage']) for r in before['roles']],[(r['hostname'],r['storage']) for r in during['roles']]);self.assertFalse(any(r['verified'] for r in during['roles']))
  with self.assertRaisesRegex(ValueError,'verification is updating'):finish(self.hub,self.f.f.f.user,1000100)
 def test_successful_recheck_restores_freshness_without_changing_display(self):
  before=self.state();self.begin()
  for node,row in self.checks.rows.items():self.checks.scan(node,row['token'])
  self.assertEqual(self.state()['roles'],before['roles']);self.assertTrue(self.state()['complete'])
 def test_busy_reply_preserves_known_roles_but_does_not_authorise(self):
  self.f.f.busy=True
  for node,row in self.checks.rows.items():self.checks.scan(node,row['token'])
  self.assertTrue(all(r['detected'] for r in self.state()['roles']));self.assertFalse(self.state()['complete'])
 def test_confirmed_unload_replaces_cached_disc_evidence(self):
  self.begin();self.f.unload();s=self.state();self.assertEqual([r['detected'] for r in s['roles']],[True,True,True,False,False]);self.assertFalse(s['complete']);self.assertTrue(all(r['verified'] for r in s['roles'][:3]))
 def test_real_disconnect_clears_that_nodes_display_immediately(self):
  node=self.f.f.f.b;self.f.f.f.registry.connections.pop(node['connection_token']);s=self.state();self.assertFalse(s['roles'][1]['detected']);self.assertFalse(s['roles'][3]['detected']);self.assertTrue(s['roles'][0]['detected']);self.assertFalse(s['complete'])
 def test_reconnect_does_not_reuse_previous_token_display(self):
  node=self.f.f.f.b;connection=self.f.f.f.registry.connections.pop(node['connection_token']);replacement={**connection,'token':'new-token'};self.f.f.f.registry.connections['new-token']=replacement
  self.assertFalse(self.state()['roles'][1]['detected']);self.assertFalse(self.state()['complete'])
 def test_old_display_is_retained_until_update_but_never_qualifies_as_verified(self):
  for row in self.checks.rows.values():row['verified_at']=time.monotonic()-301;row['state']='busy'
  self.assertTrue(all(r['detected'] for r in self.state()['roles']));self.assertFalse(self.state()['complete'])
 def test_failed_recheck_leaves_original_transaction_and_setup_unchanged(self):
  work=copy.deepcopy(self.f.f.work.read());setup=copy.deepcopy(self.hub.wallet_builder.read());self.begin();self.f.f.busy=True
  for node,row in self.checks.rows.items():self.checks.scan(node,row['token'])
  self.assertEqual(self.f.f.work.read(),work);self.assertEqual(self.hub.wallet_builder.read(),setup);self.assertFalse(self.state()['complete'])

 def test_three_known_node_signers_do_not_drop_during_recheck_with_discs_unloaded(self):
  self.f.unload();before=self.state();self.assertEqual([r['detected'] for r in before['roles']],[True,True,True,False,False]);self.begin();during=self.state();self.assertEqual([r['detected'] for r in during['roles']],[True,True,True,False,False]);self.assertFalse(during['complete']);self.assertTrue(during['checking'])
