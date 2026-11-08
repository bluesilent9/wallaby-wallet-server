"""Public route bindings, distinct from the secret peer-to-peer channel keys."""
from secure_relay import PROTOCOL,CIPHER,endpoint_id,hexid,binary
from setup_signatures import fingerprint

def validate_transport(t):
    fields={'protocol','version','cipher_suite','sender_endpoint','receiver_endpoint','sender_identity','receiver_identity','sender_noise_key','receiver_noise_key'}
    if not isinstance(t,dict) or set(t)!=fields or t['protocol']!=PROTOCOL or type(t['version']) is not int or t['version']!=1 or t['cipher_suite']!=CIPHER:raise ValueError('Invalid relay transport binding.')
    for side in ('sender','receiver'):
        fingerprint(t[side+'_identity']);binary(t[side+'_noise_key'],32,32)
        if t[side+'_endpoint']!=endpoint_id('agent',t[side+'_identity']):raise ValueError('Relay peer must be an authenticated Agent.')
    if t['sender_endpoint']==t['receiver_endpoint']:raise ValueError('Distinct relay peers required.')
    return t

def matches_preview(v,p):
    if p.get('transfer_version')==3:
        validate_transport(p['transport'])
        return v.get('version')==3 and v.get('transfer_id')==p['transfer_id'] and v.get('challenge')==p['preview_challenge'] and v.get('transport')==p['transport'] and v.get('sender_ipv6') is None and v.get('receiver_ipv6') is None
    return v.get('version')==2 and (v.get('transfer_id'),v.get('challenge'),v.get('sender_ipv6'),v.get('receiver_ipv6'))==(p['transfer_id'],p['preview_challenge'],p['node_ipv6'],p['peer']['ipv6'])

def validate_requirements(t):
    fields={'protocol','version','cipher_suite','required_agent_keys'}
    if not isinstance(t,dict) or set(t)!=fields or t['protocol']!=PROTOCOL or type(t['version']) is not int or t['version']!=1 or t['cipher_suite']!=CIPHER:raise ValueError('Invalid peer-channel requirements.')
    keys=t['required_agent_keys']
    if not isinstance(keys,list) or not 1<=len(keys)<=15 or any(not isinstance(k,str) for k in keys) or keys!=sorted(set(keys)):raise ValueError('Invalid required Agent set.')
    for key in keys:fingerprint(key)
    return t
