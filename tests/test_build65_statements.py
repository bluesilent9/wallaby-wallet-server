"""Family-wide statement notices and replace-not-append current FY inputs."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
from datetime import datetime,date,timezone
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bitaroo_freshness import warnings
from bitaroo_inputs import prepare
from transaction_workflows import WorkflowStore

class Statements(unittest.TestCase):
 def family(self):
  return {'users':[{'id':'a','name':'First'},{'id':'b','name':'Second'}],'bitaroo_accounts':{'a':True,'a:smsf':True,'b':False,'b:smsf':False},'ownership_runs':{uid:{'completed_utc':'2026-11-01T00:00:00Z','bitaroo_data':{'periods':{'2026-27':{'end':'2026-11-01'}}},'bitaroo_smsf_data':{'periods':{'2026-27':{'end':'2026-11-02'}}}} for uid in ('a','b')}}
 def test_seven_ten_day_boundaries_and_non_users_excluded(self):
  f=self.family();self.assertEqual(warnings(f,'2026-11-07'),[]);r=warnings(f,'2026-11-08');self.assertEqual(len(r),1);self.assertEqual(r[0]['severity'],'yellow');self.assertFalse(r[0]['dismissible']);r=warnings(f,'2026-11-10');self.assertEqual([n['severity'] for n in r],['yellow','yellow']);r=warnings(f,'2026-11-11');self.assertEqual([n['severity'] for n in r],['red','yellow']);self.assertEqual([n['account_id'] for n in r],['a','a:smsf'])
 def test_local_day_conversion_for_utc_statement_ending(self):
  f=self.family();self.assertEqual(warnings(f,'2026-11-08','Australia/Sydney'),[]);self.assertEqual(warnings(f,'2026-11-09','Australia/Sydney')[0]['age_days'],7)
 def test_every_declared_account_included_for_other_viewer_and_fresh_run_does_not_hide_old_pdf(self):
  f=self.family();f['ownership_runs']['a']['completed_utc']='2026-11-20T00:00:00Z'
  with tempfile.TemporaryDirectory() as tmp:
   store=WorkflowStore(Path(tmp)/'config.cfg');store.sync_bitaroo_warnings('b',f,'2026-11-20','UTC','salary');n=store.notifications('b');self.assertEqual(n['unread_count'],2);self.assertTrue(all('First' in r['text'] for r in n['notifications']))
 def test_read_on_three_pages_but_unread_elsewhere_and_not_dismissible(self):
  for page,read in [('salary',False),('balances',True),('vaults',True),('notifications',True),('ownership',False)]:
   with self.subTest(page=page),tempfile.TemporaryDirectory() as tmp:
    store=WorkflowStore(Path(tmp)/'config.cfg');store.sync_bitaroo_warnings('viewer',self.family(),'2026-11-11','UTC',page);n=store.notifications('viewer')['notifications'][0];self.assertEqual(n['read'],read)
    with self.assertRaisesRegex(ValueError,'records'):store.update_notifications('viewer',n['id'])
 def test_red_replaces_yellow_and_ignores_old_dismissals(self):
  f=self.family();f['bitaroo_accounts']['a:smsf']=False
  with tempfile.TemporaryDirectory() as tmp:
   store=WorkflowStore(Path(tmp)/'config.cfg');store._write({'jobs':{},'notices':{},'dismissed_bitaroo_warnings':{'viewer':'2026-11-01'}});store.sync_bitaroo_warnings('viewer',f,'2026-11-08','UTC','salary');one=store.notifications('viewer')['notifications'][0];self.assertEqual(one['severity'],'yellow');store.sync_bitaroo_warnings('viewer',f,'2026-11-08','UTC','vaults');self.assertEqual(store.notifications('viewer')['unread_count'],0);store.sync_bitaroo_warnings('viewer',f,'2026-11-11','UTC','salary');rows=store.notifications('viewer')['notifications'];self.assertEqual(len(rows),1);self.assertEqual(rows[0]['id'],one['id']);self.assertEqual(rows[0]['severity'],'red');self.assertFalse(rows[0]['read']);self.assertNotIn('dismissed_bitaroo_warnings',store._read())
 def test_current_upload_clears_only_updated_account_and_non_user_toggle_clears_notice(self):
  f=self.family()
  with tempfile.TemporaryDirectory() as tmp:
   store=WorkflowStore(Path(tmp)/'config.cfg');store.sync_bitaroo_warnings('viewer',f,'2026-11-20','UTC','salary');f['ownership_runs']['a']['bitaroo_data']['periods']['2026-27']['end']='2026-11-20';store.sync_bitaroo_warnings('viewer',f,'2026-11-20','UTC','salary');self.assertEqual([n['account_id'] for n in store.notifications('viewer')['notifications']],['a:smsf']);f['bitaroo_accounts']['a:smsf']=False;store.sync_bitaroo_warnings('viewer',f,'2026-11-20','UTC','salary');self.assertEqual(store.notifications('viewer')['notifications'],[])
 def test_missing_dates_are_not_invented_and_personal_smsf_declared_separately(self):
  f=self.family();f['ownership_runs']['a']['bitaroo_data']={};f['ownership_runs']['a']['bitaroo_smsf_data']={};self.assertEqual(warnings(f,'2026-11-20'),[])
 def test_settings_declared_non_user_is_not_checked_when_no_account_map(self):
  f=self.family();f.pop('bitaroo_accounts');f['ownership_runs']['a']['settings']={'non_bitaroo':['a','b'],'non_bitaroo_smsf':['a','b']};self.assertEqual(warnings(f,'2026-11-20'),[])
 def test_ownership_age_notice_does_not_remove_statement_warning(self):
  from unittest.mock import patch
  f=self.family()
  with tempfile.TemporaryDirectory() as tmp:
   store=WorkflowStore(Path(tmp)/'config.cfg');store.sync_bitaroo_warnings('viewer',f,'2026-11-20','UTC','salary')
   with patch('run_freshness.warning',return_value=None):store.sync_run_warning('viewer','2026-11-20','UTC','balances')
   self.assertEqual(len(store.notifications('viewer')['notifications']),2)

class Replacement(unittest.TestCase):
 def core(self):
  def inspect(path):
   d=json.loads(Path(path).read_text());return d['side'],2026,date(2026,7,1),date.fromisoformat(d['end'])
  return SimpleNamespace(inspect_bitaroo_statement=inspect)
 def file(self,root,name,side,end,records):
  p=root/name;p.write_text(json.dumps({'side':side,'end':end,'records':records}));return p
 def test_old_and_updated_pair_select_one_copy_per_asset_without_duplicate_overlap(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'input';root.mkdir();dest=Path(tmp)/'selected'
   for side in ('AUD','BTC'):
    self.file(root,'old-'+side+'.pdf',side,'2026-10-01',[1,2]);self.file(root,'updated-'+side+'.pdf',side,'2026-11-06',[1,2,3,3]);self.file(root,'duplicate-'+side+'.pdf',side,'2026-11-06',[1,2,3,3])
   coverage=prepare(self.core(),{'bitaroo':root},dest,'UTC',datetime(2026,11,6,tzinfo=timezone.utc));self.assertEqual(coverage['bitaroo_as_of_date'],'2026-11-06');self.assertEqual(len(list(dest.glob('*.pdf'))),2)
   for p in dest.glob('*.pdf'):self.assertEqual(json.loads(p.read_text())['records'],[1,2,3,3],'old overlap is not appended and genuinely repeated rows are retained')
 def test_only_new_pair_can_be_added_while_saved_historical_files_remain(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'input';root.mkdir();dest=Path(tmp)/'selected'
   for side in ('AUD','BTC'):self.file(root,side+'.pdf',side,'2026-10-01',[1,2])
   prepare(self.core(),{'bitaroo':root},dest,'UTC',datetime(2026,11,6,tzinfo=timezone.utc))
   for side in ('AUD','BTC'):self.file(root,side+'.pdf',side,'2026-11-06',[1,2,3])
   prepare(self.core(),{'bitaroo':root},dest,'UTC',datetime(2026,11,6,tzinfo=timezone.utc));self.assertEqual(json.loads((dest/'Bitaroo_BTC_2026-2027.pdf').read_text())['records'],[1,2,3])
 def test_conflicting_same_period_is_not_silently_combined(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'input';root.mkdir()
   for side in ('AUD','BTC'):self.file(root,side+'.pdf',side,'2026-11-06',[1,2])
   self.file(root,'conflicting.pdf','BTC','2026-11-06',[9])
   with self.assertRaisesRegex(ValueError,'Conflicting'):prepare(self.core(),{'bitaroo':root},Path(tmp)/'selected','UTC',datetime(2026,11,6,tzinfo=timezone.utc))

class NoticeHTTP(unittest.TestCase):
 def test_family_warning_read_and_delete_rules_through_actual_browser_api(self):
  import http.client,threading
  from preferences import FamilyStore
  from launch_wallaby_wallet_server import create_server
  with tempfile.TemporaryDirectory() as tmp:
   config=Path(tmp)/'config.cfg';store=FamilyStore(config);store.save_user('Viewer','green',revision=0);uid=store.snapshot()['users'][0]['id'];store.save_user('Other account','blue',revision=store.snapshot()['revision']);other=store.snapshot()['users'][1]['id']
   with store.transaction() as family:
    family['bitaroo_accounts']={uid:False,uid+':smsf':False,other:True,other+':smsf':False};family['ownership_runs']={other:{'bitaroo_data':{'periods':{'2026-27':{'end':'2026-10-01'}}}}}
   server,sessions=create_server(Path(tmp)/'cache',0,config);sessions.nodes.health.closed=True;t=threading.Thread(target=server.serve_forever,daemon=True);t.start();session=sessions.create();session.user_id=uid
   def request(method,path,body=None):
    c=http.client.HTTPConnection('::1',server.server_port,timeout=5);c.request(method,path,json.dumps(body) if body is not None else None,{'X-Session-Token':session.token,'Content-Type':'application/json'});r=c.getresponse();data=json.loads(r.read());c.close();return r.status,data
   try:
    code,data=request('GET','/api/notifications?local_date=2026-11-06&timezone=UTC&page=salary');self.assertEqual(code,200);n=next(n for n in data['notifications'] if n['kind']=='bitaroo_warning');self.assertFalse(n['read']);self.assertEqual(n['severity'],'red');self.assertIn('Other account',n['text']);self.assertEqual(request('POST','/api/notifications/delete',{'id':n['id']})[0],400)
    code,data=request('GET','/api/notifications?local_date=2026-11-06&timezone=UTC&page=vaults');self.assertEqual(code,200);self.assertTrue(next(n for n in data['notifications'] if n['kind']=='bitaroo_warning')['read']);self.assertEqual(data['unread_count'],0)
   finally:server.shutdown();server.server_close();t.join(3)

class UploadBatch(unittest.TestCase):
 def core(self):
  def inspect(path):
   d=json.loads(Path(path).read_text());y=d['fy'];return d['side'],y,date(y,7,1),date.fromisoformat(d['end'])
  return SimpleNamespace(inspect_bitaroo_statement=inspect)
 def pdf(self,side,fy,end,records=None):return json.dumps({'side':side,'fy':fy,'end':end,'records':records or [1,2]}).encode()
 def pair(self,fy,end):return [(side+'.pdf',self.pdf(side,fy,end)) for side in ('AUD','BTC')]
 def retain(self,files,root,now=None):
  from bitaroo_upload import retain
  return retain(self.core(),files,root if root.exists() else None,root,'Australia/Sydney',now or datetime(2026,11,6,tzinfo=timezone.utc))
 def test_current_single_refused_even_with_saved_counterpart_and_files_discarded(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'saved';self.retain(self.pair(2026,'2026-10-01'),root);before={p.name:p.read_bytes() for p in root.iterdir()}
   for side in ('AUD','BTC'):
    with self.assertRaisesRegex(ValueError,'together'):self.retain([(side+'.pdf',self.pdf(side,2026,'2026-11-06'))],root)
    self.assertEqual({p.name:p.read_bytes() for p in root.iterdir()},before);self.assertEqual(list(Path(tmp).iterdir()),[root])
 def test_all_years_in_one_package_duplicate_upload_idempotent_no_overlap_in_processing(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'saved';files=self.pair(2024,'2025-06-30')+self.pair(2025,'2026-06-30')+self.pair(2026,'2026-10-01')+[(s+'-new.pdf',self.pdf(s,2026,'2026-11-06')) for s in ('AUD','BTC')]
   self.retain(files,root);self.retain(files,root);self.assertEqual(len(list(root.iterdir())),8)
   dest=Path(tmp)/'effective';prepare(self.core(),{'bitaroo':root},dest,'Australia/Sydney',datetime(2026,11,6,tzinfo=timezone.utc));self.assertEqual(len(list(dest.iterdir())),6);self.assertEqual(json.loads((dest/'Bitaroo_BTC_2026-2027.pdf').read_text())['end'],'2026-11-06')
 def test_missing_historical_asset_can_be_added_alone_without_losing_current(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'saved';self.retain(self.pair(2026,'2026-11-06')+[('historical-aud.pdf',self.pdf('AUD',2025,'2026-06-30'))],root);self.retain([('historical-btc.pdf',self.pdf('BTC',2025,'2026-06-30'))],root);self.assertEqual(len(list(root.iterdir())),4)
   dest=Path(tmp)/'effective';prepare(self.core(),{'bitaroo':root},dest,'UTC',datetime(2026,11,6,tzinfo=timezone.utc));self.assertEqual(len(list(dest.iterdir())),4)
 def test_historical_existing_single_cannot_replace_saved_data(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'saved';self.retain(self.pair(2025,'2026-06-30'),root)
   with self.assertRaisesRegex(ValueError,'single historical'):self.retain([('changed.pdf',self.pdf('BTC',2025,'2026-06-30',[99]))],root)
 def test_july_first_previous_day_pair_accepted_as_current_not_older_year(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'saved';now=datetime(2026,6,30,16,tzinfo=timezone.utc);self.retain(self.pair(2025,'2026-06-30'),root,now);dest=Path(tmp)/'effective';self.assertTrue(prepare(self.core(),{'bitaroo':root},dest,'Australia/Sydney',now)['current_optional'])
   with self.assertRaisesRegex(ValueError,'together'):self.retain([('only.pdf',self.pdf('BTC',2025,'2026-06-30'))],root,now)
   with self.assertRaisesRegex(ValueError,'current financial'):prepare(self.core(),{'bitaroo':root},dest,'Australia/Sydney',datetime(2026,7,1,16,tzinfo=timezone.utc))
 def test_malformed_or_conflicting_member_discards_entire_batch(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'saved';self.retain(self.pair(2026,'2026-10-01'),root);before={p.name:p.read_bytes() for p in root.iterdir()}
   for extra in [('bad.pdf',b'bad'),('conflict.pdf',self.pdf('BTC',2026,'2026-11-06',[999]))]:
    with self.assertRaises((ValueError,json.JSONDecodeError)):self.retain(self.pair(2026,'2026-11-06')+[extra],root)
    self.assertEqual({p.name:p.read_bytes() for p in root.iterdir()},before)
 def test_multipart_preserves_files_and_rejects_path_escape(self):
  from bitaroo_upload import multipart
  def body(name):return b'--test\r\nContent-Disposition: form-data; name="files"; filename="'+name+b'"\r\nContent-Type: application/pdf\r\n\r\nhello\r\n--test--\r\n'
  self.assertEqual(multipart('multipart/form-data; boundary=test',body(b'a.pdf')),[('a.pdf',b'hello')])
  with self.assertRaisesRegex(ValueError,'PDF'):multipart('multipart/form-data; boundary=test',body(b'../a.pdf'))

class BatchHTTP(unittest.TestCase):
 def test_rejected_batch_preserves_saved_session_and_report_then_accepts_all_years(self):
  import http.client,threading
  from unittest.mock import patch
  from preferences import FamilyStore
  from launch_wallaby_wallet_server import create_server
  fixture=UploadBatch()
  with tempfile.TemporaryDirectory() as tmp:
   config=Path(tmp)/'config.cfg';store=FamilyStore(config);store.save_user('Example','green',revision=0);uid=store.snapshot()['users'][0]['id'];slot='bitaroo_user_'+uid
   server,sessions=create_server(Path(tmp)/'cache',0,config);sessions.nodes.health.closed=True;t=threading.Thread(target=server.serve_forever,daemon=True);t.start();session=sessions.create();session.user_id=uid
   def request(files):
    body=b''
    for name,data in files:body+=b'--test\r\nContent-Disposition: form-data; name="files"; filename="'+name.encode()+b'"\r\nContent-Type: application/pdf\r\n\r\n'+data+b'\r\n'
    body+=b'--test--\r\n';c=http.client.HTTPConnection('::1',server.server_port,timeout=5);c.request('POST','/api/statements/upload/'+slot+'?timezone=Australia/Sydney',body,{'X-Session-Token':session.token,'Content-Type':'multipart/form-data; boundary=test'});r=c.getresponse();result=(r.status,json.loads(r.read()));c.close();return result
   try:
    import tax_core_v107
    with patch.object(tax_core_v107,'inspect_bitaroo_statement',fixture.core().inspect_bitaroo_statement),patch.object(tax_core_v107,'PdfReader',create=True) as reader:
     # The parser fixture is JSON; expose its text for metadata-independent identity.
     reader.side_effect=lambda p:SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda **kw:Path(p).read_text())])
     self.assertEqual(request(fixture.pair(2026,'2026-10-01'))[0],200);session.report={'saved':'report'};session.inventory_ready=True;before={p.name:p.read_bytes() for p in session.uploads[slot].iterdir()}
     code,data=request([('only.pdf',fixture.pdf('BTC',2026,'2026-11-06'))]);self.assertEqual(code,400);self.assertIn('together',data['error']);self.assertEqual(session.report,{'saved':'report'});self.assertTrue(session.inventory_ready);self.assertEqual({p.name:p.read_bytes() for p in session.uploads[slot].iterdir()},before)
     self.assertEqual(request(fixture.pair(2025,'2026-06-30')+fixture.pair(2026,'2026-11-06'))[0],200);self.assertFalse(session.inventory_ready);self.assertIsNone(session.report);self.assertEqual(len(list(session.uploads[slot].iterdir())),6)
   finally:server.shutdown();server.server_close();t.join(3)

class PDFIdentity(unittest.TestCase):
 def test_identical_public_text_with_different_pdf_metadata_is_not_a_duplicate_or_conflict(self):
  from bitaroo_upload import retain
  fixture=UploadBatch();core=fixture.core()
  # Metadata differs, while extracted public statement text is unchanged.
  core.PdfReader=lambda p:SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda **kw:json.dumps({k:v for k,v in json.loads(Path(p).read_text()).items() if k!='metadata'},sort_keys=True))])
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'saved';files=fixture.pair(2026,'2026-11-06');retain(core,files,None,root,'UTC',datetime(2026,11,6,tzinfo=timezone.utc));changed=[]
   for name,body in files:
    value=json.loads(body);value['metadata']='new export';changed.append((name,json.dumps(value).encode()))
   result=retain(core,changed,root,root,'UTC',datetime(2026,11,6,tzinfo=timezone.utc));self.assertEqual(result['retained'],2);self.assertEqual(len(list(root.iterdir())),2)
