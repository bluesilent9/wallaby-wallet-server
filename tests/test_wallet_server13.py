"""Agent-signed archive origin survives the Server courier and saved state."""
import base64,copy,json,os,subprocess,sys,time,unittest
from pathlib import Path
import test_wallet_server2 as fixtures
from agent_hub import digest
from wallet_preview import canonical,NAMESPACE,verify,validate
from wallet_sync_offers import validate_saved

class SignedStorage(unittest.TestCase):
 setUp=fixtures.CurrentProtocol.setUp
 exchange=fixtures.CurrentProtocol.exchange
 def start(self):
  self.caps.append('wallet_sync_offers_v1')
  for n in (self.f.a,self.f.b):self.hub.caps[n['node_id']]=set(self.caps)
  reply=self.exchange(self.f.a)
  return next(p['requests'][0] for p in reply['proposals'] if p['kind']=='wallet_sync_queue')
 def signed(self,p,storage='disc',serial=0):
  v={'version':3,'vaults':[],'address_labels':[],'transfer_id':p['transfer_id'],'challenge':p['preview_challenge'],'sender_ipv6':None,'receiver_ipv6':None,'transport':p['transport'],'public_wallet':p['public_wallet'],'chain':'main','funded_outputs':[],'node_tip':{'height':999000+serial,'hash':'a'*64},'generated_at':int(time.time())}
  if storage is not None:v['source_storage']=storage
  file=Path(self.f.tmp.name)/('preview-'+str(storage)+'-'+str(serial));file.write_bytes(canonical(v));subprocess.run(['ssh-keygen','-q','-Y','sign','-f',str(self.f.keys[self.f.a['node_id']]),'-n',NAMESPACE,str(file)],check=True,capture_output=True)
  return {'preview':v,'public_key':p['transport']['sender_identity'],'signature':base64.b64encode(file.with_suffix('.sig').read_bytes()).decode()}
 def send(self,p,wire):
  item=self.f.item('wallet_transfer_preview',{'request_hash':digest(p),**wire});reply=self.exchange(self.f.a,[item]);self.assertIn(item['id'],reply['accepted']);return self.exchange(self.f.b)
 def test_signed_disc_forwarding_is_byte_exact_and_survives_profile_validation(self):
  p=self.start();wire=self.signed(p);before=copy.deepcopy(self.hub.read()['requests']);reply=self.send(p,wire)
  delivered=next(r for r in reply['proposals'] if r['kind']=='wallet_transfer_preview');self.assertEqual({k:v for k,v in delivered.items() if k!='kind'},wire)
  state=self.hub.read()
  for key,row in before.items():self.assertEqual(state['requests'][key]['proposal'],row['proposal']);self.assertEqual(state['requests'][key]['state'],'pending');self.assertFalse(state['requests'][key].get('active_pair'))
  from agent_state import validate as profile_validate
  profile_validate(json.loads(json.dumps(state)),{self.f.user},self.f.config)
  for node in (self.f.a,self.f.b):
   offer=state['nodes'][node['node_id']]['sync_offer_snapshot'][0];self.assertEqual(offer['source_storage'],'disc');validate_saved(state['nodes'][node['node_id']])
 def test_unknown_storage_not_inferred_from_inventory_names_or_request(self):
  p=self.start();self.assertNotIn('source_storage',p)
  before=self.hub.read()['nodes'][self.f.b['node_id']]['sync_offer_snapshot'][0];self.assertNotIn('source_storage',before)
  reply=self.send(p,self.signed(p,None));o=next(r for r in reply['proposals'] if r['kind']=='wallet_sync_offers')['offers'][0];self.assertNotIn('source_storage',o)
 def test_explicit_node_origin_is_preserved(self):
  p=self.start();wire=self.signed(p,'node');reply=self.send(p,wire);self.assertEqual(next(r for r in reply['proposals'] if r['kind']=='wallet_transfer_preview')['preview']['source_storage'],'node')
 def test_tampering_with_storage_invalidates_signature_and_unknown_values_rejected(self):
  p=self.start();wire=self.signed(p);bad=copy.deepcopy(wire);bad['preview']['source_storage']='node'
  with self.assertRaisesRegex(ValueError,'signature'):verify(self.f.config,bad)
  for value in ('archive','',None,True,[],{}):
   bad=copy.deepcopy(wire);bad['preview']['source_storage']=value
   with self.assertRaises(ValueError):validate(bad)
  bad=copy.deepcopy(wire);bad['preview']['version']=2;bad['preview'].pop('transport')
  with self.assertRaises(ValueError):validate(bad)
  self.assertFalse(any(r.get('signed_preview') for r in self.hub.read()['requests'].values()))
 def test_saved_offer_rejects_invalid_origin_and_other_extra_fields(self):
  p=self.start();self.send(p,self.signed(p));entry=self.hub.read()['nodes'][self.f.b['node_id']]
  for key,value in (('source_storage','unknown'),('source_storage',False),('private_key','forbidden')):
   bad=copy.deepcopy(entry);bad['sync_offer_snapshot'][0][key]=value
   with self.assertRaises(ValueError):validate_saved(bad)
 def test_preview_renewal_retains_signed_disc_evidence_without_reusing_it(self):
  for n in (self.f.a,self.f.b):self.hub.inventory_times[n['node_id']]=time.monotonic()
  p=self.start();wire=self.signed(p);self.send(p,wire);self.send(p,self.signed(p,serial=1));state=self.hub.read()
  old=next(r for r in state['requests'].values() if r.get('superseded_attempt') and r['direction']=='send');self.assertEqual(old['signed_preview'],wire)
  fresh=[r for r in state['requests'].values() if r.get('retry_of')];self.assertEqual(len(fresh),2);self.assertTrue(all(not r.get('signed_preview') for r in fresh))
  new=next(r['proposal'] for r in fresh if r['direction']=='send');reply=self.send(new,self.signed(new,serial=2));self.assertEqual(next(r for r in reply['proposals'] if r['kind']=='wallet_transfer_preview')['preview']['source_storage'],'disc')
 def test_inventory_records_only_agent_origin_enum_without_private_paths(self):
  from unittest.mock import patch
  from agent_hub import AgentHub
  raw=copy.deepcopy(self.f.wallet['raw']);name=raw['wallet_name']
  def rpc(node,method,params=None,wallet=None):
   if method=='listwallets':return [name]
   if method=='listwalletdir':return {'wallets':[{'name':name}]}
   if method=='getwalletinfo':return {'walletname':name,'private_keys_enabled':True,'wallaby_storage':'disc','wallet_path':'/private/archive/location'}
   if method=='listdescriptors':return raw
   raise AssertionError(method)
  node=self.f.a['node_id'];self.hub.inventory_times[node]=0
  with patch.object(self.hub,'rpc',side_effect=rpc):AgentHub.refresh_inventory(self.hub,node,self.f.a['connection_token'],requested=True)
  self.assertEqual(self.hub.inventories[node]['wallets'][0]['wallaby_storage'],'disc');self.assertNotIn('/private',json.dumps(self.hub.inventories[node]));self.assertNotIn('wallet_path',json.dumps(self.hub.read()))
 def inventory_origin(self,origin='disc'):
  node=self.f.a['node_id'];self.hub.inventory_times[node]=time.monotonic();self.hub.inventory_display[node]={'token':self.f.a['connection_token']}
  for w in self.hub.inventories[node]['wallets']:w['wallaby_storage']=origin
 def test_denied_offer_has_current_disc_inventory_hint_without_authority(self):
  from sync_permissions import policy_id
  self.inventory_origin();self.hub.permissions.live[self.f.b['node_id']]['record']['policies']=[policy_id(self.f.wallet['raw'])];self.caps.append('wallet_sync_offers_v1')
  for n in (self.f.a,self.f.b):self.hub.caps[n['node_id']]=set(self.caps)
  reply=self.exchange(self.f.b);offer=next(p for p in reply['proposals'] if p['kind']=='wallet_sync_offers')['offers'][0];self.assertEqual(offer['source_storage'],'disc');self.assertEqual(offer['status'],'disabled');self.assertFalse(any(r.get('proposal') for r in self.hub.read()['requests'].values()))
 def test_signed_preview_takes_precedence_over_inventory_hint(self):
  self.inventory_origin();p=self.start();reply=self.send(p,self.signed(p,None));offer=next(r for r in reply['proposals'] if r['kind']=='wallet_sync_offers')['offers'][0];self.assertNotIn('source_storage',offer)
 def test_stale_reconnected_ambiguous_or_unknown_inventory_origin_is_omitted(self):
  self.inventory_origin();p=self.start();original=copy.deepcopy(self.hub.inventories[self.f.a['node_id']]['wallets'])
  for cause in ('stale','reconnected','ambiguous','unknown'):
   self.inventory_origin();self.hub.inventories[self.f.a['node_id']]['wallets']=copy.deepcopy(original)
   if cause=='stale':self.hub.inventory_times[self.f.a['node_id']]=time.monotonic()-61
   elif cause=='reconnected':self.hub.inventory_display[self.f.a['node_id']]['token']='old-session'
   elif cause=='ambiguous':
    w=copy.deepcopy(original[0]);w['wallaby_storage']='node';self.hub.inventories[self.f.a['node_id']]['wallets'].append(w)
   else:self.hub.inventories[self.f.a['node_id']]['wallets'][0]['wallaby_storage']='unknown'
   reply=self.exchange(self.f.b);offer=next(r for r in reply['proposals'] if r['kind']=='wallet_sync_offers')['offers'][0];self.assertNotIn('source_storage',offer,cause)
 def test_agent93_verifies_forwarded_signature_and_displays_disc_without_approval(self):
  source=os.environ.get('WALLABY_AGENT_CURRENT_SOURCE')
  if not source:self.skipTest('Set current Agent source')
  p=self.start();wire=self.signed(p);reply=self.send(p,wire);offer=next(r for r in reply['proposals'] if r['kind']=='wallet_sync_offers')
  code='''import json,sys,tempfile
sys.path.insert(0,sys.argv[1])
from approval_store import Store
from wallet_preview import verify
from sync_offers import apply
from sync_table import state
wire,offer=json.loads(sys.stdin.read())
with tempfile.TemporaryDirectory() as tmp:
 s=Store(tmp,persistence=False);s.persistence=None
 verify(s,wire);apply(s,offer,'test-session');rows=state(s,[])['wallets']
 assert len(rows)==1 and rows[0]['traits']['disc']
 assert not s.read()['pending'] and not s.read().get('active_transfer')
 print('Agent93 signature, disc icon and no-approval checks passed')
'''
  r=subprocess.run([sys.executable,'-B','-c',code,source],input=json.dumps([wire,offer]),capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)

if __name__=='__main__':unittest.main()
