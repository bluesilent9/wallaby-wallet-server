"""Read-only receiving selection. No Core cursor writes, keys or authorisations."""
import copy,json,os
from functools import lru_cache
from contextlib import nullcontext
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from storage import data_directory,storage_lock
from descriptor_store import DescriptorStore
from preferences import resource_id
from builder_destinations import Destinations
from builder_identity import resolve
from node_wallets import NodeWalletLoader
from node_chain import RegistryRPC
from policy_accounts import has_vault
from policy_lineage import expanded
from address_book import valid_address,ordered_history
from vendor.embit.descriptor import Descriptor
from vendor.embit.networks import NETWORKS

def stamp():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def receive(row):
    if row.get('internal') is True:return False
    d=Descriptor.from_string(row['desc'])
    if row.get('internal') is False:return True
    # Inactive historical descriptors can omit Core's internal flag.
    return bool(d.keys) and all(k.allowed_derivation and k.allowed_derivation.indexes[0]==0 for k in d.keys)
def height(row):return NodeWalletLoader.vault_height(row['desc']) or 0

def external_address(info,policies):
    """Confirm external policy membership even for unlabelled watch imports."""
    parent=info.get('parent_desc')
    if parent and NodeWalletLoader.descriptor_key(parent) in policies:return True
    # Imported watch copies can report a concrete parent rather than the ranged
    # source descriptor, and classify unlabelled receipts as change. Derive the
    # exact script using public origin metadata; never infer from the label.
    try:
        concrete=Descriptor.from_string(info.get('desc',''))
        indexes={k.origin.derivation[-1] for k in concrete.keys if k.origin and k.origin.derivation}
        for row in policies.values():
            d=Descriptor.from_string(row['desc'])
            if d.is_wildcard:
                if len(indexes)!=1:continue
                index=next(iter(indexes));bounds=row.get('range',[0,0])
                if not bounds[0]<=index<=bounds[1]:continue
                d=d.derive(index)
            if d.script_pubkey()==concrete.script_pubkey() and d.address(NETWORKS['main'])==info.get('address'):return True
    except (ValueError,TypeError,KeyError,IndexError):pass
    return not parent and not info.get('ischange',False)

def cancelled_receiving(reservations):
    """Stop recommending cancelled receiving policies; keep history observable.

    A later explicit refresh may reactivate the same descriptor/height.
    """
    cancelled=set();current=set()
    for d in reservations:
        if not d.get('height'):continue
        if not d.get('policy_cancelled') and not d.get('policy_requests_started') and not d.get('policy_retained_funded'):continue
        key=NodeWalletLoader.descriptor_key(d['descriptors'][0]['desc'])
        (cancelled if d.get('policy_cancelled') and not d.get('policy_retained_funded') else current).add(key)
    return cancelled-current


@lru_cache(maxsize=1024)
def comparison_samples(rows):
    """The exact public index-zero samples shown by Agent disc loading."""
    result=[]
    for text,internal in rows:
        h=NodeWalletLoader.vault_height(text)
        if not h:continue
        row={'desc':text,'internal':internal};d=Descriptor.from_string(text)
        if d.num_branches!=1:continue
        external=receive(row)
        if not external and internal is not True and not (d.keys and all(k.allowed_derivation and k.allowed_derivation.indexes[0]==1 for k in d.keys)):continue
        sample=d.derive(0) if d.is_wildcard else d
        result.append({'height':h,'branch':'Receiving' if external else 'Change','index':0,'address':sample.address(NETWORKS['main'])})
    unique={(r['height'],r['branch'],r['address']):r for r in result}
    return tuple(sorted(unique.values(),key=lambda r:(-r['height'],r['branch']!='Receiving',r['address'])))

