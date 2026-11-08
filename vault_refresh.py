"""Linked public-policy renewal; no keys or PSBT signatures enter Wallet Builder."""
import copy,time
from storage import storage_lock
from builder_workspace import BuilderWorkspace,LOCK
from builder_destinations import Destinations,base_wallet,public_rows,refresh_wallet
from vendor.embit.descriptor import Descriptor
from vendor.embit.networks import NETWORKS
from multisig_psbt import witness_policy
from policy_accounts import keys
from preferences import FamilyStore

def start(hub,user,source,target):
    work=BuilderWorkspace(hub.config)
    with LOCK:
        tx=work.owned(user,'transaction')
        if tx['operations']:raise ValueError('A PSBT has already been prepared. Cancel this build before changing its vault policy.')
        if work.read()['workspaces'].get('wallet'):raise ValueError('Wallet Builder is already in use. Finish or cancel it first.')
        dest=Destinations(hub.config).get(target)
        if dest['base']!=source or dest['height'] is not None:raise ValueError('Choose an ordinary new receiving copy of the same wallet.')
        draft=tx['draft']
        if not any(e['from']==source and e['to']==target for e in draft.get('edges',[])):raise ValueError('Save a payment from this wallet to its own new address first.')
        wallet=refresh_wallet(hub.config,base_wallet(hub.config,source));rows=public_rows(wallet,pair=True);desc=Descriptor.from_string(rows[0]['desc']);total=len(desc.keys)
        policy=witness_policy(desc.derive(0).witness_script().data) if desc.witness_script() else {'threshold':1,'height':None}
        roles=[]
        for key in desc.keys:
            canonical=str(key).split(']')[-1].replace("'",'h')
            label='Signing key '+str(len(roles)+1)
            for setup in hub.wallet_builder.read()['sessions'].values():
                for rid,contribution in setup.get('contributions',{}).items():
                    message=contribution.get('message',{})
                    if canonical==str(message.get('receive_key','')).split(']')[-1].replace("'",'h'):
                        role=next((r for r in setup['proposal']['cosigners'] if r['id']==rid),None)
                        if role:label=role['name']
            roles.append({'name':label,'receive_key':canonical,'node_id':'','storage':'','node_locked':True})
        row=work.start(user,'wallet');state=work.read();row=state['workspaces']['wallet']
        row['renewal']={'transaction_workspace':tx['id'],'source':source,'target':target,'previous_height':policy['height'],'roles':copy.deepcopy(roles)}
        # Logical display identity is separate from each Agent's Core wallet filename.
        family=FamilyStore(hub.config).snapshot()
        owner=next((r for r in family['ownership'] if r.get('kind')=='descriptor' and r.get('source')==wallet['id'] and r.get('confirmed')), {})
        name=owner.get('dashboard_name') or (owner.get('name') if owner.get('display_name_set') else None) or wallet.get('setup_name') or owner.get('name') or wallet['name']
        row['draft']={'name':name,'type':'3' if total>1 else '2','threshold':str(policy['threshold']),'count':str(total),'roles':[{k:v for k,v in r.items() if k!='node_locked'} for r in roles]};row['revision']+=1;work.write(state)
    hub.disc_signers.ensure('renewal-'+row['id'],force=True,private_accounts=True)
    return work.snapshot(user,'wallet',hub.registry)

def proposed(config,workspace):
    """Public-only preview bound to the transaction's already reserved index."""
    renewal=workspace.get('renewal');vault=workspace.get('draft',{}).get('vault') or {};result=vault.get('result') or {};height=result.get('height')
    if not renewal or type(height) is not int or not (renewal.get('previous_height') or 0)<height<500000000:return None
    if vault.get('heightDraft') is not None and str(vault['heightDraft']).replace(',','').strip()!=str(height):return None
    target=Destinations(config).get(renewal['target'])
    if target['base']!=renewal['source'] or target['height'] is not None:raise ValueError('The linked receiving destination changed.')
    wallet=refresh_wallet(config,base_wallet(config,renewal['source']));rows=public_rows(wallet,height);index=target['index'];bounds=rows[0].get('range',[0,0])
    if not bounds[0]<=index<=min(bounds[1],999):raise ValueError('The proposed vault receiving index is outside the supported range.')
    return {'address':Descriptor.from_string(rows[0]['desc']).derive(index).address(NETWORKS['main']),'descriptor':rows[0]['desc'],'index':index,'vault_height':height,'observed_utc':workspace.get('updated_utc') or workspace['created_utc'],'txid':None,'proposed':True,'comparison_samples':__import__('refresh_comparison').samples(rows,index)}

