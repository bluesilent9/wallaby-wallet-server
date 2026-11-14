"""Validate saved advisory snapshots and retained historical offer evidence."""
from agent_hub import digest
STATUSES={'ready','secure_pairing_required','peer_offline','permissions_pending','discovery_pending','review_paused','history_recovery','local_outcome','earlier_operation','peer_changed','preview_changed','preview_expired','invalid_pair','disabled'}

def validate_saved(entry):
    import re
    from descriptor_store import clean_wallet
    offers=entry.get('sync_offer_snapshot');seen=set()
    if type(entry['sync_offer_revision']) is not int or entry['sync_offer_revision']<0 or not isinstance(offers,list) or len(offers)>128:raise ValueError('Invalid saved public wallet offers.')
    for o in offers:
        if not isinstance(o,dict) or not {'id','transfer_id','direction','peer','public_wallet','status'}<=set(o)<={'id','transfer_id','direction','peer','public_wallet','status','source_storage','source_online'} or not all(isinstance(o[k],str) and re.fullmatch('[0-9a-f]{64}',o[k]) for k in ('id','transfer_id')) or o['id'] in seen or o['direction'] not in ('send','receive') or o['status'] not in STATUSES:raise ValueError('Invalid saved public wallet offer.')
        if 'source_online' in o and type(o['source_online']) is not bool:raise ValueError('Invalid saved wallet source presence.')
        if 'source_storage' in o and o['source_storage'] not in ('node','disc'):raise ValueError('Invalid saved wallet source storage.')
        peer=o['peer']
        if not isinstance(peer,dict) or set(peer)!={'node_id','hostname'} or any(not isinstance(peer[k],str) or not peer[k] or len(peer[k])>512 for k in peer):raise ValueError('Invalid saved public wallet offer peer.')
        clean_wallet(o['public_wallet']);seen.add(o['id'])
