"""Locally approved public-policy additions; never replace keys or prior scripts."""
import copy,time
from storage import storage_lock
from agent_hub import digest,equivalent
from builder_destinations import Destinations
from policy_accounts import keys,signing_account
from node_wallets import NodeWalletLoader
CAPABILITY='wallet_policy_refresh_v1'
BATCH_CAPABILITY='wallet_policy_refresh_batch_v1'

def verified(hub,node,envelope):
    from setup_signatures import verify
    live=hub.permissions.current(node)
    identity=hub.wallet_builder.read()['identities'].get(node)
    key=(live or {}).get('identity') or (identity or {}).get('public_key')
    if not key:raise ValueError('Wait for this Agent’s signed identity before accepting public archive or policy evidence.')
    return verify(hub.config,envelope,key)

def schedule(hub,ident):
    store=Destinations(hub.config);d=store.get(ident)
    if not d['height']:raise ValueError('This destination has no vault policy.')
    wanted={'wallet_name':d['source_wallet']['wallet_name'],'descriptors':d['descriptors']}
    targets=[]
    for node in hub.registry.snapshot()['nodes']:
        if d.get('approval_nodes') and node['id'] not in d['approval_nodes']:continue
        if not node.get('rpc_ready') or node.get('blockchain',{}).get('state')!='ready':continue
        inv=hub.inventories.get(node['id'],{})
        accounts=list(inv.get('wallets',[])) if inv.get('complete') else []
        if d.get('approval_nodes'):
            accounts+=hub.disc_signers.private_inventory(node['id'])
        if not accounts:continue
        previous=__import__('builder_destinations').public_rows({'raw':d['source_wallet']},pair=True)
        required={NodeWalletLoader.descriptor_key(r['desc']) for r in previous}
        matches=[w for w in accounts if required<={NodeWalletLoader.descriptor_key(r['desc']) for r in w['raw']['descriptors']}]
        if not matches:continue
        matches.sort(key=lambda w:(w.get('signing_only',False),not equivalent(w['raw'],d['source_wallet']),w['name']))
        route=matches[0]
        targets.append((node,route))
    if not targets:raise ValueError('No connected Agent has the source wallet’s verified public signing accounts.')
    existing=hub.read()['requests'];targets=[(node,route) for node,route in targets if digest({'destination':ident,'node':node['id']}) not in existing]
    if not targets and d.get('policy_requests_started'):return [r for r in existing.values() if r.get('destination_id')==ident]
    with hub.edit() as state:
        for node,route in targets:
            key=digest({'destination':ident,'node':node['id']})
            if key in state['requests']:continue
            previous=__import__('builder_destinations').public_rows({'raw':d['source_wallet']},pair=True)
            # Route only to a wallet holding the old policy, not merely one of
            # its signing accounts. A signing account is not a policy monitor.
            if not {NodeWalletLoader.descriptor_key(r['desc']) for r in previous}<={NodeWalletLoader.descriptor_key(r['desc']) for r in route['raw']['descriptors']}:continue
            proposal={'kind':'wallet_policy_refresh','version':1,'request_id':key,'chain':'main','wallet':route['name'],'previous_descriptors':[r['desc'] for r in previous],'receive_descriptor':d['descriptors'][0]['desc'],'change_descriptor':d['descriptors'][1]['desc'],'timestamp':d['policy_timestamp'],'expires_at':int(time.time())+86390,'receiving_address':__import__('refresh_comparison').receiving_address(d)}
            state['requests'][key]={'kind':'wallet_policy_refresh','node_id':node['id'],'destination_id':ident,'workspace_id':d.get('workspace_id'),'state':'pending','proposal':proposal,'created_utc':hub.utc(),**({'batch_required':True,'required_wallets':sorted(set(d['approval_wallets'].get(node['id'],[]))|{route['name']}),'previous_wallet_descriptors':{**copy.deepcopy(d['approval_public_before'].get(node['id'],{})),route['name']:[r['desc'] for r in route['raw']['descriptors']]},'renewal_workspace_id':d['renewal_workspace_id']} if d.get('approval_nodes') else {})}

    if not d.get('policy_requests_started'):
        with storage_lock(hub.config):
            state=store.read();state['destinations'][ident]['policy_requests_started']=True;store.write(state)
    return [r for r in hub.read()['requests'].values() if r.get('destination_id')==ident]