def vault_entry(entry,wallet,reservations=()):
    """Only destinations tied to this wallet's mandatory public vault policy."""
    raw=wallet.get('raw',{}).get('descriptors',[]);policies={NodeWalletLoader.descriptor_key(r['desc']):r for r in raw if height(r) and receive(r)}
    heights={height(r) for r in policies.values()}
    if not heights and not wallet.get('has_vault'):return entry
    entry=copy.deepcopy(entry);entry.update(has_vault=True,can_generate=False)
    evidence={r['address']:r['height'] for r in wallet.get('vault_evidence',[]) if r.get('height') in heights}
    samples=copy.deepcopy(list(comparison_samples(tuple(sorted((r['desc'],r.get('internal')) for r in raw)))))
    # Exact public derivation is sufficient even for an unfunded policy. It
    # avoids trusting an old cache's vault_height label on an arbitrary address.
    proof={r['address']:r['height'] for r in samples if r['branch']=='Receiving'}
    def prove(row):
        try:
            text=row.get('descriptor');index=row.get('index')
            if type(index) is not int or not 0<=index<2**31 or not text:return None
            policy=policies.get(NodeWalletLoader.descriptor_key(text))
            if not policy:return None
            h=height(policy);d=Descriptor.from_string(policy['desc']);derived=d.derive(index) if d.is_wildcard else d
            return h if derived.address(NETWORKS['main'])==row.get('address') else None
        except (ValueError,TypeError,KeyError):return None
    for dest in reservations:
        if dest.get('height') not in heights:continue
        h=prove({'descriptor':dest['descriptors'][0]['desc'],'index':dest['index'],'address':dest.get('address')})
        if h==dest['height']:proof[dest['address']]=h
    def only_vault(rows):
        result=[]
        for row in rows:
            h=prove(row) or evidence.get(row['address']) or proof.get(row['address'])
            if h in heights:result.append(dict(row,vault_height=h))
        return result
    entry['addresses']=only_vault(entry.get('addresses',[]));entry['address_history']=only_vault(entry.get('address_history',[]))
    cancelled=cancelled_receiving(reservations)
    def eligible(row):
        return not any(NodeWalletLoader.descriptor_key(policy['desc']) in cancelled and (prove(row)==height(policy) or row['address'] in {sample['address'] for sample in samples if sample['height']==height(policy)}) for policy in policies.values())
    entry['addresses']=[row for row in entry['addresses'] if eligible(row)]
    if not entry['addresses']:
        candidates=[row for row in entry['address_history'] if eligible(row)]
        if candidates:entry['addresses']=[max(candidates,key=lambda row:(row['vault_height'],row.get('observed_utc') or ''))]
    if not entry['addresses'] and heights:
        current=wallet.get('receiving_address');latest=max(heights)
        if evidence.get(current)==latest and not any(height(policy)==latest and NodeWalletLoader.descriptor_key(policy['desc']) in cancelled for policy in policies.values()):
            row={'address':current,'vault_height':latest,'observed_utc':entry.get('checked_utc') or wallet.get('public_history',{}).get('exported_utc') or stamp(),'txid':None}
            entry['addresses']=[row];entry['address_history']=ordered_history(entry['address_history'],[row])
    funded=set(entry.get('funded_addresses',[]))|set(entry.get('confirmed_addresses',[]))|set(evidence)
    funded.update(r['address'] for r in wallet.get('node_history',[]) if r.get('address') and r.get('category')=='receive' and int(r.get('confirmations',0))>0 and Decimal(str(r.get('amount',0)))>0)
    tip=entry.get('current_height')
    funded_rows=[r for r in entry['address_history']+entry['addresses'] if r['address'] in funded]
    entry['current_vault_address']=max(funded_rows,key=lambda r:(r['vault_height'],r.get('observed_utc') or ''))['address'] if funded_rows else None
    for row in entry['addresses']:
        row['new_vault_address']=type(tip) is int and row['vault_height']>tip and row['address'] not in funded
    entry['vault_samples']=samples;entry['status']='available' if entry['addresses'] else 'unavailable'
    if not entry['addresses']:entry['reason']='Vault receiving address awaits verification. Refresh the address list with a connected Agent.'
    return entry

