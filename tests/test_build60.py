import sys,copy,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_build8 import Setup
from node_wallets import NodeWalletLoader
from descriptor_store import clean_wallet,DescriptorStore
from policy_accounts import has_vault
from vendor.embit.descriptor.checksum import checksum
from wallet_names import display_inventory
from balance_store import BalanceStore
from preferences import resource_id
from live_wallet_traits import annotate

class VaultBadges(unittest.TestCase):
 def setUp(self):
  self.f=Setup();self.f.setUp();self.addCleanup(self.f.doCleanups)
 def raw(self,kind,height=1000000):
  key=self.f.master.to_public().to_base58()+'/0/*'
  if kind=='plain':body='wpkh('+key+')'
  elif kind=='bypass':body='wsh(or_i(pk('+key+'),and_v(v:after('+str(height)+'),pk('+key+'))))'
  else:
   inner='multi(2,'+key+','+self.f.master.derive('m/1').to_public().to_base58()+'/0/*,'+self.f.master.derive('m/2').to_public().to_base58()+'/0/*)' if kind=='multi' else 'pk('+key+')'
   body='wsh(and_v(v:after('+str(height)+'),'+inner+'))'
  return {'wallet_name':'Proposed wallet','descriptors':[{'desc':body+'#'+checksum(body),'timestamp':1,'range':[0,99],'next_index':0,'internal':False,'active':True}]}
 def test_empty_single_and_multisig_vault_exports_have_badge_without_receipts(self):
  for kind in ('single','multi'):
   for height in (1,1000000):
    raw=self.raw(kind,height);w=clean_wallet(raw)
    replica={'node':{'id':'n','hostname':'Fixture'},'rpc_name':raw['wallet_name'],'wallet':w,'private_keys_enabled':True,'history':{'transactions':[],'lastblock':'a'*64}}
    actual=NodeWalletLoader(self.f.registry,lambda _:None).merge([replica]);self.assertTrue(actual['has_vault']);self.assertEqual(actual['vault_evidence'],[])
 def test_plain_wallet_and_bypass_policy_do_not_claim_mandatory_vault(self):
  for kind in ('plain','bypass'):self.assertFalse(has_vault(self.raw(kind)))
 def test_saved_false_badge_is_refreshed_in_summary_ownership_and_balance_card(self):
  w=clean_wallet(self.raw('multi'));w['has_vault']=False;DescriptorStore(self.f.config).replace_node_wallets([w]);rid=resource_id('descriptor',w['id'])
  with self.f.family.transaction() as state:state['ownership']=[{'id':rid,'kind':'descriptor','source':w['id'],'name':'Proposed wallet','owner_id':self.f.user,'confirmed':True,'smsf':False}]
  self.assertTrue(DescriptorStore(self.f.config).summary()['wallets'][0]['has_vault'])
  shown=display_inventory([{'id':rid,'kind':'descriptor','source':w['id'],'name':'Proposed wallet'}],{'wallets':[w]});self.assertTrue(shown[0]['has_vault'])
  balances=BalanceStore(self.f.config);balances.save('old',{'balances':{'wallets':[{'name':'Proposed wallet','kind':'wallet','descriptor_id':w['id'],'has_vault':False,'owner_name':'Example','btc':'0'}]}});before=balances.path.read_bytes();row=balances.personal('old',{'name':'Example'})['balances']['wallets'][0];self.assertTrue(row['has_vault']);self.assertEqual(row['multisig'],[{'required':2,'total':3}]);self.assertEqual(before,balances.path.read_bytes())
 def test_live_annotation_repairs_badge_without_full_trace_or_funding(self):
  w=clean_wallet(self.raw('single'));report={'balances':{'wallets':[{'descriptor_id':w['id'],'has_vault':False,'btc':'0'}]}};annotate(report,{'wallets':[w]},None);self.assertTrue(report['balances']['wallets'][0]['has_vault'])
if __name__=='__main__':unittest.main()
