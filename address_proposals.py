"""Read-only Address Book overlays for public Wallet Builder proposals."""
import json
from builder_workspace import BuilderWorkspace
from builder_destinations import Destinations
from descriptor_store import clean_wallet
from node_wallets import NodeWalletLoader
from storage import data_directory
from vendor.embit.descriptor import Descriptor
from vendor.embit.networks import NETWORKS

def apply(config,rows,catalog):
    state=BuilderWorkspace(config).read();work=state['workspaces'].get('wallet');tx=state['workspaces'].get('transaction')
    # Preserve the exact preview after handoff while the Agents approve and
    # install the policy. It is not a replacement for their local approvals.
    if tx and not tx.get('cancellation_id'):
        store=Destinations(config)
        for card in tx.get('draft',{}).get('nodes',[]):
            ident=card.get('id','')
            if not ident.startswith('receive-'):continue
            try:
                dest=store.get(ident);key=dest['base'];entry=rows.get(key)
                if not entry or not dest.get('height') or key not in catalog:continue
                if any(r['address']==dest['address'] for r in entry.get('addresses',[])):continue
                if dest['address'] in entry.get('funded_addresses',[]) or dest['height']<=entry.get('current_height',0):continue
                entry['proposed_address']={'address':dest['address'],'descriptor':dest['descriptors'][0]['desc'],'index':dest['index'],'vault_height':dest['height'],'observed_utc':tx.get('updated_utc') or tx['created_utc'],'txid':None,'proposed':True,'comparison_samples':__import__('refresh_comparison').samples(dest['descriptors'],dest['index'])}
            except (ValueError,KeyError,TypeError):continue
    if not work or work.get('cancellation_id'):return
    if work.get('renewal'):
        from vault_refresh import proposed
        try:preview=proposed(config,work)
        except (ValueError,KeyError,TypeError):return
        if not preview:return
        key=work['renewal']['source'];wallet=catalog.get(key)
        if not wallet:return
        if key not in rows:
            rows[key]={'id':key,'source':wallet['id'],'kind':'descriptor','has_vault':True,'status':'available','addresses':[],'address_history':[],'can_generate':False}
        if preview['vault_height']<=rows[key].get('current_height',0):return
        rows[key]['proposed_address']=preview
        return
    path=data_directory(config)/'wallet-setups.json'
    if not path.exists():return
    setups=json.loads(path.read_text()).get('sessions',{})
    for ident in work.get('operations',[]):
        setup=setups.get(ident,{})
        if setup.get('state') not in ('policy','ready') or not setup.get('policy_hash') or not setup.get('descriptors') or not setup.get('proposal',{}).get('height'):continue
        # The accepted public contributions determine the address, not the name
        # or an unfinished form. Reassemble the policy before showing a sample.
        try:
            from wallet_setup_policy import policy
            proposal=setup['proposal'];contributions=[setup['contributions'][r['id']]['message'] for r in sorted(proposal['cosigners'],key=lambda r:r['id'])]
            descriptors=policy(proposal,contributions,fresh=False)
            if descriptors!=setup['descriptors']:continue
            wallet=clean_wallet({'wallet_name':proposal['name'],'descriptors':[{'desc':d,'internal':i==1,'active':True,'range':[0,999]} for i,d in enumerate(descriptors)]})
            key=next((k for k,w in catalog.items() if {NodeWalletLoader.descriptor_key(r['desc']) for r in wallet['raw']['descriptors']}<={NodeWalletLoader.descriptor_key(r['desc']) for r in w['raw']['descriptors']}),None)
            if key is None:
                key='setup-preview-'+ident
                rows[key]={'id':key,'kind':'descriptor','source':wallet['id'],'name':proposal['name'],'builder_preview':True,'has_vault':True,'multisig':len(proposal['cosigners'])>1,'status':'available','addresses':[],'address_history':[],'can_generate':False}
            elif key not in rows:
                rows[key]={'id':key,'kind':'descriptor','source':catalog[key]['id'],'has_vault':True,'status':'available','addresses':[],'address_history':[],'can_generate':False}
            rows[key]['proposed_address']={'address':Descriptor.from_string(descriptors[0]).derive(0).address(NETWORKS['main']),'vault_height':proposal['height'],'index':0,'observed_utc':setup.get('created_utc') or work['created_utc'],'txid':None,'proposed':True}
        except (ValueError,KeyError,TypeError):continue
