"""Whole Extinct scope renewal and preservation-driven history recovery."""
import copy,time,unittest
import test_wallet_server2 as fixtures
from agent_hub import digest
from descriptor_store import clean_wallet
from vendor.embit.descriptor import Descriptor
from vendor.embit.descriptor.checksum import checksum
from extinct_history_sync import METHOD,schedule as history_schedule
from wallet_sync_queue import schedule
from sync_routes import renew,prior_in_progress

class WholeArchive(unittest.TestCase):
 exchange=fixtures.CurrentProtocol.exchange
 def setUp(self):
  fixtures.CurrentProtocol.setUp(self);self.caps.append('wallet_sync_offers_v1')
  self.archive_descriptor=self.f.wallet['raw']['descriptors'][0]['desc'];self.scope(32,46,True,32,45,True)
 def archive(self,count):
  descriptors=[];labels={}
  for i in range(count):
   address=Descriptor.from_string(self.archive_descriptor.split('#')[0]).derive(i).script_pubkey().address();body='addr('+address+')';descriptors.append({'desc':body+'#'+checksum(body),'timestamp':0});labels[address]={'label':'group one' if i<32 else 'group two | LOST:01/01/2020 00:00:00 UTC','lost_utc':None}
  w=clean_wallet({'wallet_name':'Extinct','descriptors':descriptors});return {'id':w['id'],'name':'Extinct','raw':w['raw'],'extinct':True,'signing_only':False,'private_keys_enabled':False,'address_labels':labels,'scanning':False}
 def summary(self,addresses,records,complete,tag=''):
  v={'version':1,'chain':'main','addresses':addresses,'transactions':records,'address_hash':digest({'addresses':addresses}),'transaction_hash':digest({'records':records,'tag':tag}),'label_hash':'a'*64,'history_complete':complete};return {**v,'digest':digest(v)}
 def scope(self,sa,sr,sc,ta,tr,tc):
  self.source=self.archive(sa);self.target=self.archive(ta)
  for n,w,s in ((self.f.a,self.source,self.summary(sa,sr,sc)),(self.f.b,self.target,self.summary(ta,tr,tc))):
   c=self.hub.registry.connections[n['connection_token']];c['rpc_methods']=sorted(set(c['rpc_methods'])|{METHOD});self.hub.caps[n['node_id']]=set(self.caps);self.hub.inventories[n['node_id']]={'complete':True,'loaded_complete':True,'wallets':[copy.deepcopy(w)],'extinct_summaries':{'Extinct':s},'history_checked_at':time.monotonic()};self.hub.inventory_times[n['node_id']]=time.monotonic();self.hub.inventory_display[n['node_id']]={'token':n['connection_token']}
 def ready(self):return {c['node_id']:c for c in self.hub.registry.connections.values()}
 def initial(self):
  self.exchange(self.f.b);rows=list(self.hub.read()['requests'].values());self.assertEqual(len(rows),2);self.assertTrue(all(len(r['public_wallet']['descriptors'])==32 for r in rows));return copy.deepcopy(self.hub.read()['requests'])
 def grown(self):self.scope(38,51,False,32,46,True)
 def test_pending_subset_renews_to_full38_without_changing_frozen32(self):
  old=self.initial();self.grown()
  with self.hub.edit() as state:schedule(self.hub.transfers,state)
  state=self.hub.read();fresh=[r for r in state['requests'].values() if r.get('retry_of')];self.assertEqual(len(fresh),2)
  for key,r in old.items():self.assertEqual(state['requests'][key]['proposal'],r['proposal']);self.assertEqual(state['requests'][key]['state'],'pending');self.assertTrue(state['requests'][key]['superseded_attempt'])
  for r in fresh:self.assertEqual(len(r['proposal']['public_wallet']['descriptors']),38);self.assertNotEqual(r['proposal']['preview_challenge'],next(iter(old.values()))['proposal']['preview_challenge']);self.assertFalse(r.get('signed_preview'));self.assertFalse(r['source_has_private_keys']);self.assertFalse(r['requires_blockchain_redownload']);self.assertEqual(r['subwallets'],['Extinct'])
  before=copy.deepcopy(state['requests'])
  with self.hub.edit() as state:schedule(self.hub.transfers,state)
  self.assertEqual(self.hub.read()['requests'],before)
 def test_completed_subset_does_not_suppress_full_update_from_uncertified_larger_source(self):
  old=self.initial()
  with self.hub.edit() as state:
   for r in state['requests'].values():r.update(state='complete',result={'retained':'actual old outcome'})
  completed=copy.deepcopy(self.hub.read()['requests']);self.grown()
  with self.hub.edit() as state:history_schedule(self.hub,state,self.ready())
  state=self.hub.read();fresh=[r for k,r in state['requests'].items() if k not in old];self.assertEqual(len(fresh),2);self.assertEqual(next(r['node_id'] for r in fresh if r['direction']=='send'),self.f.a['node_id']);self.assertTrue(all(len(r['public_wallet']['descriptors'])==38 for r in fresh))
  for key,r in completed.items():self.assertEqual(state['requests'][key],r)
 def test_late_success_of_old_subset_allows_separately_reviewed_full_update(self):
  old=self.initial();self.grown()
  with self.hub.edit() as state:
   schedule(self.hub.transfers,state)
   for key in old:state['requests'][key]['state']='complete'
   schedule(self.hub.transfers,state)
  rows=[r for r in self.hub.read()['requests'].values() if r.get('retry_of')];self.assertEqual(len(rows),2);self.assertTrue(all(r['queue_visible'] for r in rows));self.assertFalse(prior_in_progress(self.hub.transfers,self.hub.read(),rows))
 def test_late_error_or_recovery_does_not_bypass_original_operation(self):
  old=self.initial();self.grown()
  with self.hub.edit() as state:schedule(self.hub.transfers,state)
  for outcome in ('error','denied','recovery_required'):
   with self.hub.edit() as state:
    for key in old:state['requests'][key]['state']=outcome
    schedule(self.hub.transfers,state)
   self.assertTrue(all(not r['queue_visible'] for r in self.hub.read()['requests'].values() if r.get('retry_of')))
 def test_waiting_preservation_can_get_public_history_but_delete_restore_busy_cannot(self):
  self.grown();state=self.hub.read();preserve={'kind':'wallet_retire','state':'pending','node_id':self.f.b['node_id'],'proposal':{'version':3,'phase':'preserve','delete_wallet':False,'public_wallet':copy.deepcopy(self.f.wallet['raw'])},'frozen':'unchanged'};state['requests']['preserve']=copy.deepcopy(preserve);history_schedule(self.hub,state,self.ready());self.assertEqual(state['requests']['preserve'],preserve);self.assertEqual(len([r for r in state['requests'].values() if r.get('history_sync')]),2);schedule(self.hub.transfers,state);self.assertTrue(all(r.get('queue_visible') for r in state['requests'].values() if r.get('history_sync')))
  for mode in ('delete','restore','busy','active','recovery'):
   state=self.hub.read();r=copy.deepcopy(preserve)
   if mode=='delete':r['proposal'].update(phase='delete',delete_wallet=True)
   elif mode=='restore':r['restoration']={'requested':'now'}
   elif mode=='active':r['active_pair']=True
   elif mode=='recovery':r['state']='recovery_required'
   else:self.hub.transfers.busy.add(self.f.a['node_id'])
   state['requests']['preserve']=r;history_schedule(self.hub,state,self.ready());self.assertFalse(any(v.get('history_sync') for v in state['requests'].values()),mode);self.hub.transfers.busy.clear()
 def test_no_forced_download_for_pruned_public_archive_sources_and_targets(self):
  self.grown()
  for c in self.hub.registry.connections.values():self.hub.registry.health.values[c['token']].update(pruned=True,prune_time=2000000000)
  reply=self.exchange(self.f.b);requests=next(p for p in reply['proposals'] if p['kind']=='wallet_sync_queue')['requests'];self.assertTrue(requests);self.assertTrue(all(not p['requires_blockchain_redownload'] and len(p['public_wallet']['descriptors'])==38 for p in requests))
 def test_full_scope_offer_withdraws_old_subset_while_permissions_are_denied(self):
  old=self.initial();self.grown();from sync_permissions import policy_id
  self.hub.permissions.live[self.f.b['node_id']]['record']['policies']=[policy_id(self.source['raw'])]
  with self.hub.edit() as state:schedule(self.hub.transfers,state)
  rows=[r for r in self.hub.read()['requests'].values() if r.get('retry_of')];self.assertEqual(len(rows),2);self.assertTrue(all(len(r['public_wallet']['descriptors'])==38 and not r.get('proposal') for r in rows));self.assertTrue(all(not r['queue_visible'] for r in self.hub.read()['requests'].values()))
 def test_counts_are_only_hints_equal_union_has_no_new_offer(self):
  self.scope(38,51,False,38,51,False);state=self.hub.read();history_schedule(self.hub,state,self.ready());self.assertFalse(state['requests'])
  self.hub.inventories[self.f.b['node_id']]['extinct_summaries']['Extinct']=self.summary(38,51,False,'different records');history_schedule(self.hub,state,self.ready());self.assertEqual(len(state['requests']),2);self.assertTrue(all(r['source_has_private_keys'] is False for r in state['requests'].values()))
 def test_active_subset_is_retained_without_new_automatic_review(self):
  old=self.initial();self.grown()
  with self.hub.edit() as state:
   for r in state['requests'].values():r['active_pair']=True
   schedule(self.hub.transfers,state)
  state=self.hub.read();self.assertEqual(len(state['requests']),2)
  for key,r in old.items():self.assertEqual(state['requests'][key]['proposal'],r['proposal']);self.assertTrue(state['requests'][key]['active_pair'])

if __name__=='__main__':unittest.main()
