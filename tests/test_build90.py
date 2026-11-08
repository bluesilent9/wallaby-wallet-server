"""Immediate desired lifecycle; private-only restore proof and durable notices."""
import copy,sys,unittest,json
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
import test_build18 as fixtures
from wallet_lifecycle import request_restore,advance_restore,notices,classify,cards,read,validate_saved
from wallet_retirement import advance,group_rows,result
from transaction_workflows import WorkflowStore

class Lifecycle(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.Retirement();self.f.setUp();self.addCleanup(self.f.doCleanups);self.hub=self.f.hub;self.config=self.f.config;self.a=self.f.a['node_id'];self.b=self.f.b['node_id']
  for c in self.f.registry.connections.values():c['agent_version']='2.0.0~dev65'
  for inv in self.hub.inventories.values():inv.update(loaded_complete=True,scanned_utc=self.hub.utc())
  with self.hub.edit() as s:
   for i,n in enumerate((self.a,self.b)):
    s['nodes'].setdefault(n,{})['known_wallets']={'original':dict(copy.deepcopy(self.f.node_wallet),private_keys_enabled=True)};s['nodes'][n]['ipv6']='2001:db8::'+str(i+1)
  self.original_rpc=self.hub.rpc
  def rpc(n,m,params=None,wallet=None):
   w=next((w for w in self.hub.inventories.get(n,{}).get('wallets',[]) if w['name']==wallet),None)
   if m=='getwalletinfo' and w:return {'walletname':wallet,'private_keys_enabled':bool(w.get('private_keys_enabled')),'scanning':bool(w.get('scanning')),'lastprocessedblock':{'height':999000}}
   if m=='listdescriptors' and w:return w['raw']
   return self.original_rpc(n,m,params,wallet)
  self.hub.rpc=rpc
  self.key=self.f.request()['request_hash']
 def restore(self):
  with patch('wallet_lifecycle.advance_restore'):request_restore(self.hub,self.f.user,self.key,True)
 def old(self,node):
  text='addr('+self.f.address+')';from vendor.embit.descriptor.checksum import checksum
  self.hub.inventories[node]={'complete':True,'loaded_complete':True,'scanned_utc':self.hub.utc(),'wallets':[{'name':'historical_container','extinct':True,'private_keys_enabled':False,'raw':{'wallet_name':'historical_container','descriptors':[{'desc':text+'#'+checksum(text)}]}}]}
 def test_classification_is_immediate_before_any_agent_approval(self):
  report={'balances':{'wallets':[{'descriptor_id':self.f.wallet['id'],'name':'Example','btc':'0'}]}};self.assertTrue(classify(self.config,report)['balances']['wallets'][0]['extinct']);out=cards(self.config,[]);self.assertEqual(len(out),1);self.assertEqual(out[0]['descriptor_id'],self.f.wallet['id']);self.assertEqual(out[0]['retirement_hash'],self.key);self.assertTrue(all(r['state']=='pending' for r in group_rows(self.hub.read(),self.key)));self.assertIsNone(self.f.deletion(self.key))
 def test_restore_offline_immediately_returns_to_active_with_non_dismissible_warning(self):
  self.restore();self.hub.inventories={};advance_restore(self.hub,verify=True);report=classify(self.config,{'balances':{'wallets':[]}});self.assertFalse(report['balances']['wallets'][0]['extinct']);self.assertFalse(cards(self.config,[]));self.assertIsNone(report['balances']['wallets'][0]['btc']);n=notices(self.hub);self.assertEqual(len(n),1);self.assertFalse(n[0]['dismissible']);self.assertIn('private-key',n[0]['text'])
 def test_watch_only_does_not_clear_missing_private_warning(self):
  self.restore();self.hub.inventories[self.a]['wallets'][0]['private_keys_enabled']=False;advance_restore(self.hub,verify=True);self.assertIsNone(self.hub.read()['requests'][self.key]['restoration']['active_seen_utc']);self.assertTrue(notices(self.hub));self.assertFalse(any(r.get('lifecycle_restore') for r in self.hub.read()['requests'].values()))
 def test_fresh_private_copy_clears_warning_persistently(self):
  self.restore();advance_restore(self.hub,verify=True);self.assertTrue(self.hub.read()['requests'][self.key]['restoration']['active_seen_utc']);self.assertFalse(notices(self.hub));self.hub.inventories={};advance_restore(self.hub);self.assertFalse(notices(self.hub))
 def test_post_restore_detection_required_not_prior_cached_inventory(self):
  self.restore();advance_restore(self.hub);self.assertTrue(notices(self.hub));advance_restore(self.hub,verify=True);self.assertFalse(notices(self.hub))
 def test_original_private_assignment_requires_private_ssh_pair(self):
  self.restore();advance_restore(self.hub,verify=True);pairs=[r for r in self.hub.read()['requests'].values() if r.get('lifecycle_restore')==self.key];self.assertEqual(len(pairs),2);self.assertTrue(all(r['source_has_private_keys'] for r in pairs));self.assertEqual({r['direction'] for r in pairs},{'send','receive'});self.assertEqual(next(r for r in pairs if r['direction']=='send')['node_id'],self.a);validate_saved(self.hub.read(),self.key,self.hub.read()['requests'][self.key])
 def test_extra_agent_can_receive_watch_copy_after_private_detection(self):
  with self.hub.edit() as s:s['nodes'][self.b]['known_wallets']['original']['private_keys_enabled']=False
  self.restore();advance_restore(self.hub,verify=True);pairs=[r for r in self.hub.read()['requests'].values() if r.get('lifecycle_restore')==self.key];self.assertEqual(len(pairs),2);self.assertTrue(all(r['source_has_private_keys'] is False for r in pairs));self.assertFalse(notices(self.hub))
 def test_later_watch_copy_counts_as_active_for_that_agent(self):
  self.restore();self.old(self.b);advance_restore(self.hub,verify=True);self.assertEqual(len(notices(self.hub)),1);self.hub.inventories[self.b]=copy.deepcopy(self.f.watch_copy);self.hub.inventories[self.b]['scanned_utc']=self.hub.utc();advance_restore(self.hub,verify=True);self.assertFalse(notices(self.hub))
 def test_stale_agent_notice_is_separate_dismissible_and_dismissal_survives_polls(self):
  self.restore();self.old(self.b);advance_restore(self.hub,verify=True);n=notices(self.hub);self.assertEqual(len(n),1);self.assertTrue(n[0]['dismissible']);store=WorkflowStore(self.config);store.sync_lifecycle_notices(self.f.user,self.hub,'admin');self.assertEqual(store.notifications(self.f.user)['unread_count'],1);store.update_notifications(self.f.user,n[0]['id']);store.sync_lifecycle_notices(self.f.user,self.hub,'admin');self.assertFalse(store.notifications(self.f.user)['notifications'])
 def test_missing_private_notification_cannot_be_deleted_and_vanishes_on_detection(self):
  self.restore();self.hub.inventories[self.a]['wallets'][0]['private_keys_enabled']=False;advance_restore(self.hub,verify=True);store=WorkflowStore(self.config);store.sync_lifecycle_notices(self.f.user,self.hub,'balances');n=store.notifications(self.f.user)['notifications'][0];self.assertTrue(n['read']);self.assertFalse(n['dismissible'])
  with self.assertRaises(ValueError):store.update_notifications(self.f.user,n['id'])
  self.hub.inventories[self.a]['wallets'][0]['private_keys_enabled']=True;advance_restore(self.hub,verify=True);store.sync_lifecycle_notices(self.f.user,self.hub,'balances');self.assertFalse(store.notifications(self.f.user)['notifications'])
 def test_unsupported_agent_cannot_supply_private_restore_proof(self):
  self.restore()
  for c in self.f.registry.connections.values():c['agent_version']='2.0.0~dev64'
  advance_restore(self.hub,verify=True);self.assertTrue(notices(self.hub));self.assertFalse(any(r.get('lifecycle_restore') for r in self.hub.read()['requests'].values()))
 def test_undelivered_old_requests_stop_but_completed_outcomes_are_retained(self):
  before=self.hub.read()['requests'][self.key]['proposal'];self.restore();row=self.hub.read()['requests'][self.key];self.assertEqual(row['proposal'],before);self.assertEqual(row['state'],'cancelled');self.assertTrue(row['cancelled_before_delivery']);self.assertTrue(row['restoration'])
 def test_denial_gets_fresh_invitation_without_overwriting_denial(self):
  self.f.exchange(self.f.a,caps=list(self.hub.caps[self.a]));p={'request_hash':self.key,'status':'denied','phase':'preserve','manifest_hash':self.hub.read()['requests'][self.key]['proposal']['manifest_hash'],'message':'Denied locally'}
  with self.hub.edit() as s:result(s,self.a,p)
  advance(self.hub);rows=group_rows(self.hub.read(),self.key);self.assertEqual(len(rows),2);self.assertEqual(self.hub.read()['requests'][self.key]['result'],p);child=next(r for r in rows if r['state']=='pending');self.assertEqual(child['generation'],2);advance(self.hub);self.assertEqual(len(group_rows(self.hub.read(),self.key)),2)

 def test_restore_keeps_request_waiting_when_no_private_source_exists(self):
  self.restore();self.old(self.a);self.old(self.b);advance_restore(self.hub,verify=True);advance_restore(self.hub,verify=True)
  rows=self.hub.read()['requests'];self.assertFalse(any(r.get('lifecycle_restore') for r in rows.values()));plans=rows[self.key]['restoration']['accounts'];self.assertTrue(plans);self.assertTrue(all(p['state']=='waiting' for p in plans));self.assertTrue(notices(self.hub));self.assertTrue(all('private-key' in p['message'] for p in plans))
 def test_restoration_request_is_idempotent_without_losing_private_detection(self):
  self.restore();advance_restore(self.hub,verify=True);before=copy.deepcopy(self.hub.read()['requests']);self.restore();self.assertEqual(before,self.hub.read()['requests'])
 def test_profile_state_rejects_forged_history_and_unknown_stale_agent(self):
  self.restore();advance_restore(self.hub,verify=True);state=self.hub.read();root=state['requests'][self.key];validate_saved(state,self.key,root)
  invalid=copy.deepcopy(root);invalid['dashboard_history_fingerprint']='../different-history'
  with self.assertRaises(ValueError):validate_saved(state,self.key,invalid)
  invalid=copy.deepcopy(root);invalid['restoration']['stale_nodes']={'unknown':{'hostname':'Example','detected_utc':self.hub.utc()}}
  with self.assertRaises(ValueError):validate_saved(state,self.key,invalid)

 def test_profile_archive_keeps_desired_restoration_and_dismissed_agent_notice(self):
  from profile_archive import ProfileArchive
  from preferences import FamilyStore
  from storage import data_directory
  self.restore();self.old(self.b);advance_restore(self.hub,verify=True);store=WorkflowStore(self.config);store.sync_lifecycle_notices(self.f.user,self.hub,'admin');notice=notices(self.hub)[0];store.update_notifications(self.f.user,notice['id']);before=self.hub.read()['requests'][self.key]
  target=Path(self.f.tmp.name)/'restored-lifecycle/config.cfg';FamilyStore(target);ProfileArchive(target).load('profile.7z',ProfileArchive(self.config).save());saved=json.loads((data_directory(target)/'agent-hub.json').read_text())['requests'][self.key]
  for field in ('restoration','dashboard_wallet','dashboard_history_fingerprint','dashboard_extinct'):self.assertEqual(saved[field],before[field])
  self.assertFalse(WorkflowStore(target).notifications(self.f.user)['notifications'])

 def test_flagged_paired_proposals_match_agent65_policy_identity(self):
  import os,subprocess
  from wallet_preview import restoration_binding
  self.restore();advance_restore(self.hub,verify=True);state=self.hub.read();rows=[r for r in state['requests'].values() if r.get('lifecycle_restore')==self.key]
  proposals=[]
  for row in rows:
   row['challenge']='c'*64;p=self.hub.transfer_proposal(state,row);self.assertEqual(p['restoration'],restoration_binding(row['public_wallet']));proposals.append(p)
  source=os.environ.get('WALLABY_AGENT_RESTORATION_SOURCE')
  if source:
   code='import json,sys;sys.path.insert(0,sys.argv[1]);from build8_policy import proposal;from signer_restoration import requested;rows=json.load(sys.stdin);assert all(proposal(p) and requested(p) for p in rows);print("Agent65 accepts both exact restoration proposals")'
   run=subprocess.run([sys.executable,'-c',code,source],input=json.dumps(proposals),text=True,capture_output=True);self.assertEqual(run.returncode,0,run.stderr)
   code='''import json,sys,tempfile,time;sys.path.insert(0,sys.argv[1]);from approval_store import Store;from wallet_preview import sign,validate_preview;p=json.load(sys.stdin);v={'version':2,'transfer_id':p['transfer_id'],'challenge':p['preview_challenge'],'sender_ipv6':p['node_ipv6'],'receiver_ipv6':p['peer']['ipv6'],'public_wallet':p['public_wallet'],'restoration':p['restoration'],'chain':'main','funded_outputs':[],'node_tip':{'height':999000,'hash':'b'*64},'generated_at':int(time.time()),'vaults':[],'address_labels':[]}
with tempfile.TemporaryDirectory() as folder:
 from pathlib import Path
 payload=sign(Store(Path(folder)),v);validate_preview(payload);print(json.dumps(payload))'''
   run=subprocess.run([sys.executable,'-c',code,source],input=json.dumps(next(p for p in proposals if p['direction']=='send')),text=True,capture_output=True);self.assertEqual(run.returncode,0,run.stderr)
   from wallet_preview import verify
   payload=json.loads(run.stdout);proof=verify(self.config,payload);self.assertTrue(proof['fingerprint'].startswith('SHA256:'));payload['preview']['restoration']['policy_id']='f'*64
   with self.assertRaises(ValueError):verify(self.config,payload)

 def test_restore_purpose_cannot_be_added_to_an_ordinary_signed_preview(self):
  from agent_hub import digest
  self.restore();advance_restore(self.hub,verify=True);state=self.hub.read();rows=[r for r in state['requests'].values() if r.get('lifecycle_restore')==self.key];sender=next(r for r in rows if r['direction']=='send')
  for row in rows:row['challenge']='c'*64;row['proposal']=self.hub.transfer_proposal(state,row);row['base_sent']=1;row['queue_visible']=True
  p=sender['proposal'];v={'version':2,'transfer_id':p['transfer_id'],'challenge':p['preview_challenge'],'sender_ipv6':p['node_ipv6'],'receiver_ipv6':p['peer']['ipv6'],'public_wallet':p['public_wallet']};payload={'request_hash':digest(p),'preview':v,'public_key':'test','signature':'test'}
  with self.assertRaisesRegex(ValueError,'restoration purpose'):self.hub.transfers.accept_preview(state,sender['node_id'],payload,{})
  v['restoration']=p['restoration'];self.hub.transfers.accept_preview(state,sender['node_id'],payload,{});self.assertEqual(sender['signed_preview']['preview']['restoration'],p['restoration'])

 def test_distinct_original_accounts_with_identical_public_policy_are_not_collapsed(self):
  second=copy.deepcopy(self.f.node_wallet);second['name']='Distinct original signer';second['raw']['wallet_name']=second['name']
  with self.hub.edit() as state:state['nodes'][self.b]['known_wallets']['second-role']=second
  self.restore();advance_restore(self.hub,verify=True);plans=[p for p in self.hub.read()['requests'][self.key]['restoration']['accounts'] if p['node_id']==self.b]
  self.assertEqual(len(plans),2);self.assertEqual(len({p['id'] for p in plans}),2);self.assertEqual({p['public_wallet']['wallet_name'] for p in plans},{self.f.node_wallet['raw']['wallet_name'],second['name']})

 def test_new_extinction_supersedes_restore_even_when_timestamps_are_identical(self):
  from wallet_lifecycle import roots,permitted_transfer
  self.restore();advance_restore(self.hub,verify=True);old=self.hub.read()['requests'][self.key];new=self.f.request()['request_hash'];state=self.hub.read();self.assertEqual(roots(state)[old['wallet_id']][0],new);self.assertEqual(state['requests'][self.key]['superseded_lifecycle'],new);self.assertFalse(any(permitted_transfer(state,r) for r in state['requests'].values() if r.get('lifecycle_restore')));self.assertFalse(notices(self.hub));self.assertTrue(cards(self.config,[]));validate_saved(state,self.key,state['requests'][self.key])

 def test_restore_withdraws_old_disc_destruction_even_after_restart(self):
  from archive_queue import ArchiveQueue
  from agent_hub import digest
  queue=ArchiveQueue(self.hub);state=queue.read();task={'kind':'destroy_disc','reason':'wallet_extinction','operation_id':self.hub.read()['requests'][self.key]['proposal']['operation_id'],'nonce':'d'*64};ident=digest(task);task['request_id']=ident
  state['requests'][ident]={'state':'active','request':task,'node_id':self.a,'hostname':'Example Agent','user_id':self.f.user,'created_utc':self.hub.utc(),'status':'Waiting'};queue.write(state)
  self.restore();self.assertFalse(queue.proposal(self.a)['requests']);self.assertFalse(queue.read()['requests'][ident]['queue_visible']);advance_restore(self.hub,verify=True);self.assertEqual(queue.read()['requests'][ident]['state'],'withdrawn');self.assertNotIn('result',queue.read()['requests'][ident])

 def test_concurrent_inventory_checks_do_not_duplicate_restoration_transfers(self):
  import threading
  from concurrent.futures import ThreadPoolExecutor
  import wallet_lifecycle
  self.restore();barrier=threading.Barrier(2);original=wallet_lifecycle.active_accounts
  def simultaneous(*args,**kwargs):
   accounts=original(*args,**kwargs);barrier.wait(timeout=5);return accounts
  with patch('wallet_lifecycle.active_accounts',side_effect=simultaneous),ThreadPoolExecutor(max_workers=2) as pool:
   futures=[pool.submit(advance_restore,self.hub,verify=True) for _ in range(2)]
   for future in futures:future.result(timeout=10)
  rows=[r for r in self.hub.read()['requests'].values() if r.get('lifecycle_restore')==self.key];self.assertEqual(len(rows),2);self.assertEqual(len({r['transfer_id'] for r in rows}),1)

 def test_later_extinct_copy_after_success_gets_fresh_request_without_replaying_outcome(self):
  self.restore();advance_restore(self.hub,verify=True)
  with self.hub.edit() as state:
   rows=[r for r in state['requests'].values() if r.get('lifecycle_restore')==self.key];old=rows[0]['transfer_id']
   for row in rows:row.update(state='complete',finished_utc='2000-01-01T00:00:00Z')
  self.old(self.b);advance_restore(self.hub,verify=True);state=self.hub.read();oldrows=[r for r in state['requests'].values() if r.get('transfer_id')==old];newrows=[r for r in state['requests'].values() if r.get('lifecycle_restore')==self.key and r.get('transfer_id')!=old];self.assertEqual(len(newrows),2);self.assertTrue(all(r['state']=='complete' for r in oldrows));self.assertTrue(all(r['state']=='pending' for r in newrows));self.assertNotEqual(newrows[0]['transfer_id'],old)

 def test_sender_denial_gets_one_fresh_invitation_and_keeps_old_outcome(self):
  self.restore();advance_restore(self.hub,verify=True)
  with self.hub.edit() as state:
   rows=[r for r in state['requests'].values() if r.get('lifecycle_restore')==self.key];sender=next(r for r in rows if r['direction']=='send');old=sender['transfer_id'];sender['state']='denied'
  advance_restore(self.hub,verify=True);after=self.hub.read();pairs=[r for r in after['requests'].values() if r.get('lifecycle_restore')==self.key];self.assertEqual(len(pairs),4);self.assertEqual(next(r for r in pairs if r['transfer_id']==old and r['direction']=='send')['state'],'denied');new=next(r['transfer_id'] for r in pairs if r['transfer_id']!=old);advance_restore(self.hub,verify=True);self.assertEqual(len([r for r in self.hub.read()['requests'].values() if r.get('lifecycle_restore')==self.key]),4);self.assertNotEqual(new,old)

 def test_agent_role_verification_failure_is_shown_without_automatic_retry(self):
  self.restore();advance_restore(self.hub,verify=True)
  with self.hub.edit() as state:
   sender=next(r for r in state['requests'].values() if r.get('lifecycle_restore')==self.key and r['direction']=='send');sender.update(state='error',message='Different signer keys; no file was sent.')
  advance_restore(self.hub,verify=True);state=self.hub.read();failed=[p for p in state['requests'][self.key]['restoration']['accounts'] if p['node_id']==self.b];self.assertEqual(failed[0]['state'],'error');self.assertIn('Different signer keys',failed[0]['message']);self.assertEqual(len([r for r in state['requests'].values() if r.get('lifecycle_restore')==self.key]),2)

if __name__=='__main__':unittest.main()