def proposals(hub,node):
    # A connected node may appear after the destination was first prepared.
    for ident,d in Destinations(hub.config).read()['destinations'].items():
        if d.get('policy_requests_started'):
            try:schedule(hub,ident)
            except ValueError:pass
            if d.get('archive_roles') and not d.get('archive_submitted') and destination_ready(hub,d):
                from archive_queue import ArchiveQueue
                queue=ArchiveQueue(hub);options=queue.options(d['base']);selected=[r['id'] for r in options if r['compatible'] and any(role['node_id']==r['node_id'] and role['receive_key'] in keys(r['public_wallet']) for role in d['archive_roles'])]
                if selected:
                    queue.create(d['user_id'],d['base'],selected)
                    with storage_lock(hub.config):
                        store=Destinations(hub.config);saved=store.read();saved['destinations'][ident]['archive_submitted']=True;store.write(saved)
    with hub.edit() as s:
        result=[]
        for key,r in s['requests'].items():
            if r['kind']=='wallet_policy_refresh' and r['node_id']==node and r['state']=='pending':
                if r.get('batch_required') and BATCH_CAPABILITY not in hub.caps.get(node,set()):continue
                if 'receiving_address' in r['proposal'] and not __import__('refresh_comparison').supported(hub,node):continue
                if r['proposal']['expires_at']<=time.time():r.update(state='error',message='Policy request expired. Review the existing local outcome before requesting another refresh.');continue
                r['delivered']=True;result.append(r['proposal'])
        return result

def accept_receipt(hub,node,envelope):
    p=verified(hub,node,envelope)
    if not isinstance(p,dict) or set(p)!={'version','request_id','request_hash','status'} or type(p['version']) is not int or p['version']!=1 or p['status']!='received':raise ValueError('Invalid policy receipt.')
    with hub.edit() as state:
        row=state['requests'].get(p['request_id'])
        if not row or row.get('kind')!='wallet_policy_refresh' or row['node_id']!=node or not row.get('delivered') or p['request_hash']!=digest(row['proposal']):raise ValueError('Policy receipt does not match this Agent’s delivered request.')
        row.setdefault('received_utc',hub.utc());row.setdefault('receipt',copy.deepcopy(envelope))


