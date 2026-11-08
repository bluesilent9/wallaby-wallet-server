"""Decode the actual PSBT output after a nonzero-index vault-refresh handoff."""
import unittest,copy
from types import SimpleNamespace,MethodType
from unittest.mock import patch
import test_build84 as fixtures
import test_build80 as approvals
from vault_refresh import proposed,complete
from builder_destinations import Destinations
from address_proposals import apply
from vendor.embit.descriptor import Descriptor
from vendor.embit.networks import NETWORKS
from vendor.embit.transaction import Transaction,TransactionInput,TransactionOutput
from signed_psbt import decode
from unsigned_psbt import construct

class RefreshPaymentAddress(unittest.TestCase):
 def test_address_book_preview_equals_handoff_catalog_and_actual_psbt_output(self):
  f=fixtures.ExactRefresh();f.setUp();self.addCleanup(f.doCleanups)
  for method in ('installed','result','approve_all'):setattr(f,method,MethodType(getattr(approvals.GroupedApproval,method),f))
  cfg=f.f.f.config;source=f.f.f.rid;wallet=f.f.f.wallet
  preview=proposed(cfg,f.work.owned(f.user,'wallet'));self.assertEqual(preview['index'],15)
  rows={source:{'current_height':1000000,'addresses':[]}}
  apply(cfg,rows,{source:wallet});self.assertEqual(rows[source]['proposed_address']['address'],preview['address'])
  f.begin();f.approve_all();handoff=complete(f.hub,f.user);draft=f.work.owned(f.user,'transaction')['draft']
  self.assertEqual(draft['edges'][0]['to'],handoff['destination'])
  original=Descriptor.from_string(wallet['raw']['descriptors'][0]['desc']).derive(0)
  catalog={'wallets':[{'id':source,'name':'Invented fixture wallet','funded_vault':True,'can_send':True,'can_receive':True,'address':original.address(NETWORKS['main'])}]}
  catalog=Destinations(cfg).enrich(catalog,[source,handoff['destination']],f.hub,require_policy=True)
  receiving=next(w for w in catalog['wallets'] if w['id']==handoff['destination'])
  self.assertEqual(receiving['address'],preview['address']);self.assertEqual(receiving['output_index'],15)
  # Synthetic confirmed funding coin; production planning/PSBT encoding run unchanged.
  prev=Transaction(vin=[TransactionInput(b'\x11'*32,0)],vout=[TransactionOutput(100000,original.script_pubkey())])
  coin={'txid':prev.txid().hex(),'vout':0,'value':100000,'script':original.script_pubkey().data.hex(),'weight':600,'witness':True,'raw_tx':prev.serialize().hex(),'height':1000001}
  edges=[{'from':source,'to':handoff['destination'],'amount_sats':'0','fee_rate':'0','max':True},{'from':source,'to':'network-fee','amount_sats':'0','fee_rate':'1','max':False}]
  with patch('unsigned_psbt.planning_history',return_value={}),patch('unsigned_psbt.live_coins',return_value={source:[coin]}):
   result=construct(SimpleNamespace(preferences_path=cfg,node_registry=f.hub.registry),catalog,edges,{})
  document=decode(result['psbt'].encode());self.assertEqual(len(document['tx'].vout),1)
  output=document['tx'].vout[0];self.assertEqual(output.script_pubkey.address(NETWORKS['main']),preview['address'])
  self.assertEqual(output.script_pubkey.data,Descriptor.from_string(receiving['output_descriptor']).derive(15).script_pubkey().data)
  self.assertEqual(result['output_policies'][0]['address'],preview['address']);self.assertEqual(result['output_policies'][0]['index'],15)
  self.assertEqual(output.value+int(result['estimate']['total_fee_sats']),100000)
  self.assertNotEqual(output.script_pubkey.address(NETWORKS['main']),Descriptor.from_string(receiving['output_descriptor']).derive(0).address(NETWORKS['main']))
