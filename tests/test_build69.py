"""Creation identity survives approved additive policy generations only."""
import copy,json,tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from descriptor_store import clean_wallet
from setup_wallet_views import SetupWalletViews
from storage import data_directory
from vendor.embit import bip32
from vendor.embit.descriptor.checksum import checksum
from wallet_names import display_summary
from preferences import resource_id

class Naming(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.cfg=Path(self.tmp.name)/'config.cfg';self.data=data_directory(self.cfg);self.data.mkdir()
  self.keys=[bip32.HDKey.from_seed(bytes([i])*32).to_public().to_base58() for i in range(1,6)];self.original=self.rows(100)
  self.session={'proposal':{'name':'Treasury'},'descriptors':self.original,'state':'ready','routes':{},'completion_confirmed':{},'contributions':{}};self.save()
 def rows(self,height,threshold=3):
  result=[]
  for branch in range(2):
   body='wsh(and_v(v:after('+str(height)+'),multi('+str(threshold)+','+','.join(k+'/'+str(branch)+'/*' for k in self.keys)+')))';result.append(body+'#'+checksum(body))
  return result
 def save(self,requests=None):
  (self.data/'wallet-setups.json').write_text(json.dumps({'sessions':{'setup':self.session}}))
  if requests is not None:(self.data/'agent-hub.json').write_text(json.dumps({'requests':requests}))
 def request(self,old,new,state='complete'):
  return {'kind':'wallet_policy_refresh','state':state,'proposal':{'previous_descriptors':old,'receive_descriptor':new[0],'change_descriptor':new[1]}}
 def wallet(self,rows):
  return clean_wallet({'wallet_name':'Treasury Australia - Signer','descriptors':[{'desc':d,'range':[0,10],'internal':bool(i%2),'timestamp':1} for i,d in enumerate(rows)]})
 def test_three_refreshes_preserve_overall_name_without_relying_on_ownership(self):
  rows=list(self.original);old=self.original;requests={}
  for height in (100,200,300,400):
   if height!=100:
    new=self.rows(height);requests[str(height)]=self.request(old,new);rows+=new;old=new
   self.save(requests);w=SetupWalletViews(self.cfg).annotate(self.wallet(rows));self.assertEqual(w['setup_name'],'Treasury');self.assertEqual(display_summary({'wallets':[w]},{'ownership':[]})['wallets'][0]['name'],'Treasury');self.assertEqual(w['raw']['wallet_name'],'Treasury Australia - Signer')
 def test_pending_denied_or_failed_transitions_cannot_establish_identity(self):
  new=self.rows(200)
  for state in ('pending','denied','error'):
   self.save({'r':self.request(self.original,new,state)});self.assertNotIn('setup_name',SetupWalletViews(self.cfg).annotate(self.wallet(self.original+new)))
 def test_unrelated_descriptor_cannot_borrow_setup_name(self):
  new=self.rows(200);self.save({'r':self.request(self.original,new)});w=self.wallet(self.original+new+self.rows(300,2));self.assertNotIn('setup_name',SetupWalletViews(self.cfg).annotate(w))
 def test_missing_original_branch_or_discontinuous_generation_is_not_matched(self):
  new=self.rows(200);later=self.rows(300);self.save({'r':self.request(new,later)})
  for rows in (self.original[:1]+later,self.original+later):self.assertNotIn('setup_name',SetupWalletViews(self.cfg).annotate(self.wallet(rows)))
 def test_confirmed_dashboard_rename_still_wins(self):
  new=self.rows(200);self.save({'r':self.request(self.original,new)});w=SetupWalletViews(self.cfg).annotate(self.wallet(self.original+new));family={'ownership':[{'id':resource_id('descriptor',w['id']),'kind':'descriptor','source':w['id'],'name':'Treasury','dashboard_name':'Household Treasury','confirmed':True}]};self.assertEqual(display_summary({'wallets':[w]},family)['wallets'][0]['name'],'Household Treasury')
