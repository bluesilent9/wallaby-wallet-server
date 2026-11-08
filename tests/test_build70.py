"""Read-only receiving selection, vault ordering, replica checks and profile cache."""
import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_build27 as fixtures
from address_destinations import AddressDestinations,receive
from descriptor_store import clean_wallet,DescriptorStore
from builder_destinations import public_rows,Destinations
from preferences import resource_id,FamilyStore
from vendor.embit.descriptor import Descriptor
from vendor.embit.networks import NETWORKS

class Addresses(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.DestinationsTest();self.f.setUp();self.addCleanup(self.f.doCleanups);self.calls=[];self.received=[];self.utxos=[];self.failed=set();self.rejected=set();self.raws={n:copy.deepcopy(self.f.wallet['raw']) for n in self.f.hub.inventories};self.install(self.f.wallet['raw'])
  self.f.registry.rpc.call=self.rpc;self.service=AddressDestinations(self.f.config,self.f.registry)
 def install(self,raw):
  w=clean_wallet(raw);w['node_sources']=[{'node_id':n,'hostname':'fixture','wallet_name':'node-wallet'} for n in self.f.hub.inventories];self.wallet=w;self.rid=resource_id('descriptor',w['id']);DescriptorStore(self.f.config).replace_node_wallets([w]);self.raws={n:copy.deepcopy(raw) for n in self.f.hub.inventories}
 def address(self,row,index=0):return Descriptor.from_string(row['desc']).derive(index).address(NETWORKS['main'])
 def rpc(self,node,method,params=None,wallet=None,**kw):
  self.calls.append((node,method,params,wallet,kw.get('priority')))
  if node in self.failed:return {'state':'error','error':{'message':'fixture unavailable'}}
  if method=='getblockcount':value=999000
  elif method=='listdescriptors':value=self.raws[node]
  elif method=='listreceivedbyaddress':value=self.received
  elif method=='listunspent':value=self.utxos
  elif method=='getaddressinfo':value={'address':params[0],'ismine':params[0] not in self.rejected,'ischange':False}
  else:raise AssertionError('Unexpected RPC '+method)
  return {'state':'succeeded','result':value}
 def test_generate_is_read_only_and_repeats_same_unused_address(self):
  a=self.service.generate(self.rid);b=self.service.generate(self.rid);self.assertEqual(a['address'],b['address']);self.assertEqual(a['index'],1);self.assertEqual(a['address'],self.address(self.wallet['raw']['descriptors'][0],1));self.assertEqual({c[1] for c in self.calls},{'getblockcount','listdescriptors','listreceivedbyaddress','getaddressinfo'});self.assertTrue(all(c[-1]==0 for c in self.calls));self.assertFalse(self.service.overlay(None)['entries'][0]['addresses'])
 def test_used_address_advances_without_reusing_paid_address(self):
  a=self.service.generate(self.rid);self.received=[{'address':a['address'],'amount':'0.001','confirmations':6}];b=self.service.generate(self.rid);self.assertEqual(b['index'],2);e=self.service.overlay(None)['entries'][0];self.assertEqual(e['addresses'][0]['address'],a['address']);self.assertIn(a['address'],e['confirmed_addresses'])
 def test_pending_receipt_is_not_confirmed_at_five_confirmations(self):
  a=self.service.generate(self.rid);self.received=[{'address':a['address'],'amount':'0.001','confirmations':5}];self.service.refresh();self.assertNotIn(a['address'],self.service.overlay(None)['entries'][0]['confirmed_addresses']);self.assertTrue(all(c[-1] in (0,100) for c in self.calls))
 def vault(self):
  original=copy.deepcopy(self.wallet);rows=public_rows(original,1000000);later=public_rows({'raw':{'descriptors':rows}},1000200);raw={'wallet_name':'Treasury Australia - Signer','descriptors':rows+later};self.install(raw);return rows,later
 def test_unfunded_furthest_vault_is_default_and_generate_is_rejected(self):
  old,new=self.vault();self.service.refresh(foreground=True);e=self.service.overlay(None)['entries'][0];self.assertEqual(e['addresses'][0]['address'],self.address(new[0]));self.assertEqual(e['addresses'][0]['vault_height'],1000200);self.assertEqual([r['vault_height'] for r in e['address_history']],[1000000,1000200]);self.assertFalse(e['can_generate']);self.assertIn(self.address(old[0]),[r['address'] for r in e['address_history']]);self.assertTrue(all(c[-1]==0 for c in self.calls))
  with self.assertRaisesRegex(ValueError,'unavailable for vault'):self.service.generate(self.rid)
 def test_exact_reserved_unfunded_refresh_address_is_selected(self):
  old,new=self.vault();Destinations(self.f.config).write({'version':1,'destinations':{'r':{'descriptors':new,'index':7,'height':1000200}}});self.service.refresh();e=self.service.overlay(None)['entries'][0];self.assertEqual(e['addresses'][0]['address'],self.address(new[0],7))
 def test_node_missing_new_policy_does_not_hide_policy_on_second_node(self):
  old,new=self.vault();self.raws[self.f.a['node_id']]['descriptors']=old;self.service.refresh();e=self.service.overlay(None)['entries'][0];self.assertEqual(e['addresses'][0]['vault_height'],1000200);self.assertEqual({n for n,m,*_ in self.calls if m=='listdescriptors'},set(self.raws))
 def test_failed_new_policy_source_retains_cached_latest_instead_of_older(self):
  old,new=self.vault();self.service.refresh();before=self.service.read()['entries'];self.raws[self.f.a['node_id']]['descriptors']=old;self.failed.add(self.f.b['node_id']);self.service.refresh();self.assertEqual(self.service.read()['entries'][self.rid]['addresses'],before[self.rid]['addresses']);self.assertIn('refresh_error',self.service.read()['entries'][self.rid])
 def test_uncorroborated_generated_address_is_rejected(self):
  self.rejected.add(self.address(self.wallet['raw']['descriptors'][0],1));
  with self.assertRaisesRegex(ValueError,'confirmed this receiving address'):self.service.generate(self.rid)
 def test_watch_replica_can_verify_without_private_keys_or_authorisation(self):
  self.failed.add(self.f.a['node_id']);self.assertTrue(self.service.generate(self.rid)['address']);self.assertFalse(self.f.hub.read()['requests'])
 def test_existing_builder_reservation_not_reused(self):
  row=self.wallet['raw']['descriptors'][0];reserved=self.address(row,0);Destinations(self.f.config).write({'version':1,'destinations':{'r':{'address':reserved}}});self.assertEqual(self.service.generate(self.rid)['index'],1)
 def test_inactive_change_descriptor_without_flag_is_not_receive(self):
  row=copy.deepcopy(self.wallet['raw']['descriptors'][1]);row.pop('internal');row['active']=False;self.assertFalse(receive(row));row=copy.deepcopy(self.wallet['raw']['descriptors'][0]);row.pop('internal');self.assertTrue(receive(row))
 def test_cache_and_vault_addresses_roundtrip_in_profile(self):
  from profile_archive import ProfileArchive
  self.vault();self.service.refresh();before=self.service.read();target=Path(self.f.tmp.name)/'restored/config.cfg';FamilyStore(target);ProfileArchive(target).load('profile.7z',ProfileArchive(self.f.config).save());self.assertEqual(AddressDestinations(target).read(),before)

 def test_unused_external_parent_wins_over_core_addressbook_change_flag(self):
  original=self.rpc
  def routed(node,method,params=None,wallet=None,**kwargs):
   result=original(node,method,params,wallet,**kwargs)
   if method=='getaddressinfo':result['result'].update(ischange=True,parent_desc=self.wallet['raw']['descriptors'][0]['desc'])
   return result
  self.f.registry.rpc.call=routed;self.assertTrue(self.service.generate(self.rid)['address'])


 def test_new_unknown_vault_policy_blocks_unrestricted_address_generation(self):
  extra=public_rows(self.wallet,1000000)
  for raw in self.raws.values():raw['descriptors']+=extra
  with self.assertRaisesRegex(ValueError,'new vault policy'):self.service.generate(self.rid)


class AddressEndpoints(unittest.TestCase):
 def test_refresh_and_generate_use_current_authenticated_session_without_builder_guard(self):
  import tempfile,threading,http.client
  from unittest.mock import patch
  from launch_wallaby_wallet_server import create_server
  with tempfile.TemporaryDirectory() as folder:
   cfg=Path(folder)/'config.cfg';family=FamilyStore(cfg);family.save_user('Example','green',revision=0);server,pool=create_server(Path(folder)/'browser',0,cfg);pool.nodes.health.closed=True;thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();session=pool.create();session.user_id=family.snapshot()['users'][0]['id'];session.access=lambda:{'ownership_available':True};session.family=lambda:{'address_book':{'entries':[]}}
   def post(path,body):
    c=http.client.HTTPConnection('::1',server.server_port,timeout=5);c.request('POST',path,json.dumps(body),{'X-Session-Token':session.token,'Content-Type':'application/json'});r=c.getresponse();value=json.loads(r.read());c.close();return r.status,value
   try:
    with patch('address_destinations.AddressDestinations') as factory:
     factory.return_value.refresh.side_effect=lambda **k:self.assertEqual(session.active_operations,1)
     factory.return_value.generate.return_value={'address':'fixture'}
     self.assertEqual(post('/api/addresses/refresh',{}),(200,{'address_book':{'entries':[]}}));factory.return_value.refresh.assert_called_once_with(foreground=True)
     self.assertEqual(post('/api/addresses/generate',{'resource':'wallet'}),(200,{'address':'fixture'}));factory.return_value.generate.assert_called_once_with('wallet');self.assertEqual(session.active_operations,0)
     session.access=lambda:{'ownership_available':False};self.assertEqual(post('/api/addresses/refresh',{})[0],400)
   finally:server.shutdown();server.server_close();thread.join(3)
