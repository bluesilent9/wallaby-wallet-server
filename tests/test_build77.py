"""Vault receiving destinations must be proven against public vault policies."""
import copy,unittest
import test_build70 as fixtures
from address_destinations import vault_entry
from builder_destinations import Destinations

class VaultAddresses(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.Addresses();self.f.setUp();self.addCleanup(self.f.doCleanups)
 def test_temporary_duplicate_card_reservation_does_not_replace_vault_address(self):
  old,new=self.f.vault()
  Destinations(self.f.f.config).write({'version':1,'destinations':{'temporary':{'descriptors':new,'index':7,'height':None}}})
  self.f.service.refresh();entry=self.f.service.overlay(None)['entries'][0]
  self.assertEqual(entry['addresses'][0]['address'],self.f.address(new[0],0))
  self.assertNotEqual(entry['addresses'][0]['address'],self.f.address(new[0],7))
 def test_wrong_height_reservation_cannot_override_policy(self):
  old,new=self.f.vault()
  Destinations(self.f.f.config).write({'version':1,'destinations':{'temporary':{'descriptors':new,'index':7,'height':1000000}}})
  self.f.service.refresh();self.assertEqual(self.f.service.overlay(None)['entries'][0]['addresses'][0]['address'],self.f.address(new[0],0))
 def test_ordinary_saved_addresses_and_forged_height_are_removed(self):
  ordinary=self.f.address(self.f.wallet['raw']['descriptors'][0]);old,new=self.f.vault()
  good={'address':self.f.address(new[0],7),'descriptor':new[0]['desc'],'index':7}
  bad={'address':ordinary,'vault_height':1000200}
  entry=vault_entry({'addresses':[bad,good],'address_history':[bad,good]},self.f.wallet)
  self.assertEqual([r['address'] for r in entry['addresses']],[good['address']]);self.assertEqual([r['address'] for r in entry['address_history']],[good['address']]);self.assertFalse(entry['can_generate'])
 def test_missing_proof_disables_destination_instead_of_offering_ordinary_address(self):
  ordinary=self.f.address(self.f.wallet['raw']['descriptors'][0]);self.f.vault()
  entry=vault_entry({'addresses':[{'address':ordinary}],'address_history':[]},self.f.wallet)
  self.assertEqual(entry['status'],'unavailable');self.assertFalse(entry['addresses'])
 def test_disc_samples_are_index_zero_for_both_branches_all_generations(self):
  old,new=self.f.vault();self.f.service.refresh();entry=self.f.service.overlay(None)['entries'][0]
  samples=entry['vault_samples'];self.assertEqual(len(samples),4)
  for rows,h in ((old,1000000),(new,1000200)):
   for row,branch in zip(rows,('Receiving','Change')):
    self.assertIn({'height':h,'branch':branch,'index':0,'address':self.f.address(row,0)},samples)
 def test_actual_renewal_address_stays_distinct_from_disc_sample(self):
  old,new=self.f.vault();Destinations(self.f.f.config).write({'version':1,'destinations':{'renewal':{'descriptors':new,'index':7,'height':1000200}}})
  self.f.service.refresh();entry=self.f.service.overlay(None)['entries'][0]
  self.assertEqual(entry['addresses'][0]['address'],self.f.address(new[0],7));self.assertNotEqual(entry['addresses'][0]['address'],entry['vault_samples'][0]['address'])
 def test_ordinary_wallet_unchanged(self):
  entry={'addresses':[{'address':self.f.address(self.f.wallet['raw']['descriptors'][0])}],'address_history':[]}
  self.assertEqual(vault_entry(copy.deepcopy(entry),self.f.wallet),entry)
