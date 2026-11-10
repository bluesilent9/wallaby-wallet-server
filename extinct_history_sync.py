"""Discovery fingerprints only. Actual history is verified directly by Agents."""
import copy,re,time
from itertools import combinations
from agent_hub import digest
from extinct_sync import containers

METHOD='wallaby_extinct_summary'
FIELDS={'version','chain','addresses','transactions','address_hash','transaction_hash','label_hash','history_complete','digest'}

def validate(value):
    if not isinstance(value,dict) or set(value)!=FIELDS or type(value['version']) is not int or value['version']!=1 or value['chain']!='main' or type(value['history_complete']) is not bool:raise ValueError('Invalid Extinct history summary.')
    for k,limit in (('addresses',10000),('transactions',100000)):
        if type(value[k]) is not int or not 0<=value[k]<=limit:raise ValueError('Invalid Extinct summary record count.')
    if any(not isinstance(value[k],str) or not re.fullmatch('[0-9a-f]{64}',value[k]) for k in ('address_hash','transaction_hash','label_hash','digest')) or value['digest']!=digest({k:v for k,v in value.items() if k!='digest'}):raise ValueError('Invalid Extinct summary fingerprint.')
    return copy.deepcopy(value)

def supported(connection):return METHOD in connection.get('rpc_methods',[])

def group(hub,node):
    inv=hub.inventories.get(node,{})
    if not inv.get('complete') or any(w.get('scanning') for w in inv.get('wallets',[])):return None
    summaries=inv.get('extinct_summaries',{})
    if len(summaries)!=1:return None
    summary=validate(next(iter(summaries.values())))
    wallets=[w for w in containers(inv.get('wallets',[])) if w.get('extinct')]
    if len(wallets)!=1 or len(wallets[0]['raw']['descriptors'])!=summary['addresses']:return None
    return wallets[0],summary

def schedule(hub,state,ready):
    available={}
    for node,c in ready.items():
        if not supported(c) or hub.inventory_display.get(node,{}).get('token')!=c.get('token') or time.monotonic()-hub.inventories.get(node,{}).get('history_checked_at',hub.inventory_times.get(node,0))>90:continue
        try:g=group(hub,node)
        except ValueError:continue
        if g:available[node]=g
    for a,b in combinations(sorted(available),2):
        wa,sa=available[a];wb,sb=available[b]
        if sa['digest']==sb['digest']:continue
        # Counts choose a useful first direction, never establish authority.
        candidates=sorted(((a,wa,sa),(b,wb,sb)),key=lambda x:(x[2]['history_complete'],x[2]['transactions'],x[2]['addresses'],x[0]),reverse=True)
        source,wallet,summary=candidates[0]
        if not summary['history_complete']:continue
        target=b if source==a else a;other=available[target][1]
        # Do not compete with a currently executing/importing archive operation.
        if any(r.get('kind')=='wallet_retire' and r.get('state') in ('pending','recovery_required') and r.get('node_id') in (a,b) and not r.get('node_deleted') for r in state['requests'].values()):continue
        pairs=hub.transfers.pairs(state)
        if any(len(rows)==2 and {r['node_id'] for r in rows}=={a,b} and all(r['public_wallet']['descriptors'] and all(d['desc'].startswith('addr(') for d in r['public_wallet']['descriptors']) for r in rows) and any(r['state'] in ('pending','recovery_required') for r in rows) and not any(r.get('superseded_attempt') or r.get('superseded_container') for r in rows) for rows in pairs.values()):continue
        if not hub.permissions.allows_offer(target,wallet['raw']) and ('wallet_sync_offers_v1' not in hub.caps.get(target,set()) or hub.permissions.permits(target,wallet['raw']) is False):continue
        binding={source:summary['digest'],target:other['digest']}
        ident=digest({'purpose':'extinct_history_sync','source':source,'target':target,'summaries':binding})
        # Same observed mismatch is offered once, including denied/error results.
        if any(r.get('history_sync',{}).get('summaries')==binding and {r.get('node_id'),r.get('peer_id')}=={a,b} for r in state['requests'].values()):continue
        earliest=min((d.get('timestamp',0) for d in wallet['raw']['descriptors']),default=0)
        for node,peer,direction in ((source,target,'send'),(target,source,'receive')):
            state['requests'][digest({'transfer':ident,'direction':direction})]={'kind':'wallet_transfer','node_id':node,'peer_id':peer,'direction':direction,'transfer_id':ident,'state':'pending','descriptor_id':wallet['id'],'public_wallet':copy.deepcopy(wallet['raw']),'source_has_private_keys':False,'earliest_timestamp':earliest,'requires_blockchain_redownload':False,'created_utc':hub.utc(),'message':'Extinct history summaries differ. Review the direct Agent-to-Agent history comparison.','subwallets':wallet['subwallets'],'history_sync':{'version':1,'summaries':binding}}
        hub.registry.diagnostic_log.append('Wallet sync','Extinct history summaries differ · offered direct Agent comparison · source='+source[:12]+' · target='+target[:12]+'. History and labels remain on Agents.')

def validate_saved(row):
    value=row['history_sync']
    if row.get('kind')!='wallet_transfer' or row.get('source_has_private_keys') is not False or row.get('lifecycle_restore') or not row.get('public_wallet',{}).get('descriptors') or any(not d['desc'].startswith('addr(') for d in row['public_wallet']['descriptors']):raise ValueError('History comparison must be public Extinct data only.')
    if not isinstance(value,dict) or set(value)!={'version','summaries'} or type(value['version']) is not int or value['version']!=1 or not isinstance(value['summaries'],dict) or set(value['summaries'])!={row['node_id'],row['peer_id']} or row['node_id']==row['peer_id'] or any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v) for v in value['summaries'].values()):raise ValueError('Invalid saved direct history comparison.')
