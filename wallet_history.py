"""Public, confirmed wallet movements; never use purchase-cost provenance as a ledger."""
from descriptor_store import DescriptorStore
from descriptor_snapshot import saved_history
from preferences import resource_id
from node_wallets import NodeWalletLoader


def rows(chain, wallet, tip=None):
    uid=wallet['id'];owned=chain.get('wallet_outputs',{});transactions=chain.get('transactions',{})
    ledger={}
    for item in wallet.get('node_history',[]):ledger.setdefault(item['txid'],[]).append(item)
    scripts={o['script'] for ident,t in transactions.items() for n,o in enumerate(t.get('outputs',[])) if owned.get(ident+':'+str(n))==uid}
    result=[];balance=0
    # Use Core block position; retain scanner ancestry order when unavailable.
    def position(pair):
        order,(ident,t)=pair;value=t.get('block_index')
        if type(value) is not int:value=next((r['blockindex'] for r in ledger.get(ident,[]) if type(r.get('blockindex')) is int),order)
        return t['height'],value,order
    ordered=sorted(enumerate(transactions.items()),key=position)
    for rank,(order,(ident,t)) in enumerate(ordered):
        outputs=t.get('outputs',[]);inputs=t.get('inputs',[])
        mine=lambda i:owned.get(str(i.get('txid'))+':'+str(i.get('vout')))==uid or i.get('script') in scripts
        incoming=sum(o['value'] for n,o in enumerate(outputs) if owned.get(ident+':'+str(n))==uid)
        outgoing=sum(i['value'] for i in inputs if mine(i) and i.get('value') is not None)
        if any(mine(i) and i.get('value') is None for i in inputs):raise ValueError('Wallet input value is unavailable; the balance cannot be reconstructed.')
        if not incoming and not outgoing:continue
        delta=incoming-outgoing;balance+=delta
        if balance<0:raise ValueError('Wallet history is incomplete; a running balance cannot be safely reconstructed.')
        known=ledger.get(ident,[]);reported=[r['confirmations'] for r in known if type(r.get('confirmations')) is int]
        confirmations=max(0,tip-t['height']+1) if type(tip) is int else min(reported) if reported else 0
        if confirmations<6:continue
        sent=delta<0 or delta==0 and outgoing>0
        internal={NodeWalletLoader.descriptor_key(r['desc']) for r in wallet.get('raw',{}).get('descriptors',[]) if r.get('internal') is True}
        external={NodeWalletLoader.descriptor_key(r['desc']) for r in wallet.get('raw',{}).get('descriptors',[]) if r.get('internal') is False}
        change=set();receiving=set()
        for r in known:
            parents={NodeWalletLoader.descriptor_key(d) for d in r.get('parent_descs',[])}
            if parents & internal:change.add(r.get('vout'))
            elif parents & external:receiving.add(r.get('vout'))
        # include_change=True deliberately retains change in the saved ledger.
        # Core also reports it as a send: exclude it using public parent policies,
        # never by size, name, or by guessing which output is the recipient.
        addresses=list(dict.fromkeys(r['address'] for r in known if r.get('category')=='send' and r.get('address') and r.get('vout') not in change and (r.get('vout') in receiving or owned.get(ident+':'+str(r.get('vout')))!=uid))) if sent else []
        if not addresses:
            addresses=list(dict.fromkeys(o['address'] for n,o in enumerate(outputs) if o.get('address') and (owned.get(ident+':'+str(n))!=uid if sent else owned.get(ident+':'+str(n))==uid)))
        # Self-transfers still reduce the wallet by their fee. If Core's send
        # destination is missing, link the TXID rather than guess a change address.
        label=addresses[0] if len(addresses)==1 else 'Multiple send addresses' if sent and len(addresses)>1 else 'View transaction'
        fee=t.get('fee_sats') if t.get('fee_known') else None
        shared=bool(t.get('joint'));net=abs(delta)-fee if sent and fee is not None and not shared else None if sent else delta
        row={'txid':ident,'utc':t['utc'],'height':t['height'],'confirmations':confirmations,'direction':'send' if sent else 'receive','addresses':addresses,'address':label,'address_query':addresses[0] if len(addresses)==1 else ident,'amount_sats':str(delta),'balance_sats':str(balance),'net_sats':str(net) if net is not None else None,'gross_sats':str(abs(delta)),'fee_sats':str(fee) if fee is not None else None,'shared_fee':shared,'internal_transfer':bool(outgoing and not any(o['value']>0 and owned.get(ident+':'+str(n))!=uid for n,o in enumerate(outputs))),'rbf':t.get('rbf'),'segwit':t.get('segwit'),'taproot':t.get('taproot'),'taproot_outputs':t.get('taproot_outputs'),'order':rank,'movement_order':0}
        if outgoing and incoming and row['internal_transfer'] and not shared:
            # A self-transfer has two physical movements within one transaction.
            # Debit first, then credit: the receive row is newer in the display.
            received=list(dict.fromkeys(o['address'] for n,o in enumerate(outputs) if o.get('address') and o['value']>0 and owned.get(ident+':'+str(n))==uid))
            label=received[0] if len(received)==1 else 'Multiple send addresses' if received else 'View transaction'
            result.append(dict(row,direction='send',addresses=received,address=label,address_query=received[0] if len(received)==1 else ident,amount_sats=str(-outgoing),balance_sats=str(balance-incoming),gross_sats=str(outgoing),net_sats=str(outgoing-fee) if fee is not None else None))
            result.append(dict(row,direction='receive',addresses=received,address=received[0] if len(received)==1 else 'View transaction',address_query=received[0] if len(received)==1 else ident,amount_sats=str(incoming),balance_sats=str(balance),gross_sats=str(incoming),net_sats=str(incoming),movement_order=1))
        else:result.append(row)
    return sorted(result,key=lambda r:(r['height'],r['order'],r['movement_order']),reverse=True)


def snapshot(config,ident,registry=None):
    catalog=DescriptorStore(config).read()
    wallet=next((w for w in catalog['wallets'] if ident in (w['id'],resource_id('descriptor',w['id']))),None)
    if not wallet:
        from builder_identity import resolve
        candidates={resolve(config,ident),resolve(config,resource_id('descriptor',ident))}
        wallet=next((w for w in catalog['wallets'] if resource_id('descriptor',w['id']) in candidates),None)
    lifecycle=__import__('wallet_lifecycle').read(config)
    preserved=next((r for _,r in lifecycle.values() if ident in (r['wallet_id'],__import__('json').loads(r['wallet_id'])[1])),None)
    current_wallet=wallet is not None
    if not wallet and preserved:wallet=preserved.get('dashboard_wallet')
    if not wallet:raise ValueError('Node transaction history is available for descriptor wallets only.')
    frozen=__import__('builder_history').read(config,preserved.get('dashboard_history_fingerprint')) if preserved else None
    chain=(frozen or saved_history(config,catalog)) if preserved and (not preserved.get('restoration') or not current_wallet) else saved_history(config,catalog);tip=None
    if registry:
        heights=[n.get('blockchain',{}).get('blocks') for n in registry.snapshot()['nodes'] if n.get('rpc_ready') and n.get('blockchain',{}).get('state')=='ready']
        tip=max((h for h in heights if type(h) is int),default=None)
    if tip is None:tip=chain.get('tip_height')
    return {'wallet_id':wallet['id'],'rows':rows(chain,wallet,tip),'scanned_utc':chain.get('scanned_utc'),'minimum_confirmations':6}
