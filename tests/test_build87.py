"""Physical self-transfer rows and receiving addresses on watch replicas."""
import copy,sys,unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
import test_build70 as receiving_fixture
import test_build65 as ledger_fixture
from wallet_history import rows
from address_destinations import external_address

class SelfTransfer(unittest.TestCase):
 def test_refresh_debits_then_credits_same_timestamp_without_double_counting(self):
  chain,w,(a,b,c)=ledger_fixture.Ledger().fixture()
  chain['transactions'].pop(b);chain['transactions'][a]['outputs']=chain['transactions'][a]['outputs'][:1];chain['transactions'][a]['outputs'][0]['value']=4365
  tx=chain['transactions'][c];tx['inputs']=[{'txid':a,'vout':0,'value':4365,'script':'mine'}];tx['outputs'][0]['value']=4169;tx['fee_sats']=196
  r=rows(chain,w,111);self.assertEqual([x['amount_sats'] for x in r],['4169','-4365','4365']);self.assertEqual([x['balance_sats'] for x in r],['4169','0','4365']);self.assertEqual([x['direction'] for x in r],['receive','send','receive']);self.assertEqual(r[0]['utc'],r[1]['utc']);self.assertEqual(r[0]['txid'],r[1]['txid']);self.assertEqual(r[1]['net_sats'],'4169');self.assertEqual(r[1]['fee_sats'],'196');self.assertEqual(r[0]['address_query'],'new-vault')
 def test_ordinary_payment_with_change_stays_one_send(self):
  chain,w,(a,b,c)=ledger_fixture.Ledger().fixture();r=rows(chain,w,110);self.assertEqual(len(r),2);self.assertEqual(r[0]['amount_sats'],'-41000');self.assertEqual(r[0]['balance_sats'],'259000')
 def test_repeated_refreshes_have_correct_intermediate_balances(self):
  chain,w,(a,b,c)=ledger_fixture.Ledger().fixture();d='d'*64;tx=copy.deepcopy(chain['transactions'][c]);tx.update(height=107,inputs=[{'txid':c,'vout':0,'value':58000,'script':'refresh'}],outputs=[{'value':57000,'script':'next-refresh','address':'next-vault'}]);chain['transactions'][d]=tx;chain['wallet_outputs'][d+':0']=w['id'];r=rows(chain,w,112);self.assertEqual([x['balance_sats'] for x in r],['257000','200000','258000','200000','259000','300000']);self.assertEqual([x['amount_sats'] for x in r[:4]],['57000','-58000','58000','-59000'])

class WatchReceiving(unittest.TestCase):
 def setUp(self):
  self.f=receiving_fixture.Addresses();self.f.setUp();self.addCleanup(self.f.doCleanups)
 def watch(self):
  original=self.f.rpc
  def rpc(node,method,params=None,wallet=None,**kw):
   result=original(node,method,params,wallet,**kw)
   if method=='getaddressinfo':
    d=__import__('vendor.embit.descriptor',fromlist=['Descriptor']).Descriptor.from_string(self.f.wallet['raw']['descriptors'][0]['desc']).derive(0)
    result['result'].update(ismine=False,iswatchonly=True,ischange=True,parent_desc=d.to_string(),desc=d.to_string())
   return result
  self.f.f.registry.rpc.call=rpc;self.f.failed.add(self.f.f.a['node_id'])
 def test_watch_concrete_parent_proves_latest_without_private_keys(self):
  self.watch();address=self.f.address(self.f.wallet['raw']['descriptors'][0]);self.f.received=[{'address':address,'amount':'0.001','confirmations':10}];self.f.service.refresh();entry=self.f.service.overlay(None)['entries'][0];self.assertEqual(entry['addresses'][0]['address'],address);self.assertEqual(entry['status'],'available');self.assertFalse(self.f.f.hub.read()['requests'])
 def test_unlabelled_watch_receipt_from_public_history_is_latest(self):
  self.watch();address=self.f.address(self.f.wallet['raw']['descriptors'][0]);w=copy.deepcopy(self.f.wallet);w['node_history']=[{'txid':'e'*64,'address':address,'amount':'0.001','category':'receive','confirmations':10,'blocktime':1000}]
  from descriptor_store import DescriptorStore
  DescriptorStore(self.f.f.config).replace_node_wallets([w]);self.f.service.refresh();entry=self.f.service.overlay(None)['entries'][0];self.assertEqual(entry['addresses'][0]['address'],address);self.assertEqual(entry['confirmed_addresses'],[address])
 def test_change_cannot_be_promoted_using_foreign_parent_or_origin(self):
  from vendor.embit.descriptor import Descriptor
  ext=self.f.wallet['raw']['descriptors'][0];change=self.f.wallet['raw']['descriptors'][1];concrete=Descriptor.from_string(change['desc']).derive(0)
  from node_wallets import NodeWalletLoader
  policies={NodeWalletLoader.descriptor_key(ext['desc']):ext};self.assertFalse(external_address({'address':self.f.address(change),'desc':concrete.to_string(),'parent_desc':concrete.to_string(),'ischange':True},policies))
 def test_empty_cache_does_not_erase_trace_latest(self):
  address=self.f.address(self.f.wallet['raw']['descriptors'][0]);self.f.service.refresh();book={'entries':[{'id':self.f.rid,'kind':'descriptor','status':'available','addresses':[{'address':address}],'address_history':[{'address':address}]}]};entry=self.f.service.overlay(book)['entries'][0];self.assertEqual(entry['addresses'],book['entries'][0]['addresses']);self.assertEqual(entry['status'],'available')
 def test_unverifiable_receipt_retains_previous_latest(self):
  address=self.f.address(self.f.wallet['raw']['descriptors'][0]);self.f.received=[{'address':address,'amount':'0.001','confirmations':10}];self.f.service.refresh();self.f.rejected.add(address);self.f.service.refresh();entry=self.f.service.read()['entries'][self.f.rid];self.assertEqual(entry['addresses'][0]['address'],address);self.assertIn('refresh_error',entry)

if __name__=='__main__':unittest.main()
