"""Public ledger, bounded duplicate cards and clamped planning previews."""
import copy,sys,unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from wallet_history import rows
from transaction_builder import funded_vault
from fee_planner import preview_plan,plan,LiveCoins
from test_build7 import addresses
from wallet_sync_queue import current_agent
from types import SimpleNamespace

class Ledger(unittest.TestCase):
 def fixture(self):
  a,b,c='a'*64,'b'*64,'c'*64;uid='wallet'
  txs={a:{'height':100,'utc':'2026-01-01T03:04:05Z','inputs':[],'outputs':[{'value':100000,'script':'mine','address':'receive-one'},{'value':200000,'script':'mine-two','address':'receive-two'}],'fee_known':False,'fee_sats':0},b:{'height':105,'utc':'2026-01-02T04:05:06Z','inputs':[{'txid':a,'vout':0,'value':100000,'script':'mine'}],'outputs':[{'value':40000,'script':'external','address':'external-destination'},{'value':59000,'script':'change','address':'mine-change'}],'fee_known':True,'fee_sats':1000,'rbf':True,'segwit':True,'taproot':False},c:{'height':106,'utc':'2026-01-03T05:06:07Z','inputs':[{'txid':b,'vout':1,'value':59000,'script':'change'}],'outputs':[{'value':58000,'script':'refresh','address':'new-vault'}],'fee_known':True,'fee_sats':1000}}
  chain={'transactions':txs,'wallet_outputs':{a+':0':uid,a+':1':uid,b+':1':uid,c+':0':uid}}
  wallet={'id':uid,'raw':{'descriptors':[{'desc':'receive-policy','internal':False}]},'node_history':[{'txid':b,'category':'send','address':'external-destination','confirmations':6},{'txid':c,'vout':0,'category':'send','address':'new-vault','confirmations':5},{'txid':c,'vout':0,'category':'receive','parent_descs':['receive-policy'],'confirmations':5}]}
  return chain,wallet,(a,b,c)
 def test_grouped_receive_multiple_addresses_balance_send_gross_and_fee(self):
  chain,w,(a,b,c)=self.fixture();r=rows(chain,w,110);self.assertEqual([v['txid'] for v in r],[b,a]);self.assertEqual(r[0]['amount_sats'],'-41000');self.assertEqual(r[0]['net_sats'],'40000');self.assertEqual(r[0]['fee_sats'],'1000');self.assertEqual(r[0]['balance_sats'],'259000');self.assertEqual(r[1]['amount_sats'],'300000');self.assertEqual(r[1]['balance_sats'],'300000');self.assertIsNone(r[1]['fee_sats']);self.assertEqual(r[0]['address_query'],'external-destination')
 def test_self_transfer_reports_send_then_receive_with_receive_address(self):
  chain,w,(a,b,c)=self.fixture();r=rows(chain,w,111)[0];self.assertEqual(r['txid'],c);self.assertEqual(r['amount_sats'],'58000');self.assertEqual(r['net_sats'],'58000');self.assertEqual(r['balance_sats'],'258000');self.assertEqual(r['address_query'],'new-vault')
 def test_multiple_send_destinations_link_txid(self):
  chain,w,(a,b,c)=self.fixture();w['node_history'].append({'txid':b,'category':'send','address':'other-recipient','confirmations':6});r=rows(chain,w,110)[0];self.assertEqual(r['address'],'Multiple send addresses');self.assertEqual(r['address_query'],b)
 def test_six_confirmations_boundary_and_offline_saved_confirmation_counts(self):
  chain,w,(a,b,c)=self.fixture();self.assertEqual(len(rows(chain,w,104)),0);self.assertEqual([r['txid'] for r in rows(chain,w,105)],[a]);self.assertEqual([r['txid'] for r in rows(chain,w)],[b])
 def test_equal_block_ancestry_order_keeps_running_balance(self):
  chain,w,_=self.fixture();[t.update(height=100) for t in chain['transactions'].values()];r=rows(chain,w,105);self.assertEqual([x['balance_sats'] for x in r],['258000','200000','259000','300000'])
 def test_missing_owned_input_value_is_not_a_fabricated_balance(self):
  chain,w,_=self.fixture();list(chain['transactions'].values())[1]['inputs'][0]['value']=None
  with self.assertRaisesRegex(ValueError,'input value'):rows(chain,w,111)
 def test_shared_fee_not_fabricated_as_wallet_share(self):
  chain,w,_=self.fixture();list(chain['transactions'].values())[1]['joint']=True;r=rows(chain,w,110)[0];self.assertTrue(r['shared_fee']);self.assertIsNone(r['net_sats'])
 def test_funded_vault_detection_includes_expired_unspent_but_not_spent_or_ordinary(self):
  chain,w,(a,b,c)=self.fixture();w['vault_evidence']=[{'txid':a,'vout':1,'height':1}];self.assertTrue(funded_vault(w,chain));w['vault_evidence'][0]['vout']=0;self.assertFalse(funded_vault(w,chain));w['vault_evidence']=[];self.assertFalse(funded_vault(w,chain))

 def test_real_block_position_orders_independent_receipts_before_lexical_txid_order(self):
  chain,w,(a,b,c)=self.fixture();d='d'*64;chain['transactions'][a]['block_index']=2;chain['transactions'][d]={'height':100,'block_index':1,'utc':'2026-01-01T03:04:05Z','inputs':[],'outputs':[{'value':50000,'script':'mine-two','address':'receive-two'}]};chain['wallet_outputs'][d+':0']=w['id'];r=rows(chain,w,110);self.assertEqual(next(x for x in r if x['txid']==a)['balance_sats'],'350000');self.assertEqual(next(x for x in r if x['txid']==d)['balance_sats'],'50000');self.assertEqual([x['txid'] for x in r[-2:]],[a,d])
 def test_tax_loss_and_purchase_records_do_not_change_physical_bitcoin_ledger(self):
  chain,w,_=self.fixture();before=rows(chain,w,111);w['records']=[{'txid':'C1:tax-only','sats':-999999999,'cgt_loss':True}];w['cost_basis_aud']='incorrect';self.assertEqual(rows(chain,w,111),before)

