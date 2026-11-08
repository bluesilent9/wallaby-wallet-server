"""Paired mobile relay and account reads. No wallet or approval authority."""
import hashlib,json,secrets,threading,time,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit
from storage import data_directory,storage_lock
from setup_signatures import canonical,fingerprint,verify

PROTOCOL='wallaby-wallet-mobile'
PAIR_NAMESPACE='wallaby-wallet-mobile-pair-v1'
CONNECT_NAMESPACE='wallaby-wallet-mobile-connect-v1'
RESULT_NAMESPACE='wallaby-wallet-mobile-result-v1'
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def utc(stamp=None):return datetime.fromtimestamp(time.time() if stamp is None else stamp,timezone.utc).isoformat().replace('+00:00','Z')
def label(value):
    if not isinstance(value,str) or not 1<=len(value.strip())<=80 or any(ord(c)<32 or ord(c)==127 for c in value):raise ValueError('Use a device name of 1–80 characters.')
    return value.strip()
def ssh_connection(value):
    if not isinstance(value,dict) or set(value)!={'host','port','user'}:raise ValueError('Enter the server SSH address, port and username.')
    host=value['host'];user=value['user'];port=value['port']
    if not isinstance(host,str) or not 1<=len(host)<=253 or not re.fullmatch(r'[A-Za-z0-9.:%_-]+',host) or host.startswith('-') or not isinstance(user,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,63}',user) or type(port) is not int or not 1<=port<=65535:raise ValueError('Invalid SSH connection details.')
    return dict(value)
def qr_svg(payload):
    from vendor.qrcodegen import QrCode
    qr=QrCode.encode_text(json.dumps(payload,separators=(',',':')),QrCode.Ecc.MEDIUM);n=qr.get_size();parts=[]
    for y in range(n):
        for x in range(n):
            if qr.get_module(x,y):parts.append(f'M{x+4},{y+4}h1v1h-1z')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n+8} {n+8}" role="img" aria-label="Pair this mobile device"><rect width="100%" height="100%" fill="white"/><path d="'+''.join(parts)+'" fill="black"/></svg>'

def comparison_digest(claims):
    # Refreshing a signature/challenge without changing its public facts must
    # not invalidate the user's comparison. Changed keys, routes or operations do.
    rows=[]
    for claim in claims:
        row={k:v for k,v in claim.items() if k!='signed_agent_facts'}
        proof=claim.get('signed_agent_facts')
        row['agent_facts']={k:proof['message'][k] for k in ('agent_public_key','ssh_host_public_key','ipv6','hostname')} if proof else None
        rows.append(row)
    return digest(rows)

