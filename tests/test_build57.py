import copy,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from descriptor_store import DescriptorStore
from descriptor_chain import scan
from ownership import inventory_for
from wallet_names import display_inventory
from empty_wallet_cards import include_verified_empty
from preferences import resource_id
import test_build13 as vault_fixture

class LoadedVaultTests(unittest.TestCase):
 def fixture(self):
  c=vault_fixture.Display();c.setUp();self.addCleanup(c.doCleanups);return c
 def test_loaded_inventory_verifies_vault_despite_unrelated_unloaded_folders(self):
  c=self.fixture()
  for inv in c.hub.inventories.values():inv.update(complete=False,loaded_complete=True,unloaded_wallets=['Unrelated old folder'])
  card=c.card();self.assertTrue(card['balance_verified']);self.assertEqual(card['vault_sats'],1000000);self.assertEqual(card['state'],'green');self.assertFalse(any('inventory is not ready' in x for x in card['issues']))
 def test_empty_loaded_vault_is_verified_not_funded(self):
  c=self.fixture();c.coins=[]
  for inv in c.hub.inventories.values():inv.update(complete=False,loaded_complete=True)
  card=c.card();self.assertEqual(card['funding_status'],'ready_to_fund');self.assertTrue(card['balance_verified']);self.assertEqual(card['countdown'],'Not funded')
 def test_failed_inventory_and_rpc_still_do_not_claim_verification(self):
  c=self.fixture()
  for inv in c.hub.inventories.values():inv.update(complete=False,loaded_complete=False)
  self.assertFalse(c.card()['balance_verified'])
  for inv in c.hub.inventories.values():inv.update(loaded_complete=True)
  c.rpc_error='No current balance';self.assertFalse(c.card()['balance_verified'])

class LogicalEmptyTests(unittest.TestCase):
 def setUp(self):
  from test_build8 import Setup
  self.f=Setup();self.f.setUp();self.addCleanup(self.f.doCleanups)
  self.w=copy.deepcopy(self.f.wallet);self.w.update(setup_name='Proposed wallet',node_history=[])
  self.catalog={'schema':132,'wallets':[self.w]}
  chain=SimpleNamespace(nodes=lambda:[{'id':'n'}],rpc=SimpleNamespace(call=lambda *a:{'chain':'main','initialblockdownload':False}))
  self.chain=scan(self.catalog,SimpleNamespace(chain=chain,source='Fixture Core'),lambda _:None)
  self.family={'users':[{'id':'owner','name':'Example owner'}],'ownership':[{'id':resource_id('descriptor',self.w['id']),'kind':'descriptor','source':self.w['id'],'name':'User chosen label','owner_id':'owner','confirmed':True,'smsf':False}]}
 def test_scan_and_reconstructed_ownership_keep_setup_name_not_signer_filename(self):
  self.assertEqual(self.chain['wallets'][0]['setup_name'],'Proposed wallet')
  core=SimpleNamespace(DESCRIPTOR_WALLETS={self.w['name']:self.w['id']},DESCRIPTOR_SOURCE_NAMES={self.w['id']:self.w['name']},DESCRIPTOR_SNAPSHOT=self.chain,FAMILY_ACCOUNT_USERS=[])
  row=inventory_for(core,{self.w['name']:[]},[],{})[0]
  self.assertEqual(row['name'],'Proposed wallet');self.assertEqual(row['source_name'],'Proposed wallet');self.assertEqual(row['core_source_name'],self.w['name'])
  shown=display_inventory([row],self.catalog)[0];self.assertEqual(shown['source_name'],'Proposed wallet');self.assertEqual(shown['core_source_name'],self.w['name'])
 def test_new_verified_empty_wallet_appears_once_without_changing_existing_balances(self):
  balance={'wallets':[{'name':'Existing','descriptor_id':'existing','btc':'12','cost_basis_aud':'400'}]};old=copy.deepcopy(balance['wallets'][0])
  include_verified_empty(balance,self.catalog,self.chain,self.family);include_verified_empty(balance,self.catalog,self.chain,self.family)
  self.assertEqual(len(balance['wallets']),2);self.assertEqual(balance['wallets'][0],old);row=balance['wallets'][1];self.assertEqual(row['btc'],'0');self.assertEqual(row['name'],'User chosen label');self.assertEqual(row['owner_name'],'Example owner')
 def test_saved_balance_view_adds_empty_wallet_using_verified_history_and_preserves_files(self):
  from balance_store import BalanceStore
  from descriptor_snapshot import publish_history
  from preferences import FamilyStore
  DescriptorStore(self.f.config).replace_node_wallets([self.w])
  family=FamilyStore(self.f.config)
  with family.transaction() as state:
   state['ownership']=[dict(self.family['ownership'][0],owner_id=self.f.user)]
  publish_history(self.f.config,self.catalog,self.chain)
  store=BalanceStore(self.f.config);store.save('old',{'balances':{'wallets':[]}})
  before=store.path.read_bytes();catalog_before=DescriptorStore(self.f.config).path.read_bytes()
  result=store.personal('old',{'name':'Example'})
  self.assertEqual(len(result['balances']['wallets']),1);self.assertEqual(result['balances']['wallets'][0]['btc'],'0')
  self.assertEqual(before,store.path.read_bytes());self.assertEqual(catalog_before,DescriptorStore(self.f.config).path.read_bytes())
 def test_unknown_pending_funded_unassigned_and_wrong_history_never_become_zero(self):
  for case in ('no_coverage','pending','funded','unassigned','wrong_fingerprint','missing_wallet'):
   chain=copy.deepcopy(self.chain);family=copy.deepcopy(self.family);balance={'wallets':[]}
   if case=='no_coverage':chain['coverage']=[]
   elif case=='pending':chain['wallets'][0]['pending_btc']='0.00001'
   elif case=='funded':chain['wallets'][0]['records']=[{'txid':'a'*64}]
   elif case=='unassigned':family['ownership']=[]
   elif case=='wrong_fingerprint':chain['catalog_fingerprint']='wrong'
   elif case=='missing_wallet':chain['wallets']=[]
   include_verified_empty(balance,self.catalog,chain,family);self.assertEqual(balance['wallets'],[],case)
if __name__=='__main__':unittest.main()
