"""Archive aliases and fresh rediscovery after completed local imports."""
import copy,time,unittest
from unittest.mock import patch
import test_wallet_server16 as whole
import test_wallet_server7 as history
from agent_rpc import request
from agent_hub import AgentHub,digest
from agent_state import validate

class Rediscovery(unittest.TestCase):
 def setUp(self):
  self.f=whole.WholeArchive();self.f.setUp();self.addCleanup(self.f.doCleanups);self.hub=self.f.hub
 def completed(self):
  self.f.initial()
  with self.hub.edit() as state:
   for r in state['requests'].values():r.update(state='complete',finished_utc='2026-11-14T01:00:00Z',message='Actual verified import')
   self.hub.transfers.schedule_queues(state)
  return copy.deepcopy(self.hub.read()['requests'])
 def deleted(self):
  self.f.scope(38,51,False,1,0,False);inv=self.hub.inventories[self.f.f.b['node_id']];inv['wallets']=[];inv['archive_wallets']=[];inv['extinct_summaries']={};inv['scanned_utc']='2026-11-15T01:00:00Z'
 def exchange(self):return self.f.exchange(self.f.f.b)
 def test_deleted_archive_gets_new_full_offer_and_challenge_without_rewriting_completed_import(self):
  old=self.completed();self.deleted();self.exchange();state=self.hub.read();new=[r for k,r in state['requests'].items() if k not in old];self.assertEqual(len(new),2);self.assertTrue(all(len(r['public_wallet']['descriptors'])==38 and r['queue_visible'] for r in new));self.assertTrue(all(r['proposal']['preview_challenge']!=next(iter(old.values()))['proposal']['preview_challenge'] for r in new));self.assertTrue(all(not r.get('signed_preview') for r in new))
  for k,r in old.items():self.assertEqual(state['requests'][k],r)
  self.exchange();self.assertEqual(len(self.hub.read()['requests']),4);validate(self.hub.read(),{self.f.f.user},self.f.f.config)
 def test_same_scope_completed_import_can_be_received_again_after_deletion(self):
  old=self.completed();self.deleted();self.f.scope(32,46,True,1,0,False);inv=self.hub.inventories[self.f.f.b['node_id']];inv.update(wallets=[],scanned_utc='2026-11-15T01:00:00Z',extinct_summaries={});self.exchange();new=[r for k,r in self.hub.read()['requests'].items() if k not in old];self.assertEqual(len(new),2);self.assertNotEqual(new[0]['transfer_id'],next(iter(old.values()))['transfer_id'])
 def test_failed_stale_unloaded_scanning_and_reconnected_destinations_do_not_prove_deletion(self):
  for mode in ('failed','stale','unloaded','scanning','reconnected','before_completion'):
   with self.subTest(mode=mode):
    # New independent fixture avoids retained invitation state between cases.
    f=Rediscovery();f.setUp()
    try:
     old=f.completed();f.deleted();n=f.f.f.b;inv=f.hub.inventories[n['node_id']]
     if mode in ('failed','unloaded'):inv['complete']=False
     elif mode=='stale':inv['history_checked_at']=0
     elif mode=='reconnected':f.hub.inventory_display[n['node_id']]['token']='previous'
     elif mode=='scanning':inv['wallets']=[{**copy.deepcopy(f.f.target),'scanning':True}]
     else:inv['scanned_utc']='2026-11-14T00:59:59Z'
     # Same-scope source so the existing completion is the relevant blocker.
     f.hub.inventories[f.f.f.a['node_id']]['wallets']=[f.f.archive(32)]
     f.exchange();self.assertEqual(len(f.hub.read()['requests']),len(old))
    finally:f.doCleanups()
 def test_denial_error_or_recovery_is_not_automatically_retried(self):
  old=self.completed();self.deleted();self.hub.inventories[self.f.f.a['node_id']]['wallets']=[self.f.archive(32)]
  for status in ('denied','error','recovery_required'):
   with self.hub.edit() as state:
    for r in state['requests'].values():r['state']=status
   self.exchange();self.assertEqual(len(self.hub.read()['requests']),len(old),status)
 def test_deleted_ordinary_wallet_also_reappears_but_local_deny_and_pairing_remain_effective(self):
  from test_wallet_server2 import CurrentProtocol
  f=CurrentProtocol();f.setUp();self.addCleanup(f.doCleanups);f.caps.append('wallet_sync_offers_v1');f.exchange(f.f.b)
  with f.hub.edit() as state:
   for r in state['requests'].values():r.update(state='complete',finished_utc='2026-11-14T01:00:00Z')
  for n in (f.f.a,f.f.b):
   f.hub.inventory_display[n['node_id']]={'token':n['connection_token']};f.hub.inventories[n['node_id']].update(history_checked_at=time.monotonic(),scanned_utc='2026-11-15T01:00:00Z')
  from sync_permissions import policy_id
  f.hub.permissions.live[f.f.b['node_id']]['record']['policies']=[policy_id(f.f.wallet['raw'])];f.hub.relay.reset();reply=f.exchange(f.f.b);offers=next(p for p in reply['proposals'] if p['kind']=='wallet_sync_offers')['offers'];self.assertEqual(len(offers),1);self.assertEqual(offers[0]['status'],'disabled');self.assertFalse(next(p for p in reply['proposals'] if p['kind']=='wallet_sync_queue')['requests']);self.assertEqual(len(f.hub.read()['requests']),4)
 def test_missing_source_and_current_wallet_do_not_reoffer_completed_work(self):
  old=self.completed();self.hub.inventories[self.f.f.b['node_id']]['wallets']=[self.f.archive(32)];self.exchange();self.assertEqual(len(self.hub.read()['requests']),len(old));self.deleted();self.hub.registry.connections.pop(self.f.f.a['connection_token']);self.exchange();self.assertEqual(len(self.hub.read()['requests']),len(old))

