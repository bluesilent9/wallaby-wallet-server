"""Real OPAQUE exchanges, role-bound encrypted relaying, and exact mobile data."""
import base64,copy,json,os,secrets,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from password_auth import PasswordAuth,opaque,SUITE
from preferences import FamilyStore
from secure_relay import SecureRelay,PROTOCOL,NAMESPACE,CIPHER,endpoint_id
from setup_signatures import canonical
from balance_store import BalanceStore,BALANCE_ALGORITHM
from mobile_data import snapshot

class Passwords(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.config=self.root/'config.cfg';f=FamilyStore(self.config);f.save_user('Example','green',revision=0,date_of_birth='01/01/1980');self.uid=f.snapshot()['users'][0]['id'];self.auth=PasswordAuth(self.config);self.password='An invented test passphrase 123!'
 def client(self,action,**params):
  js=Path(__file__).resolve().parent/'opaque_client.cjs'
  p=subprocess.run([os.environ['WALLABY_NODE'],str(js)],input=json.dumps({'action':action,'params':params}),capture_output=True,text=True,check=True);return json.loads(p.stdout)
 def begin(self,scope='browser-one'):
  c=self.client('startRegistration',password=self.password);r=self.auth.start(scope,{'user_id':self.uid,'mode':'register','request':c['registrationRequest']});return c,r
 def enroll(self,scope='browser-one'):
  c,r=self.begin(scope);ids={'client':self.uid,'server':r['server_identity']};record=self.client('finishRegistration',password=self.password,clientRegistrationState=c['clientRegistrationState'],registrationResponse=r['response'],identifiers=ids,keyStretching={'argon2id-custom':{'iterations':3,'memory':65536,'parallelism':1}});login=self.client('startLogin',password=self.password);r=self.auth.registration(scope,{'id':r['id'],'record':record['registrationRecord'],'request':login['startLoginRequest']});proof=self.client('finishLogin',password=self.password,clientLoginState=login['clientLoginState'],loginResponse=r['response'],identifiers=ids,keyStretching={'argon2id-custom':{'iterations':3,'memory':65536,'parallelism':1}});request={'id':r['id'],'request':proof['finishLoginRequest']};self.assertEqual(self.auth.finish(scope,request),self.uid);return request
 def login(self,scope,password=None):
  password=password or self.password;c=self.client('startLogin',password=password);r=self.auth.start(scope,{'user_id':self.uid,'mode':'login','request':c['startLoginRequest']});proof=self.client('finishLogin',password=password,clientLoginState=c['clientLoginState'],loginResponse=r['response'],identifiers={'client':self.uid,'server':r['server_identity']},keyStretching={'argon2id-custom':{'iterations':3,'memory':65536,'parallelism':1}});return r,proof
 def test_registration_never_replaces_saved_wallets_or_exposes_password(self):
  marker=self.root/'descriptors.cfg';marker.write_text('saved vault policy marker');self.assertTrue(self.auth.metadata(self.uid)['registration_required']);self.enroll();self.assertEqual(marker.read_text(),'saved vault policy marker');self.assertFalse(self.auth.metadata(self.uid)['registration_required']);raw=self.auth.path.read_text();self.assertNotIn(self.password,raw);self.assertNotIn('sessionKey',raw);self.assertNotIn('serverLoginState',raw)
 def test_same_password_works_on_other_devices_after_restart(self):
  self.enroll();self.auth=PasswordAuth(self.config)
  for scope in ('browser-two','phone-three'):
   r,p=self.login(scope);self.assertEqual(self.auth.finish(scope,{'id':r['id'],'request':p['finishLoginRequest']}),self.uid)
 def test_bad_password_cannot_finish_login(self):
  self.enroll();_,proof=self.login('phone','incorrect password 123!');self.assertIsNone(proof)
 def test_replay_and_cross_workspace_proofs_are_rejected(self):
  done=self.enroll()
  with self.assertRaises(ValueError):self.auth.finish('browser-one',done)
  r,p=self.login('phone')
  with self.assertRaises(ValueError):self.auth.finish('different-device',{'id':r['id'],'request':p['finishLoginRequest']})
 def test_cannot_overwrite_existing_registration(self):
  self.enroll()
  with self.assertRaises(ValueError):self.begin()
 def test_expired_and_invalid_registration_cannot_claim_account(self):
  _,r=self.begin();self.auth.pending[r['id']]['expires']=0
  with self.assertRaises(ValueError):self.auth.registration('browser-one',{'id':r['id'],'record':'A'*256,'request':'A'*64})
  self.assertTrue(self.auth.metadata(self.uid)['registration_required'])
 def test_plain_password_fields_are_never_accepted(self):
  with self.assertRaises(ValueError):self.auth.start('phone',{'user_id':self.uid,'mode':'register','password':self.password})
 def test_failed_logins_are_rate_limited(self):
  c=self.client('startLogin',password=self.password)
  for i in range(10):
   with self.assertRaises(ValueError):self.auth.start('browser',{'user_id':self.uid,'mode':'login','request':c['startLoginRequest']})
  with self.assertRaisesRegex(ValueError,'Too many'):self.auth.start('browser',{'user_id':self.uid,'mode':'login','request':c['startLoginRequest']})

class Relay(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.config=self.root/'config.cfg';self.hub=SimpleNamespace(registry=SimpleNamespace(connections={}))
  self.relay=SecureRelay(self.config,self.hub);self.peers=[]
  for i in range(3):
   key=self.root/str(i);subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(key)],check=True);public=' '.join(key.with_suffix('.pub').read_text().split()[:2]);role='agent' if i<2 else 'mobile';p=self.relay.principal(role,public,str(i),'scope'+str(i));self.hub.registry.connections[p['scope']]={'node_id':p['owner']};self.peers.append((p,key))
 def sign(self,p,key,message):
  file=self.root/'message';file.write_bytes(canonical(message));file.with_suffix('.sig').unlink(missing_ok=True);subprocess.run(['ssh-keygen','-q','-Y','sign','-f',str(key),'-n',NAMESPACE,str(file)],check=True,capture_output=True);return {'message':message,'public_key':p['identity_key'],'signature':base64.b64encode(file.with_suffix('.sig').read_bytes()).decode()}
 def register(self,i):
  p,key=self.peers[i];c=self.relay.dispatch(p,{'action':'challenge'});m={'protocol':PROTOCOL,'version':1,'kind':'register','endpoint_id':p['id'],'role':p['role'],'challenge':c['challenge'],'noise_public_key':base64.b64encode(bytes([i+1])*32).decode(),'cipher_suite':CIPHER};proof=self.sign(p,key,m);self.relay.dispatch(p,{'action':'register','proof':proof});return proof
 def report(self,i,j,channel='a'*64,handshake='b'*64):
  p,key=self.peers[i];peer,_=self.peers[j];c=self.relay.dispatch(p,{'action':'challenge'});m={'protocol':PROTOCOL,'version':1,'kind':'channel','endpoint_id':p['id'],'role':p['role'],'challenge':c['challenge'],'peer_id':peer['id'],'peer_role':peer['role'],'peer_noise_public_key':self.relay.endpoints[peer['id']]['noise_public_key'],'channel_id':channel,'handshake_hash':handshake,'state':'ready','paired_by_qr':True};return self.relay.dispatch(p,{'action':'channel','proof':self.sign(p,key,m)})
 def frame(self,p=None,to=None):
  return {'version':1,'id':secrets.token_hex(32),'from':(p or self.peers[0][0])['id'],'to':(to or self.peers[1][0])['id'],'channel_id':'a'*64,'sequence':0,'kind':'transport','ciphertext':base64.b64encode(os.urandom(100)).decode()}
 def test_both_agents_must_attest_same_live_handshake(self):
  self.register(0);self.register(1);self.report(0,1);self.assertFalse(self.relay.mesh(['0','1'])['ready']);self.report(1,0,handshake='c'*64);self.assertFalse(self.relay.mesh(['0','1'])['ready']);self.report(1,0);self.assertTrue(self.relay.mesh(['0','1'])['ready']);self.hub.registry.connections.clear();self.assertFalse(self.relay.mesh(['0','1'])['ready'])
 def test_missing_endpoint_blocks_multisig_even_on_single_agent(self):
  with self.assertRaises(ValueError):self.relay.require_mesh(['0'])
 def test_roles_are_cryptographically_bound_and_registration_cannot_replay(self):
  proof=self.register(2);p,key=self.peers[2]
  with self.assertRaises(ValueError):self.relay.dispatch(p,{'action':'register','proof':proof})
  c=self.relay.dispatch(p,{'action':'challenge'});m=dict(proof['message'],role='agent',challenge=c['challenge'])
  with self.assertRaises(ValueError):self.relay.dispatch(p,{'action':'register','proof':self.sign(p,key,m)})
 def test_queue_is_opaque_idempotent_and_only_recipient_can_ack(self):
  self.register(0);self.register(1);p=self.peers[0][0];target=self.peers[1][0];frame=self.frame();self.relay.dispatch(p,{'action':'send','frame':frame});self.relay.dispatch(p,{'action':'send','frame':frame});self.assertEqual(len(self.relay.messages),1);self.assertEqual(self.relay.dispatch(target,{'action':'receive'})['frames'],[frame]);
  with self.assertRaises(ValueError):self.relay.dispatch(p,{'action':'ack','ids':[frame['id']]})
  self.relay.dispatch(target,{'action':'ack','ids':[frame['id']]});self.assertTrue(self.relay.dispatch(p,{'action':'send','frame':frame})['acknowledged']);self.assertFalse(self.relay.messages)
 def test_different_payload_with_same_id_is_rejected(self):
  self.register(0);self.register(1);p=self.peers[0][0];f=self.frame();self.relay.dispatch(p,{'action':'send','frame':f});f['ciphertext']=base64.b64encode(os.urandom(100)).decode()
  with self.assertRaises(ValueError):self.relay.dispatch(p,{'action':'send','frame':f})
 def test_unexpected_plaintext_and_sender_spoofing_are_rejected(self):
  self.register(0);self.register(1);p=self.peers[0][0];f=self.frame();f['plaintext']='secret'
  with self.assertRaises(ValueError):self.relay.dispatch(p,{'action':'send','frame':f})
  del f['plaintext'];f['from']=self.peers[1][0]['id']
  with self.assertRaises(ValueError):self.relay.dispatch(p,{'action':'send','frame':f})
 def test_expiry_and_reset_never_replay_old_messages_or_channels(self):
  self.register(0);self.register(1);p=self.peers[0][0];f=self.frame();self.relay.dispatch(p,{'action':'send','frame':f});self.relay.messages[f['id']]['expires']=0;self.assertFalse(self.relay.dispatch(self.peers[1][0],{'action':'receive'})['frames']);self.relay.reset();self.assertFalse(self.relay.endpoints)
 def test_mobile_peer_is_not_an_agent_mesh_member(self):
  self.register(0);self.register(2);self.report(0,2);self.report(2,0);self.assertFalse(self.relay.mesh(['0','2'])['ready'])

