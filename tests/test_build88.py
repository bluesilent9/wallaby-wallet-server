"""Current display names and a viewable, immutable linked transaction."""
import copy,json,http.client,threading,tempfile,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
import test_build80 as approvals
from salary_planning import funding_catalog
from vault_refresh import complete,cancel
from builder_workspace import BuilderWorkspace

class Names(unittest.TestCase):
 def test_salary_uses_current_dashboard_names_by_identity(self):
  snapshot={'ownership':[{'id':'old','name':'Treasury Wallet','dashboard_name':'Treasury Wallet (2022 - 2026)','confirmed':True,'owner_id':'owner'},{'id':'new','name':'Treasury','dashboard_name':'Treasury Wallet','confirmed':True,'owner_id':'owner'}]}
  balances={'balances':{'wallets':[{'resource_id':'old','name':'Treasury Wallet','btc':'10'},{'resource_id':'new','name':'Treasury','btc':'1'}]}}
  before=copy.deepcopy(balances);catalog=funding_catalog(snapshot,balances);self.assertEqual([w['name'] for w in catalog],['Treasury Wallet (2022 - 2026)','Treasury Wallet']);self.assertEqual([w['id'] for w in catalog],['old','new']);self.assertEqual([w['btc'] for w in catalog],['10','1']);self.assertEqual(balances,before)
 def test_old_records_without_display_name_still_work(self):
  self.assertEqual(funding_catalog({'ownership':[{'id':'w','name':'Example','confirmed':True}]},{'balances':{'wallets':[{'resource_id':'w','name':'Stale'}]}})[0]['name'],'Example')

class Lock(unittest.TestCase):
 def setUp(self):
  self.f=approvals.GroupedApproval();self.f.setUp();self.addCleanup(self.f.doCleanups)
 def state(self):return self.f.work.snapshot(self.f.user,'transaction')
 def test_approval_keeps_diagram_locked_until_handoff_then_unlocks(self):
  before=copy.deepcopy(self.f.work.owned(self.f.user,'transaction'));self.assertTrue(self.state()['read_only']);self.f.begin();self.assertTrue(self.state()['read_only']);self.f.approve_all();self.assertTrue(self.state()['read_only']);out=complete(self.f.hub,self.f.user);state=self.state();self.assertFalse(state.get('read_only',False));self.assertEqual(state['workspace']['draft']['edges'][0]['to'],out['destination']);self.assertEqual(state['workspace']['draft']['edges'][0]['amount_sats'],before['draft']['edges'][0]['amount_sats'])
 def test_cancel_before_requests_preserves_diagram_and_unlocks(self):
  before=copy.deepcopy(self.f.work.owned(self.f.user,'transaction'));self.assertTrue(self.state()['read_only']);self.assertEqual(cancel(self.f.hub,self.f.user)['return_to'],'builder');self.assertFalse(self.state().get('read_only',False));self.assertEqual(self.f.work.owned(self.f.user,'transaction'),before);self.assertFalse(self.f.hub.read()['requests'])
 def test_direct_draft_edit_cannot_bypass_lock(self):
  tx=self.f.work.owned(self.f.user,'transaction');draft=copy.deepcopy(tx['draft']);draft['nodes'][0]['x']+=20
  with self.assertRaisesRegex(ValueError,'linked vault policy'):self.f.work.save(self.f.user,'transaction',{'id':tx['id'],'revision':tx['revision'],'draft':draft})
  self.assertEqual(self.f.work.owned(self.f.user,'transaction')['draft'],tx['draft'])

class Endpoints(unittest.TestCase):
 def test_reads_remain_available_but_mutations_and_templates_are_blocked(self):
  from launch_wallaby_wallet_server import create_server
  from preferences import FamilyStore
  with tempfile.TemporaryDirectory() as folder:
   cfg=Path(folder)/'config.cfg';family=FamilyStore(cfg);family.save_user('Example','green',revision=0);server,pool=create_server(Path(folder)/'browser',0,cfg);pool.nodes.health.closed=True;thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();session=pool.create();session.user_id=family.snapshot()['users'][0]['id'];session.access=lambda:{'templates_ready':False}
   work=BuilderWorkspace(cfg);tx=work.start(session.user_id,'transaction');work.start(session.user_id,'wallet');state=work.read();state['workspaces']['wallet']['renewal']={'transaction_workspace':tx['id']};work.write(state)
   def request(method,path):
    conn=http.client.HTTPConnection('::1',server.server_port,timeout=5);conn.request(method,path,'{}' if method=='POST' else None,{'X-Session-Token':session.token,'Content-Type':'application/json'});r=conn.getresponse();body=json.loads(r.read());conn.close();return r.status,body
   try:
    before=work.read();code,body=request('GET','/api/builders/transaction');self.assertEqual(code,200);self.assertTrue(body['read_only'])
    with patch('launch_wallaby_wallet_server.builder_catalog',return_value={'wallets':[]}) as catalog:
     code,body=request('GET','/api/builder');self.assertEqual(code,200);self.assertEqual(body['wallets'],[]);self.assertTrue(catalog.call_args.kwargs['view_only'])
    for path in ('/api/builders/transaction/start','/api/builders/transaction/save','/api/builders/transaction/cancel','/api/builder/new-address','/api/builder/prepare','/api/transaction/broadcast','/api/templates/save','/api/templates/delete','/api/salary/template'):
     code,body=request('POST',path);self.assertEqual(code,400,path);self.assertIn('linked vault policy',body['error'])
    self.assertEqual(work.read(),before)
   finally:server.shutdown();server.server_close();thread.join(3)

if __name__=='__main__':unittest.main()