class Preview(unittest.TestCase):
 def fixture(self):
  a,b,_=addresses();catalog={'wallets':[{'id':'source','name':'Source','can_send':True,'address':a},{'id':'target','can_receive':True,'address':b},{'id':'other','can_receive':True,'address':a}]};coins=LiveCoins();coins['source']=[{'txid':'a'*64,'vout':0,'value':100000,'weight':273,'witness':True},{'txid':'b'*64,'vout':0,'value':20000,'weight':273,'witness':True}];edges=[{'from':'source','to':'network-fee','amount_sats':'0','fee_rate':'1'},{'from':'source','to':'target','amount_sats':'999999','fee_rate':'0'}];return edges,catalog,coins
 def test_oversize_is_exact_maximum_with_fee_and_still_prepares(self):
  edges,catalog,coins=self.fixture();r=preview_plan(edges,catalog,coins,{'from':'source','to':'target'});adjusted=r['preview_adjustments'][0];self.assertTrue(adjusted['max']);self.assertEqual(int(adjusted['amount_sats'])+int(r['total_fee_sats']),120000);edges[1].update(adjusted);self.assertTrue(plan(edges,catalog,coins)['can_continue'])
 def test_clamp_reserves_other_payments_and_does_not_mutate_input(self):
  edges,catalog,coins=self.fixture();edges.append({'from':'source','to':'other','amount_sats':'20000','fee_rate':'0'});before=copy.deepcopy(edges);r=preview_plan(edges,catalog,coins,{'from':'source','to':'target'});self.assertEqual(edges,before);self.assertEqual(int(r['preview_adjustments'][0]['amount_sats'])+int(r['total_fee_sats'])+20000,120000)
 def test_small_edit_is_not_max_or_changed(self):
  edges,catalog,coins=self.fixture();edges[1]['amount_sats']='5000';r=preview_plan(edges,catalog,coins,{'from':'source','to':'target'});self.assertNotIn('preview_adjustments',r);self.assertTrue(r['can_continue'])
 def test_maximum_checkbox_resolves_without_apply(self):
  edges,catalog,coins=self.fixture();edges[1].update(max=True,amount_sats='0');r=preview_plan(edges,catalog,coins,{'from':'source','to':'target'});self.assertGreater(int(r['maximum_amounts']['source']),0)
 def test_fee_edit_also_clamps_existing_payment(self):
  edges,catalog,coins=self.fixture();r=preview_plan(edges,catalog,coins,{'from':'source','to':'network-fee'});self.assertEqual(r['preview_adjustments'][0]['to'],'target')
 def test_unsupported_old_agent_is_not_current(self):
  for version,expected in [('2.0.0~dev55',False),('2.0.0~dev56',True),('2.0.0',True),(None,False)]:self.assertEqual(current_agent(SimpleNamespace(registry=SimpleNamespace(connections={'t':{'node_id':'n','agent_version':version}})),'n'),expected)

class CurrentProtocol(unittest.TestCase):
 def test_register_rejects_unknown_and_older_agents_without_creating_nodes(self):
  import tempfile
  from nodes import NodeRegistry
  with tempfile.TemporaryDirectory() as tmp:
   reg=NodeRegistry(Path(tmp)/'config.cfg');reg.health.closed=True
   for version in (None,'2.0.0~dev8','2.0.0~dev55','garbage'):
    with self.assertRaisesRegex(ValueError,'Build 56'):reg.register('02:00:00:00:00:65','fixture',{'version':1,'methods':[]},version)
   self.assertEqual(reg._read()['nodes'],[])
 def test_missing_rpc_capability_object_is_rejected(self):
  from agent_rpc import capabilities
  with self.assertRaises(ValueError):capabilities(None)
 def test_no_version_based_permission_bypass(self):
  from sync_permissions import Permissions
  hub=SimpleNamespace(registry=SimpleNamespace(connections={'token':{'node_id':'n'}}));permissions=Permissions(hub)
  self.assertIsNone(permissions.permits('n',{}));self.assertFalse(permissions.allows_offer('n',{}))
 def test_three_related_cards_and_unfunded_duplicates_are_rejected(self):
  from builder_destinations import Destinations
  store=Destinations('/tmp/build65-unused-config');store.get=lambda ident:{'base':'v'}
  with self.assertRaisesRegex(ValueError,'two cards'):store.enrich({'wallets':[{'id':'v','funded_vault':True}]},['v','receive-a','receive-b'])
  with self.assertRaisesRegex(ValueError,'funded vault'):store.enrich({'wallets':[{'id':'v','funded_vault':False}]},['v','receive-a'])

class AUDCeiling(unittest.TestCase):
 def test_large_aud_preview_caps_at_available_satoshis(self):
  from fiat_amount import convert
  r=convert('999999999999',{'aud_per_btc':'100000'},'100000');self.assertEqual(r['sats'],'100000');self.assertEqual(r['estimated_aud'],'100.00')
 def test_ceiling_cannot_loosen_supply_or_precision(self):
  from fiat_amount import convert
  for ceiling in ('2100000000000001','1.2','-1',123):
   with self.assertRaises(ValueError):convert('100',{'aud_per_btc':'100000'},ceiling)
