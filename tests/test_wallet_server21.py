"""Internal staging cannot shadow an archive; signer readiness is retained."""
import copy,unittest
from unittest.mock import patch
import test_wallet_server20 as previous
import test_build28 as historical
from agent_hub import AgentHub
from node_wallets import NodeWalletLoader
from wallet_sync_hints import wallets
from wallet_visibility import internal,history_staging,advisory_wallet

HISTORY='.wallaby-history-'+('a'*24)
POLICY='Wallaby policy '+('b'*20)
KEY='Wallaby key '+('c'*12)+' '+('d'*8)

class Visibility(unittest.TestCase):
 def test_reserved_patterns_match_only_complete_generated_names(self):
  for name in (HISTORY,HISTORY.upper(),POLICY,POLICY+'_watch',KEY,KEY+'_watch'):self.assertTrue(internal(name),name)
  for name in ('Extinct','extinct_watch','Treasury','Treasury Node Australia - Signer','Wallaby History Family','Wallaby policy notes','.wallaby-history-short',HISTORY+'-notes',KEY+' archive',None):self.assertFalse(internal(name),name)
  self.assertTrue(history_staging(HISTORY));self.assertFalse(history_staging(KEY));self.assertFalse(history_staging(POLICY))
 def test_internal_actual_route_and_internal_export_name_both_exclude_hints(self):
  for field in ('name','raw'):
   w={'name':'Treasury','raw':{'wallet_name':'Treasury'}}
   if field=='name':w['name']=HISTORY
   else:w['raw']['wallet_name']=KEY
   self.assertFalse(advisory_wallet(w))

class Advisory(unittest.TestCase):
 setUp=previous.Hints.setUp
 fresh=previous.Hints.fresh
 exchange=previous.Hints.exchange
 hints=previous.Hints.hints
 def children(self):return historical.ExtinctSync.children(self.f)
 def test_staging_excluded_before_extinct_grouping_cannot_poison_real_archive(self):
  real=self.children();stage=copy.deepcopy(real[0]);stage['name']=HISTORY;stage['raw']['descriptors'][0]['timestamp']=123456;stage['address_labels']={a:{'label':'Conflicting staged label','lost_utc':None} for a in stage['address_labels']};original=copy.deepcopy(stage)
  self.hub.inventories[self.a['node_id']]['wallets']=[stage]+real
  p=self.hints();self.assertEqual(len(p['offers']),1);self.assertEqual(p['offers'][0]['public_wallet']['wallet_name'],'Extinct');self.assertEqual(len(p['offers'][0]['public_wallet']['descriptors']),2);self.assertEqual(stage,original);self.assertFalse(self.hub.read()['requests'])
 def test_duplicate_descriptor_staging_does_not_shadow_ordinary_wallet(self):
  real=copy.deepcopy(self.f.node_wallet);stage=copy.deepcopy(real);stage['name']=HISTORY;stage['raw']['wallet_name']=HISTORY;self.hub.inventories[self.a['node_id']]['wallets']=[stage,real];p=self.hints();self.assertEqual([o['public_wallet']['wallet_name'] for o in p['offers']],[real['raw']['wallet_name']])
 def test_all_reserved_accounts_removed_without_relying_on_local_denials(self):
  values=[]
  for name in (HISTORY,POLICY,KEY,KEY+'_watch'):
   w=copy.deepcopy(self.f.node_wallet);w['name']=w['raw']['wallet_name']=name;values.append(w)
  self.hub.inventories[self.a['node_id']]['wallets']=values;before=copy.deepcopy(values)
  with patch.object(self.hub.permissions,'permits',side_effect=AssertionError('Denied on Server')):self.assertEqual(self.hints()['offers'],[])
  self.assertEqual(values,before)
 def test_previous_bad_hint_is_withdrawn_on_next_snapshot_without_touching_outcomes(self):
  real=self.children();self.hub.inventories[self.a['node_id']]['wallets']=real
  with self.hub.edit() as state:state['nodes'][self.b['node_id']]={'sync_offer_revision':7,'sync_offer_snapshot':[{'old':'internal history hint'}]}
  p=self.hints();self.assertEqual(p['revision'],8);self.assertEqual([o['public_wallet']['wallet_name'] for o in p['offers']],['Extinct']);self.assertFalse(self.hub.read()['requests'])
 def test_inventory_skips_staging_but_keeps_policy_and_private_signer_for_builder(self):
  calls=[];raw=self.f.node_wallet['raw'];names=[HISTORY,KEY,POLICY,'Treasury'];unloaded='.wallaby-history-'+('e'*24)
  def rpc(node,method,params=None,wallet=None):
   calls.append((method,wallet))
   if method=='listwallets':return names
   if method=='listwalletdir':return {'wallets':[{'name':n} for n in names+[unloaded]]}
   if wallet in (HISTORY,unloaded):raise AssertionError('Retained staging must not be queried')
   if method=='getwalletinfo':return {'walletname':wallet,'private_keys_enabled':wallet!=POLICY,'scanning':False}
   if method=='listdescriptors':return dict(copy.deepcopy(raw),wallet_name=wallet)
   raise AssertionError(method)
  self.hub.rpc=rpc;self.hub.inventory_times[self.a['node_id']]=0
  with patch.object(self.hub.wallet_builder,'confirm_installed') as confirm:
   AgentHub.refresh_inventory(self.hub,self.a['node_id'],self.a['connection_token']);inv=self.hub.inventories[self.a['node_id']];self.assertTrue(inv['complete'],inv);self.assertEqual({w['name'] for w in inv['wallets']},{KEY,POLICY,'Treasury'});self.assertIn(HISTORY,inv['wallet_directory']);self.assertIn(unloaded,inv['wallet_directory']);self.assertEqual(inv['unloaded_wallets'],[]);self.assertEqual(len(confirm.call_args.args[2]),3)
  self.assertEqual([o['public_wallet']['wallet_name'] for o in self.hints()['offers']],['Treasury'])
 def test_ordinary_unloaded_wallet_remains_incomplete(self):
  loader=NodeWalletLoader(self.f.registry);node={'id':self.a['node_id'],'hostname':'first'}
  def rpc(n,m,params=None,wallet=None):return ['Treasury'] if m=='listwallets' else {'wallets':[{'name':'Treasury'},{'name':HISTORY},{'name':'Actual unloaded wallet'}]}
  loader.rpc=rpc
  with self.assertRaisesRegex(ValueError,'Actual unloaded wallet'):loader.discover_node(node)
 def test_history_discovery_and_cached_export_skip_staging_without_extra_rpc(self):
  loader=NodeWalletLoader(self.f.registry);node={'id':self.a['node_id'],'hostname':'first'};names=[HISTORY,'Treasury']
  def rpc(n,m,params=None,wallet=None):return names if m=='listwallets' else {'wallets':[{'name':n} for n in names+[HISTORY.upper()]]}
  loader.rpc=rpc;self.assertEqual(loader.discover_node(node),[(node,'Treasury')])
  with patch.object(loader,'rpc',side_effect=AssertionError('Staging export issued RPC')):self.assertEqual(loader.export((node,HISTORY)),[])

if __name__=='__main__':unittest.main()
