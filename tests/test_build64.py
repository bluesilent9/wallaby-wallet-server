"""Automatic-broadcast negotiation and ownership/history separation."""
import sys,copy,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from test_build8 import Setup
from agent_transactions import queue_sign,queue_broadcast,signing_state
from signed_psbt import final_transaction
from launch_wallaby_wallet_server import Session
from descriptor_store import DescriptorStore,clean_wallet

class AutomaticBroadcast(Setup):
 def signed_job(self):
  ident=self.job();session=SimpleNamespace(user_id=self.user);self.hub.caps[self.a['node_id']]={'partial_signing','automatic_broadcast_v1'};q=queue_sign(self.hub,session,ident,self.rid,self.a['node_id']);self.exchange(self.a,[self.item('partial_sign_result',{'request_hash':q['request_hash'],'status':'signed','psbt':self.signed})],caps=['partial_signing','automatic_broadcast_v1']);return ident,session
 def test_old_broadcast_capability_cannot_reintroduce_second_approval(self):
  ident,session=self.signed_job();self.hub.caps[self.a['node_id']]={'broadcast'}
  self.assertEqual(signing_state(self.hub,self.user,ident)['broadcast_nodes'],[])
  with self.assertRaisesRegex(ValueError,'automatic broadcast'):queue_broadcast(self.hub,session,ident,self.a['node_id'])
 def test_unchanged_proposal_automatic_result_and_idle_refresh_trigger(self):
  ident,session=self.signed_job();q=queue_broadcast(self.hub,session,ident,self.a['node_id']);proposal=self.hub.read()['requests'][q['request_hash']]['proposal'];self.assertEqual(proposal['kind'],'broadcast_transaction');self.assertNotIn('require_local_authorisation',proposal)
  out=self.exchange(self.a,caps=['automatic_broadcast_v1']);self.assertIn(proposal,out['proposals']);reset=[];self.registry.history_changed=lambda:reset.append(True)
  result=self.item('broadcast_result',{'request_hash':q['request_hash'],'status':'broadcast','txid':q['txid']})
  with patch.object(self.hub,'rpc',return_value=final_transaction(proposal['psbt']).serialize().hex()):self.exchange(self.a,[result],caps=['automatic_broadcast_v1'])
  self.assertTrue(reset);self.assertEqual(signing_state(self.hub,self.user,ident)['broadcast_txid'],q['txid']);self.assertEqual(self.hub.read()['requests'][q['request_hash']]['state'],'complete')

 def test_explicit_retry_after_error_has_new_identity_same_signed_transaction(self):
  ident,session=self.signed_job();first=queue_broadcast(self.hub,session,ident,self.a['node_id']);same=queue_broadcast(self.hub,session,ident,self.a['node_id']);self.assertEqual(first,same)
  self.exchange(self.a,[self.item('broadcast_result',{'request_hash':first['request_hash'],'status':'error','message':'Core temporarily unavailable'})],caps=['automatic_broadcast_v1'])
  second=queue_broadcast(self.hub,session,ident,self.a['node_id']);self.assertNotEqual(first['request_hash'],second['request_hash']);self.assertEqual(first['txid'],second['txid']);requests=self.hub.read()['requests'];self.assertEqual(requests[first['request_hash']]['state'],'error');self.assertEqual(requests[second['request_hash']]['state'],'pending');self.assertEqual(signing_state(self.hub,self.user,ident)['broadcast_request']['state'],'pending')

class OwnershipHistory(Setup):
 def session(self):
  s=Session(Path(self.tmp.name)/'browser',self.config);self.addCleanup(s.close);s.node_registry=self.registry;s.user_id=self.user;s.sync_workspace=lambda data:None;s.inventory_ready=True;s.inventory=[{'id':self.rid,'kind':'descriptor','source':self.wallet['id'],'name':'Example Wallet'}];return s
 def test_known_assigned_wallets_are_history_refresh_not_new_ownership(self):
  s=self.session();access=s.access();self.assertTrue(access['ownership_assignments_ready']);self.assertTrue(access['builder_history_refreshing']);self.assertFalse(access['ownership_ready'])
 def test_new_unassigned_wallet_still_requires_ownership(self):
  s=self.session();w=copy.deepcopy(self.wallet);w['raw']['descriptors'][0]['desc']=w['raw']['descriptors'][0]['desc'].replace('/0/*','/1/*').split('#')[0]
  from vendor.embit.descriptor.checksum import checksum
  d=w['raw']['descriptors'][0]['desc'];w['raw']['descriptors'][0]['desc']=d+'#'+checksum(d);other=clean_wallet(w['raw']);DescriptorStore(self.config).replace_node_wallets([self.wallet,other]);self.assertFalse(s.access()['ownership_assignments_ready'])
if __name__=='__main__':unittest.main()
