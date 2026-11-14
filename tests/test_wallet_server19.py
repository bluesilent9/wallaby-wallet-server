"""Server is a rendezvous, not a wallet-discovery or transfer-scope authority."""
import copy,time,unittest
from unittest.mock import patch
from pathlib import Path
import test_build8 as fixtures
import test_build18 as retirement
from agent_hub import AgentHub,digest
from wallet_transfers import Transfers
from wallet_retirement import deliverable,result,snapshot,validate_saved,latest_phases,group_rows,group_complete
from retirement_presence import reconcile

class AgentOwnedSync(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.Setup();self.f.setUp();self.addCleanup(self.f.doCleanups);self.hub=self.f.hub;self.hub.transfer_proposal=AgentHub.transfer_proposal.__get__(self.hub);self.hub.transfers.schedule_queues=Transfers.schedule_queues.__get__(self.hub.transfers);self.hub.refresh_inventory=lambda *a:None
  for c in self.hub.registry.connections.values():c['agent_version']='2.0.0~dev99'
  self.hub.inventories[self.f.b['node_id']]={'complete':True,'wallets':[]};self.caps=['wallet_transfer','wallet_sync_offers_v1','wallet_relay_v1'];self.exchange()
 def exchange(self):return self.hub.exchange(self.f.b['connection_token'],{'version':1,'outbox':[],'known_vaults':[],'capabilities':self.caps})
 def old(self,status='pending'):
  ident='a'*64
  with self.hub.edit() as state:
   for n,peer,direction in ((self.f.a,self.f.b,'send'),(self.f.b,self.f.a,'receive')):
    p={'kind':'wallet_transfer','transfer_id':ident,'direction':direction};state['requests'][digest(p)]={'kind':'wallet_transfer','transfer_id':ident,'direction':direction,'node_id':n['node_id'],'peer_id':peer['node_id'],'public_wallet':copy.deepcopy(self.f.wallet['raw']),'state':status,'proposal':p,'base_sent':1,'queue_visible':True,'frozen_evidence':{'untouched':True}}
   state['nodes'][self.f.b['node_id']].update(sync_revision=4,sync_snapshot=[{'old':'queue'}],sync_offer_revision=2,sync_offer_snapshot=[{'old':'offer'}])
  return copy.deepcopy(self.hub.read()['requests'])
 def test_missing_wallet_never_creates_server_offer_queue_preview_or_transfer(self):
  with patch.object(self.hub,'pair_transfers',side_effect=AssertionError('Server chose a scope')),patch.object(self.hub,'rpc',side_effect=AssertionError('Server fetched transfer inventory')):
   for _ in range(3):
    reply=self.exchange();self.assertFalse(any(p['kind'] in ('wallet_transfer','wallet_sync_queue','wallet_sync_offers','wallet_transfer_preview') for p in reply['proposals']))
  self.assertFalse(self.hub.read()['requests'])
 def test_old_queues_withdraw_without_mutating_original_proposals_or_outcomes(self):
  old=self.old();reply=self.exchange();state=self.hub.read();self.assertFalse(any(p['kind'].startswith('wallet_sync') and p['kind']!='wallet_sync_preferences' for p in reply['proposals']));self.assertEqual(state['nodes'][self.f.b['node_id']]['sync_snapshot'],[])
  for k,r in old.items():
   self.assertEqual(state['requests'][k]['proposal'],r['proposal']);self.assertEqual(state['requests'][k]['state'],r['state']);self.assertEqual(state['requests'][k]['frozen_evidence'],r['frozen_evidence']);self.assertFalse(state['requests'][k]['queue_visible'])
 def test_completed_old_operations_remain_byte_exact(self):
  old=self.old('complete');self.exchange()
  for k,r in old.items():self.assertEqual(self.hub.read()['requests'][k],r)
 def test_late_original_results_are_correlated_without_restarting_any_transfer(self):
  self.old();self.exchange();state=self.hub.read();r=next(r for r in state['requests'].values() if r['direction']=='receive');self.hub.transfers.accept_result(state,r['node_id'],{'request_hash':digest(r['proposal']),'status':'complete'});self.assertEqual(r['state'],'complete');self.assertTrue(r['server_sync_retired']);self.assertFalse(self.hub.transfers.proposals(state,r['node_id']))
 def test_server_cannot_construct_or_retry_wallet_transfers(self):
  with self.assertRaisesRegex(ValueError,'receiving Agent'):self.hub.transfers.retry('a'*64,True)
  with self.assertRaisesRegex(ValueError,'receiving Agent'):self.hub.transfers.refresh_reviews(['a'*64],True)
  with self.assertRaisesRegex(ValueError,'directly paired Agents'):self.hub.transfer_proposal({}, {})
 def test_nodes_describe_agent_ownership_without_stale_server_retry_controls(self):
  self.old();value=self.hub.node_summary(self.f.b['node_id']);self.assertEqual(value['synchronisation']['state'],'agent_managed');self.assertEqual(value['transfers'],[])

class PreservationPresence(unittest.TestCase):
 def setUp(self):
  self.f=retirement.Retirement();self.f.setUp();self.addCleanup(self.f.doCleanups);self.hub=self.f.hub;self.hub.refresh_inventory=lambda *a:None
 def absent(self,node=None,folders=None):
  n=node or self.f.a;inv=self.hub.inventories[n['node_id']];inv.update(loaded_complete=True,wallet_directory=folders or ['unrelated folder'],unloaded_wallets=folders or ['unrelated folder'],history_checked_at=time.monotonic(),scanned_utc='2099-01-01T00:00:00Z');self.hub.inventory_display[n['node_id']]={'token':n['connection_token']};return n
 def test_deleted_archive_withdraws_only_that_request_without_cancelling_whole_extinction(self):
  key=self.f.delivered();old=copy.deepcopy(self.hub.read()['requests'][key]);n=self.absent();self.assertEqual(reconcile(self.hub,n['node_id'],n['connection_token']),1);row=self.hub.read()['requests'][key];self.assertTrue(row['preservation_withdrawn']);self.assertEqual(row['state'],'pending');self.assertEqual(row['proposal'],old['proposal']);self.assertNotIn('cancel_requested',row);self.assertEqual(row['expected_holders'],old['expected_holders']);self.assertFalse(deliverable(self.hub.read(),key));self.assertEqual(latest_phases(group_rows(self.hub.read(),key)),[])
  reply=self.f.exchange(self.f.a,caps=[retirement.CAPABILITY,'wallet_retirement_cancel_v1']);self.assertFalse(any(p['kind']=='wallet_retire' for p in reply['proposals']));self.assertTrue(any(p['kind']=='wallet_retire_cancel' and p['request_hash']==key for p in reply['proposals']))
  with self.hub.edit() as state:result(state,n['node_id'],{'request_hash':key,'status':'cancelled','phase':'preserve','manifest_hash':old['proposal']['manifest_hash']})
  row=self.hub.read()['requests'][key];self.assertEqual(row['state'],'cancelled');self.assertFalse(row.get('archive_checked'));validate_saved(self.hub.read(),key,row,{self.f.user})
 def test_unloaded_existing_archive_is_never_treated_as_deleted(self):
  key=self.f.delivered();n=self.absent(folders=['historical_container','unrelated']);self.assertEqual(reconcile(self.hub,n['node_id'],n['connection_token']),0);self.assertFalse(self.hub.read()['requests'][key].get('preservation_withdrawn'))
 def test_offline_stale_failed_or_previous_connection_cannot_withdraw(self):
  key=self.f.delivered();original=copy.deepcopy(self.hub.inventories);n=self.f.a
  for mode in ('stale','failed','previous','offline'):
   self.hub.inventories=copy.deepcopy(original);self.absent();c=self.hub.registry.connections[n['connection_token']]
   if mode=='stale':self.hub.inventories[n['node_id']]['history_checked_at']=0
   elif mode=='failed':self.hub.inventories[n['node_id']]['loaded_complete']=False
   elif mode=='previous':self.hub.inventory_display[n['node_id']]['token']='old'
   else:self.hub.registry.connections.pop(n['connection_token'])
   self.assertEqual(reconcile(self.hub,n['node_id'],n['connection_token']),0,mode);self.hub.registry.connections[n['connection_token']]=c
  self.assertFalse(self.hub.read()['requests'][key].get('preservation_withdrawn'))
 def test_complete_preservation_and_pending_deletion_are_never_withdrawn(self):
  key=self.f.delivered();self.f.preserve(key);state=copy.deepcopy(self.hub.read());n=self.absent();self.assertEqual(reconcile(self.hub,n['node_id'],n['connection_token']),0);self.assertEqual(self.hub.read()['requests'],state['requests'])
 def test_undelivered_request_can_be_retired_without_a_fabricated_agent_result(self):
  key=self.f.request()['request_hash'];n=self.absent();self.assertEqual(reconcile(self.hub,n['node_id'],n['connection_token']),1);row=self.hub.read()['requests'][key];self.assertTrue(row['preservation_withdrawn_before_delivery']);self.assertFalse(row.get('result'));validate_saved(self.hub.read(),key,row,{self.f.user})
 def test_agent_cancel_before_server_refresh_is_reconciled_without_overwriting_result(self):
  key=self.f.delivered();p=self.hub.read()['requests'][key]['proposal'];message={'request_hash':key,'status':'cancelled','phase':'preserve','manifest_hash':p['manifest_hash'],'message':'Local archive absent'}
  with self.hub.edit() as state:result(state,self.f.a['node_id'],message)
  n=self.absent();self.assertEqual(reconcile(self.hub,n['node_id'],n['connection_token']),1);row=self.hub.read()['requests'][key];self.assertEqual(row['result'],message);self.assertEqual(row['state'],'cancelled');validate_saved(self.hub.read(),key,row,{self.f.user})

 def test_withdrawal_keeps_other_agents_preservation_and_deletion_barrier(self):
  self.hub.inventories[self.f.b['node_id']]=self.f.watch_copy;self.hub.inventories[self.f.b['node_id']]['archive_wallets']=['family_history'];self.hub.caps[self.f.b['node_id']]={retirement.CAPABILITY}
  key=self.f.delivered();other=next((k,r) for k,r in self.hub.read()['requests'].items() if k!=key);before=copy.deepcopy(other[1]);n=self.absent();reconcile(self.hub,n['node_id'],n['connection_token']);self.assertEqual(self.hub.read()['requests'][other[0]],before);retirement.advance(self.hub);self.assertIsNone(self.f.deletion(key));self.assertFalse(group_complete(self.hub.read(),key))
 def test_withdrawn_route_cannot_release_deletion_even_with_late_real_completion(self):
  key=self.f.delivered();n=self.absent();reconcile(self.hub,n['node_id'],n['connection_token']);self.f.preserve(key);self.assertIsNone(self.f.deletion(key));self.assertFalse(group_complete(self.hub.read(),key));validate_saved(self.hub.read(),key,self.hub.read()['requests'][key],{self.f.user})

class RestoreOwnership(unittest.TestCase):
 def test_restore_is_observed_without_server_creating_private_or_watch_transfer(self):
  import test_build90
  from wallet_lifecycle import advance_restore,notices,validate_saved
  f=test_build90.Lifecycle();f.setUp();self.addCleanup(f.doCleanups);f.restore();advance_restore(f.hub,verify=True);rows=f.hub.read()['requests'];self.assertFalse(any(r.get('kind')=='wallet_transfer' for r in rows.values()));restored=rows[f.key]['restoration'];self.assertTrue(restored['active_seen_utc']);self.assertTrue(any(p['state']=='waiting' and 'locally' in p['message'] for p in restored['accounts']));validate_saved(f.hub.read(),f.key,rows[f.key]);self.assertFalse(notices(f.hub))

if __name__=='__main__':unittest.main()
