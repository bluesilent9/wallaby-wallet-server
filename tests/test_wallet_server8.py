"""Retire only unattempted IPv6 invitations; never replay an operation."""
import copy,json,os,subprocess,sys,time,unittest
import test_wallet_server2 as fixtures
from agent_hub import digest
from wallet_sync_queue import schedule

class Routes(unittest.TestCase):
 def setUp(self):
  fixtures.CurrentProtocol.setUp(self);self.exchange(self.f.b);self.old=copy.deepcopy(self.hub.read()['requests'])
  with self.hub.edit() as state:
   for row in state['requests'].values():
    p=row['proposal'];p.pop('transport');p['transfer_version']=2;p['node_ipv6']='2001:db8::1' if row['direction']=='send' else '2001:db8::2';p['peer']['ipv6']='2001:db8::2' if row['direction']=='send' else '2001:db8::1'
    row['base_sent']=1
   for n in (self.f.a,self.f.b):
    state['nodes'][n['node_id']].pop('ipv6',None);self.hub.inventory_times[n['node_id']]=time.monotonic()
  self.old=copy.deepcopy(self.hub.read()['requests'])
 exchange=fixtures.CurrentProtocol.exchange
 def refresh(self):
  with self.hub.edit() as state:schedule(self.hub.transfers,state)
  return self.hub.read()
 def test_no_ip_needed_fresh_v3_bound_to_actual_paired_identities(self):
  state=self.refresh();fresh=[r for r in state['requests'].values() if r.get('retry_of')];self.assertEqual(len(fresh),2)
  for r in fresh:
   self.assertEqual(r['proposal']['transfer_version'],3);self.assertIsNone(r['proposal']['node_ipv6']);self.assertIsNone(r['proposal']['peer']['ipv6']);self.assertIn('sender_identity',r['proposal']['transport']);self.assertTrue(r['queue_visible']);self.assertNotIn('signed_preview',r)
  for key,old in self.old.items():
   current=state['requests'][key];self.assertEqual(current['proposal'],old['proposal']);self.assertEqual(current['state'],'pending');self.assertTrue(current['superseded_attempt'])
 def test_repeated_poll_creates_only_one_replacement(self):
  self.refresh();self.refresh();self.assertEqual(len(self.hub.read()['requests']),4)
 def test_operation_evidence_prevents_automatic_replacement(self):
  for field,value in (('active_pair',True),('finished_utc','2026-11-13T01:00:00Z'),('result',{'status':'unknown'})):
   with self.hub.edit() as state:
    state['requests']=copy.deepcopy(self.old);next(iter(state['requests'].values()))[field]=value
   state=self.refresh();self.assertEqual(len(state['requests']),2,field);self.assertEqual(next(iter(state['requests'].values()))[field],value)
 def test_terminal_or_recovery_results_are_never_restarted(self):
  for outcome in ('denied','error','complete','recovery_required'):
   with self.hub.edit() as state:
    state['requests']=copy.deepcopy(self.old);next(iter(state['requests'].values()))['state']=outcome
   self.assertEqual(len(self.refresh()['requests']),2,outcome)
 def test_local_denial_prevents_replacement(self):
  from sync_permissions import policy_id
  self.hub.permissions.live[self.f.b['node_id']]['record']['policies']=[policy_id(self.f.wallet['raw'])];self.assertEqual(len(self.refresh()['requests']),2)
 def test_missing_source_or_stale_inventory_prevents_replacement(self):
  self.hub.inventories[self.f.a['node_id']]['wallets']=[];self.assertEqual(len(self.refresh()['requests']),2)
 def test_busy_agent_prevents_replacement(self):
  self.hub.transfers.busy.add(self.f.a['node_id']);self.assertEqual(len(self.refresh()['requests']),2)
 def test_unpaired_new_route_cannot_be_executed(self):
  self.hub.relay.channels.clear();state=self.refresh();fresh=[r for r in state['requests'].values() if r.get('retry_of')];self.assertEqual(len(fresh),2);self.assertTrue(all(not r.get('proposal') and not r.get('queue_visible') for r in fresh))
 def test_late_old_delivery_is_recorded_and_blocks_new_invitation(self):
  self.refresh();receiver=next(r for r in self.old.values() if r['direction']=='receive')
  with self.hub.edit() as state:
   self.hub.transfers.accept_result(state,receiver['node_id'],{'request_hash':digest(receiver['proposal']),'status':'complete'})
   schedule(self.hub.transfers,state)
  state=self.hub.read();old=next(r for r in state['requests'].values() if r['transfer_id']==receiver['transfer_id'] and r['direction']=='receive');self.assertEqual(old['state'],'complete');self.assertTrue(all(not r['queue_visible'] for r in state['requests'].values() if r.get('retry_of')))
 def test_existing_addresses_do_not_block_a_history_update_replacement(self):
  from test_wallet_server7 import HistoryOffers
  f=HistoryOffers();f.setUp();self.addCleanup(f.doCleanups);f.exchange(f.f.b)
  with f.hub.edit() as state:
   for row in state['requests'].values():
    p=row['proposal'];p.pop('transport');p.update(transfer_version=2,node_ipv6='2001:db8::1');p['peer']['ipv6']='2001:db8::2'
   schedule(f.hub.transfers,state)
  fresh=[r for r in f.hub.read()['requests'].values() if r.get('retry_of')];self.assertEqual(len(fresh),2);self.assertTrue(all(r['history_sync'] for r in fresh));self.assertTrue(all(r['proposal']['transfer_version']==3 for r in fresh))
 def test_current_v3_requests_remain_frozen(self):
  self.refresh();before=copy.deepcopy(self.hub.read()['requests']);self.refresh();self.assertEqual(self.hub.read()['requests'],before)
 def test_current_agent_accepts_replacement_protocol(self):
  source=os.environ.get('WALLABY_AGENT_CURRENT_SOURCE')
  if not source:self.skipTest('Set WALLABY_AGENT_CURRENT_SOURCE')
  state=self.refresh();p=next(r['proposal'] for r in state['requests'].values() if r.get('retry_of'))
  code="import sys,json;sys.path.insert(0,sys.argv[1]);from vault_policy import validate_proposal;validate_proposal(json.loads(sys.stdin.read()))"
  r=subprocess.run([sys.executable,'-c',code,source],input=json.dumps(p),capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)

 def test_stale_inventory_prevents_replacement(self):
  self.hub.inventory_times[self.f.a['node_id']]=0;self.assertEqual(len(self.refresh()['requests']),2)
 def test_same_ips_still_retire_unsigned_legacy_review_for_native_peers(self):
  with self.hub.edit() as state:
   for row in state['requests'].values():state['nodes'][row['node_id']]['ipv6']=row['proposal']['node_ipv6']
  self.hub.relay.channels.clear();fresh=[r for r in self.refresh()['requests'].values() if r.get('retry_of')];self.assertEqual(len(fresh),2);self.assertTrue(all(not r.get('proposal') for r in fresh))
