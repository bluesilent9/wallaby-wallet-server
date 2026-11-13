"""Keep one durable ledger for an explicitly preserved retired wallet.

A saved active descriptor and its address-only Extinct copy are two views of
one account, not two owners of its scripts. Only recorded retirement evidence
may establish this alias; unrelated script collisions remain errors.
"""
from copy import deepcopy
from wallet_lifecycle import roots
from node_wallets import NodeWalletLoader

def reconcile(fresh,old,state):
    result=deepcopy(fresh);aliases=set()
    for key,root in roots(state).values():
        if not root.get('dashboard_extinct'):continue
        restoring=bool(root.get('restoration'))
        # The Server must already have verified the complete preservation receipt.
        preserved=any(r.get('root_hash')==key and r.get('state')=='complete' and r.get('archive_checked') and r.get('proposal',{}).get('phase')=='preserve' and r['proposal'].get('manifest_hash')==root['proposal'].get('manifest_hash') for r in state['requests'].values())
        if not preserved:continue
        manifest=root['proposal'].get('manifest',{});expected={r['address']:r['label'] for r in manifest.get('addresses',[])}
        if not expected:continue
        original=root.get('dashboard_wallet')
        if not original:continue
        keys={NodeWalletLoader.descriptor_key(r['desc']) for r in original['raw']['descriptors']}
        saved=next((w for w in old if w['id']==original['id']),original)
        matches=[];covered=set()
        for w in result:
            labels=w.get('address_labels',{})
            if not w.get('extinct') or not labels or not set(labels)<=expected.keys():continue
            if any(metadata['label']!=expected[address] for address,metadata in labels.items()):continue
            if any(not r['desc'].startswith('addr(') for r in w['raw']['descriptors']):continue
            matches.append(w);covered.update(labels)
        if covered!=set(expected):continue
        # An old still-loaded replica may remain during deletion. Prefer fresh
        # archive history while retaining the original policy/account identity.
        active=[w for w in result if {NodeWalletLoader.descriptor_key(r['desc']) for r in w['raw']['descriptors']}==keys]
        received={r.get('address') for w in [saved]+active for r in w.get('node_history',[]) if r.get('category') in ('receive','generate','immature') and r.get('address')}
        if not restoring and not received<=covered:continue
        wallet=deepcopy(active[0] if restoring and active else saved);wallet.update(extinct=not restoring,watch_only=all(w.get('watch_only',True) for w in active) if restoring and active else True)
        wallet['node_sources']=list({(r['node_id'],r['wallet_name']):deepcopy(r) for w in matches+(active if restoring else []) for r in w.get('node_sources',[])}.values())
        # Keep every previously verified transaction discoverable until the
        # archive supplies it. Chain readback still rejects missing/conflicted
        # data; absence in an incomplete archive must never erase old history.
        wallet['node_history']=list({(r['txid'],r.get('vout'),r.get('category')):deepcopy(r) for w in [saved]+matches+(active if restoring else []) for r in w.get('node_history',[])}.values())
        wallet['address_labels']={a:deepcopy(m) for w in matches for a,m in w['address_labels'].items()}
        histories=[w.get('public_history',{}) for w in matches]
        wallet['public_history']={**deepcopy(histories[0]),'outputs':list({(r['txid'],r['vout']):deepcopy(r) for h in histories for r in h.get('outputs',[])}.values())}
        if not restoring:wallet['receiving_address']=None
        consumed={w['id'] for w in matches+active}
        # Also remove a previously published smaller archive view whose ID
        # changed after additional preserved addresses were imported.
        for prior in old:
            labels=prior.get('address_labels',{})
            if prior.get('extinct') and labels and set(labels)<=expected.keys() and all(m['label']==expected[a] for a,m in labels.items()) and all(r['desc'].startswith('addr(') for r in prior['raw']['descriptors']):consumed.add(prior['id'])
        aliases.update(consumed-{wallet['id']});result=[w for w in result if w['id'] not in consumed]+[wallet]
    return result,aliases
