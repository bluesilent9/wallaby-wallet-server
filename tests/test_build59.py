import sys,json,threading,http.client,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_build8 import Setup
from descriptor_store import DescriptorStore
from balance_store import BalanceStore
from preferences import resource_id,FamilyStore
from launch_wallaby_wallet_server import create_server

class OwnershipHttp(Setup):
 def test_http_owner_save_without_combined_history_persists_and_returns_wallet_card(self):
  w=copy.deepcopy(self.wallet);w.update(setup_name='Proposed wallet',node_history=[],node_sources=[{'node_id':'n','hostname':'Fixture','wallet_name':w['name']}],public_history={'exported_utc':'2026-11-04T11:00:00Z','lastblock':'a'*64,'outputs':[]})
  DescriptorStore(self.config).replace_node_wallets([w]);rid=resource_id('descriptor',w['id'])
  with self.family.transaction() as data:data['ownership']=[]
  BalanceStore(self.config).save('old',{'balances':{'wallets':[]}})
  server,pool=create_server(Path(self.tmp.name)/'http',0,self.config,ipv6=False);pool.discovery.close();pool.nodes.health.closed=True
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();s=pool.create();s.user_id=self.user;s.sync_workspace=lambda *a:None;s.inventory_ready=True;s.inventory=[{'id':rid,'kind':'descriptor','source':w['id'],'name':'Proposed wallet'}]
  def request(path,body=None):
   c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5);c.request('POST' if body else 'GET',path,json.dumps(body) if body else None,{'X-Session-Token':s.token,'Content-Type':'application/json'});r=c.getresponse();result=json.loads(r.read());c.close();return r.status,result
  try:
   code,before=request('/api/family');self.assertEqual(code,200);self.assertFalse(before['descriptor_history_ready']);self.assertEqual(before['balance_report']['balances']['wallets'],[])
   code,after=request('/api/ownership/save',{'revision':self.family.snapshot()['revision'],'rows':[{'id':rid,'name':'Proposed wallet','owner_id':self.user,'external':False,'smsf':False}]})
   self.assertEqual(code,200,after);self.assertFalse(after['descriptor_history_ready']);self.assertFalse(after['ownership_ready']);self.assertEqual(after['balance_report']['balances']['wallets'][0]['name'],'Proposed wallet');self.assertEqual(after['balance_report']['balances']['wallets'][0]['btc'],'0');self.assertEqual(s.status,'idle')
   saved=FamilyStore(self.config).snapshot()['ownership'][0];self.assertTrue(saved['confirmed']);self.assertEqual(saved['owner_id'],self.user)
   code,again=request('/api/family');self.assertEqual(code,200);self.assertEqual(len(again['balance_report']['balances']['wallets']),1)
  finally:server.shutdown();server.server_close();thread.join(3);s.close()
