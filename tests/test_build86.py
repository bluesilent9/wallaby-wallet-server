"""Stable displayed signer choices; fresh per-account checks before queuing."""
import copy,time,unittest
from types import SimpleNamespace
from unittest.mock import patch
import test_build71 as fixtures
from agent_transactions import eligible,queue_sign,signing_state
from transaction_workflows import WorkflowStore
from disc_signers import inventory,verify_selection

class StableSigners(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.Discs();self.f.setUp();self.addCleanup(self.f.doCleanups);self.f.check();self.hub=self.f.f.hub;self.node=self.f.node;self.token=self.f.token;self.wallet=self.f.f.rid
 def test_disc_choice_survives_checking_and_busy_without_claiming_fresh_proof(self):
  before=eligible(self.hub,self.wallet,display=True);disc=next(r for r in before if r.get('archive_id'))
  self.f.checks.jobs.add('signing')
  with patch.object(self.f.checks,'scan'):
   self.f.checks.ensure('signing',force=True)
   self.assertIn(disc,eligible(self.hub,self.wallet,display=True));self.assertNotIn(disc,eligible(self.hub,self.wallet));self.assertFalse(self.f.checks.is_verified(self.node))
  self.f.busy=True;self.f.checks.scan(self.node,self.token)
  self.assertIn(disc,eligible(self.hub,self.wallet,display=True));self.assertNotIn(disc,eligible(self.hub,self.wallet))
 def test_click_during_background_check_queues_one_exact_psbt_after_live_disc_checks(self):
  job=self.f.f.job();before=WorkflowStore(self.hub.config)._read();disc=next(r for r in eligible(self.hub,self.wallet,display=True) if r.get('archive_id'))
  self.f.checks.rows[self.node].update(state='checking',active=True);self.f.calls.clear()
  session=SimpleNamespace(user_id=self.f.f.user)
  result=queue_sign(self.hub,session,job,self.wallet,self.node,disc['signer_id']);self.f.busy=True;again=queue_sign(self.hub,session,job,self.wallet,self.node,disc['signer_id']);self.assertEqual(result['request_hash'],again['request_hash'])
  requests=[r for r in self.hub.read()['requests'].values() if r.get('job_id')==job];self.assertEqual(len(requests),1);self.assertEqual(requests[0]['proposal']['wallet'],'Disc role');self.assertEqual(requests[0]['proposal']['psbt'],WorkflowStore(self.hub.config).job(session.user_id,job)['psbt']);self.assertEqual(WorkflowStore(self.hub.config)._read(),before)
  self.assertEqual([c[1] for c in self.f.calls],['getwalletinfo','listdescriptors','getwalletinfo'])
 def test_busy_unload_and_policy_change_never_queue_from_cached_choice(self):
  job=self.f.f.job();disc=next(r for r in eligible(self.hub,self.wallet,display=True) if r.get('archive_id'));self.f.checks.rows[self.node]['state']='checking';session=SimpleNamespace(user_id=self.f.f.user)
  for mode in ('busy','changed'):
   self.f.busy=mode=='busy';self.f.mismatch=mode=='changed'
   with self.assertRaises(ValueError):queue_sign(self.hub,session,job,self.wallet,self.node,disc['signer_id'])
   self.assertFalse([r for r in self.hub.read()['requests'].values() if r.get('job_id')==job])
  self.f.busy=self.f.mismatch=False;self.f.mounted=False;self.f.checks.scan(self.node,self.token);self.assertFalse(any(n.get('archive_id') for n in eligible(self.hub,self.wallet,display=True)))
 def test_disconnect_or_new_connection_never_reuses_disc_choice(self):
  self.f.f.registry.connections.pop(self.token);self.assertFalse(eligible(self.hub,self.wallet,display=True))
 def test_node_inventory_failure_keeps_display_only_choice_until_live_recheck(self):
  base=copy.deepcopy(self.hub.inventories[self.node]);self.hub.inventory_display[self.node]={'token':self.token,'inventory':base};self.hub.inventories[self.node]={'wallets':[],'complete':False,'error':'Agent busy'}
  choices=eligible(self.hub,self.wallet,display=True);regular=next(n for n in choices if not n.get('archive_id'));self.assertTrue(regular['needs_verification']);self.assertFalse([n for n in eligible(self.hub,self.wallet) if not n.get('archive_id')])
  self.hub.inventory_display[self.node]['token']='old-token';self.assertFalse([n for n in eligible(self.hub,self.wallet,display=True) if not n.get('archive_id')])
 def test_stale_health_retains_displayed_choice_but_downloading_removes_it(self):
  health=self.f.f.registry.health.values[self.token];health.update(state='ready',checked_at=time.monotonic()-61)
  self.assertTrue(eligible(self.hub,self.wallet,display=True));self.assertFalse(eligible(self.hub,self.wallet))
  health.update(state='downloading',checked_at=time.monotonic());self.assertFalse(eligible(self.hub,self.wallet,display=True))

 def test_regular_node_cached_choice_is_rechecked_before_request(self):
  job=self.f.f.job();base=copy.deepcopy(self.hub.inventories[self.node]);self.hub.inventory_display[self.node]={'token':self.token,'inventory':base};self.hub.inventories[self.node]={'wallets':[],'complete':False,'error':'Agent busy'}
  selected=next(n for n in eligible(self.hub,self.wallet,display=True) if not n.get('archive_id'));original=self.f.rpc
  def rpc(node,method,params=None,wallet=None,**kwargs):
   if method=='listdescriptors' and wallet==selected['wallet']:return {'state':'succeeded','result':copy.deepcopy(base['wallets'][0]['raw'])}
   return original(node,method,params,wallet,**kwargs)
  self.f.f.registry.rpc.call=rpc;result=queue_sign(self.hub,SimpleNamespace(user_id=self.f.f.user),job,self.wallet,self.node,selected['signer_id'])
  self.assertEqual(self.hub.read()['requests'][result['request_hash']]['proposal']['wallet'],selected['wallet'])