def accept(hub,node,envelope):
    p=verified(hub,node,envelope)
    if not isinstance(p,dict) or type(p.get('version')) is not int or p.get('version')!=1 or p.get('status') not in ('approved','history_required','denied','error'):raise ValueError('Invalid public policy refresh result.')
    key=p.get('request_id');row=hub.read()['requests'].get(key)
    if not row or row.get('kind')!='wallet_policy_refresh' or row['node_id']!=node or p.get('request_hash')!=digest(row['proposal']):raise ValueError('Policy result does not match this Agent’s exact request.')
    proposal=row['proposal']
    if p['status'] in ('denied','error'):
        with hub.edit() as state:
            current=state['requests'][key]
            if current['state'] not in ('pending','cancelled') and current.get('result')!=envelope:raise ValueError('Contradictory public policy result.')
            current.update(state='cancelled' if current['state']=='cancelled' else p['status'],result=copy.deepcopy(envelope),message='Declined locally on Agent' if p['status']=='denied' else 'Agent reported a public-policy error. Reconcile locally before retrying.')
        if p['status']=='denied' and row.get('renewal_workspace_id'):
            __import__('vault_refresh').declined(hub,row['renewal_workspace_id'])
        return
    if any(p.get(k)!=proposal[k] for k in ('wallet','previous_descriptors','receive_descriptor','change_descriptor')):raise ValueError('Approved policy differs from the requested transition.')
    transition={k:proposal[k] for k in ('previous_descriptors','receive_descriptor','change_descriptor','timestamp')}
    if p.get('policy_hash')!=digest(transition):raise ValueError('Agent approved a different public policy transition.')
    if not isinstance(p.get('monitor_wallet'),str) or not p['monitor_wallet']:raise ValueError('The locally installed monitor is missing.')
    # Signed acknowledgement is not sufficient: independently ask Core whether
    # both exact new public descriptors were installed, preserving old history.
    try:
        raw=hub.rpc(node,'listdescriptors',[False],p['monitor_wallet'])
        expected={NodeWalletLoader.descriptor_key(proposal[k]) for k in ('receive_descriptor','change_descriptor')}
        if not expected<={NodeWalletLoader.descriptor_key(r['desc']) for r in raw['descriptors']}:raise ValueError('Core did not confirm both refreshed public policies.')
        persistent=False
        if row.get('batch_required'):
            updated=p.get('updated_wallets')
            if not isinstance(updated,list) or not 1<=len(updated)<=64 or not all(isinstance(name,str) and 0<len(name)<=1024 for name in updated) or not set(row['required_wallets'])<=set(updated):raise ValueError('Agent did not confirm every local signer and policy wallet was updated.')
            for name in set(row['required_wallets'])|set(updated)|{p['monitor_wallet']}:
                descriptors=hub.rpc(node,'listdescriptors',[False],name)
                actual={NodeWalletLoader.descriptor_key(r['desc']) for r in descriptors['descriptors']}
                prior={NodeWalletLoader.descriptor_key(desc) for desc in row['previous_wallet_descriptors'].get(name,proposal['previous_descriptors'])}
                if not (expected|prior)<=actual:raise ValueError('Core did not confirm the refreshed policy and retained history for every local signer.')
            info=hub.rpc(node,'getwalletinfo',[],p['monitor_wallet'])
            persistent=info.get('wallaby_storage')!='disc' and not info.get('wallaby_archive_id')
    except (ValueError,OSError,KeyError,TypeError) as error:
        with hub.edit() as state:state['requests'][key]['verification_error']=str(error)
        raise
    with hub.edit() as s:
        r=s['requests'][key]
        if r['state'] not in ('pending','cancelled') or r.get('result'):
            if r.get('result')!=envelope:raise ValueError('Contradictory public policy result.')
            return
        r.pop('verification_error',None)
        r.update(state='cancelled' if r['state']=='cancelled' else 'complete' if p['status']=='approved' else 'recovery_required',result=copy.deepcopy(envelope),verified_utc=hub.utc(),persistent_monitor=persistent)
    hub.inventory_times[node]=0

def destination_ready(hub,d):
    rows=[r for r in hub.read()['requests'].values() if r.get('destination_id')==d['id']]
    if d.get('policy_cancelled'):return False
    if d.get('approval_nodes'):
        by_node={r['node_id']:r for r in rows}
        return all(node in by_node and by_node[node]['state']=='complete' for node in d['approval_nodes']) and any(r.get('persistent_monitor') for r in rows)
    connected={n['id'] for n in hub.registry.snapshot()['nodes'] if n.get('rpc_ready') and n.get('blockchain',{}).get('state')=='ready'}
    current=[r for r in rows if r['node_id'] in connected]
    if not current or any(r['state']!='complete' for r in current):return False
    # Require one persistent Core monitor; a transient disc alias alone cannot
    # establish the durable watch policy needed to rediscover future funds.
    return any(any(not w.get('signing_only') and equivalent(w['raw'],{'descriptors':[{'desc':r['proposal'][k]} for k in ('receive_descriptor','change_descriptor')]}) for w in hub.inventories.get(r['node_id'],{}).get('wallets',[])) for r in current)

