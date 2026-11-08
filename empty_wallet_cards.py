"""Show assigned, verified empty wallets absent from an older balance trace."""
from decimal import Decimal
from preferences import resource_id
from wallet_names import dashboard_name
from policy_accounts import multisig_summary

def include_verified_empty(balance,catalog,chain,family):
    if chain.get('catalog_fingerprint')!=__import__('descriptor_store').DescriptorStore.fingerprint(catalog):return
    existing={w.get('descriptor_id') for w in balance['wallets']}
    owners={r['source']:r for r in family.get('ownership',[]) if r.get('kind')=='descriptor' and r.get('confirmed')}
    histories={w['id']:w for w in chain.get('wallets',[])}
    covered={r['wallet_id'] for r in chain.get('coverage',[]) if r.get('basis')=='Core listsinceblock complete loaded-wallet history' and r.get('transactions')==0}
    users={u['id']:u['name'] for u in family.get('users',[])}
    for w in catalog['wallets']:
        uid=w['id'];record=owners.get(uid);history=histories.get(uid)
        if uid in existing or uid not in covered or w.get('extinct') or not record or history is None:continue
        if history.get('records')!=[] or Decimal(str(history.get('pending_btc','NaN')))!=0:continue
        # Never interpret unknown/missing history as empty, or overwrite a funded row.
        balance['wallets'].append({'name':dashboard_name(record),'kind':'wallet','descriptor_id':uid,'resource_id':resource_id('descriptor',uid),
            'owner_id':record.get('owner_id'),'owner_name':users.get(record.get('owner_id'),'Someone else / external'),'smsf':bool(record.get('smsf')),
            'btc':'0','confirmed_btc':'0','unconfirmed_btc':'0','cash_aud':'0','value_aud':'0','btc_value_aud':'0','cost_basis_aud':'0','unrealised_gain_aud':'0','state':'neutral',
            'has_vault':bool(w.get('has_vault')),'watch_only':bool(w.get('watch_only')),'multisig':multisig_summary(w['raw']),
            'cost_basis_note':'No transactions in the complete verified Core wallet history.','balance_mode':'Confirmed descriptor blockchain history','last_update_utc':chain.get('scanned_utc'),
            'record_count':0,'last_record':'','planning_lots':[],'sources':[]})
        existing.add(uid)


def include_discovered(balance,catalog,family):
    """Existence is independent of the combined historical accounting scan."""
    import re
    from datetime import datetime
    existing={w.get('descriptor_id') for w in balance['wallets']}
    owners={r['source']:r for r in family.get('ownership',[]) if r.get('kind')=='descriptor' and r.get('confirmed')}
    users={u['id']:u['name'] for u in family.get('users',[])}
    for w in catalog['wallets']:
        uid=w['id'];record=owners.get(uid)
        if uid in existing or w.get('extinct') or not record:continue
        public=w.get('public_history',{});stamp=public.get('exported_utc')
        try:dated=bool(datetime.fromisoformat(stamp.replace('Z','+00:00')).utcoffset() is not None)
        except (TypeError,ValueError,AttributeError):dated=False
        # NodeWalletLoader publishes these together only after successful
        # listsinceblock exports from non-scanning loaded wallet replicas.
        empty=bool(w.get('node_history')==[] and public.get('outputs')==[] and w.get('node_sources') and dated and re.fullmatch('[0-9a-f]{64}',str(public.get('lastblock'))))
        zero='0' if empty else None
        balance['wallets'].append({'name':dashboard_name(record),'kind':'wallet','descriptor_id':uid,'resource_id':resource_id('descriptor',uid),
            'owner_id':record.get('owner_id'),'owner_name':users.get(record.get('owner_id'),'Someone else / external'),'smsf':bool(record.get('smsf')),
            'btc':zero,'confirmed_btc':zero,'unconfirmed_btc':zero,'cash_aud':'0','value_aud':zero,'btc_value_aud':zero,'cost_basis_aud':zero,'unrealised_gain_aud':zero,'state':'neutral' if empty else 'unavailable',
            'has_vault':bool(w.get('has_vault')),'watch_only':bool(w.get('watch_only')),'multisig':multisig_summary(w['raw']),
            'cost_basis_note':'No transactions in this loaded Core wallet’s exported history.' if empty else 'Balance and acquisition cost await verification; this wallet is shown from its discovered public policy and confirmed Ownership.',
            'balance_mode':'Loaded Core wallet history snapshot' if empty else 'Discovered wallet — balance verification pending','last_update_utc':stamp if dated else None,
            'record_count':0,'last_record':'','planning_lots':[],'sources':[]})
        existing.add(uid)
