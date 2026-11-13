"""Accepted statement inputs survive an unrelated failed wallet-history run.

Coverage describes PDFs we hold, never verified ownership/balances or tax results.
"""
from pathlib import Path
from datetime import date
import hashlib,json,os,re,shutil,tempfile,uuid
from storage import data_directory,storage_lock
from family_inputs import account_slot,smsf_slot
from ownership_workspace import generation_access

class StatementRecords:
    def __init__(self,config):
        self.config=Path(config);self.root=data_directory(config)/'statement-inputs';self.path=data_directory(config)/'statement-inputs.json'
    def read(self):
        data=json.loads(self.path.read_text()) if self.path.exists() else {'version':1,'revision':0,'accounts':{}}
        if data.get('version')!=1 or type(data.get('revision')) is not int or not isinstance(data.get('accounts'),dict):raise ValueError('Invalid saved statement inputs.')
        for key,row in data['accounts'].items():
            if not re.fullmatch('[0-9a-f]{32}(:smsf)?',key) or not re.fullmatch('[0-9a-f]{32}',row.get('generation','')) or not isinstance(row.get('files'),dict):raise ValueError('Invalid saved statement account.')
            if row.get('statement_date') is not None:date.fromisoformat(row['statement_date'])
            for name,sha in row['files'].items():
                if not re.fullmatch(r'\d{4}-\d{4}-\d{2}-\d{2}-(AUD|BTC)\.pdf',name) or not re.fullmatch('[0-9a-f]{64}',str(sha)):raise ValueError('Invalid saved statement file.')
        return data
    def write(self,data):
        self.path.parent.mkdir(parents=True,exist_ok=True);temp=self.path.with_suffix('.tmp')
        try:
            temp.write_text(json.dumps(data,sort_keys=True));temp.chmod(0o600);os.replace(temp,self.path)
        finally:temp.unlink(missing_ok=True)
    def verify(self,row):
        folder=self.root/row['generation']
        for name,sha in row['files'].items():
            p=folder/name
            if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:raise ValueError('Saved Bitaroo PDFs are missing or changed. Upload the statements again.')
        return folder
    def accept(self,core,key,files,existing,target,zone,now=None):
        from bitaroo_upload import retain
        if not re.fullmatch('[0-9a-f]{32}(:smsf)?',key):raise ValueError('Invalid statement account.')
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        # Parsing is serial only for this account, outside the profile-wide lock.
        with generation_access(self.root,key.replace(':','-'),exclusive=True),tempfile.TemporaryDirectory(prefix='.statements-',dir=self.config.parent) as tmp:
            tmp=Path(tmp);base=tmp/'base';base.mkdir();previous=self.read()['accounts'].get(key)
            if previous:
                with storage_lock(self.config):shutil.copytree(self.verify(previous),base/'accepted')
            if existing and Path(existing).is_dir():shutil.copytree(existing,base/'browser')
            merged=tmp/'merged';result=retain(core,files,base,merged,zone,now)
            periods=set()
            for p in merged.iterdir():
                side,fy,start,end=core.inspect_bitaroo_statement(p);periods.add((start,end,side))
            ends=[end.isoformat() for start,end,side in periods if (start,end,'BTC' if side=='AUD' else 'AUD') in periods]
            generation=uuid.uuid4().hex;row={'generation':generation,'statement_date':max(ends,default=None),'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in merged.iterdir()}}
            with storage_lock(self.config):
                data=self.read();old=data['accounts'].get(key);dest=self.root/generation
                try:
                    shutil.copytree(merged,dest);dest.chmod(0o700)
                    for p in dest.iterdir():p.chmod(0o600)
                    data['accounts'][key]=row;data['revision']+=1;self.write(data)
                except BaseException:
                    shutil.rmtree(dest,ignore_errors=True);raise
                if old:shutil.rmtree(self.root/old['generation'],ignore_errors=True)
                self.copy_account(row,Path(target))
            return result
    def copy_account(self,row,target):
        source=self.verify(row);target.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.restore-statements-',dir=target.parent) as tmp:
            staged=Path(tmp)/'files';shutil.copytree(source,staged)
            if target.exists():shutil.rmtree(target)
            staged.rename(target)
    def overlay(self,uploads,input_dir,users):
        with storage_lock(self.config):
            data=self.read();valid={u['id'] for u in users}
            for key,row in data['accounts'].items():
                uid=key.removesuffix(':smsf')
                if uid not in valid:continue
                slot=smsf_slot(uid) if key.endswith(':smsf') else account_slot(uid)
                target=Path(input_dir)/slot;self.copy_account(row,target);uploads[slot]=target
        return uploads
    def dates(self):return {key:row['statement_date'] for key,row in self.read()['accounts'].items() if row.get('statement_date')}
    def discard(self,keys=None):
        with storage_lock(self.config):
            data=self.read()
            for key in list(data['accounts']):
                if keys is not None and key not in keys:continue
                row=data['accounts'].pop(key);shutil.rmtree(self.root/row['generation'],ignore_errors=True)
            data['revision']+=1;self.write(data)
