"""Current Agent authoritative public lists. Listing is never transfer authority."""
import copy,secrets
from node_wallets import NodeWalletLoader


def current_agent(hub,node):
    version=next((c.get('agent_version') for c in hub.registry.connections.values() if c['node_id']==node),None)
    from agent_protocol import supported
    return supported(version)


def keys(raw):return {NodeWalletLoader.descriptor_key(r['desc']) for r in raw['descriptors']}
def contains(wallets,raw):
    available=set().union(*(keys(w['raw']) for w in wallets)) if wallets else set()
    return keys(raw)<=available


def schedule(transfers,state):
    """Retain prior outcomes, retire only Server queue delivery metadata."""
    for row in state['requests'].values():
        if row.get('kind')=='wallet_transfer' and row.get('state') not in ('complete','denied','error'):
            row['queue_visible']=False
            row['server_sync_retired']=True
    for entry in state['nodes'].values():
        for field in ('sync_snapshot','sync_offer_snapshot'):
            if entry.get(field):
                entry[field]=[]
                revision='sync_revision' if field=='sync_snapshot' else 'sync_offer_revision'
                entry[revision]=entry.get(revision,0)+1

def proposals(transfers,state,node):return []
def warnings(hub):return []
