"""Keep one durable ledger for an explicitly preserved retired wallet.

A saved active descriptor and its address-only Extinct copy are two views of
one account, not two owners of its scripts. Only recorded retirement evidence
may establish this alias; unrelated script collisions remain errors.
"""
from copy import deepcopy
import json
from wallet_lifecycle import roots
from node_wallets import NodeWalletLoader

def upgrade(hub,catalog):
    """Migrate saved extinction metadata, without rewriting signed proposals.

    Earlier completed preservation records had the durable wallet ID and policy,
    but predated the presentation/restoration metadata introduced afterwards.
    """
    if not any(not r.get('dashboard_wallet') or 'dashboard_extinct' not in r for _,r in roots(hub.read()).values()):return
    with hub.edit() as state:
        by_id={w['id']:w for w in catalog}
        for key,root in roots(state).values():
            if root.get('cancel_requested') or root.get('restoration'):continue
            if root.get('dashboard_wallet') and 'dashboard_extinct' in root:continue
            preserved=any(r.get('root_hash')==key and r.get('state')=='complete' and r.get('archive_checked') and r.get('proposal',{}).get('phase')=='preserve' and r['proposal'].get('manifest_hash')==root['proposal'].get('manifest_hash') for r in state['requests'].values())
            if not preserved:continue
            try:kind,uid=json.loads(root['wallet_id'])
            except (ValueError,TypeError,KeyError):continue
            wallet=by_id.get(uid)
            if kind!='descriptor' or not wallet or not root.get('retirement_wallet'):continue
            policy=lambda raw:{NodeWalletLoader.descriptor_key(r['desc']) for r in raw['descriptors']}
            if policy(wallet['raw'])!=policy(root['retirement_wallet']):continue
            if not root.get('dashboard_wallet'):root['dashboard_wallet']=deepcopy(wallet)
            if 'dashboard_extinct' not in root:root['dashboard_extinct']=True
            hub.registry.diagnostic_log.append('Wallet discovery','Saved extinction metadata migrated · wallet='+uid[:12]+' · verified preservation and original request retained.')


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

def prepare(config,hub):
    """Reconcile saved views before an explicit scan, without waiting for polling."""
    from descriptor_store import DescriptorStore
    from preferences import FamilyStore
    store=DescriptorStore(config);old=store.read();upgrade(hub,old['wallets'])
    wallets,aliases=reconcile(old['wallets'],old['wallets'],hub.read())
    if wallets==old['wallets']:return False
    if store.read()!=old:raise ValueError('Wallet inventory changed during reconciliation; retry the Ownership run.')
    store.replace_node_wallets(wallets)
    if aliases:
        with FamilyStore(config).transaction() as data:
            data['ownership']=[r for r in data['ownership'] if not (r.get('kind')=='descriptor' and r['source'] in aliases)]
            for meta in data.get('ownership_runs',{}).values():meta['inventory']=[r for r in meta.get('inventory',[]) if not (r.get('kind')=='descriptor' and r['source'] in aliases)]
    hub.registry.diagnostic_log.append('Wallet discovery','Saved retirement views reconciled before wallet tracing · archive aliases='+str(len(aliases))+'. Original account identities retained.')
    return True
