"""History fingerprints are discovery hints, never historical data or approval."""
import copy,json,time,unittest
import test_wallet_server2 as fixtures
import test_build28 as history_fixtures
from agent_hub import digest
from agent_rpc import request
from extinct_history_sync import METHOD,validate,validate_saved
from agent_state import validate as validate_profile
from sync_permissions import policy_id

class HistoryOffers(unittest.TestCase):
 def setUp(self):
  fixtures.CurrentProtocol.setUp(self);self.caps.append('wallet_sync_offers_v1');self.children=history_fixtures.ExtinctSync.children(self.f)
  self.sa=self.summary(5);self.sb=self.summary(3)
  for n,s in ((self.f.a,self.sa),(self.f.b,self.sb)):
   c=self.hub.registry.connections[n['connection_token']];c['rpc_methods']=sorted(set(c['rpc_methods'])|{METHOD})
   self.hub.inventories[n['node_id']]={'complete':True,'wallets':copy.deepcopy(self.children),'extinct_summaries':{'Wallaby Extinct':s}}
   self.hub.inventory_display[n['node_id']]={'token':n['connection_token']};self.hub.inventory_times[n['node_id']]=time.monotonic();self.hub.caps[n['node_id']]=set(self.caps)
 def summary(self,count=5,complete=True,**extra):
  s={'version':1,'chain':'main','addresses':2,'transactions':count,'address_hash':'a'*64,'transaction_hash':digest({'transactions':count}),'label_hash':'b'*64,'history_complete':complete};s.update(extra);s['digest']=digest(s);return s
 exchange=fixtures.CurrentProtocol.exchange
 def rows(self):return list(self.hub.read()['requests'].values())
 def test_same_addresses_different_spent_history_offers_direct_sync(self):
  r=self.exchange(self.f.b);rows=self.rows();self.assertEqual(len(rows),2);self.assertTrue(all(x['history_sync'] for x in rows));self.assertTrue(all(x['source_has_private_keys'] is False for x in rows));self.assertEqual(next(x['node_id'] for x in rows if x['direction']=='send'),self.f.a['node_id'])
  p=next(p for p in r['proposals'] if p['kind']=='wallet_sync_queue')['requests'][0];self.assertEqual(p['transfer_version'],3);self.assertNotIn('history_sync',p);self.assertNotIn('transactions',p);self.assertNotIn('labels',p);validate_profile(self.hub.read(),{self.f.user},self.f.config)
 def test_unpaired_and_unknown_permissions_are_visible_but_not_executable(self):
  self.hub.relay.channels.clear();self.hub.permissions.live.clear();r=self.exchange(self.f.b)
  self.assertEqual(len(next(p for p in r['proposals'] if p['kind']=='wallet_sync_offers')['offers']),1);self.assertFalse(next(p for p in r['proposals'] if p['kind']=='wallet_sync_queue')['requests']);self.assertFalse(any(x.get('proposal') for x in self.rows()))
 def test_equal_summaries_need_no_sync_and_new_blocks_do_not_enter_digest(self):
  self.hub.inventories[self.f.b['node_id']]['extinct_summaries']['Wallaby Extinct']=copy.deepcopy(self.sa);self.exchange(self.f.b);self.assertFalse(self.rows())
 def test_label_disagreement_is_detected_without_fetching_labels_as_history(self):
  self.hub.inventories[self.f.b['node_id']]['extinct_summaries']['Wallaby Extinct']=self.summary(label_hash='c'*64);self.exchange(self.f.b);self.assertEqual(len(self.rows()),2)
 def test_stored_native_records_can_be_offered_without_local_scan_receipts(self):
  self.hub.inventories[self.f.a['node_id']]['extinct_summaries']['Wallaby Extinct']=self.summary(complete=False);self.hub.inventories[self.f.b['node_id']]['extinct_summaries']['Wallaby Extinct']=self.summary(3,complete=False);self.exchange(self.f.b);self.assertEqual(len(self.rows()),2);self.assertTrue(all(r.get('history_sync') for r in self.rows()))
 def test_stale_or_reconnected_inventories_wait(self):
  self.hub.inventory_display[self.f.a['node_id']]['token']='old';self.exchange(self.f.b);self.assertFalse(self.rows())
  self.hub.inventory_display[self.f.a['node_id']]['token']=self.f.a['connection_token'];self.hub.inventory_times[self.f.a['node_id']]=0;self.exchange(self.f.b);self.assertFalse(self.rows())
 def test_local_denial_preserves_public_discovery_without_execution(self):
  from extinct_sync import containers
  raw=containers(self.children)[0]['raw'];self.hub.permissions.live[self.f.b['node_id']]['record']['policies']=[policy_id(raw)];reply=self.exchange(self.f.b);self.assertEqual(len(self.rows()),2);self.assertFalse(any(r.get('proposal') for r in self.rows()));self.assertEqual(next(p for p in reply['proposals'] if p['kind']=='wallet_sync_offers')['offers'][0]['status'],'disabled');self.assertFalse(next(p for p in reply['proposals'] if p['kind']=='wallet_sync_queue')['requests'])
 def test_repeated_poll_and_terminal_outcomes_do_not_reissue_same_mismatch(self):
  self.exchange(self.f.b);before=copy.deepcopy(self.hub.read());self.exchange(self.f.b);self.assertEqual(self.hub.read()['requests'],before['requests'])
  for result in ('error','denied','complete'):
   with self.hub.edit() as state:
    for row in state['requests'].values():row['state']=result
   self.exchange(self.f.b);self.assertEqual(len(self.rows()),2)
 def test_receiver_union_can_trigger_reverse_comparison_with_new_fingerprints(self):
  self.exchange(self.f.b)
  with self.hub.edit() as state:
   for row in state['requests'].values():row['state']='complete'
  self.hub.inventories[self.f.b['node_id']]['extinct_summaries']['Wallaby Extinct']=self.summary(7);self.exchange(self.f.b);rows=[x for x in self.rows() if x['state']=='pending'];self.assertEqual(len(rows),2);self.assertEqual(next(x['node_id'] for x in rows if x['direction']=='send'),self.f.b['node_id'])
 def test_old_agents_ambiguous_archives_and_scanning_cannot_offer_history_update(self):
  c=self.hub.registry.connections[self.f.a['connection_token']];c['rpc_methods']=[m for m in c['rpc_methods'] if m!=METHOD];self.exchange(self.f.b);self.assertFalse(self.rows());c['rpc_methods']=sorted(set(c['rpc_methods'])|{METHOD})
  self.hub.inventories[self.f.a['node_id']]['wallets'][0]['scanning']=True;self.exchange(self.f.b);self.assertFalse(self.rows())
 def test_summary_and_saved_signal_validation_rejects_malformed_or_private_purpose(self):
  for s in ({**self.sa,'history_complete':1},{**self.sa,'digest':'0'*64},{**self.sa,'records':[]}):
   with self.assertRaises(ValueError):validate(s)
  self.exchange(self.f.b);row=self.rows()[0];validate_saved(row);row['source_has_private_keys']=True
  with self.assertRaises(ValueError):validate_saved(row)
 def test_summary_rpc_is_bounded_read_only_and_requires_exact_archive(self):
  request(METHOD,[],'Wallaby Extinct')
  for params,wallet in (([1],'Wallaby Extinct'),([],None),([],'active_wallet')):
   with self.assertRaises(ValueError):request(METHOD,params,wallet)
 def test_deliberate_retry_keeps_history_purpose_even_when_addresses_already_exist(self):
  self.exchange(self.f.b);before=self.rows();ident=before[0]['transfer_id']
  with self.hub.edit() as state:
   for row in state['requests'].values():row['state']='error'
  result=self.hub.transfers.retry(ident,True);rows=[r for r in self.rows() if r['transfer_id']==result['transfer_id']]
  self.assertEqual(len(rows),2);self.assertTrue(all(r['history_sync']==before[0]['history_sync'] for r in rows));self.assertTrue(all(r['source_has_private_keys'] is False for r in rows))
 def test_inventory_collects_optional_summary_and_failure_preserves_normal_inventory(self):
  from agent_hub import AgentHub
  from extinct_sync import containers
  from unittest.mock import patch
  raw=copy.deepcopy(containers(self.children)[0]['raw']);raw['wallet_name']='Wallaby Extinct';labels={a:m['label'] for w in self.children for a,m in w['address_labels'].items()};calls=[]
  def rpc(node,method,params=None,wallet=None):
   calls.append(method)
   if method=='listwallets':return ['Wallaby Extinct']
   if method=='listwalletdir':return {'wallets':[{'name':'Wallaby Extinct'}]}
   if method=='getwalletinfo':return {'walletname':'Wallaby Extinct','private_keys_enabled':False,'wallaby_extinct':True}
   if method=='listdescriptors':return raw
   if method=='getaddressinfo':return {'labels':[labels[params[0]]]}
   if method==METHOD:
    if broken[0]:raise ValueError('History verification is pending')
    return self.sa
   raise AssertionError(method)
  broken=[False];node=self.f.a['node_id'];token=self.f.a['connection_token']
  with patch.object(self.hub,'rpc',side_effect=rpc):
   self.hub.inventory_times[node]=0;AgentHub.refresh_inventory(self.hub,node,token);self.assertIn(METHOD,calls);self.assertEqual(self.hub.inventories[node]['extinct_summaries']['Wallaby Extinct'],self.sa)
   broken[0]=True;self.hub.inventory_times[node]=0;AgentHub.refresh_inventory(self.hub,node,token);self.assertTrue(self.hub.inventories[node]['complete']);self.assertEqual(len(self.hub.inventories[node]['wallets']),2);self.assertEqual(self.hub.inventories[node]['extinct_summaries'],{})
 def test_ambiguous_archives_do_not_choose_one_silently(self):
  self.hub.inventories[self.f.a['node_id']]['extinct_summaries']['Extinct']=self.sa;self.exchange(self.f.b);self.assertFalse(self.rows())
 def test_agent78_accepts_existing_signal_format_without_server_history_payload(self):
  import os,subprocess,sys
  source=os.environ.get('WALLABY_AGENT_HISTORY_SOURCE')
  if not source:self.skipTest('Set WALLABY_AGENT_HISTORY_SOURCE to Agent Build 78 source')
  reply=self.exchange(self.f.b);p=next(p for p in reply['proposals'] if p['kind']=='wallet_sync_queue')['requests'][0]
  code="import sys,json;sys.path.insert(0,sys.argv[1]);from build8_policy import proposal;proposal(json.loads(sys.stdin.read()));print('accepted')"
  out=subprocess.run([sys.executable,'-c',code,source],input=json.dumps(p),capture_output=True,text=True);self.assertEqual(out.returncode,0,out.stderr)
 def test_pending_retirement_defers_another_archive_operation(self):
  from extinct_history_sync import schedule
  state=self.hub.read();state['requests']['retiring']={'kind':'wallet_retire','state':'pending','node_id':self.f.a['node_id']};ready={c['node_id']:c for c in self.hub.registry.connections.values()};schedule(self.hub,state,ready);self.assertEqual(len(state['requests']),1)

 def test_frozen_history_request_pauses_if_peer_no_longer_supports_direct_history(self):
  self.exchange(self.f.b);before=copy.deepcopy(self.hub.read()['requests']);c=self.hub.registry.connections[self.f.a['connection_token']];c['rpc_methods']=[m for m in c['rpc_methods'] if m!=METHOD]
  reply=self.exchange(self.f.b);self.assertFalse(next(p for p in reply['proposals'] if p['kind']=='wallet_sync_queue')['requests'])
  for key,row in self.hub.read()['requests'].items():self.assertEqual(row['proposal'],before[key]['proposal'])