class MobileData(unittest.TestCase):
 setUp=Passwords.setUp
 def test_balances_never_include_market_valuation_or_fetch_a_quote(self):
  BalanceStore(self.config).save('test',{'balances':{'price_aud_per_btc':'999999','wallets':[{'name':'Example','kind':'wallet','btc':'0.00000123','value_aud':'9999','gain_aud':'8888','cash_aud':'7777'}]}})
  with patch('urllib.request.urlopen',side_effect=AssertionError('No FX request permitted')):r=snapshot(self.config,self.uid,'balances')
  self.assertEqual(r['wallets'][0]['satoshis'],123);self.assertNotIn('aud',json.dumps(r).lower());self.assertFalse(r['market_prices_included'])
 def test_cgt_keeps_tax_aud_but_removes_live_balance_data(self):
  from mobile_data import without_live_balances
  self.assertEqual(without_live_balances({'proceeds_aud':'100','balances':{'value_aud':'900'}}),{'proceeds_aud':'100'})


class CurrentProtocol(unittest.TestCase):
 def setUp(self):
  from test_build8 import Setup
  from relay_fixtures import signed_mesh
  from agent_hub import AgentHub
  from wallet_transfers import Transfers
  self.f=Setup();self.f.setUp();self.addCleanup(self.f.doCleanups);self.hub=self.f.hub
  # Exercise the real v3 path, not the pre-upgrade invitation fixture.
  self.hub.transfer_proposal=AgentHub.transfer_proposal.__get__(self.hub)
  self.hub.transfers.schedule_queues=Transfers.schedule_queues.__get__(self.hub.transfers)
  signed_mesh(self.f)
  self.hub.refresh_inventory=lambda *a:None
  self.hub.inventories[self.f.b['node_id']]={'complete':True,'wallets':[]}
  self.caps=['wallet_transfer','wallet_relay_v1'];self.hub.caps={n['node_id']:set(self.caps) for n in (self.f.a,self.f.b)}
  with self.hub.edit() as state:
   for n in (self.f.a,self.f.b):state['nodes'][n['node_id']]={}
 def exchange(self,n,items=None):return self.hub.exchange(n['connection_token'],{'version':1,'outbox':items or [],'known_vaults':[],'capabilities':self.caps})
 def test_new_sync_routes_by_authenticated_keys_without_node_ip_addresses(self):
  r=self.exchange(self.f.b);rows=next(p['requests'] for p in r['proposals'] if p['kind']=='wallet_sync_queue');self.assertEqual(len(rows),1);p=rows[0];self.assertEqual(p['transfer_version'],3);self.assertIsNone(p['peer']['ipv6']);self.assertIsNone(p['node_ipv6']);self.assertEqual(p['transport']['cipher_suite'],CIPHER)
  state=self.hub.read();self.assertEqual({r['state'] for r in state['requests'].values()},{'pending'})
 def test_no_fallback_when_an_agent_channel_is_missing(self):
  self.hub.relay.channels.clear();r=self.exchange(self.f.b);rows=next(p['requests'] for p in r['proposals'] if p['kind']=='wallet_sync_queue');self.assertEqual(rows,[]);self.assertFalse(any(row.get('proposal') for row in self.hub.read()['requests'].values()))
 def test_new_v3_preview_binds_the_actual_noise_peer_and_survives_profile_validation(self):
  from agent_hub import digest
  from wallet_preview import NAMESPACE as NS
  self.exchange(self.f.b);reply=self.exchange(self.f.a);source=next(p['requests'][0] for p in reply['proposals'] if p['kind']=='wallet_sync_queue');preview={'version':3,'vaults':[],'address_labels':[],'transfer_id':source['transfer_id'],'challenge':source['preview_challenge'],'sender_ipv6':None,'receiver_ipv6':None,'transport':source['transport'],'public_wallet':source['public_wallet'],'chain':'main','funded_outputs':[],'node_tip':{'height':999000,'hash':'a'*64},'generated_at':int(time.time())}
  key=self.f.keys[self.f.a['node_id']];file=Path(self.f.tmp.name)/'preview-v3';file.write_bytes(canonical(preview));subprocess.run(['ssh-keygen','-q','-Y','sign','-f',str(key),'-n',NS,str(file)],check=True,capture_output=True)
  payload={'request_hash':digest(source),'preview':preview,'public_key':source['transport']['sender_identity'],'signature':base64.b64encode(file.with_suffix('.sig').read_bytes()).decode()};item=self.f.item('wallet_transfer_preview',payload);self.assertIn(item['id'],self.exchange(self.f.a,[item])['accepted'])
  from agent_state import validate
  validate(self.hub.read(),{self.f.user},self.f.config)
 def test_new_multisig_proposal_requires_mesh_and_binds_peer_protocol(self):
  from test_build11 import Ceremony
  c=Ceremony();c.setUp();self.addCleanup(c.doCleanups);h,row=c.start();self.assertEqual(row['proposal']['version'],2);self.assertEqual(row['proposal']['peer_transport']['cipher_suite'],CIPHER)
  before=copy.deepcopy(c.setup.read());c.hub.relay.channels.clear();self.assertFalse(c.setup.proposals(c.a['node_id'],c.a['connection_token']));self.assertEqual(c.setup.read()['sessions'][h]['proposal'],before['sessions'][h]['proposal'])
 def test_new_multisig_cannot_start_without_qr_paired_channels(self):
  from test_build11 import Ceremony
  c=Ceremony();c.setUp();self.addCleanup(c.doCleanups);c.hub.relay.channels.clear()
  with self.assertRaisesRegex(ValueError,'QR-pair'):c.start()
  self.assertFalse(c.setup.read()['sessions'])

