"""Refresh display holdings from current public records, independently of cost tracing."""
from decimal import Decimal, InvalidOperation
from datetime import datetime

ZERO=Decimal(0)
SAT=Decimal('0.00000001')
def number(value):
    try:value=Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError):return None
    return value if value.is_finite() else None

def history_signature(wallet):
    import hashlib,json
    # Confirmation counts and scan time change without changing acquisitions.
    fields=('txid','sats','fee_sats','fee_only','output_index','utc','cgt_loss','loss_outpoints')
    records=[{k:r[k] for k in fields if k in r} for r in wallet.get('records',[])]
    records=sorted(records,key=lambda r:json.dumps(r,sort_keys=True))
    return hashlib.sha256(json.dumps(records,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def evidence_changed(row,wallet):
    prior=row.get('balance_history_signature')
    if prior:return prior!=history_signature(wallet)
    # For already saved verified balances, only a later transaction constitutes
    # new evidence. A newer observation timestamp alone must not discard basis.
    try:
        checked=datetime.fromisoformat(row['watch_checked_utc'].replace('Z','+00:00'))
        return any(datetime.fromisoformat(r['utc'].replace('Z','+00:00'))>checked for r in wallet.get('records',[]) if r.get('utc'))
    except (KeyError,TypeError,ValueError):return False

def apply(row,btc,cash,*,changed=False):
    old=number(row.get('btc'));old_cash=number(row.get('cash_aud'))
    changed=changed or old!=btc or old_cash!=cash
    row.update(btc=str(btc) if btc else '0',cash_aud=str(cash) if cash is not None else None)
    if changed:
        row.update(cost_basis_aud='0' if btc==0 else None,unrealised_gain_aud=None,state='unavailable',planning_lots=[],sources=[],cost_basis_note='Current holdings updated. Acquisition costs are awaiting balance verification.')

def reconcile(report,snapshot,chain=None):
    """Only complete saved ledgers replace quantities; missing data is never a zero."""
    if not report:return
    rows=report['balances']['wallets'];updated=[];by_account={(r.get('owner_id'),bool(r.get('smsf'))):r for r in rows if r.get('kind')=='exchange'}
    for uid,meta in snapshot.get('ownership_runs',{}).items():
        for smsf,key in ((False,'bitaroo_data'),(True,'bitaroo_smsf_data')):
            row=by_account.get((uid,smsf));ledger=meta.get(key,{})
            if row is None or not ledger.get('periods'):continue
            periods=list(ledger['periods'].values());latest=max(periods,key=lambda p:p.get('end',''));btc=number(latest.get('closing_btc'))
            if btc is None:continue
            aud_rows=ledger.get('aud_rows',[]);btc_rows=ledger.get('btc_rows',[])
            cash=number(latest.get('closing_aud'))
            if cash is None and aud_rows:cash=number(max(enumerate(aud_rows),key=lambda r:(r[1].get('utc',''),r[0]))[1].get('balance'))
            entries=aud_rows+btc_rows;stamp=max((r.get('utc','') for r in entries),default=None)
            changed=row.get('record_count')!=len(entries) or stamp is not None and row.get('last_update_utc')!=stamp
            apply(row,btc,cash,changed=changed);updated.append(row)
            row.update(record_count=len(entries),last_update_utc=stamp,balance_as_of=latest['end'],balance_mode='Latest supplied Bitaroo statement closing balances')
    by_id={w['id']:w for w in (chain or {}).get('wallets',[])}
    for row in rows:
        wallet=by_id.get(row.get('descriptor_id'))
        if wallet is None or 'records' not in wallet:continue
        groups={}
        for r in wallet['records']:groups.setdefault(r['txid'],[]).append(r)
        sats=0
        for group in groups.values():
            delta=sum(r['sats'] for r in group)
            if not any(r['fee_only'] for r in group):delta-=max(r['fee_sats'] for r in group)
            sats+=delta
        pending=number(wallet.get('pending_btc'))
        if sats<0 or pending is None or Decimal(sats)*SAT+pending<0:continue
        changed=evidence_changed(row,wallet)
        apply(row,Decimal(sats)*SAT+pending,ZERO,changed=changed);updated.append(row)
        row.update(confirmed_btc=str(Decimal(sats)*SAT),unconfirmed_btc=str(pending),watch_checked_utc=chain.get('scanned_utc'),balance_mode='Descriptor blockchain history',balance_history_signature=history_signature(wallet))
    price=number(report['balances'].get('price_aud_per_btc'))
    for row in updated:
        btc=number(row.get('btc'));cash=number(row.get('cash_aud'));cost=number(row.get('cost_basis_aud'))
        market=btc*price if btc is not None and price is not None and price>0 else ZERO if btc==0 else None
        gain=market-cost if market is not None and cost is not None else None
        row.update(btc_value_aud=str(market) if market is not None else None,value_aud=str(market+cash) if market is not None and cash is not None else None,unrealised_gain_aud=str(gain) if gain is not None else None)
        if gain is not None:
            from decimal import ROUND_HALF_UP
            rounded=gain.quantize(Decimal('.01'),rounding=ROUND_HALF_UP);row['state']='profit' if rounded>0 else 'loss' if rounded<0 else 'neutral'

def needs_verification(saved,key,snapshot):
    """New supplied records need a trace; reconnecting unchanged nodes does not."""
    if not saved or saved.get('signature')==key:return False
    try:
        from datetime import timezone
        parse=lambda value:datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc)
        verified=parse(saved['result']['balances']['valuation_utc'])
        return any(parse(meta['completed_utc'])>verified for meta in snapshot.get('ownership_runs',{}).values())
    except (KeyError,TypeError,ValueError):return False
