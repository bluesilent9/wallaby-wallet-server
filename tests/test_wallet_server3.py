"""Direct-connection rendezvous, shared account admission and resource bounds."""
import base64,secrets,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
import test_wallet_server2 as fixture
from password_auth import PasswordAuth,OPAQUE_SLOTS,opaque
from secure_relay import PROTOCOL

class Admission(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.auth=PasswordAuth(Path(self.tmp.name)/'config.cfg')
 def test_ten_distinct_users_shared_across_browser_and_phone(self):
  for i in range(10):self.auth.admit_login(('mobile:' if i%2 else 'browser:')+str(i),str(i))
  self.auth.admit_login('mobile:second-device','0')
  with self.assertRaisesRegex(ValueError,'Ten users'):self.auth.admit_login('eleventh','10')
  self.auth.release_login('browser:0')
  with self.assertRaises(ValueError):self.auth.admit_login('eleventh','10')
  self.auth.release_login('mobile:second-device');self.auth.admit_login('eleventh','10')
 def test_expiry_rotation_and_reset(self):
  for i in range(10):self.auth.admit_login(str(i),str(i))
  self.auth.rotate_login('0','rotated');self.assertNotIn('0',self.auth.logins)
  self.auth.logins['rotated']['expires']=0;self.auth.admit_login('new','new')
  self.auth.reset();self.assertFalse(self.auth.logins)
 def test_expired_session_cannot_reanimate_without_password(self):
  self.auth.admit_login('old','owner');self.auth.logins['old']['expires']=0
  self.assertFalse(self.auth.touch_login('old'));self.assertNotIn('old',self.auth.logins)
 def test_mobile_lease_does_not_linger_for_browser_duration(self):
  self.auth.admit_login('mobile:phone','owner');self.assertLess(self.auth.logins['mobile:phone']['expires']-time.monotonic(),901)
  self.auth.touch_login('mobile:phone',20);self.assertLess(self.auth.logins['mobile:phone']['expires']-time.monotonic(),21)
 def test_concurrent_admission_never_exceeds_ten_users(self):
  barrier=threading.Barrier(20);accepted=[]
  def login(i):
   barrier.wait()
   try:self.auth.admit_login(str(i),str(i));accepted.append(i)
   except ValueError:pass
  threads=[threading.Thread(target=login,args=(i,)) for i in range(20)]
  for t in threads:t.start()
  for t in threads:t.join()
  self.assertEqual(len(accepted),10)
 def test_single_user_cannot_allocate_unbounded_sessions(self):
  for i in range(64):self.auth.admit_login(str(i),'same')
  with self.assertRaises(ValueError):self.auth.admit_login('extra','same')
 def test_busy_opaque_service_starts_no_extra_process(self):
  OPAQUE_SLOTS.acquire();OPAQUE_SLOTS.acquire()
  try:
   with patch('password_auth.subprocess.run') as run:
    with self.assertRaisesRegex(ValueError,'busy'):opaque('setup')
    run.assert_not_called()
  finally:OPAQUE_SLOTS.release();OPAQUE_SLOTS.release()

 def test_real_opaque_enrollment_obeys_capacity_without_claiming_account(self):
  f=fixture.Passwords();f.setUp()
  try:
   for i in range(10):f.auth.admit_login(str(i),'other-'+str(i))
   with self.assertRaisesRegex(ValueError,'Ten users'):f.enroll()
   self.assertTrue(f.auth.metadata(f.uid)['registration_required'])
   f.auth.release_login('0');f.enroll();self.assertFalse(f.auth.metadata(f.uid)['registration_required'])
  finally:f.doCleanups()
 def test_expired_browser_is_logged_out_before_account_access(self):
  from launch_wallaby_wallet_server import Sessions
  from types import SimpleNamespace
  manager=Sessions.__new__(Sessions);manager.lock=threading.RLock();manager.auth=self.auth
  session=SimpleNamespace(password_authenticated=True,user_id='owner',token='token',last_seen=time.monotonic())
  session.select_user=lambda uid:setattr(session,'user_id',uid)
  manager.sessions={'token':session};self.auth.admit_login('token','owner');self.auth.logins['token']['expires']=0
  self.assertIs(manager.get('token'),session);self.assertIsNone(session.user_id)

class Rendezvous(unittest.TestCase):
 setUp=fixture.Relay.setUp
 sign=fixture.Relay.sign
 register=fixture.Relay.register
 report=fixture.Relay.report
 frame=fixture.Relay.frame
 def path(self,i,j,epoch='e'*64,channel='a'*64,transport='direct-ssh',state='ready'):
  p,key=self.peers[i];peer=self.peers[j][0];c=self.relay.dispatch(p,{'action':'challenge'})
  m={'protocol':PROTOCOL,'version':1,'kind':'path','endpoint_id':p['id'],'role':p['role'],'challenge':c['challenge'],'peer_id':peer['id'],'channel_id':channel,'epoch_id':epoch,'transport':transport,'state':state}
  return self.relay.dispatch(p,{'action':'path','proof':self.sign(p,key,m)})
 def ready(self):
  self.register(0);self.register(1);self.report(0,1);self.report(1,0)
 def test_policy_has_no_password_or_server_dialing(self):
  p=self.relay.dispatch(self.peers[0][0],{'action':'policy'})
  self.assertTrue(p['direct_preferred']);self.assertFalse(p['password_bootstrap']);self.assertFalse(p['server_dials_peer_addresses']);self.assertEqual(p['ssh_credential_max_age_seconds'],86400)
 def test_direct_status_requires_matching_live_attestations(self):
  self.ready();self.path(0,1);self.assertEqual(self.relay.mesh(['0','1'])['pairs'][0]['transport'],'relay')
  self.path(1,0,epoch='f'*64);self.assertEqual(self.relay.mesh(['0','1'])['pairs'][0]['transport'],'relay')
  self.path(1,0);self.assertEqual(self.relay.mesh(['0','1'])['pairs'][0]['transport'],'direct-ssh')
  self.relay.paths[(self.peers[0][0]['id'],self.peers[1][0]['id'])]['expires']=0
  self.assertEqual(self.relay.mesh(['0','1'])['pairs'][0]['transport'],'relay')
 def test_unpaired_channel_or_changed_channel_cannot_report_direct(self):
  self.register(0);self.register(1)
  with self.assertRaises(ValueError):self.path(0,1)
  self.report(0,1)
  with self.assertRaises(ValueError):self.path(0,1,channel='c'*64)
 def test_mobile_mobile_courier_still_cannot_count_as_agents(self):
  old,key=self.peers[1];p=self.relay.principal('mobile',old['identity_key'],old['owner'],old['scope']);self.peers[1]=(p,key)
  self.register(1);self.register(2);self.report(1,2);self.report(2,1)
  a=self.peers[1][0];b=self.peers[2][0];f=self.frame(a,b)
  self.relay.dispatch(a,{'action':'send','frame':f});self.assertEqual(self.relay.dispatch(b,{'action':'receive'})['frames'],[f])
  self.assertEqual(len(self.relay.dispatch(a,{'action':'directory'})['endpoints']),2)
  self.assertFalse(self.relay.mesh(['1','2'])['ready'])
 def test_byte_limit_and_idempotent_retry(self):
  self.ready();p=self.peers[0][0];f=self.frame();self.relay.dispatch(p,{'action':'send','frame':f})
  self.relay.byte_rates[p['id']]=(2097152,time.monotonic())
  self.relay.dispatch(p,{'action':'send','frame':f})
  with self.assertRaisesRegex(ValueError,'byte limit'):self.relay.dispatch(p,{'action':'send','frame':self.frame()})
 def test_control_flood_is_bounded_and_reset_clears_counters(self):
  p=self.peers[0][0];self.relay.action_rates[p['id']]=(600,time.monotonic())
  with self.assertRaisesRegex(ValueError,'request limit'):self.relay.dispatch(p,{'action':'policy'})
  self.relay.reset();self.relay.dispatch(p,{'action':'policy'})
 def test_global_limit_survives_change_of_endpoint(self):
  self.relay.action_rates['*']=(6000,time.monotonic())
  for p,_ in self.peers:
   with self.assertRaises(ValueError):self.relay.dispatch(p,{'action':'challenge'})
 def test_path_rejects_plaintext_credentials(self):
  self.ready();p=self.peers[0][0]
  with self.assertRaises(ValueError):self.relay.dispatch(p,{'action':'path','proof':{},'ssh_password':'never-allowed'})
