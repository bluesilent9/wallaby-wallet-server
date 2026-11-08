"""OPAQUE registration/login. Only blinded protocol messages reach Python.

The bundled MIT OPAQUE implementation performs all cryptography. Ephemeral
login states are bound to the browser/device workspace and never exported.
"""
from contextlib import contextmanager
import json,os,re,secrets,shutil,subprocess,threading,time,uuid
from pathlib import Path
from storage import data_directory
from preferences import FamilyStore

SUITE='opaque-serenity-1.1.0-argon2id-m65536-t3-p1'
LIMIT=128
OPAQUE_SLOTS=threading.BoundedSemaphore(2)

def opaque(action,params=None):
    binary=os.environ.get('WALLABY_NODE') or shutil.which('node') or shutil.which('nodejs')
    if not binary:raise ValueError('Password login requires Node.js. Install the updated Wallet Server package.')
    if not OPAQUE_SLOTS.acquire(blocking=False):raise ValueError('Password service is busy. Please try again shortly.')
    try:
        p=subprocess.run([binary,str(Path(__file__).parent/'vendor/opaque/worker.cjs')],input=json.dumps({'action':action,'params':params}),text=True,capture_output=True,timeout=15,check=True)
        if len(p.stdout)>32768:raise ValueError()
        return json.loads(p.stdout)
    except (subprocess.SubprocessError,ValueError,OSError):raise ValueError('Password authentication failed. Please try again.') from None
    finally:OPAQUE_SLOTS.release()

def wire(value):
    if not isinstance(value,str) or not 8<=len(value)<=4096 or not re.fullmatch(r'[A-Za-z0-9_+/=-]+',value):raise ValueError('Invalid OPAQUE protocol message.')
    return value

def validate(state,users=None):
    if not isinstance(state,dict) or set(state)!={'version','server_id','setup','users'} or type(state['version']) is not int or state['version']!=1 or not re.fullmatch('[0-9a-f]{64}',str(state['server_id'])) or not isinstance(state['users'],dict) or len(state['users'])>1024:raise ValueError('Invalid saved password authentication state.')
    wire(state['setup'])
    for uid,row in state['users'].items():
        if users is not None and uid not in users:raise ValueError('Saved password belongs to an unknown user.')
        if not re.fullmatch('[0-9a-f]{32}',uid) or not isinstance(row,dict) or set(row)!={'record','suite'} or row['suite']!=SUITE:raise ValueError('Invalid saved OPAQUE account.')
        wire(row['record'])
    return state

@contextmanager
def auth_lock(path):
    import fcntl
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix('.lock').open('a+b') as handle:
        os.chmod(handle.name,0o600);fcntl.flock(handle.fileno(),fcntl.LOCK_EX)
        try:yield
        finally:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)

