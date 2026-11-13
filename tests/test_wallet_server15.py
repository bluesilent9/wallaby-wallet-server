"""Fresh unpaired discovery from loaded sources and first identity bootstrap."""
import base64,copy,json,os,subprocess,sys,time,unittest
from pathlib import Path
from unittest.mock import patch
import test_wallet_server2 as fixtures
from test_node_loading import public_wallet
from descriptor_store import clean_wallet
from setup_signatures import canonical,fingerprint,NAMESPACE
from secure_relay import PROTOCOL,CIPHER,NAMESPACE as RELAY_NAMESPACE
from sync_permissions import policy_id,Permissions

class NewReceiver(unittest.TestCase):
 exchange=fixtures.CurrentProtocol.exchange
 def setUp(self):
  fixtures.CurrentProtocol.setUp(self);self.caps.append('wallet_sync_offers_v1');self.hub.relay.reset();self.c=self.f.register('02:80:00:00:00:03','third-source')
  self.other=self.wallet('another loaded wallet',8,False)
  self.hub.inventories[self.c['node_id']]={'wallets':[self.other],'complete':True}
  self.hub.inventories[self.f.b['node_id']]={'complete':True,'wallets':[self.wallet('receiver local one',5),self.wallet('receiver local two',6)]}
  for n in (self.f.a,self.c):self.partial(n)
  for n in (self.f.a,self.f.b,self.c):self.hub.caps[n['node_id']]=set(self.caps)
  with self.hub.edit() as s:s['requests']={}
 def wallet(self,name,index,private=True):
  w=clean_wallet(public_wallet(name,index));return {'id':w['id'],'name':name,'raw':w['raw'],'private_keys_enabled':private,'scanning':False}
 def partial(self,n):
  inv=self.hub.inventories[n['node_id']];inv.update(complete=False,loaded_complete=True,unloaded_wallets=['unrelated folder'],history_checked_at=time.monotonic());self.hub.inventory_times[n['node_id']]=time.monotonic();self.hub.inventory_display[n['node_id']]={'token':n['connection_token']}
 def offers(self):return next(p for p in self.exchange(self.f.b)['proposals'] if p['kind']=='wallet_sync_offers')['offers']
 def test_fresh_receiver_sees_both_loaded_sources_without_pairing_or_old_requests(self):
  self.assertFalse(self.hub.read()['requests']);offers=self.offers();self.assertEqual(len(offers),2);self.assertEqual({o['peer']['hostname'] for o in offers},{'first','third-source'});self.assertEqual({o['status'] for o in offers},{'secure_pairing_required'});self.assertTrue(all(o['direction']=='receive' for o in offers))
  rows=list(self.hub.read()['requests'].values());self.assertEqual(len(rows),4);self.assertFalse(any(r.get('proposal') or r.get('active_pair') for r in rows));self.assertEqual({r['source_has_private_keys'] for r in rows},{True,False})
 def test_no_duplicate_or_already_local_wallet_offers(self):
  self.hub.inventories[self.c['node_id']]['wallets'].append(copy.deepcopy(self.f.node_wallet));self.hub.inventories[self.f.b['node_id']]['wallets'].append(copy.deepcopy(self.f.node_wallet));offers=self.offers();self.assertEqual(len(offers),1);self.assertEqual(offers[0]['public_wallet'],self.other['raw'])
 def test_failed_stale_and_reconnected_loaded_source_is_not_advertised(self):
  original=copy.deepcopy(self.hub.inventories)
  for problem in ('failed','stale','reconnected'):
   with self.hub.edit() as s:s['requests']={}
   self.hub.inventories=copy.deepcopy(original)
   for n in (self.f.a,self.c):
    self.partial(n);node=n['node_id']
    if problem=='failed':self.hub.inventories[node]['loaded_complete']=False
    elif problem=='stale':self.hub.inventories[node]['history_checked_at']=time.monotonic()-91
    else:self.hub.inventory_display[node]['token']='previous connection'
   self.assertFalse(self.offers(),problem)
 def test_incomplete_receiver_does_not_prove_destination_absence(self):
  self.partial(self.f.b);self.assertFalse(self.offers());self.assertFalse(self.hub.read()['requests'])
 def test_deny_and_reenable_do_not_enable_execution_without_pairing(self):
  offers=self.offers();before=len(self.hub.read()['requests']);raw=offers[0]['public_wallet'];self.hub.permissions.live[self.f.b['node_id']]['record']['policies']=[policy_id(raw)];denied=self.offers();self.assertEqual(next(o for o in denied if o['transfer_id']==offers[0]['transfer_id'])['status'],'disabled');self.hub.permissions.live[self.f.b['node_id']]['record']['policies']=[];self.assertEqual({o['status'] for o in self.offers()},{'secure_pairing_required'});self.assertEqual(len(self.hub.read()['requests']),before);self.assertFalse(any(r.get('proposal') for r in self.hub.read()['requests'].values()))
 def test_current_agent_can_deny_discovered_wallet_before_any_pairing(self):
  source=os.environ.get('WALLABY_AGENT_CURRENT_SOURCE')
  if not source:self.skipTest('Set current Agent source')
  reply=self.exchange(self.f.b);offers=next(p for p in reply['proposals'] if p['kind']=='wallet_sync_offers')
  code='''import json,sys,tempfile
sys.path.insert(0,sys.argv[1])
from approval_store import Store
from sync_offers import apply
from sync_table import state
from sync_preferences import change,enable
p=json.loads(sys.stdin.read())
with tempfile.TemporaryDirectory() as tmp:
 s=Store(tmp,persistence=False);s.persistence=None;apply(s,p,'fresh')
 rows=state(s,[])['wallets'];assert len(rows)==2
 first=rows[0];assert first['deny_id'];change(s,first['deny_id'],True)
 denied=next(r for r in state(s,[])['wallets'] if r['policy_id']==first['policy_id']);assert denied['denied'] and denied['offers']
 enable(s,first['policy_id']);assert not next(r for r in state(s,[])['wallets'] if r['policy_id']==first['policy_id'])['denied']
 assert not s.read()['pending'] and not s.read().get('active_transfer')
'''
  r=subprocess.run([sys.executable,'-B','-c',code,source],input=json.dumps(offers),capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)

