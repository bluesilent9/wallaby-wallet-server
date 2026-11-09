"""Login routes by actual shared ownership work, with no persisted run marker."""
import unittest,copy
import test_build73 as fixture
from preferences import FamilyStore
from ownership_workspace import save_workspace
from descriptor_store import DescriptorStore

class LoginHome(unittest.TestCase):
 def setUp(self):
  self.f=fixture.Recovery();self.f.setUp();self.addCleanup(self.f.doCleanups)
 def test_assigned_wallets_land_wallets_without_any_ownership_run(self):
  self.f.linked();data=self.f.session().select_user(self.f.f.user)
  self.assertEqual(data['login_page'],'balances');self.assertFalse(data['ownership_assignment_required']);self.assertNotIn('ownership_has_run',FamilyStore(self.f.f.config).snapshot());self.assertIsNotNone(data['builders']['wallet']['workspace'])
 def test_missing_owner_sends_all_users_to_ownership(self):
  store=FamilyStore(self.f.f.config)
  with store.transaction() as data:data['ownership'][0]['owner_id']=None
  store.save_user('Another user','blue',revision=store.snapshot()['revision']);other=store.snapshot()['users'][-1]['id']
  for uid in (self.f.f.user,other):
   result=self.f.session().select_user(uid);self.assertEqual(result['login_page'],'ownership');self.assertTrue(result['ownership_assignment_required'])
 def test_past_run_does_not_hide_a_current_missing_assignment(self):
  store=FamilyStore(self.f.f.config);save_workspace(self.f.f.config,self.f.f.user,{},[],{'entries':[]},{})
  with store.transaction() as data:data['ownership'][0]['confirmed']=False
  self.assertEqual(self.f.session().select_user(self.f.f.user)['login_page'],'ownership')
 def test_empty_system_goes_to_wallets_even_without_history(self):
  store=FamilyStore(self.f.f.config)
  with store.transaction() as data:data['ownership']=[]
  DescriptorStore(self.f.f.config).replace_node_wallets([],allow_empty=True)
  result=self.f.session().select_user(self.f.f.user);self.assertEqual(result['login_page'],'balances');self.assertFalse(result['ownership_assignment_required'])
 def test_other_users_saved_exchange_inventory_is_checked(self):
  store=FamilyStore(self.f.f.config);store.save_user('Another user','blue',revision=store.snapshot()['revision']);other=store.snapshot()['users'][-1]['id']
  save_workspace(self.f.f.config,other,{},[{'id':'exchange-test','kind':'exchange','source':'exchange-test','name':'Example Exchange'}],{'entries':[]},{})
  self.assertEqual(self.f.session().select_user(self.f.f.user)['login_page'],'ownership')
 def test_saved_work_survives_login_without_forcing_builder(self):
  tx,w=self.f.linked();before=self.f.ws.read();result=self.f.session().select_user(self.f.f.user)
  self.assertEqual(result['login_page'],'balances');self.assertEqual(self.f.ws.read(),before);self.assertEqual(result['builders']['transaction']['workspace']['draft'],tx['draft']);self.assertEqual(result['builders']['wallet']['workspace']['draft'],w['draft'])
