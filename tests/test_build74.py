"""Current Agent combined-policy signer layouts, not only standalone wpkh keys."""
import copy,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_build72 as fixtures
from vault_refresh import signers,finish
from combined_signers import private_roles
from vendor.embit.descriptor import Descriptor

class Combined(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.Refresh();self.f.setUp();self.addCleanup(self.f.doCleanups);self.hub=self.f.hub;self.checks=self.f.checks;self.binding='a'*64;self.keys=[str(k) for k in Descriptor.from_string(self.f.f.wallet['raw']['descriptors'][0]['desc']).keys]
  roles=[{'id':'r'+str(i),'name':'Role '+str(i+1),'agent_key':'public identity '+str(i%2),'storage':'disc' if i>=3 else 'node'} for i in range(5)]
  self.setup={'state':'ready','policy_hash':self.binding,'proposal':{'cosigners':roles},'descriptors':[r['desc'] for r in self.f.f.wallet['raw']['descriptors']],'routes':{r['id']:list(self.f.accounts)[i%2] for i,r in enumerate(roles)},'contributions':{r['id']:{'message':{'receive_key':self.keys[i]}} for i,r in enumerate(roles)},'inventories':{}}
  self.originals=copy.deepcopy(self.f.accounts)
  for node,accounts in self.f.accounts.items():
   installation={};identity=None
   for a in accounts:
    i=int(a['name'].split()[-1])-1;role=roles[i];identity=role['agent_key'];old_name=a['name'];a['raw']=copy.deepcopy(self.f.f.wallet['raw']);a['raw']['wallet_name']='archive-key' if a.get('archive_id') else old_name
    if a.get('archive_id'):a['name']='Disc '+self.binding[:12]+' '+role['id']
    else:installation[role['id']]=old_name
   self.setup['inventories'][node]={'public_key':identity,'message':{'policy_hash':self.binding,'signing_wallets':installation}}
  self.read=patch.object(self.hub.wallet_builder,'read',return_value={'sessions':{'setup':self.setup}});self.read.start();self.addCleanup(self.read.stop)
  self.rpc_original=self.f.rpc
  def rpc(node,method,params=None,wallet=None,**kwargs):
   reply=self.rpc_original(node,method,params,wallet,**kwargs)
   if method=='getwalletinfo' and reply.get('state')=='succeeded' and reply['result'].get('wallaby_storage')=='disc':reply['result']['wallaby_policy_hash']=self.binding
   return reply
  self.f.hub.registry.rpc.call=rpc;self.f.scan()
 def state(self):return signers(self.hub,self.f.w)
 def unload(self):
  for node in self.f.accounts:self.f.accounts[node]=[a for a in self.f.accounts[node] if not a.get('archive_id')]
  self.f.scan()
 def test_three_node_signers_detected_with_discs_intentionally_unloaded(self):
  self.unload();s=self.state();self.assertEqual([r['detected'] for r in s['roles']],[True,True,True,False,False]);self.assertFalse(s['complete']);self.assertTrue(all(r['storage']=='node' for r in s['roles'][:3]));self.assertTrue(all(r['storage']=='' for r in s['roles'][3:]))
 def test_loaded_combined_disc_signers_complete_all_five_and_set_disc_storage(self):
  s=self.state();self.assertTrue(s['complete']);self.assertEqual([r['storage'] for r in s['roles']],['node','node','node','disc','disc'])
 def test_one_loaded_disc_is_not_mistaken_for_both_roles_on_same_policy(self):
  for node in self.f.accounts:self.f.accounts[node]=[a for a in self.f.accounts[node] if not a['name'].endswith(' r4')]
  self.f.scan();self.assertEqual([r['detected'] for r in self.state()['roles']],[True,True,True,True,False])
 def test_unloading_discs_removes_only_disc_roles(self):
  self.assertTrue(self.state()['complete']);self.unload();self.assertEqual(sum(r['detected'] for r in self.state()['roles']),3)
 def test_wrong_node_installation_signature_identity_cannot_identify_roles(self):
  for value in self.setup['inventories'].values():value['public_key']='different identity'
  self.assertFalse(any(r['detected'] for r in self.state()['roles'][:3]));self.assertTrue(all(r['detected'] for r in self.state()['roles'][3:]))
 def test_generic_private_multisig_monitor_cannot_impersonate_any_role(self):
  self.setup['inventories'].clear()
  for node,aa in self.f.accounts.items():
   for a in aa:
    if not a.get('archive_id'):a['name']='Other monitor';a['raw']['wallet_name']=a['name']
  self.f.scan();self.assertFalse(any(r['detected'] for r in self.state()['roles'][:3]))
 def test_wrong_archive_policy_metadata_does_not_use_alias_alone(self):
  for row in self.checks.rows.values():
   for a in row['wallets']:a['policy_hash']='b'*64
  self.assertFalse(any(r['detected'] for r in self.state()['roles'][3:]))
 def test_matching_disc_alias_requires_matching_public_policy(self):
  for row in self.checks.rows.values():
   for a in row['wallets']:a['raw']=self.originals[list(self.originals)[0]][0]['raw']
  self.assertFalse(any(r['detected'] for r in self.state()['roles'][3:]))
 def test_completed_rename_uses_verified_target_and_retains_role_identity(self):
  node=list(self.f.accounts)[0];a=next(a for a in self.f.accounts[node] if a['name']=='Role 1');a['name']='Renamed signer';a['raw']['wallet_name']=a['name'];self.f.scan();target={'node_id':node,'storage':'node','wallet':'Role 1','new_name':'Renamed signer','state':'complete','result':{'identity_verified':True,'new_wallet':'Renamed signer'}}
  with patch('wallet_renames.RenameQueue.read',return_value={'operations':{'op':{'sequence':1,'targets':{'one':target}}}}):self.assertTrue(self.state()['roles'][0]['detected'])
  self.assertFalse(self.state()['roles'][0]['detected'])
 def test_all_roles_still_required_before_handoff_and_state_is_not_recreated(self):
  before=self.f.work.read();self.unload()
  with self.assertRaisesRegex(ValueError,'Every existing signer'):finish(self.hub,self.f.f.user,1000100)
  self.assertEqual(self.f.work.read(),before)
  self.f.accounts=copy.deepcopy(self.originals);self.f.scan();self.assertTrue(self.state()['complete'])