def signers(hub,workspace,*,discover=False):
    """Resolve every immutable policy key to a currently loaded private account.

    A multisig monitor containing all public keys is never evidence that an
    Agent owns those private keys. Only independent single-key accounts count.
    """
    renewal=workspace['renewal'];checks=hub.disc_signers
    if discover:checks.ensure('renewal-'+workspace['id'],private_accounts=True)
    wanted=[r.get('receive_key') for r in renewal['roles']]
    if not all(wanted):
        # Public policy identity for an unfinished refresh saved before Build72.
        wallet=base_wallet(hub.config,renewal['source'])
        wanted=[str(k).split(']')[-1].replace("'",'h') for k in Descriptor.from_string(public_rows(wallet,pair=True)[0]['desc']).keys]
    connected=checks.connections();accounts=[];setups=list(hub.wallet_builder.read()['sessions'].values())
    for node,c in connected.items():
        for account in checks.private_inventory(node,display=True):
            own=keys({'descriptors':[r for r in account['raw'].get('descriptors',[]) if r['desc'].startswith('wpkh(')]})
            if not own or len({key.rsplit('/',2)[0] for key in own})!=1:own=set()
            own|=__import__('combined_signers').private_roles(hub,node,account,setups)
            if own:accounts.append((node,c,account,own,checks.is_verified(node)))
    roles=[]
    for i,fixed in enumerate(renewal['roles']):
        matches=[(node,c,a,fresh) for node,c,a,own,fresh in accounts if i<len(wanted) and wanted[i] in own]
        matches.sort(key=lambda row:(not row[3],row[0]!=fixed.get('node_id'),bool(row[2].get('archive_id')),row[0],row[2]['name']))
        chosen=matches[0] if matches else None
        roles.append({'name':fixed['name'],'detected':bool(chosen),'verified':bool(chosen and chosen[3]),'node_id':chosen[0] if chosen else '', 'hostname':chosen[1]['hostname'] if chosen else 'Signer not detected','wallet_name':chosen[2]['name'] if chosen else '', 'storage':('disc' if chosen[2].get('archive_id') else 'node') if chosen else ''})
    return {'roles':roles,'complete':bool(roles) and len(set(wanted))==len(roles) and all(r['verified'] for r in roles),'checking':checks.snapshot()['active']}

def cancel(hub,user):
    work=BuilderWorkspace(hub.config)
    with LOCK:
        w=work.owned(user,'wallet')
        if not w.get('renewal') or w['operations']:raise ValueError('This is not an editable linked vault renewal.')
        if w['renewal'].get('approval'):
            result=work.cancel(hub,user,'wallet',confirmed=True)
            return {'return_to':'builder'} if not result['workspace'] else {'waiting':True}
        store=Destinations(hub.config);state=store.read()
        for destination in state['destinations'].values():
            if destination.get('renewal_workspace_id')==w['id']:destination.update(policy_cancelled=True,policy_requests_started=False)
        if state['destinations']:store.write(state)
        work.finish(user,'wallet')
    return {'return_to':'builder'}

