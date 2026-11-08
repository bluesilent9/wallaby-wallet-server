"""Validate a complete browser selection before atomically retaining public statements."""
from datetime import datetime, timezone, date
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo
import hashlib, shutil, tempfile
from email.parser import BytesParser
from email.policy import default

def multipart(content_type,body):
    if not content_type.startswith('multipart/form-data;'):raise ValueError('Select Bitaroo PDFs together as one upload package.')
    message=BytesParser(policy=default).parsebytes(b'Content-Type: '+content_type.encode('ascii')+b'\r\nMIME-Version: 1.0\r\n\r\n'+body)
    if not message.is_multipart():raise ValueError('Invalid PDF upload package.')
    files=[]
    for part in message.iter_parts():
        if part.get_content_disposition()!='form-data' or part.get_param('name',header='content-disposition')!='files':raise ValueError('Invalid PDF upload field.')
        name=part.get_filename() or '';path=PurePosixPath(name)
        if path.is_absolute() or not path.parts or any(p in ('.','..') for p in path.parts) or '\\' in name or '\x00' in name or path.suffix.lower()!='.pdf':raise ValueError('Select PDF statement files only.')
        files.append((name,part.get_payload(decode=True)))
        if len(files)>1000:raise ValueError('Upload at most 1,000 PDFs together.')
    if not files:raise ValueError('No Bitaroo PDFs were provided.')
    return files

def retain(core,files,existing,target,zone,now=None):
    """An incomplete current pair never replaces saved inputs, even when a stale mate exists."""
    local=(now or datetime.now(timezone.utc)).astimezone(ZoneInfo(zone));fy=local.year-(local.month<7)
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='statement-upload-',dir=target.parent) as temporary:
        stage=Path(temporary);records={};selected={}
        def digest_file(path):
            # Re-exporting an identical statement may change PDF metadata bytes.
            # Compare its public text, never append it as a second ledger.
            if hasattr(core,'PdfReader'):
                try:text=' '.join(' '.join(page.extract_text(extraction_mode='layout') or '' for page in core.PdfReader(str(path)).pages).split())
                except Exception:raise ValueError('A Bitaroo PDF could not be read. This upload was discarded; saved files are unchanged.') from None
                return hashlib.sha256(text.encode()).hexdigest()
            return hashlib.sha256(path.read_bytes()).hexdigest()
        def inspect(path):
            try:side,year,start,end=core.inspect_bitaroo_statement(path)
            except Exception:raise ValueError('A Bitaroo PDF is unreadable or has an invalid statement header. This upload was discarded; saved files are unchanged.') from None
            if side not in ('AUD','BTC') or year>fy:raise ValueError('Invalid or future financial-year Bitaroo statement.')
            if year<fy and end!=date(year+1,6,30):raise ValueError('Historical statements must cover a complete financial year.')
            return year,start,end,side
        if existing and Path(existing).exists():
            for path in sorted(Path(existing).rglob('*')):
                if path.is_file() and path.suffix.lower()=='.pdf':
                    key=inspect(path);digest=digest_file(path)
                    if key in records and records[key][1]!=digest:raise ValueError('Conflicting saved Bitaroo statements cover the same period and asset.')
                    records[key]=(path,digest)
        for index,(name,body) in enumerate(files):
            path=stage/f'upload-{index}.pdf';path.write_bytes(body);key=inspect(path);digest=digest_file(path)
            if key in selected and selected[key][1]!=digest:raise ValueError('Conflicting uploaded Bitaroo statements cover the same period and asset.')
            selected[key]=(path,digest)
        for key,entry in selected.items():
            year,start,end,side=key;mate=(year,start,end,'BTC' if side=='AUD' else 'AUD')
            # On local 1 July, the previous day's final pair is current coverage.
            rollover=(local.month,local.day)==(7,1) and end==date(local.year,6,30)
            if year==fy or rollover:
                if mate not in selected:raise ValueError('Upload matching BTC and AUD statements together for the current financial year. This upload was discarded; saved files are unchanged.')
            elif mate not in selected and any(k[0]==year and k[3]==side for k in records) and (key not in records or records[key][1]!=entry[1]):
                raise ValueError('A single historical PDF may only fill missing statement data. Upload both assets together to replace a historical pair.')
            if key in records and records[key][1]!=entry[1]:raise ValueError('Conflicting Bitaroo statements cover the same period and asset. Saved files are unchanged.')
        records.update(selected)
        merged=stage/'merged';merged.mkdir()
        for (year,start,end,side),(path,digest) in records.items():
            shutil.copyfile(path,merged/f'{year}-{end.isoformat()}-{side}.pdf')
        previous=stage/'previous'
        if target.exists():target.rename(previous)
        try:merged.rename(target)
        except BaseException:
            if previous.exists():previous.rename(target)
            raise
    return {'files':len(selected),'retained':len(records)}
