"""Saved policy aliases, loaded-disc presence and stable gain display."""
import copy,json,tempfile,unittest
from pathlib import Path
from decimal import Decimal
import test_build72 as fixtures
from balance_identity import canonicalise
from preferences import resource_id,FamilyStore
from balance_store import BalanceStore
from descriptor_store import DescriptorStore
from live_wallet_traits import disc_presence,disc_flags,annotate
from current_balances import reconcile,history_signature

class Cards(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.Refresh();self.f.setUp();self.addCleanup(self.f.doCleanups);self.cfg=self.f.f.config;self.wallet=self.f.f.wallet;self.ident=self.wallet['id'];self.old='a'*64
  aliases=Path(self.cfg).parent/'data/builder-resource-aliases.json';aliases.write_text(json.dumps({resource_id('descriptor',self.old):resource_id('descriptor',self.ident)}))
 def row(self,ident):return {'kind':'wallet','descriptor_id':ident,'name':'Same label','owner_id':self.f.f.user,'owner_name':'Example','smsf':False,'btc':'.001','cash_aud':'0','cost_basis_aud':'20','value_aud':'100','state':'profit'}
 def test_actual_saved_balance_uses_current_identity_and_multisig_only_once(self):
  store=BalanceStore(self.cfg);store.save('verified',{'balances':{'wallets':[self.row(self.old)],'price_aud_per_btc':'100000'}})
  user=next(u for u in FamilyStore(self.cfg).snapshot()['users'] if u['id']==self.f.f.user)
  result=store.personal('verified',user);rows=result['balances']['wallets'];self.assertEqual(len(rows),1);self.assertEqual(rows[0]['descriptor_id'],self.ident);self.assertTrue(rows[0]['has_vault']);self.assertEqual(rows[0]['multisig'],[{'required':3,'total':5}]);self.assertEqual(rows[0]['cost_basis_aud'],'20')
  self.assertEqual(store.load('verified')['result']['balances']['wallets'][0]['descriptor_id'],self.old,'display does not rewrite saved accounting evidence')
 def test_duplicate_generations_never_add_balances_and_same_names_alone_never_merge(self):
  balance={'wallets':[self.row(self.old),self.row(self.ident),self.row('b'*64)]};catalog={'wallets':[self.wallet]};canonicalise(self.cfg,balance,catalog);self.assertEqual(len(balance['wallets']),2);self.assertEqual(balance['wallets'][0]['btc'],'.001');self.assertEqual(sum(Decimal(r['btc']) for r in balance['wallets']),Decimal('.002'))
 def test_loaded_private_disc_counts_alongside_node_copies_but_not_when_disconnected(self):
  node=self.f.f.a['node_id'];disc=copy.deepcopy(self.f.accounts[node][-1]);disc.update(archive_id='f'*64,signing_only=True)
  for inventory in self.f.hub.inventories.values():inventory['wallets']=[w for w in inventory['wallets'] if not w.get('archive_id')]
  self.f.hub.inventories[node]['wallets'].append(disc)
  self.f.checks.rows.clear();catalog={'wallets':[self.wallet]}
  self.assertFalse(disc_flags(catalog,self.f.hub.registry)[self.ident]);self.assertTrue(disc_presence(catalog,self.f.hub.registry)[self.ident])
  report={'balances':{'wallets':[dict(self.row(self.ident),multisig=[{'required':3,'total':5}])]}};annotate(report,catalog,self.f.hub.registry);self.assertTrue(report['balances']['wallets'][0]['has_disc'])
  self.f.hub.inventories[node]['wallets'].remove(disc);self.assertFalse(disc_presence(catalog,self.f.hub.registry)[self.ident])

class Gains(unittest.TestCase):
 def row(self):return {'kind':'wallet','descriptor_id':'w','btc':'1','cash_aud':'0','cost_basis_aud':'20','state':'profit','watch_checked_utc':'2026-11-01T00:00:00Z'}
 def chain(self):return {'scanned_utc':'2026-11-06T00:00:00Z','wallets':[{'id':'w','pending_btc':'0','records':[{'txid':'old','sats':100000000,'fee_sats':0,'fee_only':False,'utc':'2026-10-30T00:00:00Z','confirmations':6}]}]}
 def test_rescan_and_confirmation_changes_preserve_basis_and_revalue_gain(self):
  row=self.row();chain=self.chain();row['balance_history_signature']=history_signature(chain['wallets'][0]);report={'balances':{'wallets':[row],'price_aud_per_btc':'100'}};chain['wallets'][0]['records'][0]['confirmations']=20
  reconcile(report,{},chain);self.assertEqual(row['cost_basis_aud'],'20');self.assertEqual(Decimal(row['unrealised_gain_aud']),Decimal(80));self.assertEqual(row['state'],'profit')
 def test_older_saved_verified_basis_does_not_expire_on_a_new_scan_timestamp(self):
  row=self.row();reconcile({'balances':{'wallets':[row],'price_aud_per_btc':'100'}},{},self.chain());self.assertEqual(row['cost_basis_aud'],'20')
 def test_new_same_net_transaction_and_real_balance_change_still_clear_basis(self):
  for net in (0,10000):
   row=self.row();chain=self.chain();row['balance_history_signature']=history_signature(chain['wallets'][0]);chain['wallets'][0]['records'].append({'txid':'new','sats':net,'fee_sats':0,'fee_only':False,'utc':'2026-11-05T00:00:00Z'})
   reconcile({'balances':{'wallets':[row],'price_aud_per_btc':'100'}},{},chain);self.assertIsNone(row['cost_basis_aud']);self.assertEqual(row['state'],'unavailable')
