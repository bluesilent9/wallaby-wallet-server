"""Exact public receive reservation and bounded review samples; never reserves."""
import re
from vendor.embit.descriptor import Descriptor
from vendor.embit.networks import NETWORKS


def receiving_address(destination):
    index=destination.get('index')
    if type(index) is not int or not 0<=index<=999:raise ValueError('The vault receiving index must be between 0 and 999.')
    address=Descriptor.from_string(destination['descriptors'][0]['desc']).derive(index).address(NETWORKS['main'])
    if address!=destination.get('address'):raise ValueError('The saved vault address does not match its policy and receiving index. No request was sent.')
    return {'index':index,'address':address}


def samples(rows,index):
    if type(index) is not int or not 0<=index<=999:raise ValueError('Invalid vault comparison index.')
    if len(rows)!=2:raise ValueError('Both receive and change policies are required for comparison.')
    result=[]
    for branch,row in zip(('Receiving','Change'),rows):
        descriptor=Descriptor.from_string(row['desc'])
        for i in range(index,min(index+3,1000)):
            result.append({'branch':branch,'index':i,'address':descriptor.derive(i).address(NETWORKS['main'])})
    return result


def supported(hub,node):
    """New index-bound requests are never downgraded for an older Agent."""
    connections=[c for c in hub.registry.connections.values() if c['node_id']==node]
    if len(connections)!=1:return False
    match=re.fullmatch(r'2\.0\.0~dev([0-9]+)',connections[0].get('agent_version',''))
    return bool(match and int(match[1])>=60)
