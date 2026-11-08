import copy,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from empty_wallet_cards import include_discovered
from descriptor_store import DescriptorStore
from balance_store import BalanceStore
from preferences import resource_id
from test_build8 import Setup

class VisibilityTests(unittest.TestCase):
 def setUp(self):
  self.f=Setup();self.f.setUp();self.addCleanup(self.f.doCleanups)
  self.w=copy.deepcopy(self.f.wallet);self.w.update(setup_name='Proposed wallet',node_history=[],node_sources=[{'node_id':'n','hostname':'Fixture node','wallet_name':self.w['name']}],public_history={'lastblock':'a'*64,'exported_utc':'2026-11-04T11:00:00Z','outputs':[]})
  self.catalog={'wallets':[self.w]};self.record={'id':resource_id('descriptor',self.w['id']),'kind':'descriptor','source':self.w['id'],'name':'Proposed wallet','owner_id':self.f.user,'confirmed':True,'smsf':False};self.family={'users':[{'id':self.f.user,'name':'Example'}],'ownership':[self.record]}
 def test_assigned_empty_wallet_survives_unrelated_failed_combined_history(self):
  DescriptorStore(self.f.config).replace_node_wallets([self.w])
  with self.f.family.transaction() as data:data['ownership']=[self.record]
  balances=BalanceStore(self.f.config);balances.save('old',{'balances':{'wallets':[{'descriptor_id':'other','name':'Other wallet','kind':'wallet','btc':'3','value_aud':'1','cost_basis_aud':'2','owner_name':'Example'}]}})
  before=balances.path.read_bytes()
  with patch('descriptor_snapshot.history_ready',return_value=False),patch('balance_evidence.history',side_effect=AssertionError('No combined ledger needed')):
   report=balances.personal('old',{'name':'Example'})
  rows=report['balances']['wallets'];self.assertEqual(len(rows),2);self.assertEqual(rows[0]['btc'],'3');self.assertEqual(rows[0]['cost_basis_aud'],'2');self.assertEqual(rows[1]['name'],'Proposed wallet');self.assertEqual(rows[1]['btc'],'0');self.assertEqual(before,balances.path.read_bytes())
 def test_missing_pending_and_funded_history_are_visible_without_false_zero(self):
  for case in ('missing','pending','funded','undated','no_source'):
   w=copy.deepcopy(self.w)
   if case=='missing':w.pop('public_history')
   elif case=='pending':w['node_history']=[{'confirmations':0,'amount':'0.01'}]
   elif case=='funded':w['public_history']['outputs']=[{'txid':'b'*64,'vout':0}]
   elif case=='undated':w['public_history']['exported_utc']='invalid'
   elif case=='no_source':w['node_sources']=[]
   balance={'wallets':[]};include_discovered(balance,{'wallets':[w]},self.family);self.assertEqual(len(balance['wallets']),1,case);self.assertIsNone(balance['wallets'][0]['btc'],case);self.assertEqual(balance['wallets'][0]['state'],'unavailable')
 def test_existing_funded_card_is_never_overwritten_and_no_duplicates(self):
  row={'descriptor_id':self.w['id'],'btc':'100','cost_basis_aud':'1000'};balance={'wallets':[row.copy()]};include_discovered(balance,self.catalog,self.family);include_discovered(balance,self.catalog,self.family);self.assertEqual(balance['wallets'],[row])
 def test_extinct_and_unassigned_wallets_are_not_added_to_active_cards(self):
  for extinct,owners in ((True,[self.record]),(False,[])):
   w=copy.deepcopy(self.w);w['extinct']=extinct;balance={'wallets':[]};include_discovered(balance,{'wallets':[w]},dict(self.family,ownership=owners));self.assertEqual(balance['wallets'],[])
if __name__=='__main__':unittest.main()
