"""Fresh discovery can outdate an import; final ownership checks stay local."""
import time
from datetime import datetime

def current(hub,node,connection,complete=False):
    inv=hub.inventories.get(node,{})
    return bool((inv.get('complete') if complete else inv.get('complete') or inv.get('loaded_complete')) and hub.inventory_display.get(node,{}).get('token')==connection.get('token') and time.monotonic()-inv.get('history_checked_at',hub.inventory_times.get(node,0))<=90 and not any(w.get('scanning') for w in inv.get('wallets',[])))

def local_archive_review(hub,node,connection,raw):
    """An offer to inspect/merge, not an assertion that unloaded wallets are absent.

    Agent 97+ loads local wallets only inside its approved receive operation,
    checks active ownership, merges an existing archive, then restores loading.
    """
    import re
    inv=hub.inventories.get(node,{})
    version=connection.get('agent_version','')
    m=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:~dev(\d+))?',version) if isinstance(version,str) else None
    supported=bool(m and (*map(int,m.groups()[:3]),int(m[4]) if m[4] else 10**9)>=(2,0,0,97))
    return bool(supported and inv.get('unloaded_wallets') and current(hub,node,connection) and raw.get('descriptors') and all(d['desc'].startswith('addr(') for d in raw['descriptors']))

def missing_again(hub,state,ready,source,target,previous):
    # A failed read or reconnect is not evidence of deletion. Unknown unloaded
    # folders allow only a public archive review with independent local checks.
    if not (current(hub,target,ready[target],complete=True) or local_archive_review(hub,target,ready[target],previous['public_wallet'])) or not current(hub,source,ready[source]):return False
    # A known completed import may simply have returned to its unloaded state.
    # A possible local archive is not deletion evidence and must not create an
    # endless sequence of new reviews after every successful merge.
    inv=hub.inventories[target]
    if not inv.get('complete') and set(inv.get('unloaded_wallets',[])) & {'Wallaby Extinct','Extinct','extinct_watch'}:return False
    if hub.transfers.is_busy(source) or hub.transfers.is_busy(target):return False
    try:
        scanned=datetime.fromisoformat(hub.inventories[target]['scanned_utc'].replace('Z','+00:00'))
        finished=datetime.fromisoformat(previous['finished_utc'].replace('Z','+00:00'))
        if scanned<=finished:return False
    except (KeyError,ValueError,TypeError):return False
    rows=hub.transfers.pairs(state).get(previous['transfer_id'],[])
    return bool(len(rows)==2 and previous['state']=='complete' and not any(r.get('active_pair') or r['state'] in ('error','denied','recovery_required') for r in rows))
