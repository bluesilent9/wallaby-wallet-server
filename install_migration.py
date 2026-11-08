"""Move stopped legacy installation directories without merging or rewriting data."""
import os
from pathlib import Path

def migrate(root=Path('/')):
    root=Path(root);plans=[]
    for parent in ('var/lib','var/cache'):
        old=root/parent/'wallaby-dashboard';new=root/parent/'wallaby-wallet-server'
        if old.is_symlink():
            if old.resolve()!=new.resolve():raise ValueError('The legacy data path points somewhere unexpected. No data was moved.')
            continue
        if not old.exists():continue
        if not old.is_dir():raise ValueError('The legacy data path is not a directory. No data was moved.')
        if new.exists() and (not new.is_dir() or any(new.iterdir())):raise ValueError('Both old and new server data directories contain data. Resolve this explicitly; they will not be merged or overwritten.')
        plans.append((old,new,new.exists()))
    moved=[]
    try:
        for old,new,empty in plans:
            if empty:new.rmdir()
            old.rename(new);moved.append((old,new,empty))
        for old,new,_ in moved:old.symlink_to(new.name,target_is_directory=True)
    except BaseException:
        for old,new,empty in reversed(moved):
            if old.is_symlink():old.unlink()
            if new.exists() and not old.exists():new.rename(old)
            if empty and not new.exists():new.mkdir()
        raise
    return [str(new) for _,new,_ in moved]

if __name__=='__main__':migrate()
