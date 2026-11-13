"""Renew public invitations when an existing MAC-identified peer changes route.

A new invitation is never a retry/approval of an earlier wallet operation. Old
requests remain addressable so delayed real operation outcomes are retained.
"""
import copy,secrets,time
from agent_hub import digest

def deferred(hub,ident,reason):
    diagnostics=getattr(hub,'route_refresh_diagnostics',None)
    if diagnostics is None:hub.route_refresh_diagnostics={};diagnostics=hub.route_refresh_diagnostics
    if diagnostics.get(ident)!=reason:
        diagnostics[ident]=reason
        hub.registry.diagnostic_log.append('Wallet sync','Automatic invitation renewal deferred · request='+ident[:12]+' · reason='+reason)


def renew(transfers,state):
    hub=transfers.hub
    live={c['node_id']:c for c in list(hub.registry.connections.values()) if hub.registry.rpc._unique(c)}
    for ident,rows in list(transfers.pairs(state).items()):
        if len(rows)!=2 or any(r['state']!='pending' or r.get('superseded_attempt') or r.get('superseded_container') for r in rows):continue
        if any(r.get('retry_of')==ident for r in state['requests'].values()):continue
        if not all(r.get('proposal') for r in rows):continue
        versions={r['proposal'].get('transfer_version') for r in rows}
        preview_changed=versions=={3} and any(r.get('preview_notice') for r in rows)
        if versions!={2} and not preview_changed:continue
        nodes={r['node_id'] for r in rows}
        if not nodes<=live.keys() or any(transfers.is_busy(n) for n in nodes):continue
        # A replacement is a new identity-bound v3 invitation, not another
        # IPv6 request. Native peers need not advertise an IP to the Server.
        changed=versions=={2} and any(r['proposal']['node_ipv6']!=state['nodes'].get(r['node_id'],{}).get('ipv6') or r['proposal']['peer']['ipv6']!=state['nodes'].get(r['peer_id'],{}).get('ipv6') for r in rows)
        native_peers=all('wallet_relay_v1' in hub.caps.get(n,set()) for n in nodes)
        if not preview_changed and not changed and not native_peers:continue
        # A preview is produced automatically, before local authorisation. Keep
        # it on the original request, but never copy it into a replacement.
        # Agents retain active/attempted local work when a queue is withdrawn.
        if any(r.get('active_pair') or r.get('finished_utc') or r.get('result') for r in rows):
            deferred(hub,ident,'operation_evidence');continue
        receiver=next(r for r in rows if r['direction']=='receive')
        if hub.permissions.permits(receiver['node_id'],receiver['public_wallet']) is not True:
            deferred(hub,ident,'receive_permission');continue
        # Renew a known invitation using verified loaded-wallet facts. Unrelated
        # unloaded folders prevent proving absence, not reading a present source.
        if any(not (hub.inventories.get(n,{}).get('complete') or hub.inventories.get(n,{}).get('loaded_complete')) or time.monotonic()-hub.inventory_times.get(n,0)>60 for n in nodes):
            deferred(hub,ident,'loaded_inventory_missing_or_stale');continue
        if any(hub.registry.health.status(live[n]).get('state')!='ready' for n in nodes):
            deferred(hub,ident,'node_not_ready');continue
        sender=next(r for r in rows if r['direction']=='send')
        origin=[w for w in hub.inventories[sender['node_id']]['wallets'] if not w.get('signing_only')]
        if not transfers.contains(origin,sender['public_wallet']):
            deferred(hub,ident,'source_policy_missing');continue
        from wallet_preview import policies
        private=not __import__('policy_accounts').shared(sender['public_wallet']) and any(w.get('private_keys_enabled') and policies(sender['public_wallet'],True)<=policies(w['raw'],True) for w in origin)
        dest=hub.inventories[receiver['node_id']]['wallets']
        historical=bool(sender['public_wallet']['descriptors']) and all(r['desc'].startswith('addr(') for r in sender['public_wallet']['descriptors'])
        # Watched addresses do not prove that the Extinct transaction history
        # is current. Let the current Agents compare it directly.
        if not historical and not receiver.get('history_sync') and transfers.contains([w for w in dest if not w.get('signing_only')],receiver['public_wallet']):
            deferred(hub,ident,'destination_already_present');continue
        getattr(hub,'route_refresh_diagnostics',{}).pop(ident,None)
        fresh=secrets.token_hex(32)
        cause='Changed signed public preview' if preview_changed else 'Legacy IPv6-bound review'
        for old in rows:
            old.update(superseded_attempt=True,queue_visible=False,superseded_message=cause+' replaced by a new identity-bound invitation. Earlier approvals and outcomes were not reused.')
            row={k:copy.deepcopy(old[k]) for k in ('kind','node_id','peer_id','direction','descriptor_id','public_wallet','source_has_private_keys','earliest_timestamp','requires_blockchain_redownload')}
            if old.get('subwallets'):row['subwallets']=copy.deepcopy(old['subwallets'])
            if old.get('lifecycle_restore'):row['lifecycle_restore']=old['lifecycle_restore']
            if old.get('history_sync'):row['history_sync']=copy.deepcopy(old['history_sync'])
            row.update(transfer_id=fresh,state='pending',retry_of=ident,route_refresh=True,created_utc=hub.utc(),source_has_private_keys=old['source_has_private_keys'] if old.get('lifecycle_restore') else private)
            state['requests'][digest({'transfer':fresh,'direction':row['direction']})]=row
        hub.registry.diagnostic_log.append('Wallet sync',cause+' retired; new identity-bound public review requested · previous='+ident[:12]+' · request='+fresh[:12]+'. Local approval is required.')

def prior_in_progress(transfers,state,rows):
    """A late old outcome takes priority over a replacement invitation."""
    pairs=transfers.pairs(state);row=rows[0];seen=set()
    while row.get('route_refresh') and row.get('retry_of') not in seen:
        ident=row['retry_of'];seen.add(ident);prior=pairs.get(ident,[])
        if not prior:return False
        if any(r['state']!='pending' for r in prior):return True
        row=prior[0]
    return False

def summary(hub,node,state,transfers=None):
    live={c['node_id'] for c in list(hub.registry.connections.values()) if hub.registry.rpc._unique(c)}
    if node not in live:return {'state':'offline','text':'Wallet synchronisation: Agent offline.'}
    rows=[r for r in (transfers if transfers is not None else hub.transfers.summaries(state,node)) if not r['superseded'] and r['state']!='complete']
    if rows:return {'state':'pending','count':len(rows),'text':'Wallet synchronisation: '+str(len(rows))+' outstanding requests; review the details below.'}
    if not live or any(not hub.inventories.get(n,{}).get('complete') for n in live):return {'state':'checking','text':'Wallet synchronisation: loaded wallets checked; unloaded folders still prevent proving which other wallets are missing.'}
    if any(not hub.permissions.fresh(n) for n in live):return {'state':'checking','text':'Wallet synchronisation: checking the Agents’ current permissions.'}
    return {'state':'checked','text':'Wallet synchronisation: no outstanding requests among currently checked connected Agents. Blockchain status is separate.'}
