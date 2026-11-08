"""Proposed vault destinations are public, exact and separate from actual funds."""
import copy,unittest
import test_build72 as refresh_fixture
import test_build70 as address_fixture
import test_build11 as ceremony_fixture
from address_destinations import AddressDestinations
from builder_destinations import Destinations,public_rows
from builder_workspace import BuilderWorkspace
from vault_refresh import proposed,finish,cancel
from vendor.embit.descriptor import Descriptor
from vendor.embit.networks import NETWORKS

class RefreshPreview(unittest.TestCase):
 def setUp(self):
  self.f=refresh_fixture.Refresh();self.f.setUp();self.addCleanup(self.f.doCleanups);self.config=self.f.f.config;self.service=AddressDestinations(self.config)
  self.current=Descriptor.from_string(self.f.f.wallet['raw']['descriptors'][0]['desc']).derive(0).address(NETWORKS['main'])
  self.service.write({'version':1,'entries':{self.f.f.rid:{'id':self.f.f.rid,'kind':'descriptor','source':self.f.f.wallet['id'],'addresses':[{'address':self.current}],'address_history':[{'address':self.current}],'funded_addresses':[self.current],'current_height':999000}}})
  self.height(1000100)
 def height(self,height):
  row=self.f.work.owned(self.f.f.user,'wallet');draft=copy.deepcopy(row['draft']);draft['vault']={'result':{'height':height},'heightDraft':str(height)};self.f.work.save(self.f.f.user,'wallet',{'id':row['id'],'revision':row['revision'],'draft':draft})
 def entry(self):return self.service.overlay(None)['entries'][0]
 def test_preview_is_exact_policy_at_existing_reserved_index_without_rpc_or_writes(self):
  before=self.f.work.read();calls=list(self.f.calls);entry=self.entry();preview=entry['proposed_address'];index=self.f.dest['index'];rows=public_rows(self.f.f.wallet,1000100)
  self.assertEqual(preview['address'],Descriptor.from_string(rows[0]['desc']).derive(index).address(NETWORKS['main']));self.assertEqual(entry['addresses'][0]['address'],self.current);self.assertEqual(self.f.work.read(),before);self.assertEqual(self.f.calls,calls)
 def test_handoff_uses_the_exact_preview_and_preserves_signers_name_and_payment(self):
  preview=self.entry()['proposed_address'];before=copy.deepcopy(self.f.work.read()['workspaces']['transaction']['draft']);result=finish(self.f.hub,self.f.f.user,1000100);dest=Destinations(self.config).get(result['destination'])
  self.assertEqual(dest['address'],preview['address']);self.assertEqual(dest['index'],preview['index']);self.assertEqual(self.entry()['proposed_address']['address'],preview['address']);self.assertEqual(self.f.work.read()['workspaces']['transaction']['draft']['edges'][0]['amount_sats'],before['edges'][0]['amount_sats']);self.assertEqual(dest['source_wallet']['wallet_name'],'Logical vault')
 def test_height_change_changes_preview_and_cancel_removes_it(self):
  old=self.entry()['proposed_address'];self.height(1000200);new=self.entry()['proposed_address'];self.assertNotEqual(old['address'],new['address']);self.assertEqual(new['index'],old['index']);cached=self.service.overlay(None);cancel(self.f.hub,self.f.f.user);self.assertNotIn('proposed_address',self.service.overlay(cached)['entries'][0]);self.assertNotIn('proposed_address',self.entry());self.assertEqual(self.entry()['addresses'][0]['address'],self.current)
 def test_partial_height_edit_does_not_keep_obsolete_preview(self):
  row=self.f.work.owned(self.f.f.user,'wallet');draft=copy.deepcopy(row['draft']);draft['vault']['result']=None;self.f.work.save(self.f.f.user,'wallet',{'id':row['id'],'revision':row['revision'],'draft':draft});self.assertNotIn('proposed_address',self.entry())
 def test_profile_roundtrip_keeps_the_exact_proposed_destination(self):
  from profile_archive import ProfileArchive
  from preferences import FamilyStore
  from pathlib import Path
  preview=self.entry()['proposed_address'];target=Path(self.f.f.tmp.name)/'restored-preview/config.cfg';FamilyStore(target);ProfileArchive(target).load('profile.7z',ProfileArchive(self.config).save());restored=AddressDestinations(target).overlay(None)['entries'][0];self.assertEqual(restored['proposed_address']['address'],preview['address']);self.assertEqual(restored['proposed_address']['index'],preview['index'])
 def test_different_handoff_height_cannot_silently_replace_preview(self):
  with self.assertRaisesRegex(ValueError,'differs from the Address Book preview'):finish(self.f.hub,self.f.f.user,1000200)

