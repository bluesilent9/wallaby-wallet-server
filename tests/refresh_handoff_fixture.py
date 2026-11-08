"""Simulate completed local approvals for older name/address unit tests only.

Actual signed receipt/result validation is exercised independently in test_build80.
"""
from vault_refresh import finish as begin,complete

def finish(hub,user,height):
    phase=begin(hub,user,height)
    with hub.edit() as state:
        for row in state['requests'].values():
            if row.get('destination_id')==phase['destination']:row.update(state='complete',persistent_monitor=True)
    return complete(hub,user)
