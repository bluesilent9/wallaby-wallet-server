"""Advisory snapshots never schedule, select, approve or scope Agent transfers."""
import copy,json,os,subprocess,sys,time,unittest
from pathlib import Path
from unittest.mock import patch
from test_build8 import Setup
import test_build28 as historical
from agent_hub import AgentHub,digest
from wallet_transfers import Transfers
from wallet_sync_hints import snapshot,proposal
from wallet_sync_offers import validate_saved

class Hints(unittest.TestCase):
 def setUp(self):
  self.f=Setup();self.f.setUp();self.addCleanup(self.f.doCleanups);self.hub=self.f.hub;self.a=self.f.a;self.b=self.f.b
  self.hub.refresh_inventory=lambda *a:None;self.hub.transfers.schedule_queues=Transfers.schedule_queues.__get__(self.hub.transfers);self.hub.transfer_proposal=AgentHub.transfer_proposal.__get__(self.hub)
  for c in self.f.registry.connections.values():c['agent_version']='2.0.0~dev101'
  self.fresh(self.a);self.fresh(self.b);self.caps=['wallet_sync_offers_v1','wallet_relay_v1'];self.hub.inventories[self.b['node_id']]['wallets']=[]
 def fresh(self,n):
  self.hub.inventory_times[n['node_id']]=time.monotonic();self.hub.inventories[n['node_id']]['history_checked_at']=time.monotonic();self.hub.inventory_display[n['node_id']]={'token':n['connection_token']}
 def exchange(self,caps=None):return self.f.exchange(self.b,caps=self.caps if caps is None else caps)
 def hints(self):return next(p for p in self.exchange()['proposals'] if p['kind']=='wallet_sync_offers')
 def test_live_unpaired_source_has_informational_receive_hint_without_requests(self):
  with patch.object(self.hub,'rpc',side_effect=AssertionError('Hints fetched wallet data')),patch.object(self.hub.relay,'mesh',side_effect=AssertionError('Hints tested pairing')):
   p=self.hints();self.assertEqual(len(p['offers']),1);o=p['offers'][0];self.assertEqual(o['direction'],'receive');self.assertIs(o['source_online'],True);self.assertEqual(o['status'],'discovery_pending');self.assertEqual(o['peer'],{'node_id':self.a['node_id'],'hostname':'first'});self.assertEqual(o['public_wallet'],self.f.node_wallet['raw']);self.assertFalse(self.hub.read()['requests'])
 def test_server_never_reads_or_applies_receiver_denials(self):
  before=self.hints()['offers']
  with patch.object(self.hub.permissions,'permits',side_effect=AssertionError('Server applied denial')),patch.object(self.hub.permissions,'allows_offer',side_effect=AssertionError('Server applied denial')):
   self.hub.permissions.live[self.b['node_id']]['record']['policies']=['a'*64];self.assertEqual(self.hints()['offers'],before)
 def test_connected_source_disconnect_withdraws_hint_and_increments_revision(self):
  p=self.hints();self.f.registry.heartbeat(self.a['connection_token'],True);q=self.hints();self.assertEqual(q['offers'],[]);self.assertGreater(q['revision'],p['revision']);self.assertTrue(self.hub.inventories[self.a['node_id']]['wallets'])
 def test_reconnect_requires_current_connection_inventory(self):
  p=self.hints();self.f.registry.heartbeat(self.a['connection_token'],True);n=self.f.register('02:80:00:00:00:01','renamed-host');self.assertEqual(n['node_id'],self.a['node_id']);self.assertEqual(self.hints()['offers'],[]);self.fresh(n);q=self.hints();self.assertEqual(q['offers'][0]['peer']['hostname'],'renamed-host');self.assertEqual(q['offers'][0]['id'],p['offers'][0]['id'])
 def test_source_expiry_stale_failed_and_previous_inventory_do_not_advertise(self):
  now=self.hub.inventory_times[self.a['node_id']];token=self.a['connection_token'];saved=copy.deepcopy(self.hub.inventories[self.a['node_id']]);c=self.f.registry.connections[token];seen=c['seen']
  for mode in ('expired','stale','failed','previous'):
   c['seen']=seen;self.hub.inventory_times[self.a['node_id']]=now;self.hub.inventories[self.a['node_id']]=copy.deepcopy(saved);self.hub.inventory_display[self.a['node_id']]['token']=token
   if mode=='expired':c['seen']-=10000
   elif mode=='stale':self.hub.inventories[self.a['node_id']]['history_checked_at']=0
   elif mode=='failed':self.hub.inventories[self.a['node_id']]={'wallets':saved['wallets'],'complete':False,'error':'failed'}
   else:self.hub.inventory_display[self.a['node_id']]['token']='old'
   self.assertEqual(snapshot(self.hub,self.b['node_id']),[],mode)
  c['seen']=seen
 def test_ambiguous_duplicate_identity_cannot_supply_hints(self):
  self.f.register('02:80:00:00:00:01','first');self.assertEqual(snapshot(self.hub,self.b['node_id']),[])
 def test_unloaded_folders_do_not_hide_valid_loaded_public_observations(self):
  self.hub.inventories[self.a['node_id']].update(complete=False,loaded_complete=True,unloaded_wallets=['other']);self.assertTrue(self.hints()['offers']);self.assertFalse(self.hub.inventories[self.a['node_id']]['complete'])
 def test_extinct_children_are_one_whole_archive_hint_without_labelled_child_offers(self):
  children=historical.ExtinctSync.children(self.f);self.hub.inventories[self.a['node_id']]['wallets']=children;before=copy.deepcopy(children);p=self.hints();self.assertEqual(len(p['offers']),1);raw=p['offers'][0]['public_wallet'];self.assertEqual(raw['wallet_name'],'Extinct');self.assertEqual(len(raw['descriptors']),2);self.assertEqual(children,before);self.assertFalse(self.hub.read()['requests'])
 def test_internal_policy_monitors_aliases_and_scanning_wallets_are_not_hints(self):
  for mode in ('policy','alias','scanning'):
   w=copy.deepcopy(self.f.node_wallet)
   if mode=='policy':w['raw']['wallet_name']='Wallaby policy '+('a'*20)
   elif mode=='alias':w['signing_only']=True
   else:w['scanning']=True
   self.hub.inventories[self.a['node_id']]['wallets']=[w];self.assertEqual(self.hints()['offers'],[],mode)
 def test_multiple_sources_remain_separate_and_only_disconnected_source_disappears(self):
  c=self.f.register('02:80:00:00:00:03','third');self.hub.inventories[c['node_id']]=copy.deepcopy(self.hub.inventories[self.a['node_id']]);self.fresh(c);p=self.hints();self.assertEqual(len(p['offers']),2);self.assertEqual(len({o['id'] for o in p['offers']}),2);self.f.registry.heartbeat(self.a['connection_token'],True);self.assertEqual([o['peer']['hostname'] for o in self.hints()['offers']],['third'])
 def test_names_and_storage_update_without_turning_display_ids_into_transfer_jobs(self):
  p=self.hints();w=self.hub.inventories[self.a['node_id']]['wallets'][0];w['raw']['wallet_name']='Updated wallet';w['wallaby_storage']='disc';q=self.hints();self.assertEqual(q['offers'][0]['id'],p['offers'][0]['id']);self.assertGreater(q['revision'],p['revision']);self.assertEqual(q['offers'][0]['source_storage'],'disc');self.assertEqual(q['offers'][0]['public_wallet']['wallet_name'],'Updated wallet')
 def test_repeat_poll_stable_revision_and_saved_profile_validation(self):
  p=self.hints();q=self.hints();self.assertEqual(p,q);validate_saved(self.hub.read()['nodes'][self.b['node_id']])
 def test_empty_snapshot_is_sent_to_clear_advisories(self):
  self.hub.inventories.clear();p=self.hints();self.assertEqual(p['offers'],[]);self.assertEqual(p['revision'],0)
 def test_capability_gates_envelope_without_changing_any_local_permissions(self):
  self.assertFalse(any(p['kind']=='wallet_sync_offers' for p in self.exchange([])['proposals']));self.assertTrue(self.hints()['offers'])
 def test_bounded_hints_never_split_wallet_or_block_other_replies(self):
  w=self.f.node_wallet;self.hub.inventories[self.a['node_id']]['wallets']=[w]*300
  p=self.hints();self.assertEqual(len(p['offers']),1);self.assertLessEqual(len(json.dumps(p).encode()),2*1024*1024)
 def test_bad_public_source_does_not_block_valid_source(self):
  w=copy.deepcopy(self.f.node_wallet);w['raw']['descriptors'][0]['desc']='bad';self.hub.inventories[self.a['node_id']]['wallets'].append(w);self.assertEqual(len(self.hints()['offers']),1)
 def test_new_refresh_attempt_does_not_make_old_observation_fresh(self):
  self.hints();self.hub.inventories[self.a['node_id']]['history_checked_at']=0;self.hub.inventory_times[self.a['node_id']]=time.monotonic();self.assertEqual(self.hints()['offers'],[])
 def test_saved_advisories_restore_without_reviving_offline_source(self):
  from profile_archive import ProfileArchive
  from agent_state import validate
  p=self.hints();validate(self.hub.read(),{self.f.user});blob=ProfileArchive(self.f.config).save();target=Path(self.f.tmp.name)/'restored/config.cfg';target.parent.mkdir();ProfileArchive(target).load('profile.7z',blob)
  from nodes import NodeRegistry
  registry=NodeRegistry(target);registry.health.refresh=lambda _:None;self.addCleanup(registry.hub.disc_signers.close);saved=registry.hub.read();self.assertEqual(saved['nodes'][self.b['node_id']]['sync_offer_snapshot'],p['offers']);self.assertEqual(snapshot(registry.hub,self.b['node_id']),[])
 def test_invalid_saved_presence_flag_is_rejected(self):
  self.hints();entry=copy.deepcopy(self.hub.read()['nodes'][self.b['node_id']]);entry['sync_offer_snapshot'][0]['source_online']='yes'
  with self.assertRaises(ValueError):validate_saved(entry)
 def test_agent_101_applies_hints_as_grey_denies_locally_and_clears_without_jobs(self):
  source=os.environ.get('WALLABY_AGENT_HINT_SOURCE')
  if not source:self.skipTest('Set WALLABY_AGENT_HINT_SOURCE to current Agent src for integration.')
  p=self.hints();runner=Path(__file__).with_name('agent_hints_runner.py');r=subprocess.run([sys.executable,'-B',str(runner),source],input=json.dumps(p),capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout),{'advisory':True,'denied':True,'cleared':True,'no_wallet_jobs':True})

if __name__=='__main__':unittest.main()
