"""Withdraw a stale preservation route; never erase outcomes or cancel a group."""
import time
from datetime import datetime


def reconcile(hub,node,token):
    c=hub.registry.connections.get(token)
    inv=hub.inventories.get(node,{})
    if not c or c.get('node_id')!=node or not hub.registry.rpc._unique(c) or hub.inventory_display.get(node,{}).get('token')!=token or not inv.get('loaded_complete') or not isinstance(inv.get('wallet_directory'),list) or time.monotonic()-inv.get('history_checked_at',0)>90 or hub.transfers.is_busy(node):return 0
    directory=set(inv['wallet_directory']);count=0
    with hub.edit() as state:
        for row in state['requests'].values():
            p=row.get('proposal',{})
            if row.get('node_id')!=node or row.get('kind')!='wallet_retire' or row.get('node_deleted') or row.get('state') not in ('pending','cancelled') or row.get('preservation_withdrawn') or p.get('version')!=3 or p.get('phase')!='preserve' or p.get('delete_wallet') is not False or p.get('wallet') in directory:continue
            try:
                if datetime.fromisoformat(inv['scanned_utc'].replace('Z','+00:00'))<=datetime.fromisoformat(row['created_utc'].replace('Z','+00:00')):continue
            except (KeyError,TypeError,ValueError):continue
            row.update(preservation_withdrawn=True,preservation_withdrawn_utc=hub.utc())
            if row['state']=='pending':row['message']='Preservation route withdrawn: the target archive is absent from this Agent’s current Core wallet directory. No preservation or deletion was reported successful.'
            if not row.get('delivered'):row.update(state='cancelled',preservation_withdrawn_before_delivery=True)
            count+=1
    if count:hub.registry.diagnostic_log.append('Wallet extinction','Stale preservation routes withdrawn · node='+node[:12]+' · count='+str(count)+' · prior outcomes and other Agents retained.')
    return count
