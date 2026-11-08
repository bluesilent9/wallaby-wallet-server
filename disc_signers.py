"""Focused, high-priority loaded-disc signer checks. Public metadata only."""
import copy,re,threading,time
from descriptor_store import clean_wallet

class DiscSigners:
    def __init__(self,hub):
        self.hub=hub;self.lock=threading.RLock();self.rows={};self.jobs=set();self.closed=False;self.slots=threading.BoundedSemaphore(4)
    def close(self):
        with self.lock:self.closed=True;self.rows.clear()
    def connections(self):
        ready={n['id']:n for n in self.hub.registry.presence()['nodes'] if n.get('connected') and n.get('rpc_ready') and 'partial_signing' in self.hub.caps.get(n['id'],set())}
        result={}
        for c in list(self.hub.registry.connections.values()):
            if c['node_id'] in ready and self.hub.registry.rpc._unique(c):result[c['node_id']]={**c,'hostname':ready[c['node_id']]['hostname']}
        return result
    def ensure(self,job,*,force=False,private_accounts=False,priority=0):
        connections=self.connections();now=time.monotonic()
        with self.lock:
            if self.closed:return self.snapshot()
            first=job not in self.jobs;self.jobs.add(job)
            for node,c in connections.items():
                prior=self.rows.get(node,{})
                same=prior.get('token')==c['token']
                if same and prior.get('active'):
                    prior['priority']=min(priority,prior.get('priority',0));continue
                if same and not force and not first and (not private_accounts or prior.get('private_accounts')) and now<prior.get('retry_at',0):continue
                self.rows[node]={**({k:copy.deepcopy(prior[k]) for k in ('private_wallets','loaded_private','verified_at') if k in prior} if same else {}),'state':'checking','priority':priority,'hostname':c['hostname'],'token':c['token'],'active':True,'private_accounts':private_accounts or prior.get('private_accounts',False),'wallets':prior.get('wallets',[]) if same else [],'retry_at':now+2,'log_signature':prior.get('log_signature'),'logged_at':prior.get('logged_at',0)}
                threading.Thread(target=self.scan,args=(node,c['token']),name='disc-signers-'+node[:8],daemon=True).start()
            for node,row in self.rows.items():
                if node not in connections:row.update(state='offline',active=False)
        return self.snapshot()
    def current(self,node,token):
        return not self.closed and any(c['node_id']==node and c['token']==token for c in list(self.hub.registry.connections.values()))
    def call(self,node,token,method,params=None,wallet=None):
        if not self.current(node,token):raise ValueError('Agent disconnected during signer check.')
        if self.hub.transfers.is_busy(node):raise ValueError('Agent is busy synchronising wallets.')
        reply=self.hub.registry.rpc.call(node,method,params or [],wallet,timeout_seconds=20,consume=True,priority=self.rows.get(node,{}).get('priority',0))
        if reply.get('state')!='succeeded':raise ValueError('Agent is busy or could not finish the public signer check.')
        return reply['result']
    def scan(self,node,token):
        state='ready';wallets=[];private_wallets=[];loaded_private={};message='Loaded disc signers checked.'
        try:
            with self.slots:
                names=self.call(node,token,'listwallets')
                if not isinstance(names,list) or len(names)>256 or any(not isinstance(n,str) or len(n)>256 for n in names) or len(names)!=len(set(names)):raise ValueError('Invalid loaded-wallet list.')
                for name in names:
                    info=self.call(node,token,'getwalletinfo',wallet=name)
                    if not isinstance(info,dict):raise ValueError('Invalid wallet information.')
                    if info.get('private_keys_enabled') is True and not info.get('scanning'):
                        loaded_private[name]={'walletname':info.get('walletname'),'storage':'disc' if info.get('wallaby_storage')=='disc' else 'node'}
                    disc=info.get('wallaby_storage')=='disc'
                    if not disc and not self.rows.get(node,{}).get('private_accounts'):continue
                    if disc and not re.fullmatch('[0-9a-f]{64}',str(info.get('wallaby_archive_id'))):raise ValueError('Invalid public archive identity.')
                    if info.get('scanning'):raise ValueError('Disc signer is still being loaded or scanned.')
                    if info.get('private_keys_enabled') is not True:continue
                    raw=self.call(node,token,'listdescriptors',[False],name)
                    if raw.get('wallet_name')!=info.get('walletname'):raise ValueError('Disc wallet identity changed during the check.')
                    after=self.call(node,token,'getwalletinfo',wallet=name)
                    if any(after.get(k)!=info.get(k) for k in ('walletname','wallaby_storage','wallaby_archive_id','private_keys_enabled','scanning')):raise ValueError('Disc changed while checking its public policy.')
                    checked=clean_wallet(raw)
                    account={'name':name,'id':checked['id'],'raw':checked['raw'],'private_keys_enabled':True,'scanning':False}
                    if disc:account['policy_hash']=info.get('wallaby_policy_hash')
                    if disc:wallets.append({**account,'signing_only':True,'archive_id':info['wallaby_archive_id']})
                    else:private_wallets.append(account)
        except (ValueError,OSError,KeyError,TypeError):
            state='busy';message='Checking signers… Agent busy or not ready; retrying automatically.'
        except Exception:
            state='error';message='Public disc signer check could not finish; retrying automatically.'
        with self.lock:
            if not self.current(node,token) or self.rows.get(node,{}).get('token')!=token:return
            row=self.rows[node];row.update(state=state,active=False,message=message,retry_at=time.monotonic()+(15 if state=='ready' else 2))
            if state=='ready':row.update(wallets=wallets,private_wallets=private_wallets,loaded_private=loaded_private,verified_at=time.monotonic())
            signature=(state,tuple(sorted(w['name'] for w in wallets)) if state=='ready' else ())
            log=signature!=row.get('log_signature') or time.monotonic()-row.get('logged_at',0)>60
            if log:row.update(log_signature=signature,logged_at=time.monotonic())
        if log:self.hub.registry.diagnostic_log.append('Disc signer check',row['hostname']+': '+('verified '+str(len(private_wallets))+' node private wallet(s), '+str(len(wallets))+' loaded private disc signer(s).' if state=='ready' else 'Agent busy or check incomplete; automatic retry pending.'))
    def is_verified(self,node):
        with self.lock:
            row=self.rows.get(node,{})
            return bool(row.get('private_accounts') and row.get('state')=='ready' and self.current(node,row.get('token')) and time.monotonic()-row.get('verified_at',0)<=15)
    def private_inventory(self,node,*,display=False):
        """Refresh needs every key loaded now, not historical private-key flags."""
        with self.lock:
            row=self.rows.get(node,{})
            if not row.get('private_accounts') or not self.current(node,row.get('token')):return []
            if display:
                # Retain the last known location until a completed check replaces it.
                # This is display-only; is_verified still expires after 15s.
                if row.get('state') not in ('ready','checking','busy','error'):return []
            elif not self.is_verified(node):return []
            loaded=row.get('loaded_private',{})
            merged={'wallets':row.get('private_wallets',[])+row.get('wallets',[])}
            return [copy.deepcopy(w) for w in merged.get('wallets',[]) if w.get('private_keys_enabled') is True and not w.get('scanning') and w.get('name') in loaded and w.get('raw',{}).get('wallet_name')==loaded[w['name']]['walletname'] and ('disc' if w.get('archive_id') else 'node')==loaded[w['name']]['storage']]
    def snapshot(self):
        connections=self.connections()
        with self.lock:
            nodes=[{'node_id':node,'hostname':c['hostname'],'state':self.rows.get(node,{}).get('state','checking'),'message':self.rows.get(node,{}).get('message','Checking signers…')} for node,c in connections.items()]
        return {'active':any(n['state']!='ready' for n in nodes),'nodes':nodes}
    def inventory(self,node,base,*,display=False):
        with self.lock:
            row=self.rows.get(node)
            if not row:return base
            # A targeted empty scan is authoritative for loaded discs. Preserve
            # regular signer metadata without making a partial full inventory.
            regular=[w for w in base.get('wallets',[]) if not w.get('archive_id') and not (w.get('signing_only') and w.get('private_keys_enabled'))]
            live=self.current(node,row['token']);discs=copy.deepcopy(row.get('wallets',[])) if live and (row['state']=='ready' or display and row['state'] in ('checking','busy','error')) else []
            return {**base,'wallets':regular+discs,'loaded_complete':base.get('loaded_complete',False) or bool(discs)}

