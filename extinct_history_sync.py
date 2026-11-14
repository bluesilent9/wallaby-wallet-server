"""Read-only validation of historical summary bindings in saved profiles."""
import re

def validate_saved(row):
    value=row['history_sync']
    if row.get('kind')!='wallet_transfer' or row.get('source_has_private_keys') is not False or row.get('lifecycle_restore') or not row.get('public_wallet',{}).get('descriptors') or any(not d['desc'].startswith('addr(') for d in row['public_wallet']['descriptors']):raise ValueError('History comparison must be public Extinct data only.')
    if not isinstance(value,dict) or set(value)!={'version','summaries'} or type(value['version']) is not int or value['version']!=1 or not isinstance(value['summaries'],dict) or set(value['summaries'])!={row['node_id'],row['peer_id']} or row['node_id']==row['peer_id'] or any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v) for v in value['summaries'].values()):raise ValueError('Invalid saved direct history comparison.')
