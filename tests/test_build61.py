"""Funded/unfunded expiry and shared live wallet traits for Vaults."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
import test_build13 as fixture

class VaultPresentation(unittest.TestCase):
 def setUp(self):
  self.f=fixture.Display();self.f.setUp();self.addCleanup(self.f.doCleanups)
 def expiry(self):
  for c in self.f.registry.connections.values():self.f.registry.health.values[c['token']]['blocks']=1000010
 def test_verified_empty_policy_is_red_unlocked_after_expiry(self):
  self.f.coins=[];self.expiry();c=self.f.card()
  self.assertTrue(c['balance_verified']);self.assertEqual(c['outside_sats'],0);self.assertEqual(c['vault_sats'],0)
  self.assertEqual(c['countdown'],'Unlocked');self.assertEqual(c['funding_status'],'unlocked');self.assertEqual(c['state'],'red')
 def test_unverified_empty_policy_does_not_claim_unlocked(self):
  self.f.coins=[];self.expiry();self.f.rpc_error='Unavailable'
  c=self.f.card();self.assertFalse(c['balance_verified']);self.assertEqual(c['countdown'],'Verification needed');self.assertEqual(c['state'],'amber')
 def test_funded_expired_policy_is_red(self):
  self.expiry();c=self.f.card();self.assertEqual(c['state'],'red');self.assertEqual(c['countdown'],'Unlocked');self.assertEqual(c['funding_status'],'unlocked')
 def test_vault_cards_include_live_disc_watch_and_smsf_traits(self):
  c=self.f.card();uid=c['id']
  from preferences import FamilyStore,resource_id
  with FamilyStore(self.f.config).transaction() as state:
   state['ownership']=[{'id':resource_id('descriptor',uid),'kind':'descriptor','source':uid,'name':'Example Wallet','owner_id':self.f.user,'confirmed':True,'smsf':True}]
  with patch('live_wallet_traits.disc_flags',return_value={uid:True}),patch('live_wallet_traits.watch_flags',return_value={uid:False}):
   c=self.f.card();self.assertTrue(c['disc_only']);self.assertFalse(c['watch_only']);self.assertTrue(c['smsf'])
if __name__=='__main__':unittest.main()