def destination_issues(hub,d):
    names={n['id']:n['hostname'] for n in hub.registry.snapshot()['nodes']}
    rows=[r for r in hub.read()['requests'].values() if r.get('destination_id')==d['id'] and r['state']!='complete']
    return '; '.join(names.get(r['node_id'],'Agent')+': '+('declined locally; reconcile on Authorise' if r['state']=='denied' else 'history recovery required' if r['state']=='recovery_required' else 'error; reconcile locally' if r['state']=='error' else 'awaiting local approval or reconciliation') for r in rows)

def accept_cancel(hub,node,envelope):
    """Agent alone confirms local policy retirement and physical disc cleanup."""
    from builder_workspace import BuilderWorkspace
    import re
    p=verified(hub,node,envelope);work=BuilderWorkspace(hub.config)
    if not isinstance(p,dict) or type(p.get('version')) is not int or p.get('version')!=1 or p.get('status') not in ('complete','retained_funded') or p.get('keys_retained') is not True or p.get('descriptors_retained') is not True:raise ValueError('Invalid policy cancellation result.')
    batch=work.read()['cancellations'].get(p.get('cancellation_id'),{});target=batch.get('targets',{}).get(node)
    if batch.get('kind')!='wallet' or not target or target['proposal']['operations'] or not target.get('sent_utc') or p.get('request_hash')!=target['request_hash']:raise ValueError('Policy cancellation result does not match this Agent’s delivered request.')
    originals={digest(r['proposal']):r['proposal'] for r in hub.read()['requests'].values() if r.get('kind')=='wallet_policy_refresh' and r['node_id']==node}
    expected=target['proposal']['request_hashes']
    if not expected or any(key not in originals for key in expected) or p.get('policy_request_hashes')!=sorted(expected):raise ValueError('Policy cancellation does not cover the exact requested transitions.')
    retired=sorted({digest([originals[key]['receive_descriptor'],originals[key]['change_descriptor']]) for key in expected})
    if p['status']=='retained_funded':retired=[]
    destroyed=p.get('destroyed_archives')
    if p['status']=='retained_funded' and destroyed:raise ValueError('A funded policy cannot have cancelled archive destruction confirmed.')
    if p.get('retired_policy_hashes')!=retired or not isinstance(destroyed,list) or len(destroyed)>256 or not all(isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) for v in destroyed):raise ValueError('Invalid retained-policy or disc-cleanup confirmation.')
    with storage_lock(hub.config):
        state=work.read();current=state['cancellations'][p['cancellation_id']]['targets'][node]
        if current.get('policy_cleanup') and current['policy_cleanup']!=envelope:raise ValueError('Contradictory policy cleanup evidence.')
        current.setdefault('policy_cleanup',copy.deepcopy(envelope));current.setdefault('policy_cleanup_utc',hub.utc());work.write(state)
    work.receipt(node,{'version':1,'cancellation_id':p['cancellation_id'],'request_hash':target['request_hash'],'status':'received'})
    if p['status']=='retained_funded':
        with storage_lock(hub.config):
            store=Destinations(hub.config);state=store.read()
            for row in hub.read()['requests'].values():
                if row.get('kind')=='wallet_policy_refresh' and digest(row['proposal']) in expected and row.get('destination_id') in state['destinations']:state['destinations'][row['destination_id']]['policy_retained_funded']=True
            store.write(state)
        from transaction_workflows import WorkflowStore
        with storage_lock(hub.config):
            store=WorkflowStore(hub.config);state=store._read();event=p['cancellation_id']+':'+node;seen=state.setdefault('policy_cleanup_notices',[])
            if event not in seen:
                state['notices'].setdefault(batch['owner_id'],[]).append({'id':digest({'policy_cleanup':event}),'kind':'policy_cleanup','target':'balances','severity':'red','dismissible':True,'read':False,'created_utc':hub.utc(),'text':target['hostname']+': the cancelled vault policy is funded. The Agent retained the policy, wallets, keys and archive discs. Check the wallet before continuing.'});seen.append(event);store._write(state)
