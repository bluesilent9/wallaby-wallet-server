"""Public offers are visible before pairing but cannot authorise a transfer."""
import copy,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
import test_wallet_server2 as fixtures
from sync_permissions import policy_id
from wallet_sync_offers import validate_saved

class Offers(unittest.TestCase):
 setUp=fixtures.CurrentProtocol.setUp
 exchange=fixtures.CurrentProtocol.exchange
 def setUp(self):
  fixtures.CurrentProtocol.setUp(self);self.caps.append('wallet_sync_offers_v1')
  for n in (self.f.a,self.f.b):self.hub.caps[n['node_id']]=set(self.caps)
 def offers(self,reply):return next(p for p in reply['proposals'] if p['kind']=='wallet_sync_offers')
 def queue(self,reply):return next(p for p in reply['proposals'] if p['kind']=='wallet_sync_queue')['requests']
 def test_unpaired_visible_on_both_agents_without_executable_requests(self):
  self.hub.relay.channels.clear();a=self.exchange(self.f.a);b=self.exchange(self.f.b)
  for n,r,d in ((self.f.a,a,'send'),(self.f.b,b,'receive')):
   offers=self.offers(r)['offers'];self.assertEqual(len(offers),1);self.assertEqual(offers[0]['direction'],d);self.assertEqual(offers[0]['status'],'secure_pairing_required');self.assertFalse(self.queue(r));self.assertNotIn('transport',offers[0]);validate_saved(self.hub.read()['nodes'][n['node_id']])
  self.assertFalse(any(row.get('proposal') for row in self.hub.read()['requests'].values()))
 def test_ready_offer_links_to_exact_executable_transfer_and_stable_revision(self):
  r=self.exchange(self.f.b);o=self.offers(r);q=self.queue(r);self.assertEqual(o['offers'][0]['transfer_id'],q[0]['transfer_id']);self.assertEqual(o['offers'][0]['status'],'ready');self.assertEqual(self.offers(self.exchange(self.f.b)),o)
 def test_agent_denial_keeps_discovery_and_reenable_keeps_pairing_required(self):
  self.hub.relay.channels.clear();before=self.offers(self.exchange(self.f.b));self.hub.permissions.live[self.f.b['node_id']]['record']['policies']=[policy_id(self.f.wallet['raw'])]
  denied=self.exchange(self.f.b);self.assertEqual(self.offers(denied)['offers'][0]['status'],'disabled');self.assertEqual(self.offers(denied)['offers'][0]['peer'],before['offers'][0]['peer']);self.assertFalse(self.queue(denied));self.assertGreater(self.offers(denied)['revision'],before['revision']);self.hub.permissions.live[self.f.b['node_id']]['record']['policies']=[]
  self.assertEqual(self.offers(self.exchange(self.f.b))['offers'][0]['status'],'secure_pairing_required')
 def test_completed_import_withdraws_both_offers_without_deleting_audit(self):
  self.exchange(self.f.b)
  with self.hub.edit() as state:
   for row in state['requests'].values():row['state']='complete'
  for n in (self.f.a,self.f.b):self.assertFalse(self.offers(self.exchange(n))['offers'])
  self.assertEqual(len(self.hub.read()['requests']),2)
 def test_disabled_capability_does_not_receive_unknown_message(self):
  self.caps.remove('wallet_sync_offers_v1');self.assertFalse(any(p['kind']=='wallet_sync_offers' for p in self.exchange(self.f.b)['proposals']))
 def test_saved_offer_validation_rejects_duplicate_and_executable_fields(self):
  self.exchange(self.f.b);entry=self.hub.read()['nodes'][self.f.b['node_id']];bad=copy.deepcopy(entry);bad['sync_offer_snapshot']*=2
  with self.assertRaises(ValueError):validate_saved(bad)
  entry['sync_offer_snapshot'][0]['transport']={}
  with self.assertRaises(ValueError):validate_saved(entry)
 def test_real_agent70_accepts_offer_without_creating_approval_or_transfer(self):
  source=os.environ.get('WALLABY_AGENT_OFFERS_SOURCE')
  if not source:self.skipTest('Set WALLABY_AGENT_OFFERS_SOURCE to Agent Build 70 source')
  self.hub.relay.channels.clear();offer=self.offers(self.exchange(self.f.b))
  code="""import sys,json,tempfile
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from approval_store import Store
from sync_offers import apply,rows
from sync_preferences import change,enable
p=json.loads(sys.stdin.read())
with tempfile.TemporaryDirectory() as folder:
 s=Store(Path(folder));apply(s,p,'test-session');r=rows(s)
 assert len(r)==1 and r[0]['request_id'] is None and not s.read()['pending']
 change(s,r[0]['id'],True);assert not rows(s) and not s.read()['pending']
 ident=next(iter(s.read()['sync_exclusions']));enable(s,ident);assert len(rows(s))==1 and not s.read()['pending']
 print(json.dumps({'rows':len(r),'status':r[0]['status'],'pending':len(s.read()['pending'])}))
"""
  out=subprocess.run([sys.executable,'-c',code,source],input=json.dumps(offer),capture_output=True,text=True);self.assertEqual(out.returncode,0,out.stderr);self.assertEqual(json.loads(out.stdout)['status'],'secure_pairing_required')

 def test_obsolete_signer_invitations_never_appear_and_frozen_proposals_unchanged(self):
  self.exchange(self.f.b);before=copy.deepcopy(self.hub.read()['requests'])
  with self.hub.edit() as state:
   for row in state['requests'].values():row['superseded_container']=True
  self.assertFalse(self.offers(self.exchange(self.f.b))['offers'])
  for ident,row in self.hub.read()['requests'].items():self.assertEqual(row['proposal'],before[ident]['proposal'])
 def test_source_goes_offline_offer_explains_it_without_transfer_authority(self):
  self.hub.relay.channels.clear();self.exchange(self.f.b);self.hub.registry.connections.pop(self.f.a['connection_token'])
  r=self.exchange(self.f.b);o=self.offers(r)['offers'][0];self.assertEqual(o['status'],'peer_offline');self.assertEqual(o['peer']['hostname'],'first');self.assertFalse(self.queue(r))

 def test_unknown_permissions_do_not_hide_public_discovery_or_enable_execution(self):
  self.hub.permissions.live.clear();self.hub.relay.channels.clear();r=self.exchange(self.f.b)
  self.assertEqual(self.offers(r)['offers'][0]['status'],'permissions_pending');self.assertFalse(self.queue(r));self.assertFalse(any(row.get('proposal') for row in self.hub.read()['requests'].values()))
