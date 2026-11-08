"""Wallet Server desired lifecycle is separate from independently approved Core work."""
import copy,json,secrets
from pathlib import Path
from storage import data_directory
from agent_hub import equivalent,digest
from preferences import resource_id,FamilyStore
from node_wallets import NodeWalletLoader


def roots(state):
    rows={}
    for key,row in state.get('requests',{}).items():
        if row.get('kind')!='wallet_retire' or 'expected_holders' not in row or row.get('superseded_lifecycle'):continue
        if not row.get('dashboard_extinct') and row.get('cancel_requested'):continue
        old=rows.get(row['wallet_id'])
        if old is None or (row['created_utc'],key)>(old[1]['created_utc'],old[0]):rows[row['wallet_id']]=(key,row)
    return rows


def read(config):
    path=data_directory(config)/'agent-hub.json'
    return roots(json.loads(path.read_text())) if path.exists() else {}


def extinct_ids(config):return {json.loads(ident)[1] for ident,(_,r) in read(config).items() if not r.get('restoration')}


def classify(config,report):
    if not report:return report
    states=read(config);ids={json.loads(ident)[1] for ident,(_,r) in states.items() if not r.get('restoration')}
    for row in report.get('balances',{}).get('wallets',[]):
        if row.get('descriptor_id') in ids:row.update(extinct=True,lifecycle_extinct=True)
    family=FamilyStore(config).snapshot();owners={r['id']:r for r in family['ownership']};users={u['id']:u['name'] for u in family['users']}
    from wallet_names import dashboard_name
    rows=report.get('balances',{}).get('wallets',[])
    for ident,(key,r) in states.items():
        uid=json.loads(ident)[1]
        if not r.get('restoration') or any(w.get('descriptor_id')==uid for w in rows):continue
        owner=owners.get(ident,{})
        rows.append({'descriptor_id':uid,'resource_id':ident,'kind':'wallet','name':dashboard_name(owner) if owner else r['proposal']['archive_label'],'owner_id':owner.get('owner_id',r['user_id']),'owner_name':users.get(owner.get('owner_id',r['user_id']),'Unknown'),'smsf':bool(owner.get('smsf')),'btc':None,'value_aud':None,'cash_aud':None,'cost_basis_aud':None,'unrealised_gain_aud':None,'state':'unavailable','extinct':False,'restoration_pending':True})
    return report


def cards(config,existing):
    """One logical extinct card, retaining original identity and history link."""
    state=read(config);covered=set();result=[]
    for ident,(key,r) in state.items():covered.update(a['address'] for a in r['proposal']['manifest']['addresses'])
    from descriptor_store import DescriptorStore
    catalog={w['id']:w for w in DescriptorStore(config).read()['wallets']}
    for card in existing:
        raw=catalog.get(card['id'],{}).get('raw',{});addresses={r['desc'].split('addr(',1)[1].split(')',1)[0] for r in raw.get('descriptors',[]) if r['desc'].startswith('addr(')}
        if addresses and addresses<=covered:continue
        result.append(card)
    family=FamilyStore(config).snapshot();owners={r['id']:r for r in family['ownership']};users={u['id']:u['name'] for u in family['users']}
    from wallet_names import dashboard_name
    for ident,(key,r) in state.items():
        if r.get('restoration'):continue
        uid=json.loads(ident)[1];owner=owners.get(ident);wallet=r.get('dashboard_wallet',{});years=[str(row.get('blocktime',row.get('time',''))) for row in wallet.get('node_history',[])]
        dates=[]
        from datetime import datetime,timezone
        for stamp in years:
            try:
                if float(stamp)>0:dates.append(datetime.fromtimestamp(float(stamp),timezone.utc).year)
            except (ValueError,OverflowError,OSError):pass
        span=str(min(dates)) if dates and min(dates)==max(dates) else str(min(dates))+' - '+str(max(dates)) if dates else 'History retained'
        result.append({'id':uid,'descriptor_id':uid,'resource_id':ident,'name':dashboard_name(owner) if owner else r['proposal']['archive_label'],'owner_name':users.get(owner.get('owner_id'),'Unknown') if owner else 'Unknown','owner_id':owner.get('owner_id') if owner else r['user_id'],'extinct':True,'lifecycle_extinct':True,'retirement_hash':key,'activity_years':span})
    return sorted(result,key=lambda w:w['name'].casefold())


