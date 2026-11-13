"""Accepted personal/SMSF PDF coverage is independent of failed wallet tracing."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
from datetime import date,datetime,timezone
from unittest.mock import patch
from types import SimpleNamespace
from preferences import FamilyStore
from statement_records import StatementRecords
from transaction_workflows import WorkflowStore
from family_inputs import account_slot,smsf_slot
from launch_wallaby_wallet_server import Session
import test_build65_statements as statement_fixtures

class AcceptedStatements(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.config=self.root/'config.cfg';self.family=FamilyStore(self.config)
  for name in ('First','Second'):self.family.save_user(name,'green',revision=self.family.snapshot()['revision'])
  self.a,self.b=[u['id'] for u in self.family.snapshot()['users']];self.records=StatementRecords(self.config);self.f=statement_fixtures.UploadBatch();self.now=datetime(2026,11,13,tzinfo=timezone.utc)
  with self.family.transaction() as d:
   d['bitaroo_accounts']={self.a:True,self.a+':smsf':True,self.b:True,self.b+':smsf':False}
   d['ownership_runs']={uid:{'completed_utc':'2026-10-01T00:00:00Z','bitaroo_data':{'periods':{'2026-27':{'end':'2026-10-01'}}},'bitaroo_smsf_data':{'periods':{'2026-27':{'end':'2026-10-01'}}}} for uid in (self.a,self.b)}
 def accept(self,key,files=None,existing=None):
  return self.records.accept(self.f.core(),key,files or self.f.pair(2026,'2026-11-13'),existing,self.root/'browser'/key.replace(':','-'),'UTC',self.now)
 def notices(self,viewer=None):
  viewer=viewer or self.b;flow=WorkflowStore(self.config);flow.sync_bitaroo_warnings(viewer,self.family.snapshot(),'2026-11-13','UTC','balances');return [n for n in flow.notifications(viewer)['notifications'] if n['kind']=='bitaroo_warning']
 def test_all_three_updated_accounts_clear_without_successful_ownership(self):
  before=copy.deepcopy(self.family.snapshot()['ownership_runs']);self.assertEqual(len(self.notices()),3)
  self.accept(self.a);self.assertEqual({n['account_id'] for n in self.notices()},{self.a+':smsf',self.b})
  self.accept(self.a+':smsf');self.accept(self.b);self.assertFalse(self.notices());self.assertEqual(self.family.snapshot()['ownership_runs'],before)
 def test_explicit_clear_removes_only_that_account_accepted_inputs(self):
  self.accept(self.a);self.accept(self.a+':smsf');session=Session(self.root/'session',self.config);self.addCleanup(session.close);session.user_id=self.a;session.clear_slot(account_slot(self.a));self.assertNotIn(self.a,self.records.dates());self.assertIn(self.a+':smsf',self.records.dates());self.assertIn(self.a,{n['account_id'] for n in self.notices()})
 def test_same_account_warnings_clear_for_all_viewers(self):
  self.assertEqual(len(self.notices(self.a)),3);self.accept(self.a)
  for viewer in (self.a,self.b):self.assertNotIn(self.a,{n['account_id'] for n in self.notices(viewer)})
 def test_rejected_single_and_malformed_batch_cannot_advance_saved_date(self):
  self.accept(self.a,self.f.pair(2026,'2026-10-01'));before=copy.deepcopy(self.records.read())
  for files in ([self.f.pair(2026,'2026-11-13')[0]],self.f.pair(2026,'2026-11-13')+[('bad.pdf',b'invalid')]):
   with self.assertRaises(ValueError):self.accept(self.a,files)
   self.assertEqual(self.records.read(),before);self.assertIn(self.a,{n['account_id'] for n in self.notices()})
 def test_historical_only_fill_keeps_current_coverage_and_no_duplicates(self):
  self.accept(self.a);one=[('old-aud.pdf',self.f.pdf('AUD',2025,'2026-06-30'))];self.accept(self.a,one);self.accept(self.a,one)
  r=self.records.read()['accounts'][self.a];self.assertEqual(r['statement_date'],'2026-11-13');self.assertEqual(len(r['files']),3);self.assertEqual(len([p for p in self.records.root.iterdir() if p.is_dir()]),1)
 def test_new_session_restores_accepted_inputs_even_without_completed_run(self):
  self.accept(self.a);self.accept(self.a+':smsf')
  with self.family.transaction() as d:d.pop('ownership_runs')
  session=Session(self.root/'new-session',self.config);self.addCleanup(session.close);session.user_id=self.a;session.sync_workspace(self.family.snapshot())
  self.assertEqual(set(session.uploads),{account_slot(self.a),smsf_slot(self.a)})
  self.assertEqual(len(list(session.uploads[account_slot(self.a)].iterdir())),2);self.assertIsNone(session.ownership_completed_utc);self.assertFalse(session.inventory_ready)
 def test_actual_session_upload_saves_before_any_worker_and_survives_close(self):
  session=Session(self.root/'session',self.config);self.addCleanup(session.close);session.user_id=self.a
  before=copy.deepcopy(self.family.snapshot()['ownership_runs'])
  with patch.dict(sys.modules,{'tax_core_v107':self.f.core()}):session.upload_statements(smsf_slot(self.a),self.f.pair(2026,'2026-11-13'),'UTC')
  session.last_job_error='Two distinct wallets claim the same script.';session.close();self.assertNotIn(self.a+':smsf',{n['account_id'] for n in self.notices()});self.assertEqual(self.family.snapshot()['ownership_runs'],before)
 def test_stale_browser_cannot_replace_newer_accepted_current_pair(self):
  old=self.root/'old';self.f.retain(self.f.pair(2026,'2026-10-01'),old,self.now)
  self.accept(self.a);self.accept(self.a,[('old-aud.pdf',self.f.pdf('AUD',2025,'2026-06-30'))],existing=old)
  self.assertEqual(self.records.dates()[self.a],'2026-11-13');self.assertEqual(len(self.records.read()['accounts'][self.a]['files']),5)
 def test_statement_record_round_trip_in_dashboard_profile(self):
  from profile_archive import ProfileArchive
  with self.family.transaction() as d:d.pop('ownership_runs')
  self.accept(self.a);self.accept(self.a+':smsf');archive=ProfileArchive(self.config).save();target=self.root/'restored/config.cfg';target.parent.mkdir();ProfileArchive(target).load('profile.7z',archive)
  r=StatementRecords(target);self.assertEqual(r.dates(),self.records.dates());[r.verify(row) for row in r.read()['accounts'].values()]
 def test_tampered_saved_file_is_rejected_before_overlay(self):
  self.accept(self.a);row=self.records.read()['accounts'][self.a];(self.records.root/row['generation']/next(iter(row['files']))).write_bytes(b'tampered')
  with self.assertRaisesRegex(ValueError,'missing or changed'):self.records.overlay({},self.root/'restore',self.family.snapshot()['users'])
 def test_non_users_are_still_excluded_and_each_account_ages_independently(self):
  self.accept(self.a);self.accept(self.a+':smsf',self.f.pair(2026,'2026-11-01'))
  notices=self.notices();self.assertEqual(next(n['severity'] for n in notices if n['account_id']==self.a+':smsf'),'red');self.assertNotIn(self.a,{n['account_id'] for n in notices})
  with self.family.transaction() as d:d['bitaroo_accounts'][self.a+':smsf']=False
  self.assertNotIn(self.a+':smsf',{n['account_id'] for n in self.notices()})


class LegacyRetirement(unittest.TestCase):
 def fixture(self):
  import test_wallet_server10 as fixtures
  f=fixtures.RetiredLedgers();f.setUp();self.addCleanup(f.doCleanups)
  f.root.pop('dashboard_wallet');f.root.pop('dashboard_extinct')
  from contextlib import contextmanager
  @contextmanager
  def edit():yield f.state
  hub=SimpleNamespace(read=lambda:copy.deepcopy(f.state),edit=edit,foreground_active=lambda *a:False,registry=SimpleNamespace(diagnostic_log=SimpleNamespace(append=lambda *a:None)))
  f.service.registry.hub=hub
  return f,hub
 def test_exact_live_failure_missing_new_fields_is_migrated_and_traced_once(self):
  from retired_catalog import upgrade,reconcile
  from node_chain import configure
  from descriptor_chain import scan,HistoryClient,wallet_rows
  from worker import load_core
  from decimal import Decimal
  f,hub=self.fixture();old=copy.deepcopy(f.root['proposal']);upgrade(hub,[f.original,f.archive]);self.assertTrue(f.root['dashboard_extinct']);self.assertEqual(f.root['dashboard_wallet']['id'],f.original['id']);self.assertEqual(f.root['proposal'],old)
  fresh,aliases=reconcile([f.archive,f.core.wallets[1]],[f.original,f.archive],f.state);self.assertEqual(len(fresh),2)
  configure(f.core,{'wallets':fresh});snapshot=scan({'wallets':fresh},HistoryClient(None),lambda x:None);rows=wallet_rows(load_core(),snapshot);self.assertEqual(rows['First'][-1].balance,Decimal('.00039'))
 def test_offline_original_agent_does_not_prevent_background_reconstruction(self):
  from descriptor_store import DescriptorStore
  from descriptor_snapshot import history_ready
  f,hub=self.fixture();store=DescriptorStore(f.config);store.replace_node_wallets([f.original,f.archive,f.core.wallets[1]])
  f.nodes=f.nodes[1:];f.archive['node_sources']=[{'node_id':'node1','hostname':'remaining-node','wallet_name':'Extinct'}]
  f.cycle([f.archive,f.core.wallets[1]]);catalog=store.read();self.assertEqual(len(catalog['wallets']),2);self.assertTrue(history_ready(f.config,catalog));self.assertTrue(next(w for w in catalog['wallets'] if w['id']==f.original['id'])['extinct'])
 def test_reconnecting_old_copy_remains_one_retired_account(self):
  from retired_catalog import upgrade,reconcile
  f,hub=self.fixture();upgrade(hub,[f.original]);fresh,aliases=reconcile([f.archive,f.original,f.core.wallets[1]],[f.original],f.state);self.assertEqual(len(fresh),2);self.assertEqual(sum(w['id']==f.original['id'] for w in fresh),1)
 def test_explicit_scan_preflight_repairs_catalog_before_background_polling(self):
  from retired_catalog import prepare
  from descriptor_store import DescriptorStore
  from preferences import resource_id
  from node_chain import configure
  from descriptor_chain import scan,HistoryClient
  f,hub=self.fixture();store=DescriptorStore(f.config);store.replace_node_wallets([f.original,f.archive,f.core.wallets[1]])
  rid=resource_id('descriptor',f.original['id'])
  with FamilyStore(f.config).transaction() as data:data['ownership']=[{'id':rid,'kind':'descriptor','source':f.original['id'],'name':'Original account','owner_id':f.uid,'confirmed':True}]
  self.assertTrue(prepare(f.config,hub));catalog=store.read();self.assertEqual(len(catalog['wallets']),2);configure(f.core,catalog);self.assertEqual(len(scan(catalog,HistoryClient(None),lambda x:None)['wallets']),2);self.assertTrue(FamilyStore(f.config).snapshot()['ownership'][0]['confirmed']);self.assertFalse(prepare(f.config,hub))
 def test_migration_cannot_infer_extinction_without_verified_preservation(self):
  from retired_catalog import upgrade
  f,hub=self.fixture();f.root.pop('archive_checked');upgrade(hub,[f.original]);self.assertNotIn('dashboard_extinct',f.root);self.assertNotIn('dashboard_wallet',f.root)
 def test_migration_never_uses_name_match_or_rewrites_signed_policy(self):
  from retired_catalog import upgrade
  f,hub=self.fixture();wrong=copy.deepcopy(f.core.wallets[1]);wrong['id']=f.original['id'];wrong['name']=f.original['name'];upgrade(hub,[wrong]);self.assertNotIn('dashboard_wallet',f.root)
 def test_actual_persisted_agent_hub_accepts_legacy_metadata_migration(self):
  import test_build18 as fixtures
  from retired_catalog import upgrade
  f=fixtures.Retirement();f.setUp();self.addCleanup(f.doCleanups);key=f.delivered();f.preserve(key);before=copy.deepcopy(f.hub.read()['requests']);original=copy.deepcopy(before[key]['dashboard_wallet'])
  with f.hub.edit() as s:s['requests'][key].pop('dashboard_wallet');s['requests'][key].pop('dashboard_extinct')
  upgrade(f.hub,[original]);after=f.hub.read()['requests'];self.assertTrue(after[key]['dashboard_extinct']);self.assertEqual(after[key]['dashboard_wallet'],original)
  for ident,row in before.items():self.assertEqual(after[ident]['proposal'],row['proposal']);self.assertEqual(after[ident].get('result'),row.get('result'))

if __name__=='__main__':unittest.main()
