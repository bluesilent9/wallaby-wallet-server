"""Fresh absence can outdate a completed import, never its recorded outcome."""
import time
from datetime import datetime

def current(hub,node,connection,complete=False):
    inv=hub.inventories.get(node,{})
    return bool((inv.get('complete') if complete else inv.get('complete') or inv.get('loaded_complete')) and hub.inventory_display.get(node,{}).get('token')==connection.get('token') and time.monotonic()-inv.get('history_checked_at',hub.inventory_times.get(node,0))<=90 and not any(w.get('scanning') for w in inv.get('wallets',[])))

def missing_again(hub,state,ready,source,target,previous):
    # A failed read, unloaded folder or reconnect is not evidence of deletion.
    if not current(hub,target,ready[target],complete=True) or not current(hub,source,ready[source]):return False
    if hub.transfers.is_busy(source) or hub.transfers.is_busy(target):return False
    try:
        scanned=datetime.fromisoformat(hub.inventories[target]['scanned_utc'].replace('Z','+00:00'))
        finished=datetime.fromisoformat(previous['finished_utc'].replace('Z','+00:00'))
        if scanned<=finished:return False
    except (KeyError,ValueError,TypeError):return False
    rows=hub.transfers.pairs(state).get(previous['transfer_id'],[])
    return bool(len(rows)==2 and previous['state']=='complete' and not any(r.get('active_pair') or r['state'] in ('error','denied','recovery_required') for r in rows))