def supported(hub,node):
    # No older Agent may bypass the direct-SSH-only local restoration guard.
    import re
    versions=[c.get('agent_version','') for c in hub.registry.connections.values() if c['node_id']==node]
    return any(v=='2.0.0' or (m:=re.fullmatch(r'2\.0\.0~dev(\d+)',v)) and int(m[1])>=65 for v in versions)


def relevant(raw,w):
    from policy_accounts import signing_account
    return equivalent(raw,w['raw']) or signing_account(dict(w,private_keys_enabled=True),{'raw':raw})


def active_accounts(hub,raw,*,verify=False):
    live={n['id'] for n in hub.registry.snapshot()['nodes'] if n.get('connected') and n.get('rpc_ready') and n.get('blockchain',{}).get('state')=='ready'};found=[]
    for node,inv in list(hub.inventories.items()):
        if node not in live or not supported(hub,node) or not (inv.get('complete') or inv.get('loaded_complete')):continue
        for w in inv.get('wallets',[]):
            if w.get('extinct') or w.get('signing_only') or w.get('archive_id') or w.get('scanning') or not relevant(raw,w):continue
            if verify:
                try:
                    info=hub.rpc(node,'getwalletinfo',[],w['name']);actual=hub.rpc(node,'listdescriptors',[False],w['name'])
                    if info.get('scanning') or not equivalent(actual,w['raw']) or info.get('walletname',w['name'])!=w['name'] or (info.get('private_keys_enabled') is True)!=bool(w.get('private_keys_enabled')):continue
                except (ValueError,OSError,KeyError):continue
            found.append((node,w))
    return found


def request_restore(hub,user,key,confirmed):
    if confirmed is not True:raise ValueError('Confirm restoration first.')
    with hub.edit() as state:
        r=state['requests'].get(key)
        if not r or r.get('user_id')!=user or not r.get('retirement_wallet') or roots(state).get(r['wallet_id'],(None,))[0]!=key:raise ValueError('No Wallet Server extinction matches this wallet.')
        if r.get('restoration'):return {'restoring':True,'request_hash':key}
        r.update(dashboard_extinct=True,cancel_requested=True,cancel_requested_utc=hub.utc())
        r['restoration']={'created_utc':hub.utc(),'accounts':[],'active_seen_utc':None,'state':'pending','stale_nodes':{}}
        for row in state['requests'].values():
            if row.get('kind')!='wallet_retire' or row.get('root_hash')!=key or row['state']!='pending':continue
            row['cancel_requested']=True
            if not row.get('delivered'):row.update(state='cancelled',cancelled_before_delivery=True,message='Extinction withdrawn before delivery; Wallet Server restoration requested.')
    # Data classification is already committed even with no connected Agents.
    import threading
    threading.Thread(target=advance_restore,args=(hub,),kwargs={'only':key,'verify':True},daemon=True).start()
    return {'restoring':True,'request_hash':key}


