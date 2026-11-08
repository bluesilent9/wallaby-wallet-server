"""Durable public vault identities for immediate, explicitly unverified card placeholders."""
import json,os,uuid
from storage import data_directory,storage_lock
from pathlib import Path

def validate(data):
    if not isinstance(data,dict) or data.get('schema')!=1 or not isinstance(data.get('wallets'),list) or len(data['wallets'])>10000:raise ValueError('Invalid saved vault display identities.')
    seen=set()
    for row in data['wallets']:
        if not isinstance(row,dict) or set(row)!={'id','name'} or any(not isinstance(row[k],str) or not row[k] or len(row[k])>1000 or any(ord(c)<32 for c in row[k]) for k in ('id','name')) or row['id'] in seen:raise ValueError('Invalid saved vault display identity.')
        seen.add(row['id'])
    return data

def load(config):
    try:return validate(json.loads((data_directory(Path(config))/'vault-display.json').read_text()))['wallets']
    except (OSError,ValueError,TypeError):return []

def save(config,wallets):
    config=Path(config);data=validate({'schema':1,'wallets':[{'id':w['id'],'name':w['name']} for w in wallets]});path=data_directory(config)/'vault-display.json'
    with storage_lock(config):
        path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(uuid.uuid4().hex+'.tmp')
        try:tmp.write_text(json.dumps(data,ensure_ascii=True));tmp.chmod(0o600);os.replace(tmp,path)
        finally:tmp.unlink(missing_ok=True)

def known(config,prior=()):
    from descriptor_store import DescriptorStore
    from preferences import FamilyStore
    from policy_accounts import has_vault
    config=Path(config);family=FamilyStore(config).snapshot();owners={r['source']:r for r in family['ownership'] if r['kind']=='descriptor'};rows={r['id']:{'id':r['id'],'name':r['name']} for r in prior}
    for wallet in DescriptorStore(config).read()['wallets']:
        if not wallet.get('extinct') and has_vault(wallet.get('raw',{})):
            owner=owners.get(wallet['id'],{});rows[wallet['id']]={'id':wallet['id'],'name':owner.get('dashboard_name') or owner.get('name') or wallet.get('setup_name') or wallet['name']}
    return list(rows.values())

def placeholders(rows):return [{'id':r['id'],'name':r['name'],'state':'amber','issues':[],'stale':True,'balance_available':False,'current_height':None} for r in rows]
