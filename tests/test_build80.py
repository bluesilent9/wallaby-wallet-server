"""Durable grouped approval, signed receipt binding, and safe linked cancellation."""
import base64,copy,json,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
import test_build72 as fixture
from vault_refresh import finish,complete,progress,cancel
from wallet_policy_updates import proposals,accept_receipt,accept,destination_ready,BATCH_CAPABILITY
from builder_destinations import Destinations
from builder_workspace import BuilderWorkspace
from agent_hub import digest

class GroupedApproval(unittest.TestCase):
 def setUp(self):
  self.f=fixture.Refresh();self.f.setUp();self.addCleanup(self.f.doCleanups);self.hub=self.f.hub;self.user=self.f.f.user;self.work=self.f.work;self.keys={};self.public={}
  for connection in self.hub.registry.connections.values():connection['agent_version']='2.0.0~dev60'
  for i,node in enumerate(self.f.accounts):
   key=Path(self.f.f.tmp.name)/('approval-key-'+str(i));subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(key)],check=True);self.keys[node]=key
   pub=' '.join(key.with_suffix('.pub').read_text().split()[:2]);self.hub.permissions.live[node]['identity']=pub;self.hub.caps[node].update({'wallet_policy_refresh_v1',BATCH_CAPABILITY})
 def sign(self,node,body):
  key=self.keys[node];message=key.with_suffix('.message');message.write_text(json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=True));sig=Path(str(message)+'.sig');sig.unlink(missing_ok=True);subprocess.run(['ssh-keygen','-Y','sign','-f',str(key),'-n','wallaby-wallet-setup-v1',str(message)],check=True,capture_output=True)
  return {'message':body,'public_key':' '.join(key.with_suffix('.pub').read_text().split()[:2]),'signature':base64.b64encode(sig.read_bytes()).decode()}
 def target(self,node):return next(t for t in progress(self.hub,self.user)['targets'] if t['node_id']==node)
 def begin(self):
  result=finish(self.hub,self.user,1000100);self.d=Destinations(self.f.f.config).get(result['destination']);self.rows={r['node_id']:r for r in self.hub.read()['requests'].values() if r.get('destination_id')==self.d['id']};return result
 def receipt(self,node):
  r=self.rows[node];return self.sign(node,{'version':1,'request_id':r['proposal']['request_id'],'request_hash':digest(r['proposal']),'status':'received'})
 def installed(self,node,*,missing=None,drop_old=None):
  r=self.rows[node];p=r['proposal']
  for name in set(r['required_wallets'])|{'Logical vault'}:
   self.public[node,name]={'descriptors':[{'desc':desc} for desc in r['previous_wallet_descriptors'].get(name,[])]+[{'desc':p[k]} for k in ('receive_descriptor','change_descriptor')]}
  if missing:self.public[node,missing]['descriptors']=[{'desc':p['receive_descriptor']}]
  if drop_old:self.public[node,drop_old]['descriptors']=[{'desc':p[k]} for k in ('receive_descriptor','change_descriptor')]
  self.hub.rpc=lambda n,m,params=None,wallet=None:copy.deepcopy(self.public[n,wallet]) if m=='listdescriptors' else {'wallaby_storage':'node','walletname':wallet}
 def result(self,node,status='approved',updated=None):
  r=self.rows[node];p=r['proposal'];body={'version':1,'request_id':p['request_id'],'request_hash':digest(p),'status':status,'wallet':p['wallet']}
  if status in ('approved','history_required'):
   body.update({k:p[k] for k in ('previous_descriptors','receive_descriptor','change_descriptor')});body.update(policy_hash=digest({k:p[k] for k in ('previous_descriptors','receive_descriptor','change_descriptor','timestamp')}),monitor_wallet='Logical vault',updated_wallets=updated if updated is not None else r['required_wallets'])
  return self.sign(node,body)
 def approve_all(self):
  for node in self.rows:self.installed(node);accept(self.hub,node,self.result(node))
 def test_wait_is_one_row_per_agent_not_per_disc_signer_and_transaction_unchanged(self):
  before=copy.deepcopy(self.work.read()['workspaces']['transaction']);state=self.begin();self.assertTrue(state['waiting']);self.assertEqual(len(state['targets']),2);self.assertEqual(sum(len(r['required_wallets']) for r in self.rows.values()),7);self.assertTrue(all(r['colour']=='red' for r in state['targets']));self.assertEqual(self.work.read()['workspaces']['transaction'],before)
  with self.assertRaisesRegex(ValueError,'every Agent'):complete(self.hub,self.user)
 def test_reentry_keeps_exact_reservation_proposals_and_saved_profile(self):
  self.begin();before=Destinations(self.f.f.config).read();requests=self.hub.read()['requests'];again=finish(self.hub,self.user,1000100);self.assertEqual(again['destination'],self.d['id']);self.assertEqual(Destinations(self.f.f.config).read(),before);self.assertEqual(self.hub.read()['requests'],requests)
  from profile_archive import ProfileArchive
  from preferences import FamilyStore
  restored=Path(self.f.f.tmp.name)/'restore/config.cfg';FamilyStore(restored);ProfileArchive(restored).load('profile.7z',ProfileArchive(self.f.f.config).save());w=BuilderWorkspace(restored).owned(self.user,'wallet');self.assertEqual(w['renewal']['approval']['destination'],self.d['id']);self.assertEqual(Destinations(restored).get(self.d['id'])['approval_wallets'],self.d['approval_wallets'])
 def test_delivery_without_signed_receipt_stays_red_and_duplicate_receipt_is_idempotent(self):
  self.begin();node=next(iter(self.rows));proposals(self.hub,node);self.assertEqual(self.target(node)['colour'],'red');envelope=self.receipt(node);accept_receipt(self.hub,node,envelope);before=self.hub.read();accept_receipt(self.hub,node,envelope);self.assertEqual(self.hub.read(),before);self.assertEqual(self.target(node)['colour'],'amber')
 def test_unsent_wrong_hash_wrong_node_and_tampered_receipts_rejected(self):
  self.begin();a,b=self.rows
  with self.assertRaises(ValueError):accept_receipt(self.hub,a,self.receipt(a))
  proposals(self.hub,a);body=self.receipt(a)['message'];body['request_hash']='0'*64
  with self.assertRaises(ValueError):accept_receipt(self.hub,a,self.sign(a,body))
  with self.assertRaises(ValueError):accept_receipt(self.hub,b,self.receipt(a))
  envelope=self.receipt(a);envelope['message']['status']='approved'
  with self.assertRaises(ValueError):accept_receipt(self.hub,a,envelope)
 def test_old_agent_does_not_receive_batch_request_and_cannot_unlock(self):
  self.begin();node=next(iter(self.rows));self.hub.caps[node].discard(BATCH_CAPABILITY);self.assertEqual(proposals(self.hub,node),[]);self.assertIn('update required',self.target(node)['status']);self.assertFalse(destination_ready(self.hub,self.d))
 def test_partial_disc_coverage_or_missing_core_descriptors_cannot_go_green(self):
  self.begin();node=next(iter(self.rows));self.installed(node)
  with self.assertRaisesRegex(ValueError,'every local signer'):accept(self.hub,node,self.result(node,updated=['Logical vault']))
  alias=next(name for name in self.rows[node]['required_wallets'] if name!='Logical vault');self.installed(node,missing=alias)
  with self.assertRaisesRegex(ValueError,'every local signer'):accept(self.hub,node,self.result(node))
  self.installed(node,drop_old=alias)
  with self.assertRaisesRegex(ValueError,'retained history'):accept(self.hub,node,self.result(node))
  self.assertTrue(all(t['colour']=='red' for t in progress(self.hub,self.user)['targets']))
 def test_all_confirmations_required_even_when_unapproved_agent_disconnects(self):
  self.begin();a,b=self.rows;self.installed(a);accept(self.hub,a,self.result(a));self.f.f.registry.connections.pop(next(token for token,c in self.f.f.registry.connections.items() if c['node_id']==b));self.assertFalse(progress(self.hub,self.user)['complete']);self.assertIn('disconnected',self.target(b)['status'])
 def test_completion_preserves_payment_keys_and_only_swaps_destination(self):
  before=copy.deepcopy(self.work.read()['workspaces']['transaction']);self.begin();self.approve_all();self.assertTrue(progress(self.hub,self.user)['complete']);result=complete(self.hub,self.user);after=self.work.owned(self.user,'transaction');self.assertNotIn('wallet',self.work.read()['workspaces']);self.assertEqual(after['draft']['edges'][0]['to'],result['destination']);self.assertEqual(after['draft']['edges'][0]['amount_sats'],before['draft']['edges'][0]['amount_sats']);self.assertEqual(after['operations'],[])
 def test_decline_immediately_restores_original_transaction_and_persists_scoped_cleanup(self):
  before=copy.deepcopy(self.work.read()['workspaces']['transaction']);self.begin();a,b=self.rows
  for node in self.rows:proposals(self.hub,node)
  self.installed(a);accept(self.hub,a,self.result(a));accept(self.hub,b,self.result(b,'denied'));self.assertNotIn('wallet',self.work.read()['workspaces']);self.assertEqual(self.work.read()['workspaces']['transaction'],before);self.assertFalse(Destinations(self.f.f.config).get(self.d['id'])['policy_requests_started']);self.assertFalse(destination_ready(self.hub,Destinations(self.f.f.config).get(self.d['id'])))
  batches=self.work.read()['cancellations'];self.assertEqual(len(batches),1);batch=next(iter(batches.values()));self.assertEqual(set(batch['targets']),{a},'the Agent which already declined needs no second local cleanup approval')
  for node,t in batch['targets'].items():self.assertEqual(t['proposal']['operations'],[]);self.assertEqual(t['proposal']['request_hashes'],[digest(self.rows[node]['proposal'])])
 def test_user_cancel_preserves_transaction_and_offline_cancellation_delivery(self):
  before=copy.deepcopy(self.work.read()['workspaces']['transaction']);self.begin();a=next(iter(self.rows));proposals(self.hub,a);self.assertTrue(cancel(self.hub,self.user)['waiting']);self.assertEqual(self.work.read()['workspaces']['transaction'],before);proposal=self.work.proposals(a)[0];self.work.receipt(a,{'version':1,'cancellation_id':proposal['cancellation_id'],'request_hash':digest(proposal),'status':'received'});self.assertNotIn('wallet',self.work.read()['workspaces']);self.assertEqual(proposals(self.hub,a),[])
 def test_submitted_wallet_height_and_transaction_draft_are_locked(self):
  self.begin();w=self.work.owned(self.user,'wallet');draft=copy.deepcopy(w['draft']);draft['vault']={'result':{'height':1000200}}
  with self.assertRaisesRegex(ValueError,'locked'):self.work.save(self.user,'wallet',{'id':w['id'],'revision':w['revision'],'draft':draft})
  tx=self.work.owned(self.user,'transaction');draft=copy.deepcopy(tx['draft']);draft['edges'][0]['amount_sats']='1'
  with self.assertRaisesRegex(ValueError,'linked vault'):self.work.save(self.user,'transaction',{'id':tx['id'],'revision':tx['revision'],'draft':draft})
 def test_signed_local_cleanup_result_binds_exact_policy_and_never_deletes_wallets(self):
  from wallet_policy_updates import accept_cancel
  self.begin();node=next(iter(self.rows));proposals(self.hub,node);cancel(self.hub,self.user);request=self.work.proposals(node)[0]
  body={'version':1,'cancellation_id':request['cancellation_id'],'request_hash':digest(request),'status':'complete','policy_request_hashes':request['request_hashes'],'retired_policy_hashes':[digest([self.rows[node]['proposal']['receive_descriptor'],self.rows[node]['proposal']['change_descriptor']])],'keys_retained':True,'descriptors_retained':True,'destroyed_archives':[]}
  bad=dict(body,keys_retained=False)
  with self.assertRaises(ValueError):accept_cancel(self.hub,node,self.sign(node,bad))
  envelope=self.sign(node,body);accept_cancel(self.hub,node,envelope);accept_cancel(self.hub,node,envelope);target=self.work.read()['cancellations'][request['cancellation_id']]['targets'][node];self.assertEqual(target['policy_cleanup'],envelope);self.assertTrue(target['received_utc'])
 def test_cancelled_height_can_be_reproposed_without_reusing_a_new_wallet_or_keys(self):
  from builder_destinations import refresh_wallet
  self.begin();cancelled=self.d;cancel(self.hub,self.user)
  # Model retained Core descriptors after a policy has been locally retired.
  original=copy.deepcopy(self.f.f.wallet);raw=copy.deepcopy(original['raw']);raw['descriptors'].extend(cancelled['descriptors']);wallet=copy.deepcopy(original);wallet['raw']=raw
  planning=refresh_wallet(self.f.f.config,wallet);self.assertEqual(planning['raw']['descriptors'],original['raw']['descriptors']);self.assertEqual(wallet['raw'],raw,'planning never removes stored recovery descriptors')
 def test_cancelled_policy_not_recommended_by_cached_address_book(self):
  from address_destinations import vault_entry
  from vendor.embit.descriptor import Descriptor
  from vendor.embit.networks import NETWORKS
  self.begin();cancelled=self.d;cancel(self.hub,self.user);cancelled=Destinations(self.f.f.config).get(cancelled['id']);wallet=copy.deepcopy(self.f.f.wallet);wallet['raw']['descriptors'].extend(cancelled['descriptors']);old=wallet['raw']['descriptors'][0];address=Descriptor.from_string(old['desc']).derive(0).address(NETWORKS['main']);entry={'addresses':[{'address':cancelled['address'],'descriptor':cancelled['descriptors'][0]['desc'],'index':cancelled['index']}],'address_history':[{'address':address,'descriptor':old['desc'],'index':0},{'address':cancelled['address'],'descriptor':cancelled['descriptors'][0]['desc'],'index':cancelled['index']}],'current_height':999000};result=vault_entry(entry,wallet,[cancelled]);self.assertEqual(result['addresses'][0]['address'],address);self.assertIn(cancelled['address'],[r['address'] for r in result['address_history']])
 def test_cancel_before_late_approval_keeps_withdrawal_and_original_transaction(self):
  before=copy.deepcopy(self.work.read()['workspaces']['transaction']);self.begin();node=next(iter(self.rows));proposals(self.hub,node);cancel(self.hub,self.user);self.installed(node);accept(self.hub,node,self.result(node));row=self.hub.read()['requests'][self.rows[node]['proposal']['request_id']];self.assertEqual(row['state'],'cancelled');self.assertTrue(row['result']);self.assertEqual(self.work.read()['workspaces']['transaction'],before);self.assertFalse(destination_ready(self.hub,Destinations(self.f.f.config).get(self.d['id'])))
 def test_matching_agent58_generated_receipt_and_denial_are_accepted(self):
  import os,sys
  source=Path(os.environ.get('WALLABY_AGENT_SOURCE','/nonexistent'))
  if not (source/'policy_refresh_group.py').exists():self.skipTest('Matching Agent grouped-refresh source not available')
  self.begin()
  from relay_fixtures import persisted_refresh_v1
  persisted_refresh_v1(self)
  node=next(iter(self.rows));proposals(self.hub,node);path=Path(self.f.f.tmp.name)/'agent-request.json';path.write_text(json.dumps(self.rows[node]['proposal']));root=Path(self.f.f.tmp.name)/'actual-agent'
  script="""import json,sys\nfrom types import SimpleNamespace\nsys.path.insert(0,sys.argv[1])\nfrom approval_store import Store,digest\nfrom policy_refresh_group import received\nfrom policy_refresh import Refresh\ns=Store(sys.argv[3]);p=json.load(open(sys.argv[2]));s.receive(p);received(s,p);Refresh(None,s,SimpleNamespace(loaded={})).deny(digest(p));print(json.dumps(list(s.read()['outbox'].values())))\n"""
  items=json.loads(subprocess.check_output([sys.executable,'-c',script,str(source),str(path),str(root)],text=True));by_kind={item['kind']:item['payload'] for item in items};self.hub.permissions.live[node]['identity']=by_kind['wallet_policy_refresh_receipt']['public_key'];accept_receipt(self.hub,node,by_kind['wallet_policy_refresh_receipt']);self.assertEqual(self.target(node)['colour'],'amber');accept(self.hub,node,by_kind['wallet_policy_refresh_result']);self.assertNotIn('wallet',self.work.read()['workspaces']);self.assertTrue(self.work.read()['cancellations'])
 def test_funded_retention_is_not_misreported_as_policy_or_disc_destruction(self):
  from wallet_policy_updates import accept_cancel
  from transaction_workflows import WorkflowStore
  self.begin();node=next(iter(self.rows));proposals(self.hub,node);cancel(self.hub,self.user);request=self.work.proposals(node)[0];body={'version':1,'cancellation_id':request['cancellation_id'],'request_hash':digest(request),'status':'retained_funded','policy_request_hashes':request['request_hashes'],'retired_policy_hashes':[],'keys_retained':True,'descriptors_retained':True,'destroyed_archives':[]};envelope=self.sign(node,body);accept_cancel(self.hub,node,envelope);accept_cancel(self.hub,node,envelope);notices=WorkflowStore(self.f.f.config).notifications(self.user)['notifications'];self.assertEqual(len(notices),1);self.assertEqual(notices[0]['severity'],'red');self.assertIn('is funded',notices[0]['text']);self.assertTrue(Destinations(self.f.f.config).get(self.d['id'])['policy_retained_funded']);from builder_destinations import refresh_wallet
  wallet=copy.deepcopy(self.f.f.wallet);wallet['raw']['descriptors'].extend(self.d['descriptors']);self.assertEqual(refresh_wallet(self.f.f.config,wallet)['raw'],wallet['raw']);WorkflowStore(self.f.f.config).update_notifications(self.user,delete=notices[0]['id']);accept_cancel(self.hub,node,envelope);self.assertFalse(WorkflowStore(self.f.f.config).notifications(self.user)['notifications'])
