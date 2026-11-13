"""Stale reviewed invitations and explicit retirement ledger aliases."""
import copy,json,os,subprocess,sys,unittest
from pathlib import Path
from unittest.mock import patch
import test_wallet_server9 as route_fixtures
import test_wallet_server7 as history_fixtures
import test_build21_revision as discovery_fixtures
from retired_catalog import reconcile
from descriptor_store import clean_wallet,DescriptorStore
from descriptor_policy import parse_policy
from vendor.embit.descriptor.checksum import checksum
from preferences import resource_id,FamilyStore
from node_chain import configure
from descriptor_chain import scan,HistoryClient,wallet_rows
from worker import load_core
from decimal import Decimal

class ReviewedRoutes(route_fixtures.LoadedRoutes):
 def test_automatic_review_is_retained_only_on_original_attempt(self):
  with self.hub.edit() as state:
   sender=next(r for r in state['requests'].values() if r['direction']=='send')
   sender.update(signed_preview={'retained':'signed public review'},preview_proof='original comparison proof',preview_notice='Snapshot changed before authorisation')
  fresh=self.fresh();self.assertEqual(len(fresh),2)
  self.assertTrue(all('signed_preview' not in r and 'preview_proof' not in r for r in fresh))
  old=next(r for r in self.hub.read()['requests'].values() if r.get('superseded_attempt') and r['direction']=='send')
  self.assertEqual(old['signed_preview'],{'retained':'signed public review'});self.assertEqual(old['preview_proof'],'original comparison proof')
 def test_late_denial_or_error_on_original_withdraws_replacement(self):
  from agent_hub import digest
  from wallet_sync_queue import schedule
  for outcome in ('denied','error','recovery_required','complete'):
   with self.hub.edit() as state:state['requests']=copy.deepcopy(self.old)
   self.refresh();original=next(r for r in self.old.values() if r['direction']=='receive')
   with self.hub.edit() as state:
    self.hub.transfers.accept_result(state,original['node_id'],{'request_hash':digest(original['proposal']),'status':outcome})
    schedule(self.hub.transfers,state)
   self.assertTrue(all(not r['queue_visible'] for r in self.hub.read()['requests'].values() if r.get('retry_of')))
 def test_already_watched_extinct_addresses_allow_legacy_review_replacement(self):
  f=history_fixtures.HistoryOffers();f.setUp();self.addCleanup(f.doCleanups);f.exchange(f.f.b)
  from wallet_sync_queue import schedule
  with f.hub.edit() as state:
   for r in state['requests'].values():
    r.pop('history_sync');r['proposal'].pop('transport');r['proposal'].update(transfer_version=2,node_ipv6='2001:db8::1');r['proposal']['peer']['ipv6']='2001:db8::2'
    r['signed_preview']={'retained':'automatic review'}
   for inv in f.hub.inventories.values():inv.update(complete=False,loaded_complete=True,unloaded_wallets=['unrelated'])
   schedule(f.hub.transfers,state)
  fresh=[r for r in f.hub.read()['requests'].values() if r.get('retry_of')]
  self.assertEqual(len(fresh),2);self.assertTrue(all(r['proposal']['transfer_version']==3 and r['queue_visible'] and not r['source_has_private_keys'] for r in fresh))
 def test_current_agent_retains_attempted_work_and_requires_fresh_choices(self):
  source=os.environ.get('WALLABY_AGENT_CURRENT_SOURCE')
  if not source:self.skipTest('Set current Agent source')
  p=self.fresh()[0]['proposal']
  code='''import copy,json,sys,tempfile
sys.path.insert(0,sys.argv[1])
from approval_store import Store,digest
from sync_queue import apply_snapshot,freeze
p=json.loads(sys.stdin.read());old=copy.deepcopy(p);old['transfer_id']='a'*64;old['preview_challenge']='b'*64
with tempfile.TemporaryDirectory() as tmp:
 store=Store(tmp,persistence=False);store.persistence=None
 apply_snapshot(store,1,[old]);key=digest(old)
 with store.edit() as s:
  s['sync_choices']={key:{'selected':True,'watch_only':True}}
  s['transfer_previews']={key:{'retained':'automatic review'}}
 apply_snapshot(store,2,[p]);s=store.read();assert key not in s['pending'];assert key not in s.get('sync_choices',{});assert digest(p) not in s.get('sync_choices',{});assert digest(p) not in s.get('transfer_previews',{})
 # A separate active old attempt must be retained, and cannot be bypassed.
 with store.edit() as s:
  s['pending'][key]={'proposal':old,'received':1,'state':'approved'};s['active_transfer']=key
 apply_snapshot(store,3,[p]);s=store.read();assert s['pending'][key]['withdrawn'];assert s['active_transfer']==key
 try:freeze(store,[digest(p)],p['direction'])
 except ValueError:pass
 else:raise AssertionError('An active old operation was bypassed')
'''
  r=subprocess.run([sys.executable,'-B','-c',code,source],input=json.dumps(p),capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)

