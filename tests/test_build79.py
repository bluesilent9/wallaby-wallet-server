"""A refresh reuses keys, waits for policy approvals and still verifies all keys."""
import unittest,copy
from unittest.mock import patch
import test_build72 as fixtures
from vault_refresh import signers,finish
from builder_destinations import Destinations
from wallet_policy_updates import destination_ready

class RefreshHandoff(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.Refresh();self.f.setUp();self.addCleanup(self.f.doCleanups)
 def test_handoff_needs_no_new_wallet_identity_and_queues_policy_approvals(self):
  before=copy.deepcopy(self.f.hub.wallet_builder.read());self.assertFalse(before['identities']);self.assertFalse(before['challenges']);result=finish(self.f.hub,self.f.f.user,1000100)
  self.assertTrue(result['waiting']);self.assertEqual(self.f.hub.wallet_builder.read(),before);requests=list(self.f.hub.read()['requests'].values());self.assertTrue(requests);self.assertTrue(all(r['kind']=='wallet_policy_refresh' and r['state']=='pending' for r in requests));self.assertIn('wallet',self.f.work.read()['workspaces'])
 def test_preparing_payment_still_waits_for_local_policy_approval(self):
  result=finish(self.f.hub,self.f.f.user,1000100);store=Destinations(self.f.f.config);d=store.get(result['destination']);self.assertFalse(destination_ready(self.f.hub,d))
  catalog={'wallets':[{'id':self.f.f.rid,'funded_vault':True}]}
  with self.assertRaisesRegex(ValueError,'awaiting local Agent approval'):store.enrich(catalog,[self.f.f.rid,d['id']],self.f.hub,require_policy=True)
 def test_backend_still_refuses_incomplete_reverification(self):
  with patch.object(self.f.checks,'scan'):self.f.checks.ensure('button-check',force=True,private_accounts=True,priority=0)
  self.assertTrue(all(r['detected'] for r in signers(self.f.hub,self.f.w)['roles']));self.assertFalse(signers(self.f.hub,self.f.w)['complete']);before=self.f.work.read()
  with self.assertRaisesRegex(ValueError,'verification is updating'):finish(self.f.hub,self.f.f.user,1000100)
  self.assertEqual(self.f.work.read(),before);self.assertFalse(self.f.hub.read()['requests'])
