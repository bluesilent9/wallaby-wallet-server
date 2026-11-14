"""A received archive's signed completion clears preservation without new deletion."""
import copy,unittest
from unittest.mock import patch
import test_build18 as previous
from wallet_retirement import advance,result,group_rows,group_complete,CAPABILITY,snapshot

class ExistingArchive(unittest.TestCase):
 def setUp(self):
  self.f=previous.Retirement();self.f.setUp();self.addCleanup(self.f.doCleanups);self.hub=self.f.hub
  self.key=self.f.delivered();self.f.finish(self.key);self.hub.inventories[self.f.a['node_id']]['wallets']=[]
  self.hub.inventories[self.f.b['node_id']].update(wallets=[],archive_wallets=['historical_container']);self.hub.caps[self.f.b['node_id']]={CAPABILITY};advance(self.hub)
  self.child=next(k for k,r in self.hub.read()['requests'].items() if r['node_id']==self.f.b['node_id'] and r['proposal']['phase']=='preserve');self.f.exchange(self.f.b,caps=[CAPABILITY]);self.proof=self.f.proof(self.child)
 def accept(self):
  with self.hub.edit() as state:result(state,self.f.b['node_id'],self.proof)
 def test_late_completed_preservation_is_verified_when_no_original_or_delete_work_remains(self):
  before=copy.deepcopy(self.hub.read()['requests']);self.accept()
  with self.hub.edit() as state:state['requests'][self.key]['coordination_error']='Earlier data was missing'
  self.f.calls=[]
  with patch('wallet_retirement.history_manifest',side_effect=AssertionError('Original wallet is gone')),patch('wallet_retirement.zero_balances',side_effect=AssertionError('No new deletion needed')):advance(self.hub)
  state=self.hub.read();row=state['requests'][self.child];self.assertTrue(row['archive_checked']);self.assertEqual(row['result'],self.proof);self.assertNotIn('coordination_error',state['requests'][self.key]);self.assertEqual(set(state['requests']),set(before));self.assertTrue(group_complete(state,self.key));self.assertTrue(any(n==self.f.b['node_id'] and m=='gettransaction' for n,m,w in self.f.calls));self.assertEqual(row['proposal'],before[self.child]['proposal'])
 def test_repeated_refresh_does_not_reverify_or_reissue_completed_task(self):
  self.accept();advance(self.hub);self.assertTrue(self.hub.read()['requests'][self.child].get('archive_checked'));before=copy.deepcopy(self.hub.read()['requests']);self.f.calls=[];advance(self.hub);advance(self.hub);self.assertEqual(self.hub.read()['requests'],before);self.assertFalse([c for c in self.f.calls if c[1] in ('getaddressinfo','gettransaction','listtransactions')]);self.assertFalse(any(p.get('kind')=='wallet_retire' and p.get('phase')=='preserve' for p in self.f.exchange(self.f.b,caps=[CAPABILITY])['proposals']))
 def test_advisory_inventory_alone_cannot_complete_pending_preservation(self):
  state=copy.deepcopy(self.hub.read()['requests'][self.child]);advance(self.hub);row=self.hub.read()['requests'][self.child];self.assertEqual(row['state'],'pending');self.assertFalse(row.get('archive_checked'));self.assertEqual(row['proposal'],state['proposal'])
 def test_missing_archive_record_does_not_verify_received_completion(self):
  self.accept();self.f.missing_tx=True;advance(self.hub);row=self.hub.read()['requests'][self.child];self.assertFalse(row.get('archive_checked'));self.assertEqual(row['result'],self.proof)
 def test_conflicting_label_does_not_clear_preservation(self):
  self.accept();rpc=self.hub.rpc
  def wrong(n,m,p=None,wallet=None):
   v=rpc(n,m,p,wallet)
   if n==self.f.b['node_id'] and m=='getaddressinfo':v['labels']=['Conflicting owner']
   return v
  self.hub.rpc=wrong;advance(self.hub);self.assertFalse(self.hub.read()['requests'][self.child].get('archive_checked'))
 def test_signed_receipt_mismatch_cannot_verify(self):
  self.proof['archive_receipt']['message']['manifest_hash']='f'*64;self.accept();advance(self.hub);self.assertFalse(self.hub.read()['requests'][self.child].get('archive_checked'))
 def test_disconnected_archive_cannot_verify(self):
  self.accept();self.hub.registry.heartbeat(self.f.b['connection_token'],True);advance(self.hub);self.assertFalse(self.hub.read()['requests'][self.child].get('archive_checked'))
 def test_saved_profile_retains_real_completion_and_verified_evidence(self):
  self.accept();advance(self.hub)
  from agent_state import validate
  from profile_archive import ProfileArchive
  from pathlib import Path
  validate(self.hub.read(),{self.f.user});blob=ProfileArchive(self.f.config).save();target=Path(self.f.tmp.name)/'restored/config.cfg';target.parent.mkdir();ProfileArchive(target).load('profile.7z',blob)
  from nodes import NodeRegistry
  registry=NodeRegistry(target);self.addCleanup(registry.hub.disc_signers.close);saved=registry.hub.read()['requests'][self.child];self.assertTrue(saved['archive_checked']);self.assertEqual(saved['result'],self.proof)

if __name__=='__main__':unittest.main()
