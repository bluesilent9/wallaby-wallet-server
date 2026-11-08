"""Untrusted store-and-forward transport. No Noise keys or plaintext live here.

Peers implement Noise_IKpsk2_25519_ChaChaPoly_SHA256 and authenticate the pinned
role-bound keys from an independently scanned Agent QR. The server validates
signed liveness reports only for UI/readiness; those are not Agent approvals.
"""
import base64,copy,hashlib,json,re,secrets,threading,time
from setup_signatures import canonical,fingerprint,verify

PROTOCOL='wallaby-wallet-relay'
NAMESPACE='wallaby-wallet-relay-control-v1'
CIPHER='Noise_IKpsk2_25519_ChaChaPoly_SHA256'
def digest(x):return hashlib.sha256(canonical(x)).hexdigest()
def hexid(x):return isinstance(x,str) and re.fullmatch('[0-9a-f]{64}',x) is not None
def endpoint_id(role,key):return digest({'role':role,'identity_key':key})
def binary(value,minimum,maximum):
    if not isinstance(value,str) or len(value)>((maximum+2)//3)*4:raise ValueError('Invalid encrypted relay frame.')
    try:b=base64.b64decode(value,validate=True)
    except (ValueError,TypeError):raise ValueError('Relay payload must be base64 ciphertext.') from None
    if not minimum<=len(b)<=maximum or base64.b64encode(b).decode()!=value:raise ValueError('Invalid encrypted relay frame size.')
    return b

class SecureRelay:
    def __init__(self,config,hub):
        self.config=config;self.hub=hub;self.lock=threading.RLock();self.endpoints={};self.challenges={};self.channels={};self.messages={};self.tombstones={};self.rates={};self.action_rates={};self.byte_rates={};self.paths={}
    def reset(self):
        with self.lock:
            for name in ('endpoints','challenges','channels','messages','tombstones','rates','action_rates','byte_rates','paths'):getattr(self,name).clear()
    def prune(self):
        now=time.monotonic()
        for rows in (self.challenges,self.messages,self.tombstones):
            for k,v in list(rows.items()):
                if v['expires']<=now:rows.pop(k,None)
        self.channels={k:v for k,v in self.channels.items() if v['expires']>now}
        self.paths={k:v for k,v in self.paths.items() if v['expires']>now}
        self.rates={k:v for k,v in self.rates.items() if now-v[1]<60}
        for name in ('action_rates','byte_rates'):
            setattr(self,name,{k:v for k,v in getattr(self,name).items() if now-v[1]<60})
    def principal(self,role,key,owner,scope):
        if role not in ('agent','mobile'):raise ValueError('Unknown device role.')
        fingerprint(key)
        return {'id':endpoint_id(role,key),'role':role,'identity_key':key,'owner':owner,'scope':scope}
    def agent(self,token):
        c=self.hub.connection(token);node=c['node_id'];identity=self.hub.wallet_builder.read().get('identities',{}).get(node,{})
        if not identity.get('public_key'):raise ValueError('Wait for this Agent to return its signed identity first.')
        return self.principal('agent',identity['public_key'],node,token)
    def mobile(self,devices,token):
        with devices.lock:
            session,device=devices.client(token)
            return self.principal('mobile',device['public_key'],session['user_id'],token)
    def challenge(self,p):
        self.prune()
        if len(self.challenges)>=256:raise ValueError('Too many pending relay challenges.')
        nonce=secrets.token_hex(32);self.challenges[nonce]={'principal':p,'expires':time.monotonic()+45}
        return {'protocol':PROTOCOL,'version':1,'endpoint_id':p['id'],'role':p['role'],'challenge':nonce,'namespace':NAMESPACE,'cipher_suite':CIPHER}
    def control(self,p,envelope,kind):
        if not isinstance(envelope,dict) or not isinstance(envelope.get('message'),dict):raise ValueError('Signed relay control required.')
        m=envelope['message'];pending=self.challenges.pop(m.get('challenge'),None)
        if not pending or pending['principal']!=p or pending['expires']<=time.monotonic():raise ValueError('Relay challenge expired or was already used.')
        if m.get('protocol')!=PROTOCOL or type(m.get('version')) is not int or m['version']!=1 or m.get('kind')!=kind or m.get('endpoint_id')!=p['id'] or m.get('role')!=p['role']:raise ValueError('Relay control has a different device role or identity.')
        return verify(self.config,envelope,p['identity_key'],NAMESPACE)
    def registered(self,p):
        endpoint=self.endpoints.get(p['id'])
        if not endpoint or endpoint['principal']!=p:raise ValueError('Register this device’s signed relay identity first.')
        endpoint['seen']=time.monotonic();return endpoint
    def dispatch(self,p,data):
        if not isinstance(data,dict) or not isinstance(data.get('action'),str):raise ValueError('Invalid relay action.')
        with self.lock:
            self.prune();action=data['action']
            for key,limit in ((p['id'],600),('*',6000)):
                count,stamp=self.action_rates.get(key,(0,time.monotonic()))
                if count>=limit:raise ValueError('Relay request limit reached. Retry shortly.')
            for key in (p['id'],'*'):
                count,stamp=self.action_rates.get(key,(0,time.monotonic()));self.action_rates[key]=(count+1,stamp)
            schemas={'policy':{'action'},'path':{'action','proof'},'challenge':{'action'},'register':{'action','proof'},'directory':{'action'},'channel':{'action','proof'},'send':{'action','frame'},'receive':{'action'},'ack':{'action','ids'},'disconnect':{'action'}}
            if action not in schemas or set(data)!=schemas[action]:raise ValueError('Unexpected relay fields.')
            if action=='policy':return {'protocol':PROTOCOL,'version':1,'peer_transport':'direct-ssh-v1','direct_preferred':True,'encrypted_relay_fallback':True,'ssh_credential_max_age_seconds':86400,'password_bootstrap':False,'max_logged_in_users':10,'max_ciphertext_bytes_per_minute':2097152,'server_dials_peer_addresses':False}
            if action=='challenge':return self.challenge(p)
            if action=='register':
                m=self.control(p,data['proof'],'register');expected={'protocol','version','kind','endpoint_id','role','challenge','noise_public_key','cipher_suite'}
                if set(m)!=expected or m['cipher_suite']!=CIPHER:raise ValueError('Unsupported relay identity.')
                binary(m['noise_public_key'],32,32)
                if len(self.endpoints)>=256 and p['id'] not in self.endpoints:raise ValueError('Relay directory is full.')
                old=self.endpoints.get(p['id'])
                if old and (old['noise_public_key']!=m['noise_public_key'] or old['principal']!=p):self.invalidate(p['id'])
                self.endpoints[p['id']]={'principal':p,'noise_public_key':m['noise_public_key'],'proof':copy.deepcopy(data['proof']),'seen':time.monotonic()}
                return {'endpoint_id':p['id'],'registered':True,'cipher_suite':CIPHER}
            own=self.registered(p)
            if action=='directory':
                return {'protocol':PROTOCOL,'version':1,'endpoints':[{'endpoint_id':k,'role':v['principal']['role'],'identity_key':v['principal']['identity_key'],'noise_public_key':v['noise_public_key'],'registration_proof':v['proof'],'online':self.online(v),'node_id':v['principal']['owner'] if v['principal']['role']=='agent' else None} for k,v in self.endpoints.items()],'trusted':False}
            if action=='disconnect':self.invalidate(p['id']);self.endpoints.pop(p['id'],None);return {'disconnected':True}
            if action=='path':
                m=self.control(p,data['proof'],'path')
                expected={'protocol','version','kind','endpoint_id','role','challenge','peer_id','channel_id','epoch_id','transport','state'}
                channel=self.channels.get((p['id'],m.get('peer_id')))
                if set(m)!=expected or not hexid(m['epoch_id']) or m['transport'] not in ('direct-ssh','relay') or m['state'] not in ('ready','closed') or not channel or channel['state']!='ready' or channel['channel_id']!=m['channel_id']:raise ValueError('Path report must match a current authenticated peer channel.')
                self.paths[(p['id'],m['peer_id'])]={'epoch_id':m['epoch_id'],'channel_id':m['channel_id'],'transport':m['transport'],'state':m['state'],'expires':time.monotonic()+90}
                return {'recorded':True,'approval_authority':False}
            if action=='channel':
                m=self.control(p,data['proof'],'channel');expected={'protocol','version','kind','endpoint_id','role','challenge','peer_id','peer_role','peer_noise_public_key','channel_id','handshake_hash','state','paired_by_qr'}
                if set(m)!=expected or m['state'] not in ('ready','closed') or m['paired_by_qr'] is not True or not hexid(m['channel_id']) or not hexid(m['handshake_hash']):raise ValueError('Invalid authenticated channel report.')
                peer=self.endpoints.get(m['peer_id'])
                if not peer or m['peer_id']==p['id'] or peer['principal']['role']!=m['peer_role'] or peer['noise_public_key']!=m['peer_noise_public_key']:raise ValueError('Channel peer or pinned role does not match.')
                self.channels[(p['id'],m['peer_id'])]={'channel_id':m['channel_id'],'handshake_hash':m['handshake_hash'],'state':m['state'],'expires':time.monotonic()+90,'noise_public_key':own['noise_public_key'],'peer_noise_public_key':peer['noise_public_key']}
                return {'recorded':True,'approval_authority':False}
            if action=='send':return self.send(p,data['frame'])
            if action=='receive':return {'frames':[copy.deepcopy(v['frame']) for v in self.messages.values() if v['frame']['to']==p['id']][:16]}
            ids=data['ids']
            if not isinstance(ids,list) or len(ids)>32 or any(not hexid(i) for i in ids):raise ValueError('Invalid relay receipt list.')
            for ident in ids:
                row=self.messages.get(ident)
                if row and row['frame']['to']!=p['id']:raise ValueError('A device can only acknowledge its own messages.')
            for ident in ids:
                row=self.messages.pop(ident,None)
                if row:self.tombstones[ident]={'hash':digest(row['frame']),'expires':row['expires']}
            return {'accepted':ids}
    def send(self,p,frame):
        expected={'version','id','from','to','channel_id','sequence','kind','ciphertext'}
        if not isinstance(frame,dict) or set(frame)!=expected or type(frame['version']) is not int or frame['version']!=1 or not all(hexid(frame[k]) for k in ('id','from','to','channel_id')) or frame['from']!=p['id'] or frame['to']==p['id'] or type(frame['sequence']) is not int or not 0<=frame['sequence']<2**53 or frame['kind'] not in ('handshake','transport'):raise ValueError('Invalid relay frame header.')
        payload=binary(frame['ciphertext'],16,49152);peer=self.endpoints.get(frame['to'])
        if not peer:raise ValueError('Unknown or disallowed relay recipient.')
        ident=frame['id'];old=self.messages.get(ident);past=self.tombstones.get(ident)
        if old or past:
            if (digest(old['frame']) if old else past['hash'])!=digest(frame):raise ValueError('Conflicting relay message ID.')
            return {'id':ident,'queued':bool(old),'acknowledged':bool(past)}
        count,stamp=self.rates.get(p['id'],(0,time.monotonic()))
        used,byte_stamp=self.byte_rates.get(p['id'],(0,time.monotonic()))
        if used+len(payload)>2097152:raise ValueError('Relay byte limit reached. Use the direct connection for bulk data or retry shortly.')
        if count>=120:raise ValueError('Relay rate limit reached. Retry shortly.')
        if len(self.messages)+len(self.tombstones)>=1024 or sum(v['frame']['to']==frame['to'] for v in self.messages.values())>=128:raise ValueError('Relay queue is full. Retry later.')
        self.byte_rates[p['id']]=(used+len(payload),byte_stamp)
        self.rates[p['id']]=(count+1,stamp);self.messages[ident]={'frame':copy.deepcopy(frame),'expires':time.monotonic()+1800}
        return {'id':ident,'queued':True,'acknowledged':False}
    def invalidate(self,ident):
        self.channels={k:v for k,v in self.channels.items() if ident not in k};self.paths={k:v for k,v in self.paths.items() if ident not in k};self.messages={k:v for k,v in self.messages.items() if ident not in (v['frame']['from'],v['frame']['to'])}
    def online(self,row):
        p=row['principal']
        builder=getattr(self.hub,'wallet_builder',None)
        if p['role']=='agent' and builder:
            known=builder.read().get('identities',{}).get(p['owner'],{}).get('public_key')
            if known and known!=p['identity_key']:return False
        return time.monotonic()-row['seen']<90 and (p['role']!='agent' or any(c['node_id']==p['owner'] and token==p['scope'] for token,c in list(self.hub.registry.connections.items())))
    def mesh(self,nodes):
        with self.lock:
            self.prune();by_node={e['principal']['owner']:k for k,e in self.endpoints.items() if e['principal']['role']=='agent' and self.online(e)};rows=[];unique=sorted(set(nodes))
            for i,a in enumerate(unique):
                for b in unique[i+1:]:
                    left=by_node.get(a);right=by_node.get(b);x=self.channels.get((left,right));y=self.channels.get((right,left));ready=bool(x and y and x['state']==y['state']=='ready' and x['channel_id']==y['channel_id'] and x['handshake_hash']==y['handshake_hash'] and x['noise_public_key']==y['peer_noise_public_key'] and x['peer_noise_public_key']==y['noise_public_key'])
                    px=self.paths.get((left,right));py=self.paths.get((right,left));direct=bool(ready and px and py and px['state']==py['state']=='ready' and px['transport']==py['transport']=='direct-ssh' and px['epoch_id']==py['epoch_id'] and px['channel_id']==py['channel_id']==x['channel_id'])
                    rows.append({'transport':'direct-ssh' if direct else 'relay','from_node':a,'to_node':b,'ready':ready,'status':('Authenticated direct SSH channel ready' if direct else 'Authenticated encrypted relay channel ready') if ready else 'Pair these Agents using their local QR codes and keep them connected.'})
            return {'required':len(rows),'ready':all(r['ready'] for r in rows) and all(n in by_node for n in unique),'pairs':rows,'cipher_suite':CIPHER,'server_can_decrypt':False}
    def require_mesh(self,nodes):
        result=self.mesh(nodes)
        if not result['ready']:raise ValueError('Connect and QR-pair every selected Agent with the other selected Agents before starting this multisig operation.')
        return result

    def binding(self,source,target):
        with self.lock:
            self.require_mesh([source,target]);by_node={e['principal']['owner']:(key,e) for key,e in self.endpoints.items() if e['principal']['role']=='agent' and self.online(e)}
            a,x=by_node[source];b,y=by_node[target]
            return {'protocol':PROTOCOL,'version':1,'cipher_suite':CIPHER,'sender_endpoint':a,'receiver_endpoint':b,'sender_identity':x['principal']['identity_key'],'receiver_identity':y['principal']['identity_key'],'sender_noise_key':x['noise_public_key'],'receiver_noise_key':y['noise_public_key']}

    def requirements(self,nodes):
        with self.lock:
            self.require_mesh(nodes);selected=set(nodes)
            keys=sorted({e['principal']['identity_key'] for e in self.endpoints.values() if e['principal']['role']=='agent' and e['principal']['owner'] in selected and self.online(e)})
            return {'protocol':PROTOCOL,'version':1,'cipher_suite':CIPHER,'required_agent_keys':keys}
