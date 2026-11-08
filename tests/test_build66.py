"""Display holdings refresh independently of prior tax/parcel snapshots."""
import sys,unittest,copy,tempfile,json
from pathlib import Path
from decimal import Decimal as D
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from current_balances import reconcile
from wallet_valuation import revalue
from worker import load_core
from bitaroo_inputs import ledger_snapshot

class CurrentBalances(unittest.TestCase):
 def report(self):return {'balances':{'price_aud_per_btc':'110000','wallets':[{'owner_id':'u','smsf':False,'kind':'exchange','name':'Exchange','btc':'0.00487839','cash_aud':'0.01','cost_basis_aud':'500','planning_lots':[{'qty':'0.00487839'}],'record_count':1,'last_update_utc':'2026-10-22T22:15:16Z'}]}}
 def ledger(self,qty='0.00180679',cash='0.01'):
  return {'periods':{'2026-27':{'end':'2026-11-05','closing_btc':qty,'closing_aud':cash}},'btc_rows':[{'utc':'2026-11-05T08:23:12Z','balance':qty}],'aud_rows':[{'utc':'2026-11-05T08:23:12Z','balance':cash}]}
 def test_updated_statement_replaces_old_quantity_not_just_its_price(self):
  report=self.report();reconcile(report,{'ownership_runs':{'u':{'bitaroo_data':self.ledger()}}});row=report['balances']['wallets'][0];self.assertEqual(D(row['btc']),D('0.00180679'));self.assertEqual(D(row['value_aud']),D('198.75690000'));self.assertIsNone(row['cost_basis_aud']);self.assertEqual(row['planning_lots'],[])
  updated=revalue(report,{'aud_per_btc':'100000','observed_utc':'2026-11-06T00:00:00Z','source':'Fixture'});self.assertEqual(D(updated['balances']['wallets'][0]['value_aud']),D('180.689'));self.assertEqual(D(report['balances']['wallets'][0]['value_aud']),D('198.7569'))
 def test_personal_and_smsf_owners_are_separate_and_all_profiles_refresh(self):
  report=self.report();rows=report['balances']['wallets'];rows.extend([dict(rows[0],smsf=True),dict(rows[0],owner_id='other')]);snapshot={'ownership_runs':{'u':{'bitaroo_data':self.ledger(),'bitaroo_smsf_data':self.ledger('2','4')},'other':{'bitaroo_data':self.ledger('3','5')}}};reconcile(report,snapshot);self.assertEqual([D(r['btc']) for r in rows],[D('.00180679'),D(2),D(3)]);self.assertEqual([D(r['cash_aud']) for r in rows],[D('.01'),D(4),D(5)])
 def test_empty_current_fy_uses_header_balance_not_older_rows(self):
  report=self.report();ledger=self.ledger('0','25.50');ledger['aud_rows']=[];ledger['btc_rows']=[];reconcile(report,{'ownership_runs':{'u':{'bitaroo_data':ledger}}});row=report['balances']['wallets'][0];self.assertEqual(D(row['value_aud']),D('25.50'));self.assertEqual(D(row['cost_basis_aud']),0)
 def test_existing_build65_ledger_without_aud_header_uses_final_canonical_row(self):
  report=self.report();ledger=self.ledger();ledger['periods']['2026-27'].pop('closing_aud');ledger['aud_rows']=[{'utc':'2026-10-31T08:00:00Z','balance':'500'},{'utc':'2026-11-05T08:23:12Z','balance':'.01'}];reconcile(report,{'ownership_runs':{'u':{'bitaroo_data':ledger}}});self.assertEqual(D(report['balances']['wallets'][0]['cash_aud']),D('.01'))
 def test_unknown_cash_is_not_invented_as_zero_or_repriced_as_known(self):
  report=self.report();ledger=self.ledger();ledger['periods']['2026-27'].pop('closing_aud');ledger['aud_rows']=[];reconcile(report,{'ownership_runs':{'u':{'bitaroo_data':ledger}}});row=report['balances']['wallets'][0];self.assertIsNone(row['cash_aud']);self.assertIsNone(row['value_aud']);value=revalue(report,{'aud_per_btc':'100000','observed_utc':'now','source':'Fixture'});self.assertIsNone(value['balances']['wallets'][0]['value_aud'])
 def test_missing_or_invalid_ledger_does_not_replace_saved_balance(self):
  for ledger in ({},{'periods':{'2026-27':{'end':'2026-11-05','closing_btc':'NaN'}}}):
   report=self.report();before=copy.deepcopy(report);reconcile(report,{'ownership_runs':{'u':{'bitaroo_data':ledger}}});self.assertEqual(report,before)
 def test_live_wallet_receipts_sends_change_and_pending_replace_old_holdings(self):
  report={'balances':{'price_aud_per_btc':'100000','wallets':[{'kind':'wallet','descriptor_id':'id','btc':'2','cash_aud':'0','cost_basis_aud':'100','watch_checked_utc':'old'}]}};chain={'scanned_utc':'new','wallets':[{'id':'id','pending_btc':'.1','records':[{'txid':'receive','sats':100000000,'fee_sats':0,'fee_only':False},{'txid':'send','sats':-10000000,'fee_sats':1000,'fee_only':False},{'txid':'send','sats':-20000000,'fee_sats':1000,'fee_only':False},{'txid':'self','sats':-2000,'fee_sats':2000,'fee_only':True}]}]};reconcile(report,{},chain);row=report['balances']['wallets'][0];self.assertEqual(D(row['confirmed_btc']),D('.69997000'));self.assertEqual(D(row['btc']),D('.79997000'));self.assertEqual(D(row['value_aud']),D('79997'));self.assertIsNone(row['cost_basis_aud'])
 def test_unrelated_or_incomplete_chain_never_zeros_other_wallets(self):
  report=self.report();report['balances']['wallets'].append({'kind':'wallet','descriptor_id':'missing','btc':'3','value_aud':'330000'});before=copy.deepcopy(report);reconcile(report,{}, {'wallets':[]});self.assertEqual(report,before)
 def test_unchanged_verified_holdings_keep_their_basis(self):
  report=self.report();row=report['balances']['wallets'][0];row.update(btc='.00180679',record_count=2,last_update_utc='2026-11-05T08:23:12Z');reconcile(report,{'ownership_runs':{'u':{'bitaroo_data':self.ledger()}}});self.assertEqual(row['cost_basis_aud'],'500')
 def test_aud_header_balances_survive_cloning_and_saved_ledger(self):
  from family_tax import clone_reports
  from datetime import date
  core=load_core();r=core.ReportSet();r.ranges={2026:(date(2026,7,1),date(2026,11,5))};r.start_bal={2026:D(1)};r.close_bal={2026:D(1)};r.aud_start_bal={2026:D('12.34')};r.aud_close_bal={2026:D('12.34')};clone=clone_reports(r);clone.aud_close_bal[2026]=D(99);self.assertEqual(r.aud_close_bal[2026],D('12.34'));self.assertEqual(ledger_snapshot(core,r)['periods'][core.fmt_fy(2026)]['closing_aud'],'12.34')

