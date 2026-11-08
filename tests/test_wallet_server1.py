"""Server rename migration and independent, SSH-only mobile verification."""
import base64,copy,json,sys,tempfile,subprocess,unittest,threading,http.client
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mobile_devices import MobileDevices,digest,PAIR_NAMESPACE,CONNECT_NAMESPACE,RESULT_NAMESPACE
from setup_signatures import canonical
from preferences import FamilyStore
from profile_archive import ProfileGate,ProfileArchive
from mobile_transport import create_mobile_server
from install_migration import migrate

class Mobile(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.config=self.root/'config.cfg';family=FamilyStore(self.config);family.save_user('Example','green',revision=0,date_of_birth='01/01/1980');self.uid=family.snapshot()['users'][0]['id'];self.key=self.root/'phone'
  subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(self.key)],check=True);self.public=' '.join(self.key.with_suffix('.pub').read_text().split()[:2]);self.state={'requests':{},'nodes':{}}
  self.builder={'identities':{},'sessions':{}};self.hub=SimpleNamespace(read=lambda:copy.deepcopy(self.state),wallet_builder=SimpleNamespace(read=lambda:copy.deepcopy(self.builder)));self.devices=MobileDevices(self.config,self.hub);self.devices.mobile_port=56444;self.devices.ssh_host_public_key=self.public
 def proof(self,message,namespace):
  file=self.root/'message';file.write_bytes(canonical(message));file.with_suffix('.sig').unlink(missing_ok=True);subprocess.run(['ssh-keygen','-q','-Y','sign','-f',str(self.key),'-n',namespace,str(file)],check=True,capture_output=True)
  return {'message':message,'public_key':self.public,'signature':base64.b64encode(file.with_suffix('.sig').read_bytes()).decode()}
 def pending(self):
  invitation=self.devices.invite(self.uid,{'host':'example.test','user':'example','port':22});p=invitation['payload'];m={k:p[k] for k in ('protocol','version','server_id','invitation_id','secret')};m.update(purpose='pair',public_key=self.public,name='Example phone',ssh_host_fingerprint=p['ssh']['host_fingerprint']);data={'invitation_id':p['invitation_id'],'secret':p['secret'],'public_key':self.public,'name':'Example phone','proof':self.proof(m,PAIR_NAMESPACE)};return self.devices.join(data),data,invitation
 def paired(self):
  row,_,_=self.pending();self.devices.approve(self.uid,row['device_id'],row['comparison_code']);return row
 def connected(self):
  row=self.paired();m=self.devices.challenge(row['device_id']);proof=self.proof(m,CONNECT_NAMESPACE);return self.devices.connect(proof)['token'],row,proof
 def test_qr_uses_separate_ssh_mobile_port_and_actual_host_identity(self):
  _,_,invite=self.pending();p=invite['payload'];self.assertEqual(p['transport'],'ssh-loopback');self.assertEqual(p['ssh']['forward_port'],56444);self.assertEqual(p['ssh']['forward_host'],'127.0.0.1');self.assertEqual(p['ssh']['host_public_key'],self.public);self.assertIn('<svg',invite['qr_svg']);self.assertNotIn('https',json.dumps(p))
 def test_pairing_needs_explicit_matching_browser_confirmation(self):
  row,_,_=self.pending()
  with self.assertRaises(ValueError):self.devices.challenge(row['device_id'])
  with self.assertRaises(ValueError):self.devices.approve('different-user',row['device_id'],row['comparison_code'])
  with self.assertRaises(ValueError):self.devices.approve(self.uid,row['device_id'],'wrong')
  self.devices.approve(self.uid,row['device_id'],row['comparison_code']);self.assertTrue(self.devices.challenge(row['device_id']))
 def test_invitation_single_use_and_signature_binding(self):
  _,data,_=self.pending()
  with self.assertRaises(ValueError):self.devices.join(data)
 def test_expired_invitation_rejected(self):
  invite=self.devices.invite(self.uid,{'host':'example.test','user':'example','port':22});self.devices.invites[invite['payload']['invitation_id']]['expires']=0
  with self.assertRaises(ValueError):self.devices.join({'invitation_id':invite['payload']['invitation_id'],'secret':invite['payload']['secret']})
 def test_connect_is_signed_and_replay_protected(self):
  token,row,proof=self.connected();self.assertTrue(self.devices.claims(token));self.assertTrue(self.devices.snapshot(self.uid)['devices'][0]['connected'])
  with self.assertRaises(ValueError):self.devices.connect(proof)
 def test_revocation_survives_restart_and_invalidates_session(self):
  token,row,_=self.connected();self.devices.revoke(self.uid,row['device_id'])
  with self.assertRaises(ValueError):self.devices.claims(token)
  restarted=MobileDevices(self.config,self.hub)
  with self.assertRaises(ValueError):restarted.challenge(row['device_id'])
 def test_wrong_signature_namespace_cannot_connect(self):
  row=self.paired();m=self.devices.challenge(row['device_id'])
  with self.assertRaises(ValueError):self.devices.connect(self.proof(m,PAIR_NAMESPACE))
 def test_only_current_public_claims_are_exposed_and_scoped(self):
  token,_,_=self.connected();self.state['requests']={'mine':{'user_id':self.uid,'kind':'wallet_policy_refresh','node_id':'node','state':'pending','proposal':{'public_fact':'current'},'created_utc':'2026-01-01T00:00:00Z'},'other':{'user_id':'other','kind':'sign_psbt_partial','node_id':'node','state':'pending','proposal':{'psbt':'not-for-this-phone'},'created_utc':'2026-01-01T00:00:00Z'}}
  claims=self.devices.claims(token);self.assertEqual([c['id'] for c in claims['claims']],['mine']);self.assertNotIn('psbt',json.dumps(claims));self.state['requests']['mine']['state']='complete';self.assertFalse(self.devices.claims(token)['claims'])
 def test_advisory_result_never_authorises_wallet_operations_and_cannot_replay(self):
  token,row,_=self.connected();claims=self.devices.claims(token);m={'protocol':claims['protocol'],'version':1,'purpose':'comparison','server_id':claims['server_id'],'device_id':row['device_id'],'challenge':claims['challenge'],'claims_digest':claims['claims_digest'],'matches':[],'mismatches':[]};proof=self.proof(m,RESULT_NAMESPACE);before=copy.deepcopy(self.state);self.assertFalse(self.devices.result(token,proof)['approval_authority']);self.assertEqual(before,self.state)
  with self.assertRaises(ValueError):self.devices.result(token,proof)
 def test_changed_claims_invalidate_previous_comparison(self):
  token,row,_=self.connected();claims=self.devices.claims(token);m={'protocol':claims['protocol'],'version':1,'purpose':'comparison','server_id':claims['server_id'],'device_id':row['device_id'],'challenge':claims['challenge'],'claims_digest':claims['claims_digest'],'matches':[],'mismatches':[]};self.state['requests']['new']={'user_id':self.uid,'kind':'wallet_retire','node_id':'node','state':'pending','proposal':{'changed':True},'created_utc':'2026-01-01T00:00:00Z'}
  with self.assertRaises(ValueError):self.devices.result(token,self.proof(m,RESULT_NAMESPACE))
 def test_profile_backup_does_not_restore_old_mobile_access_grants(self):
  row=self.paired();target=self.root/'restored/config.cfg';FamilyStore(target);ProfileArchive(target).load('profile.7z',ProfileArchive(self.config).save());restored=MobileDevices(target,self.hub);self.assertFalse(restored.state()['devices']);self.assertNotEqual(restored.state()['server_id'],self.devices.state()['server_id'])
 def test_public_network_listener_is_forbidden(self):
  with self.assertRaises(ValueError):create_mobile_server(self.devices,'0.0.0.0',0,self.key.with_suffix('.pub'),ProfileGate())
 def test_real_mobile_loopback_listener_rejects_browser_and_other_protocols(self):
  server=create_mobile_server(self.devices,'127.0.0.1',0,self.key.with_suffix('.pub'),ProfileGate());self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
  def request(headers,path='/mobile/v1/challenge',body='{}'):
   c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5);c.request('POST',path,body=body,headers=headers);r=c.getresponse();status=r.status;r.read();c.close();return status
  native={'Content-Type':'application/json','X-Wallaby-Mobile':'1'};self.assertEqual(request({}),403);self.assertEqual(request(dict(native,Origin='http://127.0.0.1')),403);self.assertEqual(request(native,'/api/nodes/rpc'),401);self.assertEqual(request(native,body='{"device_id":"x","device_id":"y"}'),400)