class NewVaultPreview(unittest.TestCase):
 def test_new_build_waits_for_every_public_key_then_shows_the_agent_sample(self):
  f=ceremony_fixture.Ceremony();f.setUp();self.addCleanup(f.doCleanups);work=BuilderWorkspace(f.config);w=work.start(f.user,'wallet');ident,row=f.start(height=1000000)
  with f.setup.edit() as state:state['sessions'][ident]['workspace_id']=w['id']
  service=AddressDestinations(f.config);self.assertFalse(service.overlay(None)['entries']);row=f.contribute(ident,row);entries=service.overlay(None)['entries'];self.assertEqual(len(entries),1);entry=entries[0];self.assertTrue(entry['builder_preview']);self.assertEqual(entry['name'],row['proposal']['name']);self.assertEqual(entry['proposed_address']['address'],Descriptor.from_string(row['descriptors'][0]).derive(0).address(NETWORKS['main']));self.assertFalse(entry['can_generate'])
  cached=service.overlay(None)
  with f.setup.edit() as state:state['sessions'][ident]['state']='cancelled'
  self.assertFalse(service.overlay(cached)['entries']);self.assertFalse(service.overlay(None)['entries'])

class UnfundedColour(unittest.TestCase):
 def setUp(self):
  self.f=address_fixture.Addresses();self.f.setUp();self.addCleanup(self.f.doCleanups);self.old,self.new=self.f.vault()
 def entry(self):return self.f.service.overlay(None)['entries'][0]
 def test_green_until_first_confirmed_funding_and_does_not_return_after_emptying(self):
  self.f.service.refresh();self.assertTrue(self.entry()['addresses'][0]['new_vault_address']);address=self.f.address(self.new[0]);self.f.received=[{'address':address,'amount':'0.001','confirmations':1}];self.f.service.refresh();self.assertFalse(self.entry()['addresses'][0]['new_vault_address']);self.f.received=[];self.f.service.refresh();self.assertFalse(self.entry()['addresses'][0]['new_vault_address'])
 def test_expired_unfunded_address_is_not_green(self):
  rpc=self.f.rpc
  def advanced(node,method,params=None,wallet=None,**kw):
   if method=='getblockcount':return {'state':'succeeded','result':1000300}
   return rpc(node,method,params,wallet,**kw)
  self.f.f.registry.rpc.call=advanced;self.f.service.refresh();self.assertFalse(self.entry()['addresses'][0]['new_vault_address'])

class UnlabelledVault(unittest.TestCase):
 def test_confirmed_unlabelled_receiving_output_marks_vault_as_previously_funded(self):
  f=address_fixture.Addresses();f.setUp();self.addCleanup(f.doCleanups);old,new=f.vault();address=f.address(new[0]);f.utxos=[{'address':address,'amount':'0.001','confirmations':1,'parent_descs':[new[0]['desc']]}];f.service.refresh();entry=f.service.overlay(None)['entries'][0];self.assertFalse(entry['addresses'][0]['new_vault_address']);self.assertIn(address,entry['funded_addresses'])
 def test_change_output_never_replaces_or_marks_the_receiving_address(self):
  f=address_fixture.Addresses();f.setUp();self.addCleanup(f.doCleanups);old,new=f.vault();f.utxos=[{'address':f.address(new[1]),'amount':'0.001','confirmations':1,'parent_descs':[new[1]['desc']]}];f.service.refresh();entry=f.service.overlay(None)['entries'][0];self.assertEqual(entry['addresses'][0]['address'],f.address(new[0]));self.assertTrue(entry['addresses'][0]['new_vault_address']);self.assertNotIn(f.address(new[1]),entry['funded_addresses'])
 def test_old_funded_address_remains_current_when_latest_policy_is_unfunded(self):
  f=address_fixture.Addresses();f.setUp();self.addCleanup(f.doCleanups);old,new=f.vault();f.received=[{'address':f.address(old[0]),'amount':'0.001','confirmations':6}];f.service.refresh();entry=f.service.overlay(None)['entries'][0];self.assertTrue(entry['addresses'][0]['new_vault_address']);self.assertEqual(entry['current_vault_address'],f.address(old[0]))
