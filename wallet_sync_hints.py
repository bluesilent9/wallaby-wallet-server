"""Live Server observations only; paired Agents own discovery and every transfer."""
import copy,json,re,time
from agent_hub import digest
from descriptor_store import clean_wallet
from node_wallets import NodeWalletLoader

CAPABILITY='wallet_sync_offers_v1'
# Same bounded informational envelope accepted by current Agents. These IDs are
# display identities, never request hashes or transfer authorisation.
MAX_OFFERS=128
MAX_BYTES=2*1024*1024
POLICY=re.compile(r'Wallaby policy [0-9a-f]{20}(?:_watch)?',re.IGNORECASE)


def current(hub,node):
    from nodes import DISCONNECT_SECONDS
    connections=[c for c in list(hub.registry.connections.values()) if c['node_id']==node]
    if len(connections)!=1:return None
    c=connections[0]
    if hub.registry.clock()-c['seen']>=DISCONNECT_SECONDS or not hub.registry.rpc._unique(c):return None
    inv=hub.inventories.get(node,{})
    if hub.inventory_display.get(node,{}).get('token')!=c['token'] or not (inv.get('complete') or inv.get('loaded_complete')) or time.monotonic()-inv.get('history_checked_at',0)>90:return None
    return c,inv


def wallets(inv):
    # Extinct children are display groups for ownership/tracing, not separate
    # wallets to sync. Recombine only this source's public historical records.
    normal=[w for w in inv.get('wallets',[]) if not w.get('extinct')]
    historical=[w for w in inv.get('wallets',[]) if w.get('extinct')]
    if historical:
        from extinct_sync import containers
        try:normal+=containers(historical)
        except ValueError:pass # Unusable public hints cannot block Agent exchange.
    return normal


def snapshot(hub,node):
    offers=[];seen=set()
    sources=sorted({c['node_id'] for c in list(hub.registry.connections.values())}-{node})
    for source in sources:
        live=current(hub,source)
        if not live:continue
        c,inv=live
        for w in wallets(inv):
            raw=w.get('raw',{})
            if w.get('signing_only') or w.get('scanning') or POLICY.fullmatch(raw.get('wallet_name','')):continue
            try:raw=clean_wallet(raw)['raw']
            except (ValueError,TypeError,KeyError):continue
            policy=sorted(NodeWalletLoader.descriptor_key(r['desc']) for r in raw['descriptors'])
            identity=digest({'purpose':'wallet_sync_advisory_v1','source':source,'receiver':node,'policy':policy})
            if identity in seen:continue
            seen.add(identity)
            hint={'id':identity,'transfer_id':identity,'direction':'receive','peer':{'node_id':source,'hostname':c['hostname']},'public_wallet':copy.deepcopy(raw),'status':'discovery_pending','source_online':True}
            if w.get('wallaby_storage') in ('node','disc'):hint['source_storage']=w['wallaby_storage']
            offers.append(hint)
    offers.sort(key=lambda o:(o['public_wallet']['wallet_name'].casefold(),o['peer']['node_id'],o['id']))
    # Hints are deliberately bounded and non-exhaustive. Never split a wallet
    # or fetch history/private material to fill this advisory snapshot.
    bounded=[];size=256
    for o in offers:
        n=len(json.dumps(o,sort_keys=True,ensure_ascii=True,allow_nan=False).encode())+1
        if len(bounded)>=MAX_OFFERS:break
        if size+n>MAX_BYTES:continue
        bounded.append(o);size+=n
    return bounded


def proposal(hub,state,node):
    if CAPABILITY not in hub.caps.get(node,set()):return []
    entry=state['nodes'].setdefault(node,{})
    hints=snapshot(hub,node)
    if hints!=entry.get('sync_offer_snapshot'):
        entry['sync_offer_snapshot']=hints
        entry['sync_offer_revision']=entry.get('sync_offer_revision',-1)+1
    return [{'kind':'wallet_sync_offers','version':1,'revision':entry['sync_offer_revision'],'offers':copy.deepcopy(hints)}]
