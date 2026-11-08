"""Saved, explicitly typed mobile reads. Never obtains a market/FX quote."""
from copy import deepcopy
from decimal import Decimal
from balance_store import BalanceStore
from preferences import FamilyStore
from report_store import ReportStore


def without_live_balances(value):
    if isinstance(value,dict):return {k:without_live_balances(v) for k,v in value.items() if k not in ('balances','balance_report','current_quote','quote_source','price_aud_per_btc')}
    if isinstance(value,list):return [without_live_balances(v) for v in value]
    return value

def snapshot(config,user,section):
    if not isinstance(section,str) or section not in ('balances','trace','cgt'):raise ValueError('Choose balances, trace or cgt.')
    if not FamilyStore(config).user(user):raise ValueError('Unknown user.')
    if section=='cgt':
        generation,report=ReportStore(config).load(user,None,allow_saved=True)
        return {'section':'cgt','generation':generation,'report':without_live_balances(report),'aud_purpose':'historical-tax-calculation','trust':'server-supplied; verify independently'}
    saved=BalanceStore(config).latest()
    if not saved:return {'section':section,'available':False,'wallets':[] if section=='balances' else None}
    result=saved['result']
    if section=='trace':return {'section':'trace','available':True,'trace_graph':deepcopy(result.get('trace_graph')),'purpose':'historical-cost-and-transaction-trace','trust':'server-supplied; verify independently'}
    if section!='balances':raise ValueError('Choose balances, trace or cgt.')
    rows=[]
    from wallet_names import dashboard_name
    family=FamilyStore(config).snapshot();labels={r['source']:dashboard_name(r) for r in family['ownership'] if r.get('kind')=='descriptor'}
    for row in result.get('balances',{}).get('wallets',[]):
        item={k:deepcopy(row[k]) for k in ('name','kind','descriptor_id','owner_name','smsf','watch_only','has_vault','confirmed_btc','unconfirmed_btc') if k in row}
        if row.get('descriptor_id') in labels:item['name']=labels[row['descriptor_id']]
        amount=row.get('btc')
        if amount is not None:
            number=Decimal(str(amount))
            if not number.is_finite() or number<0 or number*100000000!=(number*100000000).to_integral_value():raise ValueError('Saved balance is not an exact Bitcoin amount.')
            item['btc']=format(number,'f');item['satoshis']=int(number*100000000)
        else:item.update(btc=None,satoshis=None)
        rows.append(item)
    return {'section':'balances','available':True,'wallets':rows,'signature':saved.get('signature'),'as_of_utc':result.get('balances',{}).get('valuation_utc'),'unit':'BTC','market_prices_included':False,'trust':'server-supplied; verify balances against Agents'}
