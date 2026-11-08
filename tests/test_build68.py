"""Logical renewal names, unchanged Core routes, and quiet local-date correction."""
import copy,sys,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vault_estimator import future_day,from_nodes
from preferences import FamilyStore,resource_id
from descriptor_store import DescriptorStore,clean_wallet
from vault_refresh import start
from refresh_handoff_fixture import finish
from builder_destinations import Destinations

class Dates(unittest.TestCase):
 def test_today_and_previous_dates_become_tomorrow_in_selected_local_zone(self):
  now=datetime(2026,12,31,14,30,tzinfo=timezone.utc)
  for value in ('2026-01-01','2026-12-31','2027-01-01'):
   self.assertEqual(future_day(value,'Australia/Sydney',now),'2027-01-02')
  self.assertEqual(future_day('2026-12-31','UTC',now),'2027-01-01');self.assertEqual(future_day('2027-02-01','Australia/Sydney',now),'2027-02-01')
 def test_local_leap_day_and_dst_calendar_transition(self):
  self.assertEqual(future_day('2028-02-28','UTC',datetime(2028,2,28,tzinfo=timezone.utc)),'2028-02-29')
  self.assertEqual(future_day('2026-10-04','Australia/Sydney',datetime(2026,10,3,16,tzinfo=timezone.utc)),'2026-10-05')
 def test_past_date_is_corrected_before_node_estimation(self):
  rpc=type('RPC',(),{'nodes':lambda s:[{'id':'1','hostname':'Fixture'}],'call':lambda *a:{'chain':'main','blocks':974000,'headers':974000,'initialblockdownload':False}})()
  with patch('node_chain.RegistryRPC',return_value=rpc):
   result=from_nodes(None,'2020-01-01','Australia/Sydney',datetime(2026,12,31,14,30,tzinfo=timezone.utc))
  self.assertEqual(result['target_date'],'2027-01-02');self.assertGreater(result['height'],974000)
 def test_identical_errors_from_multiple_nodes_are_not_repeated(self):
  rpc=type('RPC',(),{'nodes':lambda s:[{'id':str(i),'hostname':'Fixture'} for i in range(3)],'call':lambda *a:{'chain':'regtest'}})()
  with patch('node_chain.RegistryRPC',return_value=rpc),self.assertRaises(ValueError) as error:from_nodes(None,'2027-01-01','UTC',datetime(2026,11,6,tzinfo=timezone.utc))
  self.assertEqual(str(error.exception).count('Wait for a mainnet node'),1)

