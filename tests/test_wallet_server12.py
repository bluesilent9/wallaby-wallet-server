"""Denied source discovery and fresh signed reviews after Agent restarts."""
import base64,copy,json,os,subprocess,sys,time,unittest
from pathlib import Path
import test_wallet_server2 as fixtures
from agent_hub import digest
from wallet_preview import canonical,NAMESPACE
from wallet_sync_queue import schedule
from sync_permissions import policy_id

class RenewedPreviews(unittest.TestCase):
 setUp=fixtures.CurrentProtocol.setUp
 exchange=fixtures.CurrentProtocol.exchange
 def proposal(self,node):
  reply=self.exchange(node)
  return next(p['requests'][0] for p in reply['proposals'] if p['kind']=='wallet_sync_queue')
 def signed(self,p,number):
  preview={'version':3,'vaults':[],'address_labels':[],'transfer_id':p['transfer_id'],'challenge':p['preview_challenge'],'sender_ipv6':None,'receiver_ipv6':None,'transport':p['transport'],'public_wallet':p['public_wallet'],'chain':'main','funded_outputs':[],'node_tip':{'height':999000+number,'hash':'a'*64},'generated_at':int(time.time())}
  file=Path(self.f.tmp.name)/('preview-'+str(number));file.write_bytes(canonical(preview));subprocess.run(['ssh-keygen','-q','-Y','sign','-f',str(self.f.keys[self.f.a['node_id']]),'-n',NAMESPACE,str(file)],check=True,capture_output=True)
  return self.f.item('wallet_transfer_preview',{'request_hash':digest(p),'preview':preview,'public_key':p['transport']['sender_identity'],'signature':base64.b64encode(file.with_suffix('.sig').read_bytes()).decode()})
 def fresh_inventory(self):
  for n in (self.f.a,self.f.b):self.hub.inventory_times[n['node_id']]=time.monotonic()
 def changed(self):
  self.fresh_inventory();p=self.proposal(self.f.a);one=self.signed(p,1);self.exchange(self.f.a,[one]);self.original=copy.deepcopy(self.hub.read()['requests']);two=self.signed(p,2);self.exchange(self.f.a,[two]);return p
 def test_restart_signed_preview_gets_new_challenge_and_no_reused_approval(self):
  old=self.changed();state=self.hub.read();fresh=[r for r in state['requests'].values() if r.get('retry_of')];self.assertEqual(len(fresh),2)
  for key,row in self.original.items():
   retained=state['requests'][key];self.assertEqual(retained['proposal'],row['proposal']);self.assertEqual(retained.get('signed_preview'),row.get('signed_preview'));self.assertTrue(retained['superseded_attempt'])
  p=next(r['proposal'] for r in fresh if r['direction']=='send');self.assertNotEqual(p['transfer_id'],old['transfer_id']);self.assertNotEqual(p['preview_challenge'],old['preview_challenge']);self.assertTrue(all(not any(r.get(k) for k in ('signed_preview','preview_proof','result','active_pair')) for r in fresh))
  # A third poll and a replay of the old public preview cannot create a loop.
  self.exchange(self.f.a);self.assertEqual(len(self.hub.read()['requests']),4)
  self.exchange(self.f.a,[self.signed(old,3)]);self.assertEqual(len(self.hub.read()['requests']),4)
  self.exchange(self.f.a,[self.signed(p,4)]);self.assertEqual(len(self.hub.read()['requests']),4)
  from agent_state import validate
  validate(self.hub.read(),{self.f.user},self.f.config)
 def test_denied_receiver_remains_discoverable_without_executable_request(self):
  self.caps.append('wallet_sync_offers_v1');self.hub.caps={n['node_id']:set(self.caps) for n in (self.f.a,self.f.b)};self.hub.permissions.live[self.f.b['node_id']]['record']['policies']=[policy_id(self.f.wallet['raw'])]
  for node in (self.f.a,self.f.b):
   reply=self.exchange(node);offer=next(p for p in reply['proposals'] if p['kind']=='wallet_sync_offers')['offers'][0];self.assertEqual(offer['status'],'disabled');self.assertEqual(offer['peer']['node_id'],self.f.b['node_id'] if node==self.f.a else self.f.a['node_id']);self.assertFalse(next(p for p in reply['proposals'] if p['kind']=='wallet_sync_queue')['requests'])
  self.assertFalse(any(r.get('proposal') for r in self.hub.read()['requests'].values()))
 def test_operation_evidence_or_local_denial_prevents_automatic_replacement(self):
  self.fresh_inventory();self.proposal(self.f.a);before=copy.deepcopy(self.hub.read()['requests'])
  for field,value in (('active_pair',True),('finished_utc','now'),('result',{'retained':'outcome'})):
   with self.hub.edit() as state:
    state['requests']=copy.deepcopy(before);sender=next(r for r in state['requests'].values() if r['direction']=='send');sender.update(preview_notice='Changed signed preview');sender[field]=value;schedule(self.hub.transfers,state)
   self.assertEqual(len(self.hub.read()['requests']),2)
  with self.hub.edit() as state:
   state['requests']=copy.deepcopy(before);next(iter(state['requests'].values()))['preview_notice']='Changed signed preview'
   self.hub.permissions.live[self.f.b['node_id']]['record']['policies']=[policy_id(self.f.wallet['raw'])];schedule(self.hub.transfers,state)
  self.assertEqual(len(self.hub.read()['requests']),2)
 def test_current_agent_accepts_new_review_and_preserves_active_old_work(self):
  source=os.environ.get('WALLABY_AGENT_CURRENT_SOURCE')
  if not source:self.skipTest('Set current Agent source')
  old=self.changed();new=next(r['proposal'] for r in self.hub.read()['requests'].values() if r.get('retry_of') and r['direction']=='send')
  code='''import json,sys,tempfile
sys.path.insert(0,sys.argv[1])
from approval_store import Store,digest
from sync_queue import apply_snapshot,freeze
old,new=json.loads(sys.stdin.read())
with tempfile.TemporaryDirectory() as tmp:
 store=Store(tmp,persistence=False);store.persistence=None
 apply_snapshot(store,1,[old]);key=digest(old)
 with store.edit() as s:s['sync_choices']={key:{'selected':True,'watch_only':True}}
 apply_snapshot(store,2,[new]);s=store.read();assert key not in s['pending'];assert digest(new) not in s.get('sync_choices',{})
 with store.edit() as s:s['pending'][key]={'proposal':old,'received':1,'state':'approved'};s['active_transfer']=key
 apply_snapshot(store,3,[new]);s=store.read();assert s['pending'][key]['withdrawn'];assert s['active_transfer']==key
 try:freeze(store,[digest(new)],new['direction'])
 except ValueError:pass
 else:raise AssertionError('Active work bypassed')
'''
  out=subprocess.run([sys.executable,'-B','-c',code,source],input=json.dumps([old,new]),capture_output=True,text=True);self.assertEqual(out.returncode,0,out.stderr)

if __name__=='__main__':unittest.main()