def finish(hub,user,height):
    work=BuilderWorkspace(hub.config);started=time.monotonic()
    hub.registry.diagnostic_log.append('Vault refresh','Policy approval handoff requested.')
    with LOCK:
        w=work.owned(user,'wallet');r=w.get('renewal');tx=work.owned(user,'transaction')
        if not r or tx['id']!=r['transaction_workspace'] or tx['operations']:raise ValueError('The linked transaction changed. No policy was sent.')
        if r.get('approval'):
            if height!=r['approval']['height']:raise ValueError('The submitted vault policy is locked while Agents review it.')
            return progress(hub,user)
        if type(height) is not int or height<=(r['previous_height'] or 0):raise ValueError('The new vault height must be strictly later than the previous vault height.')
        detected=signers(hub,w)
        if not detected['complete'] and all(role['detected'] for role in detected['roles']):raise ValueError('Signer verification is updating. Wait for the current check to finish before returning to Transaction Builder.')
        if not detected['complete']:raise ValueError('Every existing signer must be detected before refreshing this vault. Connect each signing Agent and load every required archive disc. If a signer is lost, create a new wallet and transfer funds using the remaining signing quorum.')
        preview=proposed(hub.config,w)
        if preview and preview['vault_height']!=height:raise ValueError('The vault height differs from the Address Book preview. Save the updated height before continuing.')
        hub.registry.diagnostic_log.append('Vault refresh','All existing signers verified; checking the reserved receiving address. workspace='+w['id'][:12])
        d=Destinations(hub.config).create(hub.registry,user,r['source'],height,**({'reserved_index':preview['index']} if preview else {}))
        if preview and d['address']!=preview['address']:raise ValueError('The proposed vault address changed. No policy was sent.')
        participants={}
        public_before={}
        for role in detected['roles']:
            participants.setdefault(role['node_id'],{'hostname':role['hostname'],'wallets':[]})['wallets'].append(role['wallet_name'])
        previous={__import__('node_wallets').NodeWalletLoader.descriptor_key(row['desc']) for row in public_rows(refresh_wallet(hub.config,base_wallet(hub.config,r['source'])),pair=True)}
        for node in hub.registry.snapshot()['nodes']:
            inv=hub.inventories.get(node['id'],{})
            if not node.get('rpc_ready') or node.get('blockchain',{}).get('state')!='ready' or not inv.get('complete'):continue
            if any(previous<={__import__('node_wallets').NodeWalletLoader.descriptor_key(row['desc']) for row in wallet['raw']['descriptors']} for wallet in inv.get('wallets',[])):participants.setdefault(node['id'],{'hostname':node['hostname'],'wallets':[]})
        for node,connection in hub.disc_signers.connections().items():
            if not hub.disc_signers.is_verified(node):continue
            for account in hub.disc_signers.private_inventory(node):
                if previous<={__import__('node_wallets').NodeWalletLoader.descriptor_key(row['desc']) for row in account['raw']['descriptors']}:
                    wallets=participants.setdefault(node,{'hostname':connection['hostname'],'wallets':[]})['wallets']
                    if account['name'] not in wallets:wallets.append(account['name'])
        for node,participant in participants.items():
            accounts=hub.disc_signers.private_inventory(node,display=True)
            public_before[node]={a['name']:[row['desc'] for row in a['raw']['descriptors']] for a in accounts if a['name'] in participant['wallets']}
        store=Destinations(hub.config);saved=store.read();saved['destinations'][d['id']].update(workspace_id=tx['id'],archive_roles=[],approval_nodes=list(participants),approval_wallets={node:row['wallets'] for node,row in participants.items()},approval_public_before=public_before,renewal_workspace_id=w['id']);store.write(saved)
        # Save the exact reservation and participants before delivery. Reloading
        # never allocates another address or silently drops an offline signer.
        state=work.read();state['workspaces']['wallet']['renewal']['approval']={'destination':d['id'],'height':height,'participants':participants};work.write(state)
        try:__import__('wallet_policy_updates').schedule(hub,d['id'])
        except ValueError as exc:
            hub.registry.diagnostic_log.append('Vault refresh','Policy delivery waiting for verified inventory: '+str(exc))
        hub.registry.diagnostic_log.append('Vault refresh','Approval screen ready · workspace='+w['id'][:12]+' · agents='+str(len(participants))+' · elapsed_ms='+str(round((time.monotonic()-started)*1000)))
    return progress(hub,user)

def declined(hub,workspace_id):
    # Persist withdrawal independently of the interactive workspace so an
    # offline Agent receives cancellation on reconnect, without blocking the
    # user's original transaction or deleting any existing signer wallet.
    work=BuilderWorkspace(hub.config)
    with LOCK:
        w=work.read()['workspaces'].get('wallet')
        if not w or w['id']!=workspace_id:return
        work.cancel(hub,w['owner_id'],'wallet',confirmed=True)
        hub.registry.diagnostic_log.append('Vault refresh','Agent declined the public policy; refresh cancelled and original transaction retained. workspace='+workspace_id[:12])
        state=work.read();current=state['workspaces'].get('wallet')
        if current and current['id']==workspace_id:state['workspaces'].pop('wallet');work.write(state)