def advance_restore(hub,*,only=None,verify=False):
    state=hub.read()
    for key,r in list(roots(state).values()):
        if not r.get('restoration') or only and key!=only:continue
        # Withdraw stale physical-destruction intent durably, including after a
        # crash between committing Restore and withdrawing the archive queue.
        from archive_queue import ArchiveQueue
        queue=ArchiveQueue(hub)
        for ident,disc in list(queue.read()['requests'].items()):
            if disc['state']=='active' and disc['request'].get('operation_id')==r['proposal']['operation_id'] and disc['request'].get('reason')=='wallet_extinction':queue.cancel(r['user_id'],ident)
        raw=r['retirement_wallet'];accounts=active_accounts(hub,raw,verify=verify)
        fresh_active=[(n,w) for n,w in accounts if w.get('private_keys_enabled') and (verify or hub.inventories[n].get('scanned_utc','')>r['restoration']['created_utc'])]
        plans={}
        # Retain the exact previous per-node key assignments. Never distribute
        # another role just because it belongs to the same multisig policy.
        for node in set(r['expected_holders'])|set(r['restoration'].get('stale_nodes',{})):
            known=list(state['nodes'].get(node,{}).get('known_wallets',{}).values())
            known += [t for row in state['requests'].values() if row.get('root_hash')==key and row['node_id']==node and row.get('proposal',{}).get('phase')=='delete' for t in row['proposal']['delete_wallets']]
            for item in known:
                item=dict(item,raw=item.get('raw',item.get('public_wallet')))
                if not item['raw'] or not relevant(raw,item):continue
                policy=digest(sorted(NodeWalletLoader.descriptor_key(d['desc']) for d in item['raw']['descriptors']));ident=node+':'+digest({'policy':policy,'wallet_name':item['raw']['wallet_name']})
                plans[ident]={'id':ident,'node_id':node,'public_wallet':item['raw'],'private':bool(item.get('private_keys_enabled'))}
            if not any(p['node_id']==node for p in plans.values()):
                ident=node+':'+digest(raw);plans[ident]={'id':ident,'node_id':node,'public_wallet':raw,'private':None if node in r['expected_holders'] else False}
        with hub.edit() as saved:
            root=saved['requests'].get(key)
            if not root or not root.get('restoration') or root.get('superseded_lifecycle') or roots(saved).get(root['wallet_id'],(None,))[0]!=key:continue
            restoration=root['restoration']
            old={p['id']:p for p in restoration['accounts']}
            if fresh_active:restoration['active_seen_utc']=hub.utc()
            active_nodes={n for n,w in accounts};stale=restoration.setdefault('stale_nodes',{});wanted={a['address'] for a in root['proposal']['manifest']['addresses']};names={n['id']:n['hostname'] for n in hub.registry._read()['nodes']}
            for node,inv in list(hub.inventories.items()):
                if node in active_nodes:stale.pop(node,None);continue
                if not (inv.get('complete') or inv.get('loaded_complete')) or inv.get('scanned_utc','')<restoration['created_utc']:continue
                historical={d['desc'].split('addr(',1)[1].split(')',1)[0] for w in inv.get('wallets',[]) if w.get('extinct') for d in w['raw']['descriptors'] if d['desc'].startswith('addr(')}
                if wanted and wanted<=historical:stale.setdefault(node,{'hostname':names.get(node,node),'detected_utc':hub.utc()})
            for ident,p in plans.items():
                previous=old.get(ident,{})
                if previous.get('transfer_id'):
                    pair=[v for v in saved['requests'].values() if v.get('transfer_id')==previous['transfer_id']]
                    receiver=next((v for v in pair if v['direction']=='receive'),{})
                    # A completed attempt is immutable. A later positively seen
                    # extinct copy is a new mismatch, requiring a fresh review.
                    repeated=receiver.get('state')=='complete' and p['node_id'] in stale and hub.inventories.get(p['node_id'],{}).get('scanned_utc','')>receiver.get('finished_utc',hub.utc())
                    if repeated:
                        p['previous_transfer_id']=previous['transfer_id'];previous={}
                    if not repeated and any(v['state']=='denied' for v in pair) and all(v['state'] in ('pending','denied') for v in pair):
                        sender=next(v for v in pair if v['direction']=='send')
                        available=any(n==sender['node_id'] and equivalent(w['raw'],sender['public_wallet']) and (not p['private'] or w.get('private_keys_enabled')) for n,w in accounts)
                        if available and supported(hub,p['node_id']):
                            transfer=secrets.token_hex(32)
                            for oldrow in pair:
                                oldrow.update(superseded_attempt=True,queue_visible=False)
                                child={k:copy.deepcopy(oldrow[k]) for k in ('kind','node_id','peer_id','direction','descriptor_id','public_wallet','source_has_private_keys','earliest_timestamp','requires_blockchain_redownload','lifecycle_restore')}
                                child.update(transfer_id=transfer,state='pending',created_utc=hub.utc(),retry_of=oldrow['transfer_id'],message='Locally denied. Waiting for the Agent user to remove its restoration deny entry.')
                                saved['requests'][digest({'transfer':transfer,'direction':child['direction']})]=child
                            p.update(previous,transfer_id=transfer,state='pending',message='Locally denied. Waiting for the Agent user to remove its restoration deny entry.');continue
                    if not repeated:
                        outcome=next((v for v in pair if v['state'] in ('error','recovery_required')),receiver)
                        p.update(previous,state='complete' if receiver.get('state')=='complete' else outcome.get('state','pending'),message=outcome.get('message') or previous.get('message','Waiting for local Agent review.'));plans[ident]=p;continue
                same=[w for n,w in accounts if n==p['node_id'] and equivalent(w['raw'],p['public_wallet']) and (not p['private'] or w.get('private_keys_enabled') and w['raw']['wallet_name']==p['public_wallet']['wallet_name'])]
                if same:
                    p.update(state='retained',message='Original active copy is still loaded.');continue
                if p['private'] is None:
                    p.update(state='waiting',message='Original key-storage assignment is unknown. No private keys will be copied to an unverified role.');continue
                private_nodes={n for n,w in accounts if w.get('private_keys_enabled')}
                sources=[(n,w) for n,w in accounts if n in private_nodes and n!=p['node_id'] and equivalent(w['raw'],p['public_wallet']) and (not p['private'] or w.get('private_keys_enabled'))]
                sources.sort(key=lambda pair:pair[1]['raw']['wallet_name']!=p['public_wallet']['wallet_name'])
                source=next(iter(sources),None)
                if not source:
                    p.update(state='waiting',message='Waiting for an Agent with the original active '+('private-key' if p['private'] else 'public')+' wallet.');continue
                if not supported(hub,p['node_id']):
                    p.update(state='waiting',message='Connect this Agent with Build 65 or later for direct SSH restoration.');continue
                if any(v.get('root_hash')==key and v.get('proposal',{}).get('phase')=='delete' and v['node_id'] in (source[0],p['node_id']) and v['state']=='pending' for v in saved['requests'].values()):
                    p.update(state='waiting',message='Waiting for the Agents to acknowledge withdrawal of the old deletion request.');continue
                if p['public_wallet']['wallet_name'] in hub.inventories.get(p['node_id'],{}).get('unloaded_wallets',[]):
                    p.update(state='waiting',message='The original wallet folder is unloaded. Load and verify it locally before requesting an SSH replacement.');continue
                origin,w=source;transfer=secrets.token_hex(32);earliest=min((d.get('timestamp',0) for d in w['raw']['descriptors']),default=0)
                for node,peer,direction in ((origin,p['node_id'],'send'),(p['node_id'],origin,'receive')):
                    row={'kind':'wallet_transfer','node_id':node,'peer_id':peer,'direction':direction,'transfer_id':transfer,'state':'pending','descriptor_id':digest(sorted(NodeWalletLoader.descriptor_key(d['desc']) for d in w['raw']['descriptors'])),'public_wallet':copy.deepcopy(w['raw']),'source_has_private_keys':bool(p['private']),'earliest_timestamp':earliest,'requires_blockchain_redownload':False,'created_utc':hub.utc(),'lifecycle_restore':key}
                    saved['requests'][digest({'transfer':transfer,'direction':direction})]=row
                p.update(transfer_id=transfer,state='pending',source_node=origin,message='Waiting for locally approved direct SSH synchronisation.')
            restoration['accounts']=list(plans.values());restoration['state']='complete' if restoration.get('active_seen_utc') and plans and all(p['state'] in ('retained','complete') for p in plans.values()) else 'pending'