class ServedAssets(unittest.TestCase):
 def test_rendered_page_bundles_wallet_history_and_does_not_leave_missing_script(self):
  from reporting import render_html
  page=render_html();self.assertIn('window.WallabyWalletHistory=',page);self.assertNotIn('<script src="/assets/wallet_history.js"',page)

class RefreshDecision(unittest.TestCase):
 def test_only_new_supplied_records_request_automatic_verification(self):
  from current_balances import needs_verification
  saved={'signature':'old','result':{'balances':{'valuation_utc':'2026-11-04T00:00:00Z'}}};old={'ownership_runs':{'u':{'completed_utc':'2026-11-03T00:00:00Z'}}};fresh={'ownership_runs':{'u':{'completed_utc':'2026-11-05T00:00:00Z'}}}
  self.assertFalse(needs_verification(saved,'new',old),'a node reconnect alone does not start another trace');self.assertTrue(needs_verification(saved,'new',fresh));self.assertFalse(needs_verification(saved,'old',fresh),'identical inputs do not need another trace');self.assertFalse(needs_verification(None,'new',fresh))

class VaultDisplay(unittest.TestCase):
 def test_public_placeholders_survive_restart_but_are_always_unverified(self):
  from vault_display import save,load,placeholders
  from nodes import NodeRegistry
  with tempfile.TemporaryDirectory() as tmp:
   config=Path(tmp)/'config.cfg';save(config,[{'id':'remembered','name':'Example Vault'}]);reg=NodeRegistry(config);reg.health.closed=True
   self.assertEqual(reg.vaults.known(),[{'id':'remembered','name':'Example Vault'}]);row=reg.vaults.value['wallets'][0];self.assertTrue(row['stale']);self.assertFalse(row['balance_available']);self.assertIsNone(row['current_height']);self.assertNotIn('balance_sats',row)
   reg.vaults.reset();self.assertEqual(reg.vaults.known()[0]['id'],'remembered')
 def test_expired_and_unfunded_public_policies_remain_known_from_catalog(self):
  from vault_display import known
  from descriptor_store import DescriptorStore,clean_wallet
  from vendor.embit.descriptor.checksum import checksum
  from preferences import FamilyStore
  with tempfile.TemporaryDirectory() as tmp:
   config=Path(tmp)/'config.cfg';FamilyStore(config);body='wsh(and_v(v:after(1),pk(0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798)))';w=clean_wallet({'wallet_name':'Old height empty vault','descriptors':[{'desc':body+'#'+checksum(body),'timestamp':0,'active':False,'internal':False}]});DescriptorStore(config).replace_node_wallets([w]);self.assertEqual(known(config)[0]['id'],w['id'])
 def test_display_cache_corruption_is_ignored_and_cannot_supply_verification(self):
  from vault_display import load,validate
  from storage import data_directory
  with tempfile.TemporaryDirectory() as tmp:
   config=Path(tmp)/'config.cfg';data_directory(config).mkdir(parents=True,exist_ok=True);(data_directory(config)/'vault-display.json').write_text('{bad');self.assertEqual(load(config),[])
   with self.assertRaises(ValueError):validate({'schema':1,'wallets':[{'id':'id','name':'Name','balance_sats':100}]})
 def test_aud_conversion_explicitly_marks_available_limit(self):
  from fiat_amount import convert
  self.assertTrue(convert('100000',{'aud_per_btc':'110000'},'100000')['limited_to_available'])