def validate(state):
    if not isinstance(state,dict) or state.get('version')!=1 or not isinstance(state.get('entries'),dict) or len(state['entries'])>10000:raise ValueError('Invalid saved receiving addresses.')
    for key,e in state['entries'].items():
        if not isinstance(key,str) or not isinstance(e,dict) or e.get('id')!=key or e.get('kind')!='descriptor' or not isinstance(e.get('addresses'),list) or not isinstance(e.get('address_history'),list):raise ValueError('Invalid receiving address entry.')
        for row in e['addresses']+e['address_history']:
            if not isinstance(row,dict) or not valid_address(row.get('address')):raise ValueError('Invalid saved receiving address.')
        for field in ('confirmed_addresses','funded_addresses'):
            if not isinstance(e.get(field,[]),list) or any(not valid_address(a) for a in e.get(field,[])):raise ValueError('Invalid confirmed receiving addresses.')
    return state

class AddressDestinations:
    def __init__(self,config,registry=None,*,pause=lambda:None,gate=None,valid=lambda:True):
        self.config=Path(config);self.registry=registry;self.pause=pause;self.gate=gate;self.valid=valid;self.path=data_directory(config)/'address-destinations.json'
    def revision(self):
        parts=[]
        for path in (self.path,data_directory(self.config)/'builder-workspaces.json',data_directory(self.config)/'wallet-setups.json'):
            try:
                value=path.stat();parts.append(str(value.st_mtime_ns)+':'+str(value.st_size))
            except FileNotFoundError:parts.append('')
        return '|'.join(parts)
    def read(self):return validate(json.loads(self.path.read_text())) if self.path.exists() else {'version':1,'entries':{}}
    def write(self,state):
        validate(state);raw=json.dumps(state,ensure_ascii=True)
        if len(raw)>8*1024*1024:raise ValueError('Receiving address cache is full.')
        with storage_lock(self.config):
            self.path.parent.mkdir(parents=True,exist_ok=True);tmp=self.path.with_suffix('.tmp');tmp.write_text(raw);tmp.chmod(0o600);os.replace(tmp,self.path)
    def overlay(self,book):
        result=copy.deepcopy(book or {'entries':[]});rows={e['id']:e for e in result['entries'] if not e.get('builder_preview')};catalog={resource_id('descriptor',w['id']):w for w in DescriptorStore(self.config).read()['wallets'] if not w.get('extinct')};active=set(catalog)
        for key,entry in self.read()['entries'].items():
            key=resolve(self.config,key)
            if key not in active:continue
            old=rows.get(key,{})
            history=ordered_history(old.get('address_history',[]),[]);current={r['address'] for r in entry['address_history']+entry['addresses']};history=[r for r in history if r['address'] not in current]+entry['address_history']
            rows[key]={**old,**entry,'id':key,'address_history':history}
            # An empty/deferred receiving scan does not supersede the latest
            # receiving address established by the saved blockchain trace.
            if not entry['addresses'] and old.get('addresses') and not has_vault(catalog[key]['raw']):
                rows[key].update(addresses=copy.deepcopy(old['addresses']),status=old.get('status','available'))
                rows[key]['address_history']=ordered_history(history,rows[key]['addresses'])
        reservations=list(Destinations(self.config).read()['destinations'].values())
        for entry in rows.values():entry.pop('proposed_address',None)
        for key,wallet in catalog.items():
            if key in rows:rows[key]=vault_entry(rows[key],wallet,reservations)
        __import__('address_proposals').apply(self.config,rows,catalog)
        inactive=__import__('wallet_lifecycle').extinct_ids(self.config)
        result['entries']=[e for e in rows.values() if e.get('source') not in inactive];return result
    def scan(self,wallet,rpc,nodes):
        rid=resource_id('descriptor',wallet['id']);known=expanded(self.registry.hub,wallet['raw']);policies={};receipts={};routes=[];errors=[];unknown_vault=False
        for source in wallet.get('node_sources',[]):
            if source['node_id'] not in nodes:continue
            self.pause()
            try:
                raw=rpc.call(source['node_id'],'listdescriptors',[False],source['wallet_name']);present={NodeWalletLoader.descriptor_key(r['desc']) for r in raw['descriptors']}
                if not known & present:raise ValueError('The local wallet no longer matches its known policies.')
                if any(height(r) and receive(r) and NodeWalletLoader.descriptor_key(r['desc']) not in known for r in raw['descriptors']):unknown_vault=True
                rows=[r for r in raw['descriptors'] if NodeWalletLoader.descriptor_key(r['desc']) in known and receive(r)]
                received=rpc.call(source['node_id'],'listreceivedbyaddress',[0,False,True],source['wallet_name'])
                if not isinstance(received,list):raise ValueError('Core returned invalid receiving history.')
                received=list(received)
                if any(height(r) for r in rows):
                    # Inactive imported receiving policies can be unlabelled and
                    # omitted from listreceivedbyaddress. Core's owned outputs
                    # still carry their exact public parent receiving policy.
                    outputs=rpc.call(source['node_id'],'listunspent',[0,9999999],source['wallet_name'])
                    if not isinstance(outputs,list):raise ValueError('Core returned invalid vault outputs.')
                    external={NodeWalletLoader.descriptor_key(r['desc']) for r in rows}
                    for output in outputs:
                        if not valid_address(output.get('address')) or Decimal(str(output.get('amount',0)))<=0:continue
                        if not any(NodeWalletLoader.descriptor_key(p) in external for p in output.get('parent_descs',[])):continue
                        received.append({'address':output['address'],'amount':output['amount'],'confirmations':output.get('confirmations',0),'txids':[output.get('txid')] if output.get('txid') else []})
                routes.append(source)
                for row in rows:
                    k=NodeWalletLoader.descriptor_key(row['desc']);prior=policies.get(k)
                    if not prior or int(row.get('next_index',row.get('next',0)) or 0)>int(prior.get('next_index',prior.get('next',0)) or 0):policies[k]=row
                for row in received:
                    if not valid_address(row.get('address')) or Decimal(str(row.get('amount',0)))<=0:continue
                    old=receipts.get(row['address'])
                    if not old or int(row.get('confirmations',0))>int(old.get('confirmations',0)):receipts[row['address']]=row
            except (ValueError,OSError,KeyError,TypeError) as error:errors.append(str(error))
        if unknown_vault:raise ValueError('A node has a new vault policy awaiting wallet discovery. Refresh after the background check finishes; no unrestricted address was substituted.')
        if not routes:raise ValueError(errors[0] if errors else 'No connected node copy can verify this wallet.')
        current=max(int(nodes[s['node_id']].get('blockchain',{}).get('blocks',0)) for s in routes)
        info_cache={}
        def corroborate(address):
            if address in info_cache:return info_cache[address]
            for source in routes:
                self.pause()
                try:
                    info=rpc.call(source['node_id'],'getaddressinfo',[address],source['wallet_name'])
                    parent=info.get('parent_desc')
                    # Core can call an unlabeled, unused external address
                    # 'change'. Its exact external parent descriptor is stronger
                    # evidence than that address-book classification.
                    external=external_address(info,policies)
                    if info.get('address')==address and (info.get('ismine') or info.get('iswatchonly')) and external:info_cache[address]=info;return info
                except (ValueError,OSError):pass
            raise ValueError('No connected Core wallet confirmed this receiving address.')
        # Unlabelled imported watch addresses can be omitted by Core's address
        # book RPC. The verified public wallet ledger still records receipts.
        for row in wallet.get('node_history',[]):
            address=row.get('address')
            if row.get('category')!='receive' or not valid_address(address) or row.get('abandoned') or int(row.get('confirmations',0))<0 or Decimal(str(row.get('amount',0)))<=0:continue
            if address not in receipts:receipts[address]={'address':address,'amount':row['amount'],'confirmations':row.get('confirmations',0),'txids':[row['txid']]}
        history=[];times={}
        for row in wallet.get('node_history',[]):
            if row.get('category')=='receive' and row.get('address'):
                times[row['address']]=max(times.get(row['address'],0),row.get('blocktime',row.get('time',0)) or 0)
        for address,row in receipts.items():history.append({'address':address,'observed_utc':datetime.fromtimestamp(times[address],timezone.utc).isoformat() if times.get(address) else stamp(),'txid':(row.get('txids') or [None])[-1]})
        history.sort(key=lambda r:(times.get(r['address'],0),-int(receipts[r['address']].get('confirmations',0)),r['address']))
        vault=has_vault(wallet['raw']) or any(height(r) for r in policies.values());latest=[];vault_rows=[]
        for row in policies.values():
            h=height(row)
            if not h:continue
            d=Descriptor.from_string(row['desc']);index=None
            # A renewal's exact reserved address wins, including before funding.
            for dest in Destinations(self.config).read()['destinations'].values():
                if dest.get('height')==h and NodeWalletLoader.descriptor_key(dest['descriptors'][0]['desc'])==NodeWalletLoader.descriptor_key(row['desc']):index=max(index if index is not None else -1,dest['index'])
            address=None
            # Otherwise prefer an existing receiving address on this policy.
            if index is None:
                for item in reversed(history):
                    try:
                        info=corroborate(item['address'])
                        if NodeWalletLoader.vault_height(info.get('desc',''))!=h:continue
                        parent=info.get('parent_desc')
                        matches=bool(parent and NodeWalletLoader.descriptor_key(parent)==NodeWalletLoader.descriptor_key(row['desc']))
                        if not matches:
                            concrete=Descriptor.from_string(info['desc']);indices={k.origin.derivation[-1] for k in concrete.keys if k.origin and k.origin.derivation}
                            if len(indices)==1:
                                i=next(iter(indices));bounds=row.get('range',[0,0]);matches=bounds[0]<=i<=bounds[1] and d.derive(i).address(NETWORKS['main'])==item['address']
                        if matches:
                            address=item['address']
                            try:
                                indices={k.origin.derivation[-1] for k in Descriptor.from_string(info['desc']).keys if k.origin and k.origin.derivation}
                                if len(indices)==1 and d.derive(next(iter(indices))).address(NETWORKS['main'])==address:index=next(iter(indices))
                            except (KeyError,ValueError,IndexError):pass
                            break
                    except ValueError:continue
            if address is None:
                bounds=row.get('range',[0,0]);index=index if index is not None else max(bounds[0],int(row.get('next_index',row.get('next',0)) or 0)-1)
                if not bounds[0]<=index<=bounds[1]:continue
                address=d.derive(index).address(NETWORKS['main']) if d.is_wildcard else d.address(NETWORKS['main']);corroborate(address)
            vault_rows.append({'address':address,'observed_utc':stamp(),'txid':None,'vault_height':h,'descriptor':row['desc'],'index':index})
        cancelled=cancelled_receiving(Destinations(self.config).read()['destinations'].values())
        required_height=max([height(r) for r in wallet['raw']['descriptors'] if NodeWalletLoader.descriptor_key(r['desc']) not in cancelled]+[0])
        if vault and max([r['vault_height'] for r in vault_rows]+[0])<required_height:raise ValueError('The latest known vault policy could not be verified on a connected node. Saved receiving data was retained.')
        if vault_rows:
            # Furthest unexpired height is rightmost/default; if all expired,
            # retain the last policy rather than substituting an unrestricted one.
            vault_rows.sort(key=lambda r:(r['vault_height']>current,r['vault_height'],r['address']));candidates=[r for r in vault_rows if NodeWalletLoader.descriptor_key(r['descriptor']) not in cancelled];latest=[candidates[-1]] if candidates else []
            vault_addresses={r['address'] for r in vault_rows};history=[r for r in ordered_history(history,[]) if r['address'] not in vault_addresses]+vault_rows
        elif vault:raise ValueError('No connected Core copy confirmed a receiving vault policy. Earlier addresses were retained.')
        elif history:
            for selected in reversed(history):
                try:corroborate(selected['address']);latest=[selected];break
                except ValueError:continue
        if history and not latest and not vault:
            raise ValueError('Receiving history exists but its external address could not be verified. Saved receiving data was retained.')
        checked=stamp();entry={'id':rid,'source':wallet['id'],'kind':'descriptor','has_vault':vault,'status':'available' if latest else 'unavailable','addresses':latest,'address_history':history if vault_rows else ordered_history(history,latest),'funded_addresses':sorted(a for a,r in receipts.items() if int(r.get('confirmations',0))>=1),'confirmed_addresses':sorted(a for a,r in receipts.items() if int(r.get('confirmations',0))>=6),'checked_utc':checked,'observed_utc':checked,'current_height':current,'can_generate':not vault,'reason':'' if latest else 'Generate a new receiving address for this wallet.'}
        return entry,list(policies.values()),receipts,corroborate
    def refresh(self,*,foreground=False,only=None):
        if self.registry is None:raise ValueError('Connect an Agent to refresh receiving addresses.')
        nodes={n['id']:n for n in self.registry.snapshot()['nodes'] if n.get('connected') and n.get('rpc_ready') and n.get('blockchain',{}).get('state')=='ready'}
        if not nodes:raise ValueError('Connect a synchronised Agent to refresh receiving addresses.')
        if foreground:self.registry.hub.prioritise(list(nodes))
        rpc=RegistryRPC(self.registry,priority=0 if foreground else 100)
        fresh={}
        for node,n in nodes.items():
            self.pause()
            try:
                tip=rpc.call(node,'getblockcount')
                if type(tip) is not int or tip<0:raise ValueError('Invalid verified chain height.')
                fresh[node]={**n,'blockchain':{**n['blockchain'],'blocks':tip}}
            except (ValueError,OSError):continue
        nodes=fresh
        if not nodes:raise ValueError('No connected Agent could verify its current chain height.')
        epoch=getattr(self.registry,'address_epoch',0)
        if foreground:epoch+=1;self.registry.address_epoch=epoch
        updates={};details={}
        for wallet in DescriptorStore(self.config).read()['wallets']:
            rid=resource_id('descriptor',wallet['id'])
            if wallet.get('extinct') or only and rid!=only:continue
            try:
                entry,*facts=self.scan(wallet,rpc,nodes);updates[rid]=entry;details[rid]=(entry,*facts)
            except (ValueError,OSError,KeyError,TypeError) as error:
                self.registry.diagnostic_log.append('Address Book',wallet['name']+': receiving check deferred: '+str(error))
                if only:raise ValueError(str(error)) from None
                previous=self.read()['entries'].get(rid)
                if previous:updates[rid]={**previous,'refresh_error':str(error)[:500],'can_generate':False}
        self.pause()
        with self.gate.access() if self.gate else nullcontext():
            if not self.valid() or getattr(self.registry,'address_epoch',0)!=epoch:return details
            state=self.read()
            for key,entry in updates.items():entry['funded_addresses']=sorted(set(entry.get('funded_addresses',[]))|set(state['entries'].get(key,{}).get('funded_addresses',[])))
            state['entries'].update(updates);self.write(state)
        return details
    def generate(self,resource):
        if not isinstance(resource,str) or not resource.startswith('["descriptor",'):raise ValueError('Choose an active wallet for a new receiving address.')
        resource=resolve(self.config,resource);facts=self.refresh(foreground=True,only=resource).get(resource)
        if not facts:raise ValueError('Choose an active wallet with a connected Agent.')
        entry,policies,receipts,corroborate=facts
        if entry['has_vault']:raise ValueError('Generate receiving address is unavailable for vault wallets.')
        rows=[r for r in policies if r.get('active') is True and Descriptor.from_string(r['desc']).is_wildcard]
        rows.sort(key=lambda r:(not r['desc'].startswith('wpkh('),r['desc']))
        if not rows:raise ValueError('No active, publicly derivable receiving descriptor is available.')
        row=rows[0];d=Descriptor.from_string(row['desc']);bounds=row.get('range',[0,0]);index=max(bounds[0],int(row.get('next_index',row.get('next',0)) or 0));reserved={v['address'] for v in Destinations(self.config).read()['destinations'].values()}
        while index<=bounds[1]:
            address=d.derive(index).address(NETWORKS['main'])
            if address not in receipts and address not in reserved:break
            index+=1
        else:raise ValueError('The monitored receiving range is exhausted. Extend it locally on the Agent.')
        corroborate(address)
        return {'address':address,'observed_utc':stamp(),'txid':None,'index':index,'descriptor':row['desc']}