def restoration_status(hub,user):
    result=[];names={n['id']:n['hostname'] for n in hub.registry._read()['nodes']}
    for key,r in roots(hub.read()).values():
        restoration=r.get('restoration')
        if not restoration:continue
        result.append({'request_hash':key,'wallet_id':r['wallet_id'],'name':r['proposal']['archive_label'],'state':restoration['state'],'created_utc':restoration['created_utc'],'warning':None if restoration.get('active_seen_utc') else 'No Agent with an active private-key version of this wallet has been detected since Wallet Server restoration. Public Extinct history cannot recreate private keys.','targets':[dict({k:v for k,v in p.items() if k!='public_wallet'},hostname=names.get(p['node_id'],p['node_id'])) for p in restoration['accounts']]})
    return result


def notices(hub):
    result=[]
    current=hub.read()
    for key,r in roots(current).values():
        restored=r.get('restoration')
        if not restored:continue
        base={'kind':'wallet_restoration','target':'balances','created_utc':restored['created_utc'],'wallet_id':r['wallet_id']}
        if not restored.get('active_seen_utc'):
            result.append(dict(base,id='restore-missing-'+key,severity='red',dismissible=False,text=r['proposal']['archive_label']+': no Agent with an active private-key version of this wallet has been detected since Wallet Server restoration.'))
            continue
        for node,seen in restored.get('stale_nodes',{}).items():
            result.append(dict(base,id='restore-stale-'+key+'-'+node,severity='yellow',dismissible=True,created_utc=seen['detected_utc'],text=seen['hostname']+' has been detected with the extinct version of '+r['proposal']['archive_label']+'. An active version has been detected on another Agent; restore this Agent through locally approved direct SSH sync.'))
    return result