class AgentFacts(unittest.TestCase):
 setUp=Mobile.setUp
 proof=Mobile.proof
 def record(self):
  from mobile_agent_records import proposals,CAPABILITY,NAMESPACE
  self.hub.config=self.config;self.hub.mobile_verification_active=lambda:True;self.hub.permissions=SimpleNamespace(current=lambda node:None);self.builder['identities']['node']={'public_key':self.public};p=proposals(self.hub,'node',[CAPABILITY])[0]
  import time
  message={'protocol':'wallaby-wallet-verification','version':1,'kind':'agent_facts','challenge':p['challenge'],'agent_public_key':self.public,'agent_fingerprint':self.devices.snapshot(self.uid)['host_fingerprint'],'ssh_host_public_key':self.public,'ssh_host_fingerprint':self.devices.snapshot(self.uid)['host_fingerprint'],'ipv6':'2001:db8::1','hostname':'Example Agent','generated_at':int(time.time()),'expires_at':int(time.time())+90}
  return self.proof(message,NAMESPACE)
 def test_existing_agents_receive_no_new_protocol_without_opt_in(self):
  from mobile_agent_records import proposals
  self.hub.mobile_verification_active=lambda:True;self.assertFalse(proposals(self.hub,'node',[]))
 def test_fresh_agent_facts_are_signed_and_bound_to_current_challenge(self):
  from mobile_agent_records import accept,records
  proof=self.record();self.assertTrue(accept(self.hub,'node',proof));self.assertEqual(records(self.hub)['node'],proof);proof=copy.deepcopy(proof);proof['message']['ssh_host_fingerprint']='SHA256:incorrect'
  with self.assertRaises(ValueError):accept(self.hub,'node',proof)
 def test_authenticated_old_challenge_is_discarded_without_installation(self):
  from mobile_agent_records import accept,records
  proof=self.record();self.hub.mobile_verification_challenges['node']['challenge']='a'*64;self.assertFalse(accept(self.hub,'node',proof));self.assertFalse(records(self.hub))
 def test_agent_facts_are_requested_only_while_a_phone_is_present(self):
  from mobile_agent_records import proposals,CAPABILITY
  self.hub.mobile_verification_active=lambda:False;self.assertFalse(proposals(self.hub,'node',[CAPABILITY]))

