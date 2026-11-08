"""Loaded-wallet extinction must not depend on unrelated unloaded folders."""
import copy,sys,unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
import test_build18 as fixtures
from wallet_retirement import propose,readiness,zero_balances,group_rows,cancel,advance,loaded_inventory

class Extinction(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.Retirement();self.f.setUp();self.addCleanup(self.f.doCleanups)
 def unloaded(self,node):
  inv=self.f.hub.inventories[node];inv.update(complete=False,loaded_complete=True,unloaded_wallets=['unrelated_old_folder','unrelated_policy_folder'],error='Loaded wallets are available. 2 unloaded wallet folders prevent missing-wallet sync checks.')
 def test_second_connected_node_with_unloaded_folders_no_longer_blocks(self):
  self.f.hub.inventories[self.f.b['node_id']]=copy.deepcopy(self.f.watch_copy);self.unloaded(self.f.b['node_id']);r=self.f.request();self.assertTrue(r['queued']);checks=self.f.hub.read()['requests'][r['request_hash']]['balance_checks'];self.assertEqual({row['node_id'] for row in checks},{self.f.a['node_id'],self.f.b['node_id']})
 def test_loaded_holder_and_existing_extinct_container_remain_eligible(self):
  self.unloaded(self.f.a['node_id']);report=readiness(self.f.hub,self.f.user,self.f.rid);self.assertTrue(report['options']);self.assertTrue(report['archives']);self.assertTrue(next(n for n in report['nodes'] if n['id']==self.f.a['node_id'])['eligible']);self.assertTrue(self.f.request()['queued'])
 def test_confirmed_ownership_is_sufficient_during_background_history_refresh(self):
  self.f.session.access=lambda:{'ownership_ready':False,'ownership_assignments_ready':True};self.assertTrue(self.f.request()['queued'])
 def test_preservation_barrier_and_loaded_only_deletion_targets_are_unchanged(self):
  self.unloaded(self.f.a['node_id']);key=self.f.delivered();self.assertTrue(all(r['proposal']['phase']=='preserve' for r in group_rows(self.f.hub.read(),key)));self.assertIsNone(self.f.deletion(key));self.f.preserve(key);delete=self.f.deletion(key);self.assertIsNotNone(delete);p=self.f.hub.read()['requests'][delete]['proposal'];self.assertEqual([r['wallet'] for r in p['delete_wallets']],[self.f.node_wallet['name']]);self.assertTrue(p['require_zero_balance']);self.assertTrue(p['preservation']['receipt'])
 def test_failed_or_partial_loaded_inventory_still_blocks_with_node_name(self):
  node=self.f.b['node_id'];self.f.hub.inventories[node]={'complete':False,'loaded_complete':False,'wallets':[],'error':'RPC failed'}
  with self.assertRaisesRegex(ValueError,'loaded-wallet discovery'):self.f.request()
  self.assertFalse(self.f.hub.read()['requests']);self.assertFalse(loaded_inventory(self.f.hub.inventories[node]))
 def test_funded_watch_only_copy_still_blocks_all_balance_categories(self):
  node=self.f.b['node_id'];self.f.hub.inventories[node]=copy.deepcopy(self.f.watch_copy);self.unloaded(node);name=self.f.hub.inventories[node]['wallets'][0]['name']
  for category in ('trusted','untrusted_pending','immature'):
   values=dict.fromkeys(('trusted','untrusted_pending','immature'),'0');values[category]='0.001';self.f.balances={(node,name):{'watchonly':values}}
   with self.assertRaisesRegex(ValueError,'zero-balance'):self.f.request()
   self.assertFalse(self.f.hub.read()['requests'])
 def test_rescanning_loaded_wallet_still_blocks(self):
  self.unloaded(self.f.a['node_id']);self.f.scan=True
  with self.assertRaisesRegex(ValueError,'rescan'):self.f.request()
  self.assertFalse(self.f.hub.read()['requests'])
 def test_unloaded_extinct_container_is_not_invented_or_loaded(self):
  self.unloaded(self.f.a['node_id']);self.f.hub.inventories[self.f.a['node_id']]['archive_wallets']=[]
  with self.assertRaisesRegex(ValueError,'existing Extinct'):self.f.request()
  self.assertFalse(self.f.hub.read()['requests'])
 def test_cancellation_retains_visible_private_wallet_with_unrelated_unloaded_folders(self):
  self.unloaded(self.f.a['node_id']);key=self.f.request()['request_hash'];self.assertTrue(cancel(self.f.hub,self.f.user,key,True)['cancel_requested']);self.assertFalse(any(r.get('result',{}).get('wallet_deleted') for r in group_rows(self.f.hub.read(),key)))
 def test_unloaded_folders_are_not_treated_as_proof_of_wallet_absence(self):
  self.unloaded(self.f.a['node_id']);key=self.f.delivered();self.f.finish(key);self.f.hub.inventories[self.f.a['node_id']]['wallets']=[];advance(self.f.hub);self.assertNotIn(self.f.a['node_id'],self.f.hub.read()['requests'][key].get('absent_holders',[]))

if __name__=='__main__':unittest.main()
