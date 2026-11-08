"""Atomic balance snapshots and the shared context-bound trace evidence graph."""
from pathlib import Path
from copy import deepcopy
import json,os,uuid
from storage import data_directory,storage_lock

BALANCE_ALGORITHM=6

class BalanceStore:
    def __init__(self,config):self.config=Path(config);self.path=data_directory(self.config)/'balance-trace.json'
    def load(self,key):
        try:data=json.loads(self.path.read_text())
        except (OSError,ValueError):return None
        return data if data.get('schema')==1 and data.get('signature')==key else None
    def latest(self):
        for path in (self.path,self.path.with_name('balance-verified.json')):
            try:data=json.loads(path.read_text())
            except (OSError,ValueError):continue
            if data.get('schema')==1 and data.get('result',{}).get('basis_algorithm')==BALANCE_ALGORITHM and data.get('result',{}).get('balances'):return data
        return None
    def save(self,key,result):
        with storage_lock(self.config):
            previous=self.load(key)
            result=deepcopy(result)
            if 'balances' in result:result['basis_algorithm']=BALANCE_ALGORITHM
            if previous:
                old=previous['result']
                if 'balances' in old and 'balances' not in result:
                    result['balances']=deepcopy(old['balances'])
                    if 'basis_algorithm' in old:result['basis_algorithm']=old['basis_algorithm']
                graph=old.get('trace_graph')
                incoming=result.get('trace_graph')
                if graph and incoming:
                    for section in ('nodes','edges','claims'):
                        merged=dict(graph[section])
                        for ident,value in incoming[section].items():
                            if section=='claims' and ident in merged and merged[ident]!=value:
                                raise ValueError('Conflicting confirmed trace ownership evidence.')
                            merged[ident]=value
                        incoming[section]=merged
                elif graph:result['trace_graph']=deepcopy(graph)
                answers={tuple(row[:3]):row[3] for row in old.get('trace_answers',[])}
                answers.update({tuple(row[:3]):row[3] for row in result.get('trace_answers',[])})
                if result.get('trace_graph'):answers={k:v for k,v in answers.items() if k[1] not in ('source','destination')}
                if answers or 'trace_answers' in result:result['trace_answers']=[[*k,v] for k,v in answers.items()]
            # A pending/failed trace can save new evidence without erasing the
            # last verified display, even when its calculation signature changed.
            verified={'schema':1,'signature':key,'result':result} if result.get('balances') and result.get('basis_algorithm')==BALANCE_ALGORITHM else self.latest()
            self.path.parent.mkdir(parents=True,exist_ok=True)
            if verified:
                target=self.path.with_name('balance-verified.json');temp=target.with_name(uuid.uuid4().hex+'.tmp')
                try:temp.write_text(json.dumps(verified,ensure_ascii=True));temp.chmod(0o600);os.replace(temp,target)
                finally:temp.unlink(missing_ok=True)
            tmp=self.path.with_name(uuid.uuid4().hex+'.tmp')
            try:
                tmp.write_text(json.dumps({'schema':1,'signature':key,'result':result},ensure_ascii=True));tmp.chmod(0o600);os.replace(tmp,self.path)
            finally:tmp.unlink(missing_ok=True)
    def ready(self,key):
        saved=self.load(key)
        return bool(saved and saved['result'].get('balances') and saved['result'].get('basis_algorithm')==BALANCE_ALGORITHM)
    def save_evidence(self,key,graph,answers):
        # Save discoveries even when an incomplete trace cannot produce balances.
        # This must never unlock the balance/report UI by itself.
        self.save(key,{'trace_graph':graph,'trace_answers':answers})
    def personal(self,key,user,*,allow_saved=False):
        saved=self.load(key)
        if saved is None and allow_saved:saved=self.latest()
        if not saved or not saved['result'].get('balances') or saved['result'].get('basis_algorithm')!=BALANCE_ALGORITHM:return None
        balance=deepcopy(saved['result']['balances'])
        from descriptor_store import DescriptorStore
        from policy_accounts import multisig_summary,has_vault
        catalog=DescriptorStore(self.config).read()
        __import__('balance_identity').canonicalise(self.config,balance,catalog)
        policies={w['id']:multisig_summary(w['raw']) for w in catalog['wallets']}
        vaults={w['id']:has_vault(w['raw']) for w in catalog['wallets']}
        from preferences import FamilyStore
        from wallet_names import dashboard_name
        family=FamilyStore(self.config).snapshot()
        labels={r['source']:dashboard_name(r) for r in family['ownership'] if r['kind']=='descriptor'}
        from descriptor_snapshot import history_ready
        from balance_evidence import history as cached_history
        from empty_wallet_cards import include_verified_empty,include_discovered
        present={row.get('descriptor_id') for row in balance['wallets']}
        assigned={r['source'] for r in family['ownership'] if r.get('kind')=='descriptor' and r.get('confirmed')}
        missing_empty=any(w['id'] not in present and w['id'] in assigned and not w.get('extinct') and w.get('node_history')==[] for w in catalog['wallets'])
        if missing_empty and history_ready(self.config,catalog):
            fp=DescriptorStore.fingerprint(catalog);path=data_directory(self.config)/'descriptor-history'/(fp+'.json')
            try:
                stat=path.stat();chain=cached_history(str(self.config),fp,stat.st_mtime_ns,stat.st_size)
            except OSError:chain={}
            include_verified_empty(balance,catalog,chain,family)
        include_discovered(balance,catalog,family)
        for row in balance['wallets']:
            if row.get('descriptor_id') in labels:row['name']=labels[row['descriptor_id']]
            row['multisig']=policies.get(row.get('descriptor_id'),[])
            if row.get('descriptor_id') in vaults:row['has_vault']=vaults[row['descriptor_id']]
            owned=row.get('owner_name')==user['name'] and not row.get('smsf')
            row['ownership']='personal' if owned else 'external'
            if row['kind']=='exchange':row['name']=('Bitaroo SMSF Exchange · '+row.get('owner_name','Unknown')) if row.get('smsf') else 'Bitaroo Exchange' if owned else 'Bitaroo Exchange · '+row.get('owner_name','Unknown')
        from current_balances import reconcile
        chain={}
        fp=DescriptorStore.fingerprint(catalog);path=data_directory(self.config)/'descriptor-history'/(fp+'.json')
        try:
            stat=path.stat();chain=cached_history(str(self.config),fp,stat.st_mtime_ns,stat.st_size)
        except OSError:pass
        reconcile({'balances':balance},family,chain)
        from wallet_views import extinct_cards
        balance['extinct_wallets']=extinct_cards(self.config)
        return __import__('wallet_lifecycle').classify(self.config,{'taxpayer':user['name'],'balances':balance})