def inventory(hub,node,*,display=False):
    base=hub.inventories.get(node,{})
    if display and not (base.get('complete') or base.get('loaded_complete')):
        saved=getattr(hub,'inventory_display',{}).get(node,{})
        if any(c['node_id']==node and c['token']==saved.get('token') for c in hub.registry.connections.values()):
            base={**saved.get('inventory',{}),'display_only':True}
    checks=getattr(hub,'disc_signers',None)
    return checks.inventory(node,base,display=display) if checks else base


def verify_selection(hub,node,name,archive_id=None):
    """A retained dropdown choice never substitutes for a live selected-account check."""
    from node_wallets import NodeWalletLoader
    checks=hub.disc_signers
    with checks.lock:
        connection=checks.connections().get(node,{})
        token=connection.get('token')
        candidates=inventory(hub,node,display=True).get('wallets',[])
        expected=next((w for w in candidates if w['name']==name and w.get('archive_id')==archive_id),None)
        if not token or not expected or not checks.current(node,token):raise ValueError('The selected signer is no longer connected. Load it again before requesting a signature.')
        expected_policies={NodeWalletLoader.descriptor_key(r['desc']) for r in expected['raw']['descriptors']}
    def call(method,params=None,*,wallet=name):
        if not checks.current(node,token):raise ValueError('The signing Agent reconnected. Wait for the disc check before retrying.')
        response=hub.registry.rpc.call(node,method,params or [],wallet,timeout_seconds=20,consume=True,priority=0)
        if response.get('state')!='succeeded':raise ValueError('The Agent is busy or could not confirm the selected signer. No signing request was sent; retry after its local operation finishes.')
        return response['result']
    def validate(info):
        if not isinstance(info,dict) or info.get('walletname')!=expected['raw']['wallet_name'] or (info.get('wallaby_storage')=='disc')!=bool(archive_id) or (archive_id is not None and info.get('wallaby_archive_id')!=archive_id) or info.get('private_keys_enabled') is not True or info.get('scanning'):
            raise ValueError('The selected signer was unloaded, replaced, or is still scanning. No signing request was sent.')
    health=next((n.get('blockchain',{}).get('state') for n in hub.registry.presence()['nodes'] if n['id']==node),None)
    if health!='ready':
        chain=__import__('node_health').classify(call('getblockchaininfo',wallet=None))
        if chain['state']!='ready':raise ValueError('The signing node is still synchronising. No signing request was sent.')
    validate(call('getwalletinfo'))
    raw=call('listdescriptors',[False]);checked=clean_wallet(raw)
    if raw.get('wallet_name')!=expected['raw']['wallet_name'] or {NodeWalletLoader.descriptor_key(r['desc']) for r in checked['raw']['descriptors']}!=expected_policies:raise ValueError('The selected signer policy changed. Refresh signing accounts before retrying.')
    validate(call('getwalletinfo'))
    if not checks.current(node,token):raise ValueError('The signing Agent disconnected during verification. No signing request was sent.')
