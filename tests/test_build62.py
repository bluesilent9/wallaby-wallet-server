"""Transaction handoff diagnostics contain state transitions, never payloads."""
import sys,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from test_build8 import Setup
from agent_transactions import queue_sign,signing_state
from transaction_workflows import WorkflowStore

class DeliveryLogs(Setup):
 def prepare(self):
  ident=self.job();self.hub.caps[self.a['node_id']]={'partial_signing'}
  args=(self.hub,SimpleNamespace(user_id=self.user),ident,self.rid,self.a['node_id']);queued=queue_sign(*args)
  return ident,args,queued,self.item('partial_sign_result',{'request_hash':queued['request_hash'],'status':'signed','psbt':self.signed})
 def log(self):return self.registry.diagnostic_log.text()
 def test_request_and_verified_receipt_are_logged_once_without_psbt(self):
  ident,args,queued,item=self.prepare();queue_sign(*args);self.assertEqual(self.log().count('Signing request queued'),1)
  for _ in range(2):self.assertIn(item['id'],self.exchange(self.a,[item],caps=['partial_signing'])['accepted'])
  log=self.log();self.assertEqual(log.count('Result accepted'),1);self.assertIn('outcome=verified',log);self.assertNotIn(self.signed,log);self.assertNotIn(self.unsigned,log);self.assertTrue(signing_state(self.hub,self.user,ident)['all_signed'])
 def test_rejected_signature_has_no_acknowledgement_and_no_payload_in_log(self):
  ident,args,q,_=self.prepare();secret='malformed-private-looking-test-payload';item=self.item('partial_sign_result',{'request_hash':q['request_hash'],'status':'signed','psbt':secret})
  for _ in range(2):
   with self.assertRaises(ValueError):self.exchange(self.a,[item],caps=['partial_signing'])
  log=self.log();self.assertEqual(log.count('Result rejected'),1);self.assertNotIn(secret,log);self.assertNotIn('Result accepted',log);self.assertEqual(self.hub.read()['requests'][q['request_hash']]['state'],'pending')
 def test_cancelled_late_result_is_drained_without_claiming_verified(self):
  ident,args,q,item=self.prepare();store=WorkflowStore(self.config);data=store._read();data['jobs'][ident]['cancelled']=True;store._write(data)
  self.assertIn(item['id'],self.exchange(self.a,[item],caps=['partial_signing'])['accepted']);self.assertIn('outcome=drained_after_cancellation',self.log());self.assertNotIn('outcome=verified',self.log());self.assertTrue(store.job(self.user,ident)['cancelled'])
 def test_agent_error_is_logged_without_remote_error_message(self):
  ident,args,q,_=self.prepare();payload={'request_hash':q['request_hash'],'status':'error','message':'untrusted sensitive detail'};self.exchange(self.a,[self.item('partial_sign_result',payload)],caps=['partial_signing']);log=self.log();self.assertIn('outcome=agent_error',log);self.assertNotIn(payload['message'],log)
if __name__=='__main__':unittest.main()
