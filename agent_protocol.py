"""One supported Agent generation; wire API versions are independent of builds."""
import re
MINIMUM='2.0.0~dev56'

def supported(version):
    m=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:~dev(\d+))?',version or '') if isinstance(version,str) else None
    return bool(m and (*map(int,m.groups()[:3]),int(m[4]) if m[4] else 10**9)>=(2,0,0,56))

def require_current(version):
    if not supported(version):raise ValueError('Update Wallaby Agent to V2 Development Build 56 or later.')
