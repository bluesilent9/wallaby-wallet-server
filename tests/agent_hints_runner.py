"""Check an actual Server envelope through the current Agent, isolated and public-only."""
import json,sys,tempfile
sys.path.insert(0,sys.argv[1])
from approval_store import Store
from direct_wallet_catalogue import activate
from sync_offers import apply,validate
from sync_table import state
from sync_preferences import change,enable
p=validate(json.load(sys.stdin))
with tempfile.TemporaryDirectory() as root:
 store=Store(root,persistence=False);store.persistence=None;activate(store);before=store.read();apply(store,p,'server-connection')
 table=state(store,[])['wallets'];assert len(table)==1,table;row=table[0];assert row['availability']=='advisory' and row['server_hint'] and not row['receive'] and not row['send'];assert not store.read()['pending']
 change(store,row['deny_id'],True);denied=state(store,[])['wallets'][0];assert denied['availability']=='denied';assert not store.read()['pending']
 # The Server still reports the wallet unchanged while the Agent owns denial.
 apply(store,p,'server-connection');assert state(store,[])['wallets'][0]['availability']=='denied'
 apply(store,{**p,'revision':p['revision']+1,'offers':[]},'server-connection');rows=state(store,[])['wallets'];assert len(rows)==1 and rows[0]['denied'];enable(store,rows[0]['policy_id']);assert not state(store,[])['wallets'];assert not store.read()['pending'];assert store.read().get('direct_sync_keys',{})==before.get('direct_sync_keys',{})
print(json.dumps({'advisory':True,'denied':True,'cleared':True,'no_wallet_jobs':True}))