class VaultMembership(unittest.TestCase):
 def fixture(self):
  from test_build13 import Display
  f=Display();f.setUp();self.addCleanup(f.doCleanups);return f
 def test_offline_agents_do_not_remove_remembered_cards(self):
  from vault_display import load
  f=self.fixture();monitor=f.registry.vaults;monitor.refresh();before=monitor.known();f.registry.connections.clear()
  with f.hub.edit() as state:state['vaults']={}
  monitor.refresh();self.assertTrue(monitor.value['stale']);self.assertEqual(monitor.known(),before);self.assertEqual(load(f.config),before)
 def test_verified_absence_removes_public_display_cache(self):
  from vault_display import load
  f=self.fixture();monitor=f.registry.vaults;monitor.refresh();self.assertTrue(monitor.known())
  with f.hub.edit() as state:state['vaults']={}
  monitor.refresh();self.assertFalse(monitor.value['stale']);self.assertEqual(monitor.known(),[]);self.assertEqual(load(f.config),[])

class MaximumFees(unittest.TestCase):
 def fixture(self):
  from test_build65 import Preview
  return Preview().fixture()
 def test_maximum_recalculates_for_fee_rises_falls_and_other_payments_exactly(self):
  from fee_planner import plan
  edges,catalog,coins=self.fixture();edges[1].update(max=True,amount_sats='999999');edges.append({'from':'source','to':'other','amount_sats':'20000','fee_rate':'0'});amounts=[]
  for rate in ('1','2','5','0.5'):
   edges[0]['fee_rate']=rate;r=plan(edges,catalog,coins,details=True);amount=int(r['maximum_amounts']['source']);fee=int(r['wallet_fees_sats']['source']);self.assertEqual(amount+20000+fee,120000);self.assertEqual(sum(r['outputs'].values())+fee,120000);self.assertEqual(r['change_outputs'],0);self.assertEqual(r['input_count'],2);self.assertTrue(r['can_continue']);amounts.append(amount)
  self.assertGreater(amounts[0],amounts[1]);self.assertGreater(amounts[1],amounts[2]);self.assertGreater(amounts[3],amounts[0])
 def test_final_plan_rejects_an_overlarge_fixed_amount_or_fee_without_making_outputs(self):
  from fee_planner import plan
  edges,catalog,coins=self.fixture()
  with self.assertRaises(ValueError):plan(edges,catalog,coins)
  edges[1].update(max=True,amount_sats='1');edges[0]['fee_rate']='1000000'
  with self.assertRaises(ValueError):plan(edges,catalog,coins)