class RefreshNames(unittest.TestCase):
 def fixture(self):
  from test_build27 import DestinationsTest
  f=DestinationsTest();f.setUp();self.addCleanup(f.doCleanups)
  raw=copy.deepcopy(f.wallet['raw']);raw['wallet_name']='Treasury Node Australia - Signer';f.wallet=clean_wallet(raw);f.wallet['setup_name']='Treasury';f.rid=resource_id('descriptor',f.wallet['id']);self.publish(f)
  return f
 def publish(self,f):
  f.wallet['node_sources']=[{'node_id':n,'hostname':'fixture','wallet_name':'Treasury Node '+('Australia' if n==f.a['node_id'] else 'Russia')+' - Signer'} for n in f.hub.inventories]
  DescriptorStore(f.config).replace_node_wallets([f.wallet])
  with FamilyStore(f.config).transaction() as state:
   state['ownership']=[{'id':f.rid,'kind':'descriptor','source':f.wallet['id'],'name':'Treasury','owner_id':f.user,'external':False,'smsf':False,'confirmed':True}]
  for node,inv in f.hub.inventories.items():
   name='Treasury Node '+('Australia' if node==f.a['node_id'] else 'Russia')+' - Signer';raw=copy.deepcopy(f.wallet['raw']);raw['wallet_name']=name;inv['wallets']=[dict(f.node_wallet,name=name,raw=raw,private_keys_enabled=True)]
 def test_two_refreshes_keep_one_logical_name_and_original_agent_names(self):
  from wallet_names import display_summary
  f=self.fixture();original_sessions=copy.deepcopy(f.hub.wallet_builder.read()['sessions'])
  for height in (1000100,1000200):
   work,d=f.transaction();start(f.hub,f.user,f.rid,d['id']);self.assertEqual(work.owned(f.user,'wallet')['draft']['name'],'Treasury');f.confirm_signers();result=finish(f.hub,f.user,height);requests=[r for r in f.hub.read()['requests'].values() if r.get('destination_id')==result['destination']]
   self.assertTrue(requests)
   for request in requests:
    expected=next(w['name'] for w in f.hub.inventories[request['node_id']]['wallets']);self.assertEqual(request['proposal']['wallet'],expected);self.assertEqual(request['proposal']['wallet'].count(' - Signer'),1);self.assertEqual(request['kind'],'wallet_policy_refresh')
   self.assertEqual(f.hub.wallet_builder.read()['sessions'],original_sessions,'renewal does not create a new signing ceremony')
   dest=Destinations(f.config).get(result['destination']);raw=copy.deepcopy(f.wallet['raw']);raw['descriptors'].extend(dest['descriptors']);f.wallet=clean_wallet(raw);f.wallet['setup_name']='Treasury';f.rid=resource_id('descriptor',f.wallet['id']);self.publish(f);work.finish(f.user,'transaction')
   summary=display_summary(DescriptorStore(f.config).summary(),FamilyStore(f.config).snapshot());self.assertEqual([w['name'] for w in summary['wallets']],['Treasury']);self.assertEqual(len(summary['wallets']),1)
 def test_explicit_dashboard_rename_takes_precedence_over_setup_name(self):
  f=self.fixture()
  with FamilyStore(f.config).transaction() as state:state['ownership'][0]['dashboard_name']='Family Treasury'
  work,d=f.transaction();start(f.hub,f.user,f.rid,d['id']);self.assertEqual(work.owned(f.user,'wallet')['draft']['name'],'Family Treasury')

 def restore_profile(self,f):
  from profile_archive import ProfileArchive
  target=Path(f.tmp.name)/'restored/config.cfg';FamilyStore(target)
  ProfileArchive(target).load('profile.7z',ProfileArchive(f.config).save())
  return target
 def test_profile_restores_in_progress_refresh_with_original_policy_and_routes(self):
  from builder_workspace import BuilderWorkspace
  f=self.fixture();work,d=f.transaction();start(f.hub,f.user,f.rid,d['id'])
  before=work.read();target=self.restore_profile(f)
  self.assertEqual(BuilderWorkspace(target).read(),before)
  self.assertEqual(DescriptorStore(target).read(),DescriptorStore(f.config).read())
  self.assertEqual(Destinations(target).read(),Destinations(f.config).read())
  self.assertEqual(FamilyStore(target).snapshot()['ownership'],FamilyStore(f.config).snapshot()['ownership'])
 def test_profile_restores_prepared_refresh_policy_requests_and_transaction_link(self):
  import json
  from builder_workspace import BuilderWorkspace
  f=self.fixture();work,d=f.transaction();start(f.hub,f.user,f.rid,d['id']);f.confirm_signers();result=finish(f.hub,f.user,1000100)
  before=work.read();target=self.restore_profile(f)
  self.assertEqual(BuilderWorkspace(target).read(),before)
  self.assertEqual(Destinations(target).read(),Destinations(f.config).read())
  restored=json.loads((target.parent/'data/agent-hub.json').read_text())
  self.assertEqual(restored['requests'],f.hub.read()['requests'])
  dest=Destinations(target).get(result['destination']);self.assertEqual(dest['height'],1000100)
  self.assertTrue(all('after(1000100)' in r['desc'] for r in dest['descriptors']))