class RetiredLedgers(discovery_fixtures.Discovery):
 def setUp(self):
  super().setUp();self.original=copy.deepcopy(self.core.wallets[0]);self.address=parse_policy(self.original['raw']['descriptors'][0]['desc'].split('#')[0])[0].derive(0).script_pubkey().address()
  for r in self.original['node_history']:
   if r['category']=='receive':r['address']=self.address
  body='addr('+self.address+')';self.archive=clean_wallet({'wallet_name':'Retired account','descriptors':[{'desc':body+'#'+checksum(body)}]})
  self.archive.update(extinct=True,watch_only=True,address_labels={self.address:{'label':'Retired account','lost_utc':None}},node_history=copy.deepcopy(self.original['node_history']),node_sources=[{'node_id':'node0','hostname':'host0','wallet_name':'Extinct'}],public_history=copy.deepcopy(self.original['public_history']))
  self.root={'kind':'wallet_retire','wallet_id':resource_id('descriptor',self.original['id']),'expected_holders':['node0'],'created_utc':'2026-11-01T00:00:00Z','dashboard_extinct':True,'dashboard_wallet':copy.deepcopy(self.original),'retirement_wallet':copy.deepcopy(self.original['raw']),'root_hash':'retirement','state':'complete','archive_checked':{'receipt':'verified'},'proposal':{'phase':'preserve','manifest_hash':'f'*64,'manifest':{'addresses':[{'address':self.address,'label':'Retired account'}]},'archive_label':'Retired account'}}
  self.state={'requests':{'retirement':self.root}}
  call=self.core.call
  self.core.call=lambda node,method,params=None,wallet=None:call(node,method,params,self.original['name'] if wallet=='Extinct' else wallet)
 def test_real_retirement_receipt_state_enables_canonical_identity(self):
  import test_build18 as retirement_fixtures
  f=retirement_fixtures.Retirement();f.setUp();self.addCleanup(f.doCleanups);key=f.delivered();f.preserve(key);state=f.hub.read();root=state['requests'][key]
  self.assertTrue(root['archive_checked'])
  rows=[];labels={}
  for item in root['proposal']['manifest']['addresses']:
   text='addr('+item['address']+')';rows.append({'desc':text+'#'+checksum(text)});labels[item['address']]={'label':item['label'],'lost_utc':None}
  archive=clean_wallet({'wallet_name':root['proposal']['archive_label'],'descriptors':rows});archive.update(extinct=True,address_labels=labels,node_history=[],node_sources=[],public_history={'outputs':[]})
  fresh,aliases=reconcile([archive],[root['dashboard_wallet']],state)
  self.assertEqual(len(fresh),1);self.assertEqual(fresh[0]['id'],root['dashboard_wallet']['id']);self.assertTrue(fresh[0]['extinct'])
 def test_preserved_archive_and_cached_active_wallet_become_one_exact_ledger(self):
  fresh,aliases=reconcile([self.archive,self.core.wallets[1]],[self.original,self.archive],self.state)
  self.assertEqual(len(fresh),2);self.assertEqual(aliases,{self.archive['id']})
  w=next(w for w in fresh if w['id']==self.original['id']);self.assertTrue(w['extinct']);self.assertEqual(w['raw'],self.original['raw']);self.assertEqual(w['node_sources'],self.archive['node_sources'])
  catalog={'wallets':fresh};configure(self.core,catalog);snapshot=scan(catalog,HistoryClient(None),lambda x:None);rows=wallet_rows(load_core(),snapshot)
  self.assertEqual(rows[self.original['name']][-1].balance,Decimal('.00039'));self.assertEqual(rows['Second'][-1].balance,Decimal('.0006'));self.assertEqual(len(snapshot['wallets']),2)
 def test_background_replaces_previously_published_duplicate_without_new_owner(self):
  store=DescriptorStore(self.config);store.replace_node_wallets([self.original,self.archive,self.core.wallets[1]])
  rid=resource_id('descriptor',self.original['id'])
  with FamilyStore(self.config).transaction() as data:data['ownership']=[{'id':rid,'kind':'descriptor','source':self.original['id'],'name':'Example account','owner_id':self.uid,'confirmed':True}]
  self.service.registry.hub.read=lambda:copy.deepcopy(self.state)
  self.cycle([self.archive,self.core.wallets[1]]);catalog=store.read();self.assertEqual({w['id'] for w in catalog['wallets']},{self.original['id'],self.core.wallets[1]['id']});self.assertTrue(FamilyStore(self.config).snapshot()['ownership'][0]['confirmed']);self.assertEqual(FamilyStore(self.config).snapshot()['ownership'][0]['source'],self.original['id'])
 def test_no_alias_without_verified_receipt(self):
  self.root.pop('archive_checked');fresh,aliases=reconcile([self.archive],[self.original],self.state);self.assertEqual(fresh,[self.archive]);self.assertFalse(aliases)
 def test_cancelled_intent_does_not_classify_as_retired(self):
  root=copy.deepcopy(self.root);root.update(cancel_requested=True,dashboard_extinct=False)
  fresh,aliases=reconcile([self.archive],[self.original],{'requests':{'retirement':root}});self.assertEqual(fresh,[self.archive]);self.assertFalse(aliases)
 def test_restoration_preserves_one_active_identity_with_and_without_private_replica(self):
  self.root['restoration']={'created_utc':'now'}
  for active in ([],[dict(self.original,watch_only=False)]):
   fresh,aliases=reconcile([self.archive]+active,[self.original],self.state)
   self.assertEqual(len(fresh),1);self.assertEqual(fresh[0]['id'],self.original['id']);self.assertFalse(fresh[0]['extinct']);self.assertEqual(fresh[0]['watch_only'],not bool(active))
 def test_wrong_label_or_uncovered_receiving_address_does_not_hide_a_wallet(self):
  for changed in ('label','coverage'):
   archive=copy.deepcopy(self.archive);old=copy.deepcopy(self.original)
   if changed=='label':archive['address_labels'][self.address]['label']='Unrelated account'
   else:old['node_history'].append({'txid':'f'*64,'vout':0,'category':'receive','address':'uncovered'})
   fresh,aliases=reconcile([archive],[old],self.state);self.assertEqual(fresh,[archive]);self.assertFalse(aliases)
 def test_still_loaded_original_during_deletion_is_not_double_counted(self):
  fresh,aliases=reconcile([self.archive,self.original],[self.original],self.state);self.assertEqual(len(fresh),1);self.assertEqual(fresh[0]['id'],self.original['id'])
 def test_genuine_unrelated_script_conflict_still_fails_with_account_names(self):
  catalog={'wallets':[self.original,self.archive,self.core.wallets[1]]};configure(self.core,catalog)
  with self.assertRaisesRegex(ValueError,'First.*Retired account.*No duplicate balance'):scan(catalog,HistoryClient(None),lambda x:None)

# Only this release's added discovery checks, not inherited unrelated HTTP checks.
for name in discovery_fixtures.Discovery.__dict__:
 if name.startswith('test_') and name not in RetiredLedgers.__dict__:setattr(RetiredLedgers,name,None)

class PartialHistory(history_fixtures.HistoryOffers):
 def test_unrelated_unloaded_folders_do_not_hide_extinct_history_mismatch(self):
  for inv in self.hub.inventories.values():inv.update(complete=False,loaded_complete=True,unloaded_wallets=['unrelated'])
  self.exchange(self.f.b);self.assertEqual(len(self.rows()),2);self.assertTrue(all(r['history_sync'] for r in self.rows()))
for name in history_fixtures.HistoryOffers.__dict__:
 if name.startswith('test_') and name not in PartialHistory.__dict__:setattr(PartialHistory,name,None)

if __name__=='__main__':unittest.main()
