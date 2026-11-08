"""Read verified saved BTC history for planning without waiting on tax scans.

Coin selection still independently validates current UTXOs, raw transactions,
spending policies and change cursors; a cached balance is never a spend proof.
"""
import copy,hashlib,json,re
from storage import data_directory
from descriptor_store import DescriptorStore
from preferences import FamilyStore,resource_id
from builder_identity import resolve

FIELDS=('wallets','transactions','coverage','timestamp_basis','source','scanned_utc')
def read(config,fingerprint):
    if not re.fullmatch('[0-9a-f]{64}',str(fingerprint)):return None
    try:
        envelope=json.loads((data_directory(config)/'descriptor-history'/(fingerprint+'.json')).read_text());payload=envelope['payload']
        if hashlib.sha256(payload.encode()).hexdigest()!=envelope['sha256']:return None
        value=json.loads(payload)
        if value.get('catalog_fingerprint')==fingerprint and all(k in value for k in FIELDS):return value
    except (OSError,ValueError,KeyError,TypeError):pass
    return None

def planning_history(session,catalog):
    config=session.preferences_path;current=DescriptorStore.fingerprint(catalog);snapshot=read(config,current)
    if snapshot is None:
        run=FamilyStore(config).snapshot().get('ownership_runs',{}).get(getattr(session,'user_id',None),{})
        snapshot=read(config,run.get('descriptor_fingerprint'))
        if snapshot is None:
            path=getattr(session,'uploads',{}).get('chain')
            if path and run.get('descriptor_fingerprint'):
                try:
                    raw=path.read_bytes();manifest=next((row for row in run.get('files',[]) if row.get('slot')=='chain'),{})
                    candidate=json.loads(raw) if hashlib.sha256(raw).hexdigest()==manifest.get('sha256') else {}
                    if candidate.get('catalog_fingerprint')==run['descriptor_fingerprint'] and all(k in candidate for k in FIELDS):snapshot=candidate
                except (OSError,ValueError,TypeError):pass
    if snapshot is None:raise ValueError('Saved Bitcoin history is not available yet. Automatic node discovery is checking it in the background.')
    value=copy.deepcopy(snapshot);wallets={w['id']:w for w in catalog['wallets']};mapping={};rows=[];seen=set()
    for w in value['wallets']:
        ident=json.loads(resolve(config,resource_id('descriptor',w['id'])))[1]
        if ident not in wallets:continue
        if ident in seen:raise ValueError('Saved wallet history overlaps after a policy update. Wait for verification of this wallet.')
        seen.add(ident);mapping[w['id']]=ident;w['id']=ident;rows.append(w)
    for ident,wallet in wallets.items():
        if ident not in seen:rows.append({'id':ident,'name':wallet.get('setup_name') or wallet['name'],'records':[],'history_unavailable':True})
    value['wallets']=rows
    if 'wallet_outputs' in value:value['wallet_outputs']={point:mapping.get(uid,uid) for point,uid in value['wallet_outputs'].items() if mapping.get(uid,uid) in wallets}
    for row in value.get('coverage',[]):row['wallet_id']=mapping.get(row.get('wallet_id'),row.get('wallet_id'))
    value['planning_saved']=snapshot.get('catalog_fingerprint')!=current
    return value
