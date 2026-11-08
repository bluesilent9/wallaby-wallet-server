"""Refresh retries must not restart completed signers or rebuild old ceremonies."""
import json,http.client,tempfile,threading,unittest,time
from pathlib import Path
from unittest.mock import patch
import test_build72 as fixture

class RefreshRetry(unittest.TestCase):
 def test_retry_keeps_ready_node_while_other_node_is_checking(self):
  f=fixture.Refresh();f.setUp();self.addCleanup(f.doCleanups)
  checks=f.checks;nodes=list(checks.connections());checks.jobs.add('renewal-'+f.w['id'])
  checks.rows[nodes[1]].update(state='checking',active=True)
  with patch.object(checks,'scan') as scan:
   checks.ensure('renewal-'+f.w['id'],force=False,private_accounts=True,priority=0)
   self.assertEqual(checks.rows[nodes[0]]['state'],'ready')
   self.assertFalse(checks.rows[nodes[0]].get('active'))
   scan.assert_not_called()
  # Once the slow node finishes, both proofs are accepted together.
  checks.scan(nodes[1],checks.rows[nodes[1]]['token'])
  self.assertTrue(__import__('vault_refresh').signers(f.hub,f.w)['complete'])

 def test_refresh_status_avoids_old_wallet_setup_render_and_retry_is_not_forced(self):
  from preferences import FamilyStore
  from launch_wallaby_wallet_server import create_server
  with tempfile.TemporaryDirectory() as folder:
   cfg=Path(folder)/'config.cfg';family=FamilyStore(cfg);family.save_user('Example','green',revision=0)
   server,pool=create_server(Path(folder)/'browser',0,cfg);pool.nodes.health.closed=True
   thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();session=pool.create();session.user_id=family.snapshot()['users'][0]['id'];session.access=lambda:{}
   work={'id':'existing-refresh','owner_id':session.user_id,'renewal':{'roles':[]}}
   def request(method,path,body=None):
    c=http.client.HTTPConnection('::1',server.server_port,timeout=5)
    c.request(method,path,json.dumps(body) if body is not None else None,{'X-Session-Token':session.token,'Content-Type':'application/json'})
    r=c.getresponse();value=json.loads(r.read());c.close();self.assertEqual(r.status,200,value);return value
   try:
    with patch('launch_wallaby_wallet_server.BuilderWorkspace') as workspace,patch.object(pool.nodes,'ready_for_builders',return_value=True),patch.object(pool.nodes.hub.wallet_builder,'snapshot',side_effect=AssertionError('Unrelated historical ceremonies were rendered')),patch.object(pool.nodes.hub.disc_signers,'ensure') as ensure,patch('vault_refresh.signers',return_value={'complete':False}):
     workspace.return_value.snapshot.return_value={'workspace':work};workspace.return_value.owned.return_value=work
     value=request('GET','/api/wallet-builder');self.assertEqual(value['sessions'],[]);ensure.assert_not_called()
     request('POST','/api/wallet-builder/discover',{'foreground':True,'identities':False})
     ensure.assert_called_with('renewal-existing-refresh',force=True,private_accounts=True,priority=0)
     request('POST','/api/wallet-builder/discover',{'foreground':True,'identities':False,'retry':True})
     ensure.assert_called_with('renewal-existing-refresh',force=False,private_accounts=True,priority=0)
   finally:server.shutdown();server.server_close();thread.join(3)