class HTTPAuthentication(unittest.TestCase):
 def test_user_id_shortcut_and_unauthenticated_data_and_admin_are_rejected(self):
  import http.client,threading
  from launch_wallaby_wallet_server import create_server
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);cfg=root/'config.cfg';f=FamilyStore(cfg);f.save_user('Example','green',revision=0,date_of_birth='01/01/1980');uid=f.snapshot()['users'][0]['id'];server,pool=create_server(root/'cache',0,cfg,ipv6=False);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
   try:
    def request(path,data=None,token=None):
     c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5);headers={'Content-Type':'application/json','X-Wallaby-Request':'1'}
     if token:headers['X-Session-Token']=token
     c.request('POST' if data is not None else 'GET',path,json.dumps(data) if data is not None else None,headers);r=c.getresponse();result=json.loads(r.read());status=r.status;c.close();return status,result
    _,r=request('/api/session',{});token=r['token'];status,family=request('/api/family',token=token);self.assertEqual(status,200);self.assertNotIn('date_of_birth',family['users'][0]);self.assertFalse(family['ownership']);self.assertIsNone(family['user'])
    self.assertEqual(request('/api/login',{'user_id':uid},token)[0],400);self.assertEqual(request('/api/nodes',token=token)[0],401);self.assertEqual(request('/api/profile/clear',{},token)[0],400);self.assertEqual(request('/api/users/save',{'name':'Attacker'},token)[0],400)
   finally:server.shutdown();server.server_close();thread.join(3)

