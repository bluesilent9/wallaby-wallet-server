"""Login and durable working-state recovery without creating templates."""
import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_build8 as fixtures
from builder_workspace import BuilderWorkspace
from launch_wallaby_wallet_server import Session
from transaction_templates import TemplateStore
from preferences import FamilyStore
from profile_archive import ProfileArchive

class Recovery(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.Setup();self.f.setUp();self.addCleanup(self.f.doCleanups);self.ws=BuilderWorkspace(self.f.config)
 def session(self):
  s=Session(Path(self.f.tmp.name)/'browser',self.f.config);s.node_registry=self.f.registry;self.addCleanup(s.close);return s
 def draft(self,kind):return {'name':'Unfinished wallet','type':'0','threshold':'1','count':'1','roles':[{'name':'New Wallet','node_id':self.f.a['node_id'],'storage':'node'}],'vault':{'date':'2027-01-01','zone':'Australia/Sydney','heightDraft':'1000100'}} if kind=='wallet' else {'draftId':'working','nodes':[{'id':'network-fee','x':123,'y':456}],'edges':[],'template':None}
 def start(self,kind):
  row=self.ws.start(self.f.user,kind);return self.ws.save(self.f.user,kind,dict(id=row['id'],revision=row['revision'],draft=self.draft(kind)))
 def test_transaction_login_resumes_working_state_without_template(self):
  row=self.start('transaction');before=TemplateStore(self.f.config).listing();s=self.session();data=s.select_user(self.f.user);self.assertEqual(data['login_page'],'balances');self.assertEqual(data['builders']['transaction']['workspace']['draft'],row['draft']);self.assertEqual(TemplateStore(self.f.config).listing(),before)
 def test_wallet_login_resumes_all_fields(self):
  row=self.start('wallet');data=self.session().select_user(self.f.user);self.assertEqual(data['login_page'],'balances');self.assertEqual(data['builders']['wallet']['workspace']['draft'],row['draft'])
 def linked(self):
  tx=self.start('transaction');w=self.start('wallet');state=self.ws.read();state['workspaces']['wallet']['renewal']={'transaction_workspace':tx['id'],'roles':[{'name':'New Wallet','node_id':self.f.a['node_id'],'storage':'node','node_locked':True}],'source':'original','target':'new'};self.ws.write(state);return tx,w
 def test_linked_refresh_after_restart_preserves_both_without_redirecting_login(self):
  tx,w=self.linked();before=self.ws.read();first=self.session();first.select_user(self.f.user);first.close();second=self.session();data=second.select_user(self.f.user);self.assertEqual(data['login_page'],'balances');self.assertEqual(self.ws.read(),before);self.assertEqual(data['builders']['transaction']['workspace']['draft'],tx['draft']);self.assertEqual(data['builders']['wallet']['workspace']['draft'],w['draft'])
 def test_other_user_login_is_not_forced_into_owner_builder(self):
  self.linked();store=FamilyStore(self.f.config);store.save_user('Other','green',revision=store.snapshot()['revision']);other=store.snapshot()['users'][-1]['id'];data=self.session().select_user(other);self.assertEqual(data['login_page'],'balances');self.assertTrue(data['builders']['wallet']['blocked']);self.assertNotIn('renewal',data['builders']['wallet']['workspace'])
 def test_resume_is_available_with_nodes_disconnected(self):
  self.linked()
  for c in list(self.f.registry.connections.values()):self.f.registry.heartbeat(c['token'],disconnect=True)
  data=self.session().select_user(self.f.user);self.assertEqual(data['login_page'],'balances');self.assertFalse(data['node_ready'])
 def test_unacknowledged_own_write_can_recover_latest_without_overwriting_other_tab(self):
  row=self.start('transaction');prior=copy.deepcopy(row);first={**row['draft'],'draftId':'first edit'};last={**row['draft'],'draftId':'last edit'};saved=self.ws.save(self.f.user,'transaction',dict(id=row['id'],revision=row['revision'],draft=first));recovery={'revision':prior['revision'],'draft':last,'sent':{'revision':prior['revision'],'draft':first}};result=self.ws.save(self.f.user,'transaction',dict(id=row['id'],revision=prior['revision'],draft=last,recovery=recovery));self.assertEqual(result['draft'],last)
  external={**last,'draftId':'other browser'};self.ws.save(self.f.user,'transaction',dict(id=row['id'],revision=result['revision'],draft=external))
  with self.assertRaises(ValueError):self.ws.save(self.f.user,'transaction',dict(id=row['id'],revision=prior['revision'],draft=last,recovery=recovery))
  self.assertEqual(self.ws.owned(self.f.user,'transaction')['draft'],external)
 def test_duplicate_acknowledgement_is_idempotent(self):
  row=self.start('wallet');result=self.ws.save(self.f.user,'wallet',dict(id=row['id'],revision=row['revision']-1,draft=row['draft']));self.assertEqual(result['revision'],row['revision'])
 def test_profile_preserves_initial_diagram_and_linked_refresh(self):
  self.linked();before=self.ws.read();archive=ProfileArchive(self.f.config).save();target=Path(self.f.tmp.name)/'restored/config.cfg';FamilyStore(target);ProfileArchive(target).load('profile.7z',archive);self.assertEqual(BuilderWorkspace(target).read(),before)