class ArchiveAlias(unittest.TestCase):
 setUp=history.HistoryOffers.setUp
 summary=history.HistoryOffers.summary
 exchange=history.HistoryOffers.exchange
 def test_exact_extinct_watch_summary_is_allowed_but_other_wallet_names_are_rejected(self):
  request('wallaby_extinct_summary',[],'extinct_watch')
  for name in ('active_wallet','extinct_watch_extra','../extinct_watch'):
   with self.assertRaises(ValueError):request('wallaby_extinct_summary',[],name)
 def test_source_alias_is_collected_and_history_merge_offered_after_completed_subset(self):
  from extinct_sync import containers
  self.exchange(self.f.b)
  with self.hub.edit() as state:
   for r in state['requests'].values():r['state']='complete'
  self.sa=self.summary(7,complete=False)
  raw=copy.deepcopy(containers(self.children)[0]['raw']);raw['wallet_name']='extinct_watch';labels={a:m['label'] for w in self.children for a,m in w['address_labels'].items()};calls=[]
  def rpc(node,method,params=None,wallet=None):
   calls.append((method,wallet))
   if method=='listwallets':return ['extinct_watch']
   if method=='listwalletdir':return {'wallets':[{'name':'extinct_watch'}]}
   if method=='getwalletinfo':return {'walletname':'extinct_watch','private_keys_enabled':False,'wallaby_extinct':True}
   if method=='listdescriptors':return raw
   if method=='getaddressinfo':return {'labels':[labels[params[0]]]}
   if method=='wallaby_extinct_summary':return self.sa
   raise AssertionError(method)
  node=self.f.a['node_id'];token=self.f.a['connection_token']
  with patch.object(self.hub,'rpc',side_effect=rpc):
   self.hub.inventory_times[node]=0;AgentHub.refresh_inventory(self.hub,node,token)
  self.assertIn(('wallaby_extinct_summary','extinct_watch'),calls);self.assertEqual(self.hub.inventories[node]['extinct_summaries'],{'extinct_watch':self.sa});reply=self.exchange(self.f.b);self.assertEqual(len(self.hub.read()['requests']),4);self.assertTrue(any(r.get('history_sync') and r['state']=='pending' for r in self.hub.read()['requests'].values()));self.assertTrue(next(p for p in reply['proposals'] if p['kind']=='wallet_sync_queue')['requests'])

if __name__=='__main__':unittest.main()