class CurrentRefresh(unittest.TestCase):
 def setUp(self):
  from test_build80 import GroupedApproval
  self.f=GroupedApproval();self.f.setUp();self.addCleanup(self.f.doCleanups)
 def test_new_policy_hash_binds_peer_requirements_and_old_clients_are_withheld(self):
  from wallet_policy_updates import proposals
  from agent_hub import digest
  self.f.begin();node=next(iter(self.f.rows));p=self.f.rows[node]['proposal'];self.assertEqual(p['version'],2);self.assertEqual(p['peer_transport']['cipher_suite'],CIPHER);receipt=self.f.receipt(node);changed=copy.deepcopy(p);changed['peer_transport']['required_agent_keys'].reverse();self.assertNotEqual(digest(changed),receipt['message']['request_hash'])
  self.f.hub.caps[node].discard('wallet_policy_refresh_relay_v1');self.assertFalse(proposals(self.f.hub,node));self.f.hub.caps[node].add('wallet_policy_refresh_relay_v1');self.assertEqual(proposals(self.f.hub,node)[0],p)
 def test_missing_mesh_cannot_reserve_a_new_address_or_alter_builder(self):
  from vault_refresh import finish
  from builder_destinations import Destinations
  self.f.hub.relay.channels.clear();before=self.f.work.read();destinations=Destinations(self.f.f.f.config).read()
  with self.assertRaisesRegex(ValueError,'QR-pair'):finish(self.f.hub,self.f.user,1000100)
  self.assertEqual(before,self.f.work.read());self.assertEqual(destinations,Destinations(self.f.f.f.config).read())