def progress(hub,user):
    work=BuilderWorkspace(hub.config);w=work.owned(user,'wallet');phase=w.get('renewal',{}).get('approval')
    if not phase:raise ValueError('No vault policy approval is pending.')
    d=Destinations(hub.config).get(phase['destination'])
    if d['base']!=w['renewal']['source'] or d['height']!=phase['height'] or set(d.get('approval_nodes',[]))!=set(phase['participants']):raise ValueError('The saved policy approval does not match this linked vault refresh.')
    requests={r['node_id']:r for r in hub.read()['requests'].values() if r.get('destination_id')==d['id']}
    connected={n['id'] for n in hub.registry.presence()['nodes'] if n['connected']}
    rows=[]
    for node,participant in phase['participants'].items():
        r=requests.get(node,{})
        state=r.get('state');colour='red'
        if state=='complete':colour='green';label='Approved'
        elif state in ('denied','error','recovery_required'):label={'denied':'Declined on Agent','error':r.get('message') or 'Agent reported an error','recovery_required':'History recovery required on Agent'}[state]
        elif r.get('verification_error'):label='Policy verification incomplete: '+r['verification_error']
        elif node not in connected:label='Agent disconnected'
        elif __import__('wallet_policy_updates').BATCH_CAPABILITY not in hub.caps.get(node,set()):label='Agent update required for grouped policy approval'
        elif 'receiving_address' in r.get('proposal',{}) and not __import__('refresh_comparison').supported(hub,node):label='Agent Build 60 or later required for exact address comparison'
        elif r.get('received_utc'):colour='amber';label='Received — awaiting local approval'
        else:label='Sending request — waiting for receipt' if r else 'Waiting for verified wallet inventory'
        rows.append({'node_id':node,'hostname':participant['hostname'],'colour':colour,'status':label})
    ready=__import__('wallet_policy_updates').destination_ready(hub,d)
    return {'waiting':not ready,'complete':ready,'destination':d['id'],'targets':rows}

def complete(hub,user):
    work=BuilderWorkspace(hub.config)
    with LOCK:
        w=work.owned(user,'wallet');r=w.get('renewal');tx=work.owned(user,'transaction')
        if not r or not r.get('approval') or tx['id']!=r['transaction_workspace'] or tx['operations']:raise ValueError('The linked transaction changed.')
        if not progress(hub,user)['complete']:raise ValueError('Wait for every Agent to approve the new policy and confirm its installation.')
        ident=r['approval']['destination'];state=work.read();tx=state['workspaces']['transaction'];swap(tx['draft'],r['target'],ident);tx['revision']+=1
        state['workspaces'].pop('wallet');work.write(state)
    return {'return_to':'builder','destination':ident}

def swap(draft,old,new):
    for node in draft['nodes']:
        if node['id']==old:node['id']=new
    for e in draft['edges']:
        for field in ('from','to'):
            if e[field]==old:e[field]=new

def remove(hub,user,target):
    work=BuilderWorkspace(hub.config)
    with LOCK:
        tx=work.owned(user,'transaction')
        if tx['operations']:raise ValueError('A prepared transaction cannot change its destination.')
        old=Destinations(hub.config).get(target)
        if not old['height']:raise ValueError('This destination is not vaulted.')
        fresh=Destinations(hub.config).create(hub.registry,user,old['base'])
        state=work.read();tx=state['workspaces']['transaction'];swap(tx['draft'],target,fresh['id']);tx['revision']+=1;work.write(state)
        # Undelivered/delivered public additions may already be approved. Never
        # remove policies from Core. Retain their audit evidence, stop reoffering.
        with hub.edit() as s:
            for row in s['requests'].values():
                if row.get('destination_id')==target and row['state']=='pending':row.update(state='cancelled')
        store=Destinations(hub.config);s=store.read();s['destinations'][target]['policy_requests_started']=False;store.write(s)
    return {'return_to':'builder'}