class FirstIdentity(unittest.TestCase):
 def setUp(self):
  from test_build8 import Setup
  self.f=Setup();self.f.setUp();self.addCleanup(self.f.doCleanups);self.hub=self.f.hub;self.hub.permissions.live.clear();self.hub.refresh_inventory=lambda *a:None;self.n=self.f.a;self.serial=0;self.key=Path(self.f.tmp.name)/'new-identity';subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(self.key)],check=True);self.public=' '.join(self.key.with_suffix('.pub').read_text().split()[:2])
 def sign(self,m,key=None,namespace=NAMESPACE):
  self.serial+=1;key=key or self.key;public=' '.join(key.with_suffix('.pub').read_text().split()[:2]);p=Path(self.f.tmp.name)/('signed-'+str(self.serial));p.write_bytes(canonical(m));subprocess.run(['ssh-keygen','-q','-Y','sign','-f',str(key),'-n',namespace,str(p)],check=True,capture_output=True);return {'message':m,'public_key':public,'signature':base64.b64encode(p.with_suffix('.sig').read_bytes()).decode()}
 def identity(self,**change):
  p=self.hub.permissions.proposals(self.n['node_id'],self.n['connection_token'])[0];m={'version':1,'challenge':p['challenge'],'public_key':self.public,'fingerprint':fingerprint(self.public),'hostname':'new Agent'};m.update(change);return self.sign(m)
 def accept(self,e):return self.hub.permissions.identity_reply(self.n['node_id'],e)
 def test_fresh_permission_identity_reaches_relay_without_wallet_builder(self):
  self.assertFalse(self.hub.wallet_builder.read()['identities']);self.assertFalse(self.hub.wallet_builder.read()['sessions']);e=self.identity();item=self.f.item('wallet_setup_identity',e);reply=self.f.exchange(self.n,[item],caps=['wallet_relay_v1']);self.assertIn(item['id'],reply['accepted']);self.assertEqual(self.hub.wallet_builder.read()['identities'][self.n['node_id']],e)
  from wallet_builder import validate_archive
  validate_archive(self.f.config,self.hub.wallet_builder.read(),{self.f.user})
  relay=self.hub.relay;p=relay.agent(self.n['connection_token']);challenge=relay.dispatch(p,{'action':'challenge'});m={'protocol':PROTOCOL,'version':1,'kind':'register','endpoint_id':p['id'],'role':'agent','challenge':challenge['challenge'],'noise_public_key':base64.b64encode(b'x'*32).decode(),'cipher_suite':CIPHER};r=relay.dispatch(p,{'action':'register','proof':self.sign(m,namespace=RELAY_NAMESPACE)});self.assertTrue(r['registered']);directory=relay.dispatch(p,{'action':'directory'});self.assertEqual(directory['endpoints'][0]['identity_key'],self.public);self.assertFalse(relay.mesh([self.n['node_id'],self.f.b['node_id']])['ready']);self.assertFalse(self.hub.wallet_builder.read()['sessions'])
 def test_persisted_verified_identity_rejects_another_key_after_permissions_restart(self):
  e=self.identity();self.assertTrue(self.accept(e));self.hub.permissions=Permissions(self.hub);other=Path(self.f.tmp.name)/'other-key';subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(other)],check=True);public=' '.join(other.with_suffix('.pub').read_text().split()[:2]);challenge=self.hub.permissions.proposals(self.n['node_id'],self.n['connection_token'])[0]['challenge'];m={'version':1,'challenge':challenge,'public_key':public,'fingerprint':fingerprint(public),'hostname':'other key'}
  with self.assertRaisesRegex(ValueError,'previously observed'):self.accept(self.sign(m,other))
  self.assertEqual(self.hub.wallet_builder.read()['identities'][self.n['node_id']],e);self.assertFalse(self.hub.permissions.current(self.n['node_id']).get('identity'))
 def test_permission_handshake_does_not_replace_existing_builder_identity(self):
  e=self.identity();self.assertTrue(self.accept(e));builder=self.sign({**e['message'],'challenge':'b'*64})
  with self.hub.wallet_builder.edit() as saved:saved['identities'][self.n['node_id']]=builder;saved['challenges'][self.n['node_id']]='b'*64
  before=copy.deepcopy(self.hub.wallet_builder.read());self.hub.permissions=Permissions(self.hub);self.assertTrue(self.accept(self.identity()));self.assertEqual(self.hub.wallet_builder.read(),before);self.assertEqual(self.hub.relay.agent(self.n['connection_token'])['identity_key'],self.public)
 def test_stale_challenge_invalid_signature_or_hostname_does_not_pin(self):
  valid=self.identity();bad=copy.deepcopy(valid);bad['message']['hostname']='tampered'
  with self.assertRaises(ValueError):self.accept(bad)
  self.assertFalse(self.accept(self.identity(challenge='0'*64)))
  for name in ('','\ninvalid',False):
   with self.assertRaises(ValueError):self.accept(self.identity(hostname=name))
  self.assertFalse(self.hub.wallet_builder.read()['identities'])
 def test_reconnect_during_signature_verification_cannot_pin_old_connection(self):
  from sync_permissions import verify
  e=self.identity();old=self.n['connection_token']
  def reconnect(*a,**kw):
   r=verify(*a,**kw);c=self.hub.registry.connections.pop(old);c.update(token='new token');self.hub.registry.connections['new token']=c;return r
  with patch('sync_permissions.verify',side_effect=reconnect):self.assertFalse(self.accept(e))
  self.assertFalse(self.hub.wallet_builder.read()['identities'])

if __name__=='__main__':unittest.main()