def validate_saved(state,key,row):
    from descriptor_store import clean_wallet
    from datetime import datetime
    if 'dashboard_extinct' in row and type(row['dashboard_extinct']) is not bool:raise ValueError('Invalid desired extinction status.')
    if row.get('dashboard_wallet'):
        w=row['dashboard_wallet'];checked=clean_wallet(w['raw'])
        if checked['id']!=w['id'] or json.loads(row['wallet_id'])[1]!=w['id'] or not equivalent(w['raw'],row['retirement_wallet']):raise ValueError('Invalid retained Wallet Server wallet identity.')
    if row.get('superseded_lifecycle'):
        successor=state['requests'].get(row['superseded_lifecycle'],{})
        if not row.get('restoration') or successor.get('kind')!='wallet_retire' or successor.get('wallet_id')!=row['wallet_id'] or not successor.get('dashboard_extinct'):raise ValueError('Invalid successor wallet lifecycle.')
    fingerprint=row.get('dashboard_history_fingerprint')
    if fingerprint is not None and (not isinstance(fingerprint,str) or len(fingerprint)!=64 or any(c not in '0123456789abcdef' for c in fingerprint)):raise ValueError('Invalid saved wallet history fingerprint.')
    restored=row.get('restoration')
    if not restored:return
    if not row.get('dashboard_extinct') or not row.get('cancel_requested') or not {'created_utc','accounts','active_seen_utc','state'}<=set(restored)<={'created_utc','accounts','active_seen_utc','state','stale_nodes'} or restored['state'] not in ('pending','complete'):raise ValueError('Invalid desired restoration state.')
    datetime.fromisoformat(restored['created_utc'].replace('Z','+00:00'))
    if restored['active_seen_utc']:datetime.fromisoformat(restored['active_seen_utc'].replace('Z','+00:00'))
    if not isinstance(restored['accounts'],list) or len(restored['accounts'])>4096:raise ValueError('Invalid restoration targets.')
    stale=restored.get('stale_nodes',{})
    if not isinstance(stale,dict) or len(stale)>4096:raise ValueError('Invalid restored wallet Agent list.')
    for node,value in stale.items():
        if node not in state['nodes'] or not isinstance(value,dict) or set(value)!={'hostname','detected_utc'} or not isinstance(value['hostname'],str) or len(value['hostname'])>255:raise ValueError('Invalid restored wallet Agent entry.')
        datetime.fromisoformat(value['detected_utc'].replace('Z','+00:00'))
    seen=set()
    for p in restored['accounts']:
        clean_wallet(p['public_wallet'])
        if p['id'] in seen or p['node_id'] not in set(row['expected_holders'])|set(restored.get('stale_nodes',{})) or type(p.get('private')) not in (bool,type(None)) or not relevant(row['retirement_wallet'],{'raw':p['public_wallet']}):raise ValueError('Invalid restoration account assignment.')
        seen.add(p['id'])
        if p.get('transfer_id'):
            pair=[r for r in state['requests'].values() if r.get('transfer_id')==p['transfer_id']]
            if len(pair)!=2 or any(r.get('lifecycle_restore')!=key or not equivalent(r['public_wallet'],p['public_wallet']) or r['source_has_private_keys'] is not p['private'] for r in pair):raise ValueError('Invalid direct SSH restoration binding.')


def permitted_transfer(state,row):
    key=row.get('lifecycle_restore');r=state.get('requests',{}).get(key,{})
    return bool(key and r.get('restoration') and roots(state).get(r.get('wallet_id'),(None,))[0]==key)