class PasswordAuth:
    def __init__(self,config):
        self.config=Path(config);self.path=data_directory(config)/'password-auth.json';self.lock=threading.RLock();self.pending={};self.rates={};self.logins={}
    def reset(self):
        with self.lock:self.pending.clear();self.rates.clear();self.logins.clear()
    def release_login(self,scope):
        with self.lock:self.logins.pop(scope,None)
    def touch_login(self,scope,seconds=86400):
        with self.lock:
            row=self.logins.get(scope);now=time.monotonic()
            if not row or row['expires']<=now:
                self.logins.pop(scope,None);return False
            row['expires']=now+max(0,min(seconds,86400));return True
    def rotate_login(self,old,new):
        with self.lock:
            row=self.logins.pop(old,None)
            if row:self.logins[new]=row
    def admit_login(self,scope,uid):
        # Called only after OPAQUE verification, under the same reentrant lock.
        with self.lock:
            now=time.monotonic();self.logins={k:v for k,v in self.logins.items() if v['expires']>now}
            users={v['uid'] for v in self.logins.values()}
            if uid not in users and len(users)>=10:raise ValueError('Ten users are already logged in. Log out an unused account and try again.')
            if scope not in self.logins and len(self.logins)>=64:raise ValueError('All account sessions are in use. Log out an unused device and try again.')
            self.logins[scope]={'uid':uid,'expires':now+(900 if scope.startswith('mobile:') else 86400)}
    def read(self):
        return validate(json.loads(self.path.read_text())) if self.path.exists() else None
    def save(self,data):
        validate(data);self.path.parent.mkdir(parents=True,exist_ok=True);p=self.path.with_name(uuid.uuid4().hex+'.tmp')
        try:p.write_text(json.dumps(data));p.chmod(0o600);os.replace(p,self.path)
        finally:p.unlink(missing_ok=True)
    def state(self):
        with auth_lock(self.path):
            data=self.read()
            if data is None:data={'version':1,'server_id':secrets.token_hex(32),'setup':opaque('setup'),'users':{}};self.save(data)
            return data
    def metadata(self,uid):
        if not FamilyStore(self.config).user(uid):raise ValueError('Unknown user.')
        with self.lock:
            state=self.read()
            return {'password_policy':{'min_length':8,'max_length':1024,'required_digit':True,'required_special':True,'digit_definition':'ASCII 0-9','special_definition':'Unicode punctuation or symbol; whitespace excluded'},'registration_required':not state or uid not in state['users'],'suite':SUITE,'key_stretching':{'argon2id-custom':{'iterations':3,'memory':65536,'parallelism':1}},'client_identity':uid,'server_identity':state['server_id'] if state else None}
    def prune(self):
        now=time.monotonic();self.pending={k:v for k,v in self.pending.items() if v['expires']>now};self.rates={k:v for k,v in self.rates.items() if v[1]>now}
    def throttle(self,uid,scope):
        self.prune()
        for key in (('user',uid),('workspace',scope)):
            n,expiry=self.rates.get(key,(0,time.monotonic()+60))
            if n>=10:raise ValueError('Too many password attempts. Wait one minute before trying again.')
            self.rates[key]=(n+1,expiry)
        if len(self.pending)>=LIMIT:raise ValueError('Too many pending logins. Try again shortly.')
    def start(self,scope,data):
        if not isinstance(data,dict) or set(data)!={'user_id','mode','request'} or data['mode'] not in ('register','login'):raise ValueError('Send an OPAQUE login or registration request.')
        uid=data['user_id'];wire(data['request'])
        if not FamilyStore(self.config).user(uid):raise ValueError('Unknown user.')
        with self.lock:
            self.throttle(uid,scope);state=self.state();record=state['users'].get(uid);register=data['mode']=='register'
            if register and record:raise ValueError('This user already has a password. Log in instead.')
            if not register and not record:raise ValueError('Create a password for this existing profile first. Saved wallets and builders are retained.')
            params={'serverSetup':state['setup'],'userIdentifier':uid}
            if register:result=opaque('register',dict(params,registrationRequest=data['request']))
            else:result=opaque('start',dict(params,registrationRecord=record['record'],startLoginRequest=data['request'],identifiers={'client':uid,'server':state['server_id']}))
            nonce=secrets.token_urlsafe(32);self.pending[nonce]={'scope':scope,'uid':uid,'mode':data['mode'],'expires':time.monotonic()+120,'server_id':state['server_id'],'state':result.get('serverLoginState'),'record':record['record'] if record else None}
            return {'id':nonce,'response':result.get('registrationResponse') or result['loginResponse'],'server_identity':state['server_id'],'client_identity':uid,'suite':SUITE}
    def registration(self,scope,data):
        if not isinstance(data,dict) or set(data)!={'id','record','request'}:raise ValueError('Invalid OPAQUE registration completion.')
        wire(data['record']);wire(data['request'])
        with self.lock:
            self.prune();pending=self.pending.pop(data['id'],None)
            if not pending or pending['scope']!=scope or pending['mode']!='register':raise ValueError('Password setup expired. Start again.')
            state=self.state();uid=pending['uid']
            if uid in state['users']:raise ValueError('Password setup already completed. Log in instead.')
            result=opaque('start',{'serverSetup':state['setup'],'userIdentifier':uid,'registrationRecord':data['record'],'startLoginRequest':data['request'],'identifiers':{'client':uid,'server':state['server_id']}})
            nonce=secrets.token_urlsafe(32);self.pending[nonce]=dict(pending,mode='enroll',record=data['record'],state=result['serverLoginState'],expires=time.monotonic()+120)
            return {'id':nonce,'response':result['loginResponse'],'client_identity':uid,'server_identity':state['server_id']}
    def finish(self,scope,data):
        if not isinstance(data,dict) or set(data)!={'id','request'}:raise ValueError('Invalid OPAQUE login completion.')
        wire(data['request'])
        with self.lock,auth_lock(self.path):
            self.prune();pending=self.pending.pop(data['id'],None)
            if not pending or pending['scope']!=scope or pending['mode'] not in ('login','enroll'):raise ValueError('Login expired. Start again.')
            uid=pending['uid'];state=self.read()
            if not state or state['server_id']!=pending['server_id'] or not FamilyStore(self.config).user(uid):raise ValueError('Profile changed. Start login again.')
            if pending['mode']=='login' and state['users'].get(uid,{}).get('record')!=pending['record']:raise ValueError('Password changed. Log in again.')
            opaque('finish',{'serverLoginState':pending['state'],'finishLoginRequest':data['request'],'identifiers':{'client':uid,'server':state['server_id']}})
            self.admit_login(scope,uid)
            if pending['mode']=='enroll':
                if uid in state['users']:raise ValueError('This account already has a password. Log in instead.')
                state['users'][uid]={'record':pending['record'],'suite':SUITE};self.save(state)
            return uid

    def prune_users(self,users):
        with self.lock,auth_lock(self.path):
            self.logins={k:v for k,v in self.logins.items() if v['uid'] in users}
            state=self.read()
            if state and set(state['users'])-set(users):
                state['users']={k:v for k,v in state['users'].items() if k in users};self.save(state)
