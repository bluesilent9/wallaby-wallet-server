"""One public historical container per sync request; ownership stays per label."""
from copy import deepcopy
from descriptor_store import clean_wallet
from node_wallets import NodeWalletLoader

def containers(wallets):
    ordinary=[];historical=[]
    for w in wallets:
        if not w.get('extinct'):ordinary.append(w);continue
        if w.get('private_keys_enabled') or any(not r['desc'].startswith('addr(') for r in w['raw']['descriptors']):raise ValueError('Historical synchronisation requires address-only wallets with private keys disabled.')
        historical.append(w)
    if not historical:return ordinary
    rows={};labels={};names=set()
    for w in historical:
        names.add(w['raw']['wallet_name'])
        for r in w['raw']['descriptors']:
            key=NodeWalletLoader.descriptor_key(r['desc']);prior=rows.get(key)
            if prior is not None and r!=prior:raise ValueError('Conflicting public historical descriptor metadata; refresh the node inventory.')
            rows[key]=deepcopy(r)
        for address,label in w.get('address_labels',{}).items():
            if address in labels and labels[address]!=label:raise ValueError('Conflicting historical address labels; resolve them on the local Agents.')
            labels[address]=deepcopy(label)
    if len(rows)>256:raise ValueError('The Extinct archive exceeds the 256-descriptor sync bound. No addresses were omitted or split into silent partial requests.')
    checked=clean_wallet({'wallet_name':'Extinct','descriptors':[rows[k] for k in sorted(rows)]})
    ordinary.append({'id':checked['id'],'name':'Extinct','raw':checked['raw'],'private_keys_enabled':False,'signing_only':False,'extinct':True,'address_labels':labels,'subwallets':sorted(names,key=str.casefold)})
    return ordinary
