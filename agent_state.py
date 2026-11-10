"""Validate public Agent records before accepting a profile archive."""
import base64,re
from descriptor_store import clean_wallet
from agent_hub import canonical,ipv6,digest
from vault_records import public_vault
from signed_psbt import decode
from transaction_templates import clean_diagram

def validate(state,users,config=None):
    if not isinstance(state,dict) or set(state)!={'version','vaults','nodes','requests','exports','receipts'} or type(state['version']) is not int or state['version']!=1:raise ValueError('Invalid saved Agent exchange schema.')
    canonical(state)
    if any(not isinstance(state[k],dict) or len(state[k])>100000 for k in ('vaults','nodes','requests','exports','receipts')):raise ValueError('Invalid saved Agent record bounds.')
    for ident,row in state['vaults'].items():
        public_vault(row['public'])
        if ident!=digest(row['public']) or not isinstance(row['sources'],list):raise ValueError('Invalid saved vault identity.')
    for row in state['nodes'].values():
        for w in row.get('known_wallets',{}).values():clean_wallet(w['raw'])
        for w in row.get('known_archives',{}).values():
            clean_wallet(w['raw'])
            if not re.fullmatch('[0-9a-f]{64}',str(w.get('archive_id'))):raise ValueError('Invalid saved archive package identity.')
        for archive,record in row.get('archive_inventory',{}).items():
            m=record['message']
            if archive!=m.get('archive_id') or record['envelope'].get('message')!=m or not ((m.get('event')=='archive_observed' and m.get('payload_verified') is True and m.get('payload_sha256')==archive and m.get('readback_verified') is False) or (m.get('event') in ('archive_verified','replacement_verified') and m.get('readback_verified') is True)) or not re.fullmatch('[0-9a-f]{64}',archive):raise ValueError('Invalid saved public archive evidence.')
            for member in m['members']:clean_wallet(member['public_wallet'])
            if config:
                from setup_signatures import verify
                verify(config,record['envelope'],record['envelope']['public_key'])
        if 'sync_offer_revision' in row:
            from wallet_sync_offers import validate_saved
            validate_saved(row)
        if row.get('ipv6'):ipv6(row['ipv6'])
        if 'sync_revision' in row:
            if type(row['sync_revision']) is not int or row['sync_revision']<0 or not isinstance(row.get('sync_snapshot'),list) or len(row['sync_snapshot'])>128:raise ValueError('Invalid saved synchronization list.')
            seen=set()
            for p in row['sync_snapshot']:
                if p.get('kind')!='wallet_transfer' or p.get('transfer_version') not in (2,3) or p.get('transfer_id') in seen:raise ValueError('Invalid saved synchronization row.')
                seen.add(p['transfer_id']);canonical(p)
    for row in state['exports'].values():
        if row.get('user_id') not in users:raise ValueError('Saved vault proposal refers to an unknown profile.')
        public_vault(row['vault']);clean_diagram(row['diagram']);doc=decode(base64.b64decode(row['psbt'],validate=True))
        if len(doc['inputs'])!=len(row['input_wallets']):raise ValueError('Invalid saved vault funding assignments.')
        if any(any(k[0] in (2,7,8,19,20) for k in f) for f in doc['inputs']):raise ValueError('A composable vault proposal must remain unsigned.')
    for ident,row in state['requests'].items():
        if row.get('kind') not in ('wallet_transfer','sign_psbt_partial','broadcast_transaction','wallet_retire','wallet_policy_refresh') or row.get('state') not in ('pending','complete','denied','error','recovery_required','cancelled'):raise ValueError('Invalid saved Agent request.')
        if row.get('state')=='cancelled' and row.get('kind') not in ('wallet_retire','sign_psbt_partial','broadcast_transaction','wallet_policy_refresh'):raise ValueError('Invalid cancelled request kind.')
        if row.get('proposal'):canonical(row['proposal'])
        if row.get('history_sync'):
            from extinct_history_sync import validate_saved
            validate_saved(row)
        if row.get('kind')=='wallet_transfer' and row.get('proposal'):
            p=row['proposal']
            if row.get('lifecycle_restore'):
                from wallet_preview import validate_restoration
                validate_restoration(p.get('restoration'),row['public_wallet'])
            elif 'restoration' in p:raise ValueError('A restoration proposal requires a saved Wallet Server lifecycle request.')
        if row.get('kind')=='wallet_policy_refresh':
            p=row['proposal']
            if p.get('version')==2:
                from relay_bindings import validate_requirements
                validate_requirements(p.get('peer_transport'))
            if p.get('kind')!='wallet_policy_refresh' or p.get('request_id')!=ident or p.get('chain')!='main' or len(p.get('previous_descriptors',[]))!=2:raise ValueError('Invalid saved public policy refresh.')
            from builder_destinations import validate_record
            clean_wallet({'wallet_name':p['wallet'],'descriptors':[{'desc':d,'range':[0,999],'active':False,'internal':bool(i%2)} for i,d in enumerate([*p['previous_descriptors'],p['receive_descriptor'],p['change_descriptor']])]})
        if row.get('kind')=='wallet_retire' and row.get('proposal',{}).get('version')==3:
            from wallet_retirement import validate_saved
            validate_saved(state,ident,row,users)
            __import__('wallet_lifecycle').validate_saved(state,ident,row)
        if row.get('kind')=='wallet_retire' and row.get('proposal',{}).get('version')!=3:raise ValueError('Unsupported retirement protocol. Only the current phased protocol is accepted.')
        if row.get('kind')=='wallet_transfer' and row.get('signed_preview'):
            from wallet_preview import validate as validate_preview,verify,policies
            payload=row['signed_preview'];p=row['proposal'];v=payload['preview']
            proof=verify(config,payload,fresh=False) if config else validate_preview(payload,fresh=False)
            from relay_bindings import matches_preview
            if p.get('transfer_version')==3 and payload['public_key']!=p['transport']['sender_identity']:raise ValueError('Saved relay preview sender identity mismatch.')
            if row['direction']!='send' or not matches_preview(v,p) or policies(v['public_wallet'],True)!=policies(p['public_wallet'],True) or v.get('restoration')!=p.get('restoration'):raise ValueError('Saved preview does not match its frozen request.')
    return state