class MobileDevices:
    def __init__(self,config,hub):
        self.config=Path(config);self.hub=hub;self.path=data_directory(config)/'mobile-devices.json'
        self.lock=threading.RLock();self.invites={};self.pending={};self.challenges={};self.sessions={};self.results={};self.mobile_port=None;self.ssh_host_public_key=None
    def read(self):
        if self.path.exists():return json.loads(self.path.read_text())
        return {'version':1,'server_id':secrets.token_hex(32),'devices':{}}
    def save(self,state):
        self.path.parent.mkdir(parents=True,exist_ok=True);tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(state));tmp.chmod(0o600);tmp.replace(self.path)
    def state(self):
        with storage_lock(self.config):
            state=self.read()
            if not self.path.exists():self.save(state)
            return state
    def prune(self):
        now=time.time()
        for ident,result in list(self.results.items()):
            if result['expires']<=now:self.results.pop(ident,None)
        for rows in (self.invites,self.pending,self.challenges,self.sessions):
            for key,row in list(rows.items()):
                if row['expires']<=now:
                    if rows is self.sessions and hasattr(self,'auth'):self.auth.release_login('mobile:'+key)
                    rows.pop(key,None)
    def reset(self):
        with self.lock:
            if hasattr(self,'auth'):
                for token in self.sessions:self.auth.release_login('mobile:'+token)
            self.invites.clear();self.pending.clear();self.challenges.clear();self.sessions.clear();self.results.clear()
    def has_clients(self):
        with self.lock:
            self.prune();return any(time.time()-s['seen']<60 for s in self.sessions.values())
    def snapshot(self,user):
        with self.lock:
            self.prune();state=self.state();devices=[]
            for ident,row in state['devices'].items():
                if row['user_id']!=user:continue
                live=[s for s in self.sessions.values() if s['device_id']==ident]
                devices.append({'id':ident,'name':row['name'],'fingerprint':fingerprint(row['public_key']),'paired_utc':row['paired_utc'],'revoked':row['revoked'],'connected':any(time.time()-s['seen']<60 for s in live),'last_seen_utc':utc(max(s['seen'] for s in live)) if live else None,'scope':'relay-and-account-read','verification':self.results.get(ident)})
            pending=[{'id':key,'name':r['name'],'fingerprint':fingerprint(r['public_key']),'comparison_code':r['comparison_code']} for key,r in self.pending.items() if r['user_id']==user]
            return {'server_id':state['server_id'],'transport':'ssh-loopback','host_fingerprint':fingerprint(self.ssh_host_public_key) if self.ssh_host_public_key else None,'enabled':bool(self.mobile_port and self.ssh_host_public_key),'devices':devices,'pending':pending,'protocol':PROTOCOL,'version':1}
    def invite(self,user,connection):
        with self.lock:
            self.prune()
            if not self.mobile_port or not self.ssh_host_public_key:raise ValueError('Enable the loopback mobile listener and install OpenSSH server before pairing a phone.')
            connection=ssh_connection(connection)
            for key,row in list(self.invites.items()):
                if row['user_id']==user:self.invites.pop(key)
            if len(self.invites)>=32:raise ValueError('Finish an existing pairing first.')
            ident=secrets.token_hex(16);secret=secrets.token_urlsafe(32);expires=time.time()+120
            self.invites[ident]={'user_id':user,'secret_hash':hashlib.sha256(secret.encode()).hexdigest(),'expires':expires}
            payload={'protocol':PROTOCOL,'version':1,'kind':'pair','server_id':self.state()['server_id'],'transport':'ssh-loopback','ssh':dict(connection,host_public_key=self.ssh_host_public_key,host_fingerprint=fingerprint(self.ssh_host_public_key),forward_host='127.0.0.1',forward_port=self.mobile_port),'invitation_id':ident,'secret':secret,'expires_utc':utc(expires)}
            return {'payload':payload,'qr_svg':qr_svg(payload),'expires_utc':utc(expires)}
    def join(self,data):
        with self.lock:
            self.prune();ident=data.get('invitation_id');invite=self.invites.get(ident)
            if not invite or not secrets.compare_digest(invite['secret_hash'],hashlib.sha256(str(data.get('secret','')).encode()).hexdigest()):raise ValueError('Pairing invitation expired or is invalid.')
            public=data.get('public_key');fingerprint(public);name=label(data.get('name'))
            expected={'protocol':PROTOCOL,'version':1,'purpose':'pair','server_id':self.state()['server_id'],'invitation_id':ident,'secret':data['secret'],'public_key':public,'name':name,'ssh_host_fingerprint':fingerprint(self.ssh_host_public_key)}
            if verify(self.config,data.get('proof'),public,PAIR_NAMESPACE)!=expected:raise ValueError('Pairing proof does not match this invitation.')
            self.invites.pop(ident);key=digest(public);code=str(int(digest(expected)[:12],16)%1000000).zfill(6)
            self.pending[key]={'user_id':invite['user_id'],'name':name,'public_key':public,'comparison_code':code,'expires':time.time()+120}
            return {'device_id':key,'comparison_code':code,'state':'awaiting-server-confirmation'}
    def approve(self,user,ident,code):
        with self.lock:
            self.prune();row=self.pending.get(ident)
            if not row or row['user_id']!=user or not secrets.compare_digest(row['comparison_code'],str(code)):raise ValueError('Pairing expired or the comparison code does not match.')
            with storage_lock(self.config):
                state=self.read()
                if len(state['devices'])>=256 and ident not in state['devices']:raise ValueError('Revoke an unused device before pairing another.')
                state['devices'][ident]={'user_id':user,'name':row['name'],'public_key':row['public_key'],'paired_utc':utc(),'revoked':False};self.save(state)
            self.pending.pop(ident);return {'paired':True}
    def revoke(self,user,ident):
        with self.lock,storage_lock(self.config):
            state=self.read();row=state['devices'].get(ident)
            if not row or row['user_id']!=user:raise ValueError('Unknown mobile device.')
            row['revoked']=True;self.save(state)
            relay=getattr(self.hub,'relay',None)
            if relay is not None:
                with relay.lock:
                    endpoint=__import__('secure_relay').endpoint_id('mobile',row['public_key']);relay.invalidate(endpoint);relay.endpoints.pop(endpoint,None)
            for token,row in self.sessions.items():
                if row['device_id']==ident and hasattr(self,'auth'):self.auth.release_login('mobile:'+token)
            self.sessions={k:v for k,v in self.sessions.items() if v['device_id']!=ident};self.challenges={k:v for k,v in self.challenges.items() if v['device_id']!=ident}
            return {'revoked':True}
    def challenge(self,ident):
        with self.lock:
            self.prune();state=self.state();device=state['devices'].get(ident)
            if not device or device['revoked']:raise ValueError('Pair this mobile device before connecting.')
            self.challenges={k:v for k,v in self.challenges.items() if v['device_id']!=ident}
            if len(self.challenges)>=256:raise ValueError('Too many pending connections.')
            nonce=secrets.token_hex(32);self.challenges[nonce]={'device_id':ident,'expires':time.time()+45}
            return {'protocol':PROTOCOL,'version':1,'purpose':'connect','server_id':state['server_id'],'device_id':ident,'challenge':nonce}
    def connect(self,proof):
        with self.lock:
            self.prune();m=proof.get('message',{}) if isinstance(proof,dict) else {};pending=self.challenges.get(m.get('challenge')) if isinstance(m,dict) else None;state=self.state();device=state['devices'].get(m.get('device_id')) if isinstance(m,dict) else None
            if not pending or not device or device['revoked'] or pending['device_id']!=m.get('device_id'):raise ValueError('Connection challenge expired or is invalid.')
            expected={'protocol':PROTOCOL,'version':1,'purpose':'connect','server_id':state['server_id'],'device_id':m['device_id'],'challenge':m['challenge']}
            if verify(self.config,proof,device['public_key'],CONNECT_NAMESPACE)!=expected:raise ValueError('Invalid mobile connection proof.')
            for old,row in self.sessions.items():
                if row['device_id']==m['device_id'] and hasattr(self,'auth'):self.auth.release_login('mobile:'+old)
            self.challenges.pop(m['challenge']);token=secrets.token_urlsafe(32);self.sessions={k:v for k,v in self.sessions.items() if v['device_id']!=m['device_id']}
            self.sessions[token]={'device_id':m['device_id'],'user_id':device['user_id'],'seen':time.time(),'expires':time.time()+900,'challenge':secrets.token_hex(32)}
            return {'token':token,'expires_utc':utc(time.time()+900),'scope':'relay-and-account-read'}
    def client(self,token):
        self.prune();session=self.sessions.get(token)
        if not session:raise ValueError('Mobile session expired. Connect again.')
        device=self.state()['devices'].get(session['device_id'])
        from preferences import FamilyStore
        if not device or device['revoked'] or device['user_id'] not in {u['id'] for u in FamilyStore(self.config).snapshot()['users']}:raise ValueError('Mobile access was revoked.')
        session['seen']=time.time()
        if hasattr(self,'auth'):
            if session.get('account_authenticated_until',0)>time.time():self.auth.touch_login('mobile:'+token,min(session['expires'],session['account_authenticated_until'])-time.time())
            else:self.auth.release_login('mobile:'+token)
        return session,device
    def authenticate(self,token,action,data):
        with self.lock:
            session,device=self.client(token);uid=session['user_id'];scope='mobile:'+token
            if action=='logout':
                if data:raise ValueError('Unexpected logout fields.')
                self.auth.release_login(scope);session.pop('account_authenticated_until',None)
                return {'authenticated':False}
            if action=='info':
                if data:raise ValueError('Unexpected mobile authentication fields.')
                from preferences import FamilyStore
                user=FamilyStore(self.config).user(uid)
                return dict(self.auth.metadata(uid),user={k:user[k] for k in ('id','name','colour','gender') if k in user})
            if action=='start':
                if data.get('user_id')!=uid:raise ValueError('This phone is paired to a different user.')
                # Initial enrollment belongs to the existing SSH browser workflow.
                if data.get('mode')!='login':raise ValueError('Create this account password in the browser first.')
                return self.auth.start(scope,data)
            if action=='finish':
                if self.auth.finish(scope,data)!=uid:raise ValueError('Account identity changed.')
                session['account_authenticated_until']=time.time()+900
                return {'authenticated':True,'user_id':uid,'expires_utc':utc(session['account_authenticated_until'])}
            raise ValueError('Unknown mobile authentication action.')
    def data(self,token,section):
        with self.lock:
            session,_=self.client(token)
            if session.get('account_authenticated_until',0)<=time.time():raise ValueError('Log in with your account password before requesting account data.')
            from mobile_data import snapshot
            return snapshot(self.config,session['user_id'],section)
    def claims(self,token):
        with self.lock:
            session,_=self.client(token);state=self.hub.read();setups=self.hub.wallet_builder.read();identities=setups.get('identities',{});claims=[]
            from transaction_workflows import WorkflowStore
            jobs=WorkflowStore(self.config)._read()['jobs']
            for key,row in state['requests'].items():
                if row.get('state')!='pending' or not row.get('proposal') or row.get('superseded_attempt') or row.get('superseded_container') or row.get('cancel_requested'):continue
                # Shared wallet operations are still scoped to their initiating
                # user. No other user's transaction is exposed to a phone.
                owner=row.get('user_id')
                if not owner and row.get('lifecycle_restore'):owner=state['requests'].get(row['lifecycle_restore'],{}).get('user_id')
                if not owner and row.get('job_id'):owner=jobs.get(row['job_id'],{}).get('creator_id')
                if owner!=session['user_id'] and not (owner is None and row['kind']=='wallet_transfer'):continue
                proposal=row['proposal'];node=row['node_id'];identity=identities.get(node,{})
                public=identity.get('public_key') or identity.get('message',{}).get('public_key')
                claims.append({'id':key,'kind':row['kind'],'request_digest':digest(proposal),'node_id':node,'agent_public_key':public,'agent_fingerprint':fingerprint(public) if public else None,'peer':proposal.get('peer'),'node_ipv6':proposal.get('node_ipv6'),'identity_source':'server-claim; compare directly with Agent QR','created_utc':row['created_utc']})
            from mobile_agent_records import records
            verified_facts=records(self.hub)
            for node,identity in identities.items():
                public=identity.get('public_key')
                if not public:continue
                route=state['nodes'].get(node,{}).get('ipv6');facts={'public_key':public,'node_id':node,'ipv6':route};ident=digest({'purpose':'identity','facts':facts})
                claims.append({'id':ident,'kind':'agent_identity','request_digest':digest(facts),'node_id':node,'agent_public_key':public,'agent_fingerprint':fingerprint(public),'node_ipv6':route,'identity_source':'server-claim; scan the actual Agent identity','signed_agent_facts':verified_facts.get(node),'created_utc':None})
            for key,setup in setups.get('sessions',{}).items():
                if setup.get('creator_id')!=session['user_id'] or setup.get('state') in ('cancelled','ready','complete'):continue
                for node in set(setup['routes'].values()):
                    identity=identities.get(node,{});public=identity.get('public_key')
                    claims.append({'id':digest({'setup':key,'node_id':node}),'kind':'wallet_setup','request_digest':digest(setup['proposal']),'node_id':node,'agent_public_key':public,'agent_fingerprint':fingerprint(public) if public else None,'created_utc':setup['created_utc'],'identity_source':'server-claim; compare directly with Agent QR'})
            if len(claims)>256:raise ValueError('Too many pending verification claims. Finish existing operations first.')
            claims.sort(key=lambda c:c['id'])
            previous=self.results.get(session['device_id'])
            if previous and previous['claims_digest']!=comparison_digest(claims):self.results.pop(session['device_id'],None)
            return {'protocol':PROTOCOL,'version':1,'server_id':self.state()['server_id'],'challenge':session['challenge'],'claims':claims,'claims_digest':comparison_digest(claims),'approval_authority':False}
    def result(self,token,proof):
        with self.lock:
            session,device=self.client(token);current=self.claims(token);message=proof.get('message',{}) if isinstance(proof,dict) else {};expected={'protocol','version','purpose','server_id','device_id','challenge','claims_digest','matches','mismatches'}
            if not isinstance(message,dict) or set(message)!=expected or message.get('protocol')!=PROTOCOL or type(message.get('version')) is not int or message['version']!=1 or message.get('purpose')!='comparison' or message.get('server_id')!=current['server_id'] or message.get('device_id')!=session['device_id'] or message.get('challenge')!=session['challenge'] or message.get('claims_digest')!=current['claims_digest']:raise ValueError('Verification result is stale or belongs to a different operation.')
            ids={c['id'] for c in current['claims']};matches=message['matches'];mismatches=message['mismatches']
            if not isinstance(matches,list) or not isinstance(mismatches,list) or len(matches)+len(mismatches)>256 or any(not isinstance(i,str) for i in matches+mismatches) or set(matches)&set(mismatches) or len(set(matches+mismatches))!=len(matches+mismatches) or not set(matches+mismatches)<=ids:raise ValueError('Invalid comparison results.')
            verify(self.config,proof,device['public_key'],RESULT_NAMESPACE)
            self.results[session['device_id']]={'created_utc':utc(),'matches':len(matches),'mismatches':len(mismatches),'remaining':len(ids-set(matches+mismatches)),'claims_digest':message['claims_digest'],'advisory_only':True,'expires':time.time()+120}
            session['challenge']=secrets.token_hex(32)
            return {'recorded':True,'approval_authority':False}
