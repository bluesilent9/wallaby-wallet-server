"""Index-bound refresh review uses the exact reservation, not sample zero."""
import copy,json,os,subprocess,sys,unittest
from pathlib import Path
import test_build80 as fixture
from builder_destinations import Destinations
from vault_refresh import proposed,finish,progress
from refresh_comparison import receiving_address,samples
from vendor.embit.descriptor import Descriptor
from vendor.embit.networks import NETWORKS
from wallet_policy_updates import proposals
from agent_hub import digest

class ExactRefresh(unittest.TestCase):
 begin=fixture.GroupedApproval.begin
 receipt=fixture.GroupedApproval.receipt
 sign=fixture.GroupedApproval.sign
 # Reuse setup/signing helpers without rerunning inherited cases in this suite.
 def setUp(self):
  fixture.GroupedApproval.setUp(self)
  store=Destinations(self.f.f.config);state=store.read();target=state['destinations'][self.f.dest['id']]
  target['index']=15;target['address']=Descriptor.from_string(target['descriptors'][0]['desc']).derive(15).address(NETWORKS['main']);store.write(state)
  state=self.work.read();state['workspaces']['wallet']['draft']['vault']={'result':{'height':1000100}};self.work.write(state)
 def test_exact_index_address_samples_and_reentry_do_not_reserve_again(self):
  before=proposed(self.f.f.config,self.work.owned(self.user,'wallet'));self.assertEqual(before['index'],15)
  self.begin();self.assertEqual(self.d['index'],15);self.assertEqual(self.d['address'],before['address']);self.assertEqual([r['index'] for r in before['comparison_samples']],[15,16,17,15,16,17])
  for r in self.rows.values():self.assertEqual(r['proposal']['receiving_address'],{'index':15,'address':before['address']})
  saved=Destinations(self.f.f.config).read();requests=self.hub.read();finish(self.hub,self.user,1000100);self.assertEqual(saved,Destinations(self.f.f.config).read());self.assertEqual(requests,self.hub.read())
 def test_new_request_is_withheld_from_older_agent_without_downgrade(self):
  self.begin();node=next(iter(self.rows));c=next(c for c in self.hub.registry.connections.values() if c['node_id']==node);c['agent_version']='2.0.0~dev59';before=copy.deepcopy(self.hub.read())
  self.assertEqual(proposals(self.hub,node),[]);self.assertEqual(self.hub.read(),before);self.assertIn('Build 60',next(t for t in progress(self.hub,self.user)['targets'] if t['node_id']==node)['status'])
  c['agent_version']='2.0.0~dev60';self.assertEqual(proposals(self.hub,node)[0]['receiving_address']['index'],15)
 def test_saved_old_request_is_not_rewritten(self):
  self.begin();node=next(iter(self.rows))
  with self.hub.edit() as state:state['requests'][self.rows[node]['proposal']['request_id']]['proposal'].pop('receiving_address')
  before=copy.deepcopy(self.hub.read()['requests']);proposals(self.hub,node)
  after=self.hub.read()['requests'];key=self.rows[node]['proposal']['request_id'];self.assertEqual(before[key]['proposal'],after[key]['proposal']);self.assertNotIn('receiving_address',after[key]['proposal'])
 def test_actual_agent60_accepts_and_independently_rejects_wrong_address(self):
  source=Path(os.environ.get('WALLABY_AGENT_SOURCE','/nonexistent'))
  if not (source/'policy_refresh.py').exists():self.skipTest('Matching Agent source unavailable')
  self.begin();p=next(iter(self.rows.values()))['proposal'];program="""import json,sys\nsys.path.insert(0,sys.argv[1])\nfrom policy_refresh import validate\np=json.loads(sys.argv[2]);validate(p);p['receiving_address']['address']='bc1qinvalid'\ntry:validate(p)\nexcept ValueError:print('matched and tampering refused')\nelse:raise AssertionError('Wrong address accepted')\n"""
  result=subprocess.check_output([sys.executable,'-c',program,str(source),json.dumps(p)],text=True);self.assertIn('tampering refused',result)
 def test_index_changes_are_bound_by_receipt_hash(self):
  self.begin();node=next(iter(self.rows));proposals(self.hub,node);envelope=self.receipt(node)
  body=copy.deepcopy(self.rows[node]['proposal']);body['receiving_address']['index']=16
  self.assertNotEqual(digest(body),envelope['message']['request_hash'])

class SampleLimits(unittest.TestCase):
 def test_bounds_and_mismatch(self):
  f=fixture.GroupedApproval();f.setUp();self.addCleanup(f.doCleanups);f.begin();d=f.d
  for index,expected in ((998,[998,999,998,999]),(999,[999,999])):
   self.assertEqual([r['index'] for r in samples(d['descriptors'],index)],expected)
  for index in (-1,1000,True,1.0,'15'):
   with self.assertRaises(ValueError):samples(d['descriptors'],index)
  broken=copy.deepcopy(d);broken['address']='bc1qinvalid'
  with self.assertRaisesRegex(ValueError,'does not match'):receiving_address(broken)
