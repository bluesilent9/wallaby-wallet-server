"""Explicit fixtures for persisted pre-relay work and authenticated new peers."""
import base64,secrets,time,types
from pathlib import Path
import subprocess
from secure_relay import PROTOCOL,NAMESPACE,CIPHER
from setup_signatures import canonical

def legacy_transfers(test):
    # These older regression suites exercise already queued v2 attempts. Seed
    # their frozen pre-upgrade invitations; never enable a production fallback.
    hub=test.hub
    def proposal(state,row):
        peer=row['peer_id'];connection=next((c for c in hub.registry.connections.values() if c['node_id']==peer),{})
        p={'kind':'wallet_transfer','direction':row['direction'],'transfer_id':row['transfer_id'],'peer':{'node_id':peer,'hostname':connection.get('hostname',''),'ipv6':state['nodes'][peer]['ipv6']},'public_wallet':row['public_wallet'],'source_has_private_keys':row['source_has_private_keys'],'earliest_timestamp':row['earliest_timestamp'],'requires_blockchain_redownload':row['requires_blockchain_redownload'],'preview_challenge':row['challenge'],'node_ipv6':state['nodes'][row['node_id']]['ipv6'],'transfer_version':2}
        if row.get('lifecycle_restore'):
            from wallet_preview import restoration_binding
            p['restoration']=restoration_binding(row['public_wallet'])
        return p
    hub.transfer_proposal=proposal
    original=hub.transfers.schedule_queues
    def schedule(state):
        for pair in hub.transfers.pairs(state).values():
            if len(pair)!=2 or any(row.get('proposal') for row in pair) or any(not state['nodes'].get(row['node_id'],{}).get('ipv6') for row in pair):continue
            challenge=secrets.token_hex(32)
            for row in pair:
                row.update(queue_v2=True,challenge=challenge,base_sent=0,active_pair=False)
                row['proposal']=proposal(state,row)
        return original(state)
    hub.transfers.schedule_queues=schedule

def signed_mesh(test):
    hub=test.hub;relay=hub.relay;peers=[]
    for node in hub.caps:hub.caps[node].update({'wallet_relay_v1','wallet_policy_refresh_relay_v1'})
    def sign(key,public,message):
        file=Path(test.tmp.name)/'relay-message';file.write_bytes(canonical(message));file.with_suffix('.sig').unlink(missing_ok=True);subprocess.run(['ssh-keygen','-q','-Y','sign','-f',str(key),'-n',NAMESPACE,str(file)],check=True,capture_output=True);return {'message':message,'public_key':public,'signature':base64.b64encode(file.with_suffix('.sig').read_bytes()).decode()}
    test.keys=getattr(test,'keys',{})
    for i,n in enumerate([{'node_id':c['node_id'],'connection_token':token} for token,c in test.hub.registry.connections.items()]):
        key=test.keys.get(n['node_id'])
        if key is None:
            key=Path(test.tmp.name)/('relay-key-'+str(i));subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(key)],check=True);test.keys[n['node_id']]=key
        public=' '.join(key.with_suffix('.pub').read_text().split()[:2]);p=relay.principal('agent',public,n['node_id'],n['connection_token']);challenge=relay.dispatch(p,{'action':'challenge'})
        m={'protocol':PROTOCOL,'version':1,'kind':'register','endpoint_id':p['id'],'role':'agent','challenge':challenge['challenge'],'noise_public_key':base64.b64encode(bytes([i+1])*32).decode(),'cipher_suite':CIPHER};relay.dispatch(p,{'action':'register','proof':sign(key,public,m)});peers.append((p,key,public))
    for i,(p,key,public) in enumerate(peers):
        for j in range(len(peers)):
            if j==i:continue
            peer=peers[j][0];challenge=relay.dispatch(p,{'action':'challenge'});m={'protocol':PROTOCOL,'version':1,'kind':'channel','endpoint_id':p['id'],'role':'agent','challenge':challenge['challenge'],'peer_id':peer['id'],'peer_role':'agent','peer_noise_public_key':relay.endpoints[peer['id']]['noise_public_key'],'channel_id':'a'*64,'handshake_hash':'b'*64,'state':'ready','paired_by_qr':True};relay.dispatch(p,{'action':'channel','proof':sign(key,public,m)})

def persisted_refresh_v1(test):
    """Seed a pre-upgrade, unsigned v1 snapshot for old-Agent result tests only."""
    from builder_destinations import Destinations
    destination=test.d['id'];store=Destinations(test.hub.config);data=store.read();data['destinations'][destination].pop('relay_peer_transport',None);store.write(data)
    with test.hub.edit() as state:
        for row in state['requests'].values():
            if row.get('destination_id')==destination:row['proposal']['version']=1;row['proposal'].pop('peer_transport',None)
    test.d=store.get(destination);test.rows={r['node_id']:r for r in test.hub.read()['requests'].values() if r.get('destination_id')==destination}