class Migration(unittest.TestCase):
 def test_preserves_profiles_and_pending_operations_byte_for_byte(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)
   for parent in ('var/lib','var/cache'):
    old=root/parent/'wallaby-dashboard';old.mkdir(parents=True);(old/'pending.json').write_bytes(b'{"exact":"saved signatures, vault and rename history"}')
   moved=migrate(root);self.assertEqual(len(moved),2)
   for parent in ('var/lib','var/cache'):
    old=root/parent/'wallaby-dashboard';new=root/parent/'wallaby-wallet-server';self.assertTrue(old.is_symlink());self.assertEqual((old/'pending.json').read_bytes(),(new/'pending.json').read_bytes())
   self.assertEqual(migrate(root),[])
 def test_conflicting_profiles_never_merge_or_partly_move(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)
   for path in ('var/lib/wallaby-dashboard','var/cache/wallaby-dashboard','var/cache/wallaby-wallet-server'):
    p=root/path;p.mkdir(parents=True);(p/'record').write_text(path)
   with self.assertRaises(ValueError):migrate(root)
   self.assertFalse((root/'var/lib/wallaby-dashboard').is_symlink());self.assertFalse((root/'var/lib/wallaby-wallet-server').exists())
 def test_failed_second_move_rolls_first_back(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)
   for parent in ('var/lib','var/cache'):(root/parent/'wallaby-dashboard').mkdir(parents=True)
   original=Path.rename
   def fail(path,target):
    if str(path).endswith('var/cache/wallaby-dashboard'):raise OSError('Simulated failure')
    return original(path,target)
   with patch.object(Path,'rename',fail):
    with self.assertRaises(OSError):migrate(root)
   self.assertTrue((root/'var/lib/wallaby-dashboard').is_dir());self.assertFalse((root/'var/lib/wallaby-wallet-server').exists())

if __name__=='__main__':unittest.main()