class ProfileAndPhone(unittest.TestCase):
 setUp=Passwords.setUp
 client=Passwords.client
 begin=Passwords.begin
 enroll=Passwords.enroll
 login=Passwords.login
 def test_profile_roundtrip_preserves_password_and_in_progress_builder(self):
  from profile_archive import ProfileArchive
  from builder_workspace import BuilderWorkspace
  work=BuilderWorkspace(self.config).start(self.uid,'transaction');before=BuilderWorkspace(self.config).read();self.enroll();archive=ProfileArchive(self.config).save();restored=self.root/'restored/config.cfg';FamilyStore(restored);ProfileArchive(restored).load('profile.7z',archive);self.assertEqual(BuilderWorkspace(restored).read(),before);self.config=restored;self.auth=PasswordAuth(restored);r,p=self.login('restored-browser');self.assertEqual(self.auth.finish('restored-browser',{'id':r['id'],'request':p['finishLoginRequest']}),self.uid)
 def test_phone_requires_password_and_cannot_authenticate_another_user(self):
  from test_wallet_server1 import Mobile
  fixture=Mobile();fixture.setUp();self.addCleanup(fixture.doCleanups);self.config=fixture.config;self.uid=fixture.uid;self.auth=PasswordAuth(self.config);fixture.devices.auth=self.auth;self.enroll();token,_,_=fixture.connected()
  with self.assertRaisesRegex(ValueError,'password'):fixture.devices.data(token,'balances')
  c=self.client('startLogin',password=self.password)
  with self.assertRaisesRegex(ValueError,'different user'):fixture.devices.authenticate(token,'start',{'user_id':'f'*32,'mode':'login','request':c['startLoginRequest']})
  r=fixture.devices.authenticate(token,'start',{'user_id':self.uid,'mode':'login','request':c['startLoginRequest']});p=self.client('finishLogin',password=self.password,clientLoginState=c['clientLoginState'],loginResponse=r['response'],identifiers={'client':self.uid,'server':r['server_identity']},keyStretching={'argon2id-custom':{'iterations':3,'memory':65536,'parallelism':1}});self.assertTrue(fixture.devices.authenticate(token,'finish',{'id':r['id'],'request':p['finishLoginRequest']})['authenticated']);self.assertFalse(fixture.devices.data(token,'balances')['available']);fixture.devices.sessions[token]['account_authenticated_until']=0
  with self.assertRaisesRegex(ValueError,'password'):fixture.devices.data(token,'balances')

if __name__=='__main__':unittest.main()
