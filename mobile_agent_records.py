"""Opt-in public Agent facts for the next Agent QR implementation."""
import re,secrets,time
from setup_signatures import fingerprint,verify

CAPABILITY='wallet_mobile_verification_v1'
NAMESPACE='wallaby-wallet-verification-v1'
FIELDS={'protocol','version','kind','challenge','agent_public_key','agent_fingerprint','ssh_host_public_key','ssh_host_fingerprint','ipv6','hostname','generated_at','expires_at'}
def facts(envelope,expected):
    from agent_hub import ipv6
    if not isinstance(envelope,dict) or set(envelope)!={'message','public_key','signature'} or envelope['public_key']!=expected:raise ValueError('Agent verification identity differs from the connected Agent.')
    m=envelope['message']
    if not isinstance(m,dict) or set(m)!=FIELDS or m['protocol']!='wallaby-wallet-verification' or type(m['version']) is not int or m['version']!=1 or m['kind']!='agent_facts' or not isinstance(m['challenge'],str) or not re.fullmatch('[0-9a-f]{64}',m['challenge']):raise ValueError('Invalid public Agent verification record.')
    if m['agent_public_key']!=expected or m['agent_fingerprint']!=fingerprint(expected) or m['ssh_host_fingerprint']!=fingerprint(m['ssh_host_public_key']):raise ValueError('Agent verification key fingerprint does not match its full key.')
    ipv6(m['ipv6'])
    if not isinstance(m['hostname'],str) or not 1<=len(m['hostname'])<=253 or any(ord(c)<32 for c in m['hostname']):raise ValueError('Invalid Agent hostname.')
    now=time.time()
    if type(m['generated_at']) is not int or type(m['expires_at']) is not int or not now-120<=m['generated_at']<=now+30 or not now<m['expires_at']<=m['generated_at']+120:raise ValueError('Agent verification record expired.')
    return m
def accept(hub,node,envelope):
    expected=hub.wallet_builder.read().get('identities',{}).get(node,{}).get('public_key')
    permission=hub.permissions.current(node)
    if not expected and permission:expected=permission.get('identity')
    if not expected:raise ValueError('Discover this Agent identity before mobile verification.')
    m=facts(envelope,expected);verify(hub.config,envelope,expected,NAMESPACE)
    challenges=getattr(hub,'mobile_verification_challenges',{});challenge=challenges.get(node)
    # Authenticate but do not install a late reply for an expired/replaced check.
    if not challenge or challenge['challenge']!=m['challenge'] or challenge['expires']<time.time():return False
    records=getattr(hub,'mobile_verification_records',{});records[node]=envelope;hub.mobile_verification_records=records
    return True
def records(hub):
    now=time.time()
    return {n:e for n,e in getattr(hub,'mobile_verification_records',{}).items() if e['message']['expires_at']>now}
def proposals(hub,node,caps):
    if CAPABILITY not in caps or not getattr(hub,'mobile_verification_active',lambda:False)():return []
    now=time.time();available=records(hub)
    if node in available and available[node]['message']['expires_at']>now+30:return []
    challenges=getattr(hub,'mobile_verification_challenges',{});row=challenges.get(node)
    if not row or row['expires']<=now:row={'challenge':secrets.token_hex(32),'expires':now+90};challenges[node]=row
    hub.mobile_verification_challenges=challenges
    return [{'kind':'wallet_mobile_verification','version':1,'challenge':row['challenge'],'peer_facts':[{'node_id':n,'envelope':e} for n,e in sorted(available.items()) if n!=node][:32]}]
