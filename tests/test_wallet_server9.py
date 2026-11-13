"""Renew existing sync invitations despite unrelated unloaded wallet folders."""
import copy,time,unittest
import test_wallet_server8 as RouteFixture
from wallet_sync_queue import proposals

class LoadedRoutes(RouteFixture.Routes):
 def unloaded(self,node):
  self.hub.inventories[node].update(complete=False,loaded_complete=True,unloaded_wallets=['unrelated_folder'])
 def fresh(self):return [r for r in self.refresh()['requests'].values() if r.get('retry_of')]
 def test_both_nodes_unloaded_folders_create_and_deliver_current_requests(self):
  for n in (self.f.a,self.f.b):self.unloaded(n['node_id'])
  fresh=self.fresh();self.assertEqual(len(fresh),2)
  with self.hub.edit() as state:
   for n in (self.f.a,self.f.b):
    queue=next(p for p in proposals(self.hub.transfers,state,n['node_id']) if p['kind']=='wallet_sync_queue')
    self.assertEqual(len(queue['requests']),1)
    self.assertEqual(queue['requests'][0]['transfer_version'],3)
  for key,row in self.old.items():self.assertEqual(self.hub.read()['requests'][key]['proposal'],row['proposal'])
  self.assertTrue(all(r['queue_visible'] and r['proposal']['transport'] for r in fresh))
 def test_either_node_can_have_unrelated_unloaded_folders(self):
  for n in (self.f.a,self.f.b):
   with self.hub.edit() as state:state['requests']=copy.deepcopy(self.old)
   self.unloaded(n['node_id']);self.assertEqual(len(self.fresh()),2)
 def test_failed_loaded_scan_on_either_node_still_blocks(self):
  for n in (self.f.a,self.f.b):
   for inv in self.hub.inventories.values():inv.update(complete=False,loaded_complete=True)
   self.hub.inventories[n['node_id']]['loaded_complete']=False
   self.assertFalse(self.fresh())
 def test_missing_loaded_source_not_inferred_from_unloaded_folder(self):
  for n in (self.f.a,self.f.b):self.unloaded(n['node_id'])
  self.hub.inventories[self.f.a['node_id']]['wallets']=[]
  self.assertFalse(self.fresh())
 def test_stale_loaded_scan_still_blocks(self):
  self.unloaded(self.f.a['node_id']);self.hub.inventory_times[self.f.a['node_id']]=time.monotonic()-61
  self.assertFalse(self.fresh())
 def test_unloaded_folders_do_not_reuse_signed_reviews(self):
  for n in (self.f.a,self.f.b):self.unloaded(n['node_id'])
  with self.hub.edit() as state:next(iter(state['requests'].values()))['signed_preview']={'retained':'review'}
  self.assertFalse(self.fresh())
 def test_partial_inventory_does_not_make_existing_destination_absent(self):
  self.unloaded(self.f.b['node_id']);self.hub.inventories[self.f.b['node_id']]['wallets']=copy.deepcopy(self.hub.inventories[self.f.a['node_id']]['wallets'])
  self.assertFalse(self.fresh())
 def test_partial_inventory_cannot_bypass_local_permission(self):
  self.unloaded(self.f.b['node_id'])
  from sync_permissions import policy_id
  self.hub.permissions.live[self.f.b['node_id']]['record']['policies']=[policy_id(self.f.wallet['raw'])]
  self.assertFalse(self.fresh())

if __name__=='__main__':unittest.main()
