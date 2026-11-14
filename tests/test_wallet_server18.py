"""Extinct reviews must reach the Agent despite unrelated unloaded folders."""
import copy,time,unittest
import test_wallet_server17 as previous
from sync_discovery import local_archive_review

class UnloadedArchive(unittest.TestCase):
 setUp=previous.Rediscovery.setUp
 completed=previous.Rediscovery.completed
 deleted=previous.Rediscovery.deleted
 exchange=previous.Rediscovery.exchange
 def partial(self):
  for n,folders in ((self.f.f.a,['source unrelated']),(self.f.f.b,['receiver unrelated one','receiver unrelated two'])):
   c=self.hub.registry.connections[n['connection_token']];c['agent_version']='2.0.0~dev98';inv=self.hub.inventories[n['node_id']];inv.update(complete=False,loaded_complete=True,unloaded_wallets=folders,history_checked_at=time.monotonic(),scanned_utc='2026-11-15T02:00:00Z');self.hub.inventory_display[n['node_id']]={'token':n['connection_token']}
 def queues(self,reply):return next(p for p in reply['proposals'] if p['kind']=='wallet_sync_queue')['requests']
 def offers(self,reply):return next(p for p in reply['proposals'] if p['kind']=='wallet_sync_offers')['offers']
 def test_reported_deleted_archive_completed_subset_pending_preserve_two_receiver_one_source_unloaded(self):
  old=self.completed();self.deleted();self.partial();preserve={'kind':'wallet_retire','state':'pending','node_id':self.f.f.b['node_id'],'proposal':{'version':3,'phase':'preserve','delete_wallet':False,'public_wallet':copy.deepcopy(self.f.f.wallet['raw'])}}
  with self.hub.edit() as state:state['requests']['preserve']=copy.deepcopy(preserve)
  reply=self.exchange();requests=self.queues(reply);self.assertEqual(len(requests),1);p=requests[0];self.assertEqual(len(p['public_wallet']['descriptors']),38);self.assertFalse(p['source_has_private_keys']);self.assertFalse(p['requires_blockchain_redownload']);self.assertNotIn('absence_verified',p);self.assertNotIn('local_ownership_review',p)
  offers=self.offers(reply);self.assertEqual(len(offers),1);self.assertEqual(offers[0]['status'],'discovery_pending');self.assertFalse(self.hub.inventories[self.f.f.b['node_id']]['complete'])
  state=self.hub.read();self.assertEqual(state['requests']['preserve'],preserve)
  for k,r in old.items():self.assertEqual(state['requests'][k],r)
  self.exchange();self.assertEqual(len(self.hub.read()['requests']),5)
 def test_same_scope_can_be_reviewed_again_without_claiming_unloaded_archive_absent(self):
  old=self.completed();self.deleted();self.hub.inventories[self.f.f.a['node_id']]['wallets']=[self.f.archive(32)];self.partial();reply=self.exchange();self.assertEqual(len(self.queues(reply)),1);self.assertNotIn(self.queues(reply)[0]['transfer_id'],{r['transfer_id'] for r in old.values()});self.assertEqual(self.offers(reply)[0]['status'],'discovery_pending')
 def test_completed_archive_that_may_be_unloaded_does_not_generate_endless_repeat_reviews(self):
  old=self.completed();self.deleted();self.hub.inventories[self.f.f.a['node_id']]['wallets']=[self.f.archive(32)];self.partial();self.hub.inventories[self.f.f.b['node_id']]['unloaded_wallets'].append('Wallaby Extinct');reply=self.exchange();self.assertFalse(self.queues(reply));self.assertEqual(len(self.hub.read()['requests']),len(old))
 def test_first_time_unloaded_archive_can_get_local_comparison_without_asserting_absence(self):
  self.deleted();self.partial();self.hub.inventories[self.f.f.b['node_id']]['unloaded_wallets'].append('Wallaby Extinct');reply=self.exchange();self.assertTrue(self.queues(reply));self.assertEqual(self.offers(reply)[0]['status'],'discovery_pending')
 def test_first_time_partial_receiver_gets_only_public_extinct_not_ordinary_wallet(self):
  self.deleted();self.partial();self.hub.inventories[self.f.f.a['node_id']]['wallets'].append(copy.deepcopy(self.f.f.node_wallet));reply=self.exchange();self.assertEqual(len(self.queues(reply)),1);self.assertTrue(all(d['desc'].startswith('addr(') for d in self.queues(reply)[0]['public_wallet']['descriptors']))
 def test_failed_stale_scanning_reconnected_or_old_agent_cannot_use_local_review_path(self):
  for mode in ('failed','stale','scanning','reconnected','older'):
   with self.subTest(mode=mode):
    f=UnloadedArchive();f.setUp()
    try:
     f.completed();f.deleted();f.partial();node=f.f.f.b;c=f.hub.registry.connections[node['connection_token']];inv=f.hub.inventories[node['node_id']]
     if mode=='failed':inv['loaded_complete']=False
     elif mode=='stale':inv['history_checked_at']=0
     elif mode=='scanning':inv['wallets']=[{**copy.deepcopy(f.f.archive(1)),'scanning':True}]
     elif mode=='reconnected':f.hub.inventory_display[node['node_id']]['token']='old'
     else:c['agent_version']='2.0.0~dev96'
     self.assertFalse(f.queues(f.exchange()),mode);self.assertFalse(f.offers(f.exchange()),mode)
    finally:f.doCleanups()
 def test_deny_and_unpaired_channels_restrict_execution_not_public_discovery(self):
  self.deleted();self.partial();from sync_permissions import policy_id
  self.hub.permissions.live[self.f.f.b['node_id']]['record']['policies']=[policy_id(self.f.source['raw'])];reply=self.exchange();self.assertFalse(self.queues(reply));self.assertEqual(self.offers(reply)[0]['status'],'disabled')
  self.hub.permissions.live[self.f.f.b['node_id']]['record']['policies']=[];self.hub.relay.reset();reply=self.exchange();self.assertFalse(self.queues(reply));self.assertEqual(self.offers(reply)[0]['status'],'secure_pairing_required')
 def test_pending_invitation_pauses_if_receiver_inventory_no_longer_current(self):
  self.deleted();self.partial();reply=self.exchange();self.assertTrue(self.queues(reply));before=copy.deepcopy(self.hub.read()['requests']);self.hub.inventories[self.f.f.b['node_id']]['history_checked_at']=0;self.assertFalse(self.queues(self.exchange()))
  for k,r in before.items():self.assertEqual(self.hub.read()['requests'][k]['proposal'],r['proposal'])
 def test_connected_loaded_archive_remains_available_for_history_comparison(self):
  self.f.scope(38,51,False,38,46,True);self.partial();reply=self.exchange();self.assertTrue(self.queues(reply));self.assertTrue(any(r.get('history_sync') for r in self.hub.read()['requests'].values()))

if __name__=='__main__':unittest.main()
