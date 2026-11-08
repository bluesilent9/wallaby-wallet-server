"""Resolve saved display rows through approved wallet identity migrations only."""
from preferences import resource_id
from builder_identity import resolve


def canonicalise(config,balance,catalog):
    current={resource_id('descriptor',w['id']):w['id'] for w in catalog['wallets']}
    rows=[];seen={};current_ids=set(current.values())
    # Prefer a current record if both generations already exist. Never sum them.
    for row in sorted(balance['wallets'],key=lambda r:r.get('descriptor_id') not in current_ids):
        ident=row.get('descriptor_id')
        if not ident:rows.append(row);continue
        resource=resolve(config,resource_id('descriptor',ident));canonical=current.get(resource)
        if canonical is not None:
            row['descriptor_id']=canonical;row['resource_id']=resource
        key=(row.get('descriptor_id'),row.get('owner_id'),bool(row.get('smsf')))
        if key not in seen:seen[key]=row;rows.append(row)
    balance['wallets']=rows
