"""Finishing a verified broadcast never requests destruction of Agent artifacts."""
import sys,copy,unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from test_build8 import Setup
from builder_workspace import BuilderWorkspace
from transaction_workflows import WorkflowStore
from agent_transactions import queue_sign
from types import SimpleNamespace

class BroadcastClose(Setup):
 def prepare(self,broadcast=True):
  ws=BuilderWorkspace(self.config);ws.start(self.user,'transaction');ident=self.job();ws.attach(self.user,'transaction',ident)
  self.hub.caps[self.a['node_id']]={'partial_signing','builder_cancellation_v1'};q=queue_sign(self.hub,SimpleNamespace(user_id=self.user),ident,self.rid,self.a['node_id']);self.exchange(self.a,caps=['partial_signing','builder_cancellation_v1'])
  if broadcast:
   store=WorkflowStore(self.config);data=store._read();data['jobs'][ident]['broadcast_txid']='b'*64;store._write(data)
   with self.hub.edit() as s:s['requests'][q['request_hash']]['state']='complete'
  return ws,ident
 def test_cancel_after_confirmed_broadcast_finishes_locally_no_agent_requests(self):
  ws,ident=self.prepare();before=copy.deepcopy(self.hub.read()['requests']);result=ws.cancel(self.hub,self.user,'transaction',True)
  self.assertIsNone(result['workspace']);self.assertIsNone(result['cancellation']);self.assertEqual(ws.read()['cancellations'],{});self.assertEqual(self.hub.read()['requests'],before)
  job=WorkflowStore(self.config).job(self.user,ident);self.assertTrue(job['completed']);self.assertFalse(job['cancelled']);self.assertEqual(ws.proposals(self.a['node_id']),[])
 def test_before_broadcast_still_requires_agent_cancellation(self):
  ws,ident=self.prepare(False);result=ws.cancel(self.hub,self.user,'transaction',True);self.assertIsNotNone(result['cancellation']);self.assertEqual(len(result['cancellation']['targets']),1);self.assertTrue(WorkflowStore(self.config).job(self.user,ident)['cancelled'])
 def test_wrong_user_and_missing_confirmation_still_refused(self):
  ws,ident=self.prepare()
  with self.assertRaises(ValueError):ws.cancel(self.hub,'wrong','transaction',True)
  with self.assertRaises(ValueError):ws.cancel(self.hub,self.user,'transaction',False)
  self.assertIsNotNone(ws.snapshot(self.user,'transaction')['workspace'])
if __name__=='__main__':unittest.main()
