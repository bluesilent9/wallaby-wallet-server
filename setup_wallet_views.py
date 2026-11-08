"""Public setup identities for discovery/presentation; no ceremony or wallet writes."""
import json
from storage import data_directory
from policy_accounts import intentional_account

class SetupWalletViews:
    def __init__(self,config,monitors=()):
        self.config=config;path=data_directory(config)/'wallet-setups.json'
        self.setups=list(json.loads(path.read_text())['sessions'].values()) if path.exists() else []
        self.monitors=list(monitors);self.lineage=None
    def setup(self,raw):
        from node_wallets import NodeWalletLoader
        keys={NodeWalletLoader.descriptor_key(r['desc']) for r in raw.get('descriptors',[])}
        if not keys:return None
        original=[(s,{NodeWalletLoader.descriptor_key(d) for d in s.get('descriptors',[])}) for s in self.setups]
        exact=next((s for s,known in original if keys==known),None)
        if exact:return exact
        # Additive refreshes keep the original descriptors. Recognise further
        # generations only through locally approved, Core-confirmed transitions;
        # sharing keys or a Core filename alone cannot establish setup identity.
        candidates=[(s,known) for s,known in original if known and known<=keys]
        if not candidates:return None
        if self.lineage is None:
            from types import SimpleNamespace
            path=data_directory(self.config)/'agent-hub.json'
            state=json.loads(path.read_text()) if path.exists() else {'requests':{}}
            self.lineage=SimpleNamespace(read=lambda:state)
        from policy_lineage import expanded
        return next((s for s,known in candidates if keys<=expanded(self.lineage,{'descriptors':[{'desc':d} for d in s['descriptors']]})),None)
    def hidden(self,raw):
        if intentional_account(raw,self.setups,self.monitors):return True
        s=self.setup(raw)
        return bool(s and (s['state']!='ready' or not set(s['routes'].values())<=set(s.get('completion_confirmed',{}))))
    def hide_cached(self,wallet):
        # Missing history is unknown, never proof an account is empty. A key
        # account with its own receipts/sends is a real financial wallet too.
        return (isinstance(wallet.get('public_history'),dict) and 'outputs' in wallet['public_history']
                and not wallet['public_history']['outputs'] and wallet.get('node_history')==[]
                and not wallet.get('vault_evidence') and self.hidden(wallet['raw']))
    def annotate(self,wallet):
        s=self.setup(wallet['raw'])
        if s:wallet['setup_name']=s['proposal']['name']
        return wallet
