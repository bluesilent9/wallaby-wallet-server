"""Released Agent58 capability negotiation must deliver saved pending refreshes."""
import ast,copy,os,unittest
from pathlib import Path
import test_build80 as fixture
from agent_hub import CAPS,digest
from vault_refresh import progress

def released_caps():
 source=Path(os.environ.get('WALLABY_AGENT_SOURCE','/nonexistent'))/'agent_exchange.py'
 if not source.exists():raise unittest.SkipTest('Released Agent source unavailable')
 tree=ast.parse(source.read_text())
 for node in ast.walk(tree):
  if isinstance(node,ast.Dict):
   for key,value in zip(node.keys,node.values):
    if isinstance(key,ast.Constant) and key.value=='capabilities' and isinstance(value,ast.List):return ast.literal_eval(value)
 raise AssertionError('Actual Agent exchange capabilities were not found')

class ReleasedAgentExchange(unittest.TestCase):
 def setUp(self):
  self.f=fixture.GroupedApproval();self.f.setUp();self.addCleanup(self.f.doCleanups);self.f.begin();self.hub=self.f.hub;self.hub.refresh_inventory=lambda *a,**k:None
 def exchange(self,node,items=(),caps=None):
  token=next(c['token'] for c in self.f.f.f.registry.connections.values() if c['node_id']==node)
  return self.hub.exchange(token,{'version':1,'outbox':list(items),'known_vaults':[],'capabilities':released_caps() if caps is None else caps})
 def test_full_released_capabilities_deliver_existing_request_and_accept_receipt(self):
  caps=released_caps();self.assertIn('wallet_policy_refresh_cancel_v1',caps);self.assertFalse(set(caps)-CAPS)
  node=next(iter(self.f.rows));before=copy.deepcopy(self.f.work.read());request=self.f.rows[node]['proposal'];response=self.exchange(node)
  self.assertIn(request,response['proposals']);self.assertEqual(self.f.work.read(),before,'exchange preserves the in-progress refresh and original transaction')
  payload=self.f.receipt(node);item={'kind':'wallet_policy_refresh_receipt','payload':payload};item['id']=digest(item);response=self.exchange(node,[item]);self.assertIn(item['id'],response['accepted']);self.assertEqual(self.f.target(node)['colour'],'amber');self.assertFalse(progress(self.hub,self.f.user)['complete']);self.assertEqual(self.f.work.read(),before)
 def test_unknown_capability_still_rejected_without_altering_saved_build(self):
  node=next(iter(self.f.rows));before=copy.deepcopy(self.f.work.read())
  with self.assertRaisesRegex(ValueError,'Unsupported Agent capabilities'):self.exchange(node,caps=released_caps()+['unrecognised_test_capability'])
  self.assertEqual(self.f.work.read(),before)
