"""Reserved implementation accounts are not independent sync assets.

Classifies display/discovery only. Never deletes a wallet or grants authority.
Signing inventories must retain policy/key accounts; only their independent
advisory hints are excluded. Retained history staging is not a live archive.
"""
import re
HISTORY=re.compile(r'\.wallaby-history-[0-9a-f]{24}',re.IGNORECASE)
POLICY=re.compile(r'Wallaby policy [0-9a-f]{20}(?:_watch)?',re.IGNORECASE)
KEY=re.compile(r'Wallaby key [0-9a-f]{12} [0-9a-f]{8}(?:_watch)?',re.IGNORECASE)

def history_staging(name):return isinstance(name,str) and bool(HISTORY.fullmatch(name))
def internal(name):return isinstance(name,str) and any(p.fullmatch(name) for p in (HISTORY,POLICY,KEY))
def advisory_wallet(w):
    # Expanded historical children retain their actual Core route in `name`;
    # filter that route BEFORE grouping labels or deduplicating descriptors.
    return not internal(w.get('name')) and not internal(w.get('raw',{}).get('wallet_name'))
