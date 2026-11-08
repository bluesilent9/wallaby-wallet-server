"""Bind combined-policy private wallets to their authenticated setup roles.

A combined wallet exports all public keys. Its private_keys_enabled flag alone
cannot establish which of those keys it holds. Setup install receipts identify
node roles; the Agent's loaded-disc routing identity identifies disc roles.
"""
from node_wallets import NodeWalletLoader

def renamed(hub,node,name):
    from wallet_renames import RenameQueue
    operations=RenameQueue(hub).read()['operations'].values()
    for op in sorted(operations,key=lambda o:o.get('sequence',0)):
        for target in op.get('targets',{}).values():
            result=target.get('result') or {}
            if target.get('node_id')==node and target.get('storage')=='node' and target.get('wallet')==name and target.get('state')=='complete' and result.get('identity_verified') is True and result.get('new_wallet')==target.get('new_name'):
                name=target['new_name']
    return name

def private_roles(hub,node,account,setups):
    present={NodeWalletLoader.descriptor_key(r['desc']) for r in account['raw'].get('descriptors',[])}
    result=set()
    for setup in setups:
        if setup.get('state')!='ready':continue
        required={NodeWalletLoader.descriptor_key(d) for d in setup.get('descriptors',[])}
        if not required or not required<=present:continue
        roles={r['id']:r for r in setup['proposal']['cosigners']}
        installation=setup.get('inventories',{}).get(node,{})
        message=installation.get('message',{})
        for rid,envelope in setup.get('contributions',{}).items():
            role=roles.get(rid)
            if not role:continue
            if account.get('archive_id'):
                # Agent57 emits a routed alias with its full local role ID and
                # policy hash prefix, and independently tags that loaded route
                # with the full policy hash. Never infer a key from user labels.
                binding=setup.get('policy_hash')
                matched=(role.get('storage')=='disc' and account.get('policy_hash')==binding and account['name'].startswith('Disc ') and account['name'].endswith(' '+binding[:12]+' '+rid)) if binding else False
            else:
                original=message.get('signing_wallets',{}).get(rid)
                matched=bool(original and setup.get('routes',{}).get(rid)==node and installation.get('public_key')==role.get('agent_key') and message.get('policy_hash')==setup.get('policy_hash') and renamed(hub,node,original)==account['name'])
            if matched:
                result.add(envelope['message']['receive_key'].split(']')[-1].replace("'",'h'))
    return result
