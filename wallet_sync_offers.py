"""Public availability is independent of pairing and never transfer authority."""
import copy
from agent_hub import digest

CAPABILITY='wallet_sync_offers_v1'
STATUSES={'ready','secure_pairing_required','peer_offline','permissions_pending','discovery_pending','review_paused','history_recovery','local_outcome','earlier_operation','peer_changed','preview_changed','preview_expired','invalid_pair','disabled'}

def snapshot(transfers,state,node):
    from sync_status import reason
    from sync_routes import prior_in_progress
    from wallet_retirement import suppress_sync
    from wallet_renames import RenameQueue
    from agent_hub import equivalent
    hub=transfers.hub;offers=[]
    hosts={n['id']:n['hostname'] for n in hub.registry._read()['nodes']}
    hosts.update({c['node_id']:c['hostname'] for c in list(hub.registry.connections.values())})
    renames=list(RenameQueue(hub).read()['operations'].values())
    for ident,rows in transfers.pairs(state).items():
        if len(rows)!=2 or any(r.get('superseded_container') or r.get('superseded_attempt') or r.get('node_deleted') for r in rows):continue
        source=next((r for r in rows if r['direction']=='send'),None)
        receiver=next((r for r in rows if r['direction']=='receive'),None)
        if not source or not receiver or receiver['state']=='complete':continue
        row=next((r for r in rows if r['node_id']==node),None)
        if not row or prior_in_progress(transfers,state,rows):continue
        raw=source['public_wallet']
        if source.get('lifecycle_restore'):
            if not __import__('wallet_lifecycle').permitted_transfer(state,source):continue
        elif suppress_sync(state,raw):continue
        if any(o['state']=='active' and equivalent(o['raw'],raw) for o in renames):continue
        # An obsolete route must not reappear alongside its replacement.
        if any(r.get('retry_of')==ident for r in state['requests'].values()):continue
        code=reason(hub,state,rows)[0] or 'ready'
        # No executable proposal exists before pairing, so the generic blocker
        # would otherwise say discovery_pending rather than explain pairing.
        if code=='discovery_pending' and not hub.relay.mesh({r['node_id'] for r in rows})['ready']:
            code='secure_pairing_required'
        peer_host=hosts.get(row['peer_id'],row['peer_id'])
        offers.append({'id':digest({'transfer':ident,'direction':row['direction']}),'transfer_id':ident,
                       'direction':row['direction'],'peer':{'node_id':row['peer_id'],'hostname':peer_host},
                       'public_wallet':copy.deepcopy(row['public_wallet']),'status':code})
    offers.sort(key=lambda o:(o['public_wallet']['wallet_name'].casefold(),o['peer']['node_id'],o['id']))
    if len(offers)>128:raise ValueError('Too many public wallet offers; finish existing requests first.')
    return offers

def schedule(transfers,state):
    for node,entry in state['nodes'].items():
        if CAPABILITY not in transfers.hub.caps.get(node,set()):continue
        offers=snapshot(transfers,state,node)
        if offers!=entry.get('sync_offer_snapshot'):
            entry['sync_offer_revision']=entry.get('sync_offer_revision',-1)+1
            entry['sync_offer_snapshot']=offers
            transfers.hub.registry.diagnostic_log.append('Wallet sync','Public offers updated · node='+node[:12]+' · revision='+str(entry['sync_offer_revision'])+' · offers='+str(len(offers)))

def proposal(hub,entry,node):
    if CAPABILITY not in hub.caps.get(node,set()) or 'sync_offer_revision' not in entry:return []
    return [{'kind':'wallet_sync_offers','version':1,'revision':entry['sync_offer_revision'],'offers':copy.deepcopy(entry['sync_offer_snapshot'])}]

def validate_saved(entry):
    import re
    from descriptor_store import clean_wallet
    offers=entry.get('sync_offer_snapshot');seen=set()
    if type(entry['sync_offer_revision']) is not int or entry['sync_offer_revision']<0 or not isinstance(offers,list) or len(offers)>128:raise ValueError('Invalid saved public wallet offers.')
    for o in offers:
        if not isinstance(o,dict) or set(o)!={'id','transfer_id','direction','peer','public_wallet','status'} or not all(isinstance(o[k],str) and re.fullmatch('[0-9a-f]{64}',o[k]) for k in ('id','transfer_id')) or o['id'] in seen or o['direction'] not in ('send','receive') or o['status'] not in STATUSES:raise ValueError('Invalid saved public wallet offer.')
        peer=o['peer']
        if not isinstance(peer,dict) or set(peer)!={'node_id','hostname'} or any(not isinstance(peer[k],str) or not peer[k] or len(peer[k])>512 for k in peer):raise ValueError('Invalid saved public wallet offer peer.')
        clean_wallet(o['public_wallet']);seen.add(o['id'])
