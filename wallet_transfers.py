"""Correlated public synchronization records; private files travel only between Agents."""
import copy,secrets,time
from wallet_preview import policies

TERMINAL={'complete','denied','error'}
class SynchronisationBusy(ValueError):pass
class Transfers:
    def __init__(self,hub):
        self.hub=hub;self.refresh_nodes=set();self.busy=set()
    @staticmethod
    def pairs(state):
        result={}
        for key,row in state['requests'].items():
            if row.get('kind')=='wallet_transfer':result.setdefault(row['transfer_id'],[]).append(row)
        return result
    def current_agent(self,node):
        from wallet_sync_queue import current_agent
        return current_agent(self.hub,node)
    @staticmethod
    def contains(wallets,raw):
        from wallet_sync_queue import contains
        return contains(wallets,raw)
    def schedule_queues(self,state):
        from wallet_sync_queue import schedule
        schedule(self,state)
    def is_busy(self,node):return node in self.busy
    def proposals(self,state,node):
        from wallet_sync_queue import proposals
        return proposals(self,state,node)
    def obsolete_preview(self,state,node,payload):
        """A stale public notice may be retired; an operation outcome never is."""
        from agent_hub import digest
        from extinct_sync import containers
        sender=next((r for r in state['requests'].values() if r.get('kind')=='wallet_transfer' and r.get('direction')=='send' and r['node_id']==node and r.get('proposal') and digest(r['proposal'])==payload['request_hash']),None)
        if not sender or not sender.get('base_sent') or sender.get('state')!='pending' or sender.get('source_has_private_keys'):return False
        rows=self.pairs(state)[sender['transfer_id']]
        if any(r['state']!='pending' for r in rows):return False
        old=sender['public_wallet'];oldkeys=policies(old,True)
        if not all(r['desc'].startswith('addr(') for r in old['descriptors']):return False
        inventory=self.hub.inventories.get(node,{})
        if not inventory.get('complete'):return False
        replacement=next((w for w in containers(inventory['wallets']) if w.get('extinct') and oldkeys<=policies(w['raw'],True)),None)
        if not replacement or not (sender.get('superseded_container') or oldkeys<policies(replacement['raw'],True) or old['wallet_name'] not in ('Extinct','Wallaby Extinct')):return False
        p=sender['proposal'];v=payload['preview']
        if (v['transfer_id'],v['challenge'],v['sender_ipv6'],v['receiver_ipv6'])!=(p['transfer_id'],p['preview_challenge'],p['node_ipv6'],p['peer']['ipv6']) or policies(v['public_wallet'],True)!=oldkeys:raise ValueError('Obsolete preview does not match its original frozen request.')
        return True
    def accept_preview(self,state,node,payload,proof):
        from agent_hub import digest
        if not isinstance(payload,dict) or set(payload)!={'request_hash','preview','public_key','signature'}:raise ValueError('Invalid wallet transfer preview outbox.')
        rows=next((rows for rows in self.pairs(state).values() if any(r.get('proposal') and digest(r['proposal'])==payload['request_hash'] for r in rows)),None)
        sender=next((r for r in rows or [] if r['direction']=='send' and r['node_id']==node),None)
        if not sender or digest(sender.get('proposal',{}))!=payload['request_hash'] or not sender.get('base_sent'):raise ValueError('Unsolicited preview or not the paired sending Agent.')
        wire={k:payload[k] for k in ('preview','public_key','signature')};v=wire['preview'];p=sender['proposal']
        from relay_bindings import matches_preview
        if not matches_preview(v,p) or policies(v['public_wallet'],True)!=policies(p['public_wallet'],True) or v.get('restoration')!=p.get('restoration'):raise ValueError('Preview wallet, restoration purpose, challenge or authenticated peers differ from the frozen request.')
        if p.get('transfer_version')==3 and wire['public_key']!=p['transport']['sender_identity']:raise ValueError('Signed preview identity differs from the authenticated sending Agent.')
        original=sender.get('signed_preview')
        if original and original['public_key']!=wire['public_key']:raise ValueError('The sending Agent preview identity changed. Reconcile locally.')
        # Authenticated public notices are not operation outcomes. A stale notice
        # must not block fresh permissions/queues for every wallet in this batch.
        if not sender.get('queue_visible') or sender['state']!='pending' or any(r['state'] in ('denied','error','complete') for r in rows):
            return 'Late preview acknowledged without changing its inactive transfer'
        if original:
            if original!=wire:
                sender['preview_notice']='Changed preview acknowledged; original frozen snapshot retained. Reconcile locally before a fresh attempt.'
                return sender['preview_notice']
            return
        sender['signed_preview']=copy.deepcopy(wire);sender['preview_proof']=proof
    def accept_result(self,state,node,p):
        from agent_hub import digest
        if not isinstance(p,dict) or not {'request_hash','status'}<=set(p) or set(p)-{'request_hash','status','message'} or p['status'] not in TERMINAL|{'recovery_required'}:raise ValueError('Invalid transfer result.')
        row=next((r for r in state['requests'].values() if r.get('kind')=='wallet_transfer' and r.get('proposal') and digest(r['proposal'])==p['request_hash'] and r['node_id']==node),None)
        if not row or not row.get('base_sent'):raise ValueError('Unsolicited transfer result.')
        if row['state'] in TERMINAL:
            if row['state']!=p['status']:raise ValueError('A terminal transfer outcome cannot be changed.')
            return
        if row['state']=='recovery_required' and p['status'] not in ('recovery_required','complete','error'):raise ValueError('History recovery must finish or report an error.')
        row.update(state=p['status'],message=str(p.get('message',''))[:1000],finished_utc=self.hub.utc())
        self.refresh_nodes.add(node)
    def retry(self,transfer,confirmed):
        raise ValueError('Manage wallet synchronisation on the receiving Agent. Wallet Server cannot create or retry a wallet transfer.')
    def refresh_reviews(self,identities,confirmed):
        raise ValueError('Manage wallet synchronisation on the receiving Agent. Wallet Server cannot create wallet reviews.')
    def summaries(self,state,node):
        # Earlier outcomes remain in the profile; old Server queues have no
        # authority over current Agent-owned inventory or locally chosen work.
        return []
