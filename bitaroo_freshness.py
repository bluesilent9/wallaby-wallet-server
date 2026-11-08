"""Age date-only UTC statements at 23:59 UTC on the browser's local calendar."""
from datetime import date,datetime,time,timezone
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError

def statement_age(stamp,local_date,zone='UTC'):
    try:
        end=datetime.combine(date.fromisoformat(stamp),time(23,59),timezone.utc)
        local=end.astimezone(ZoneInfo(zone)).date()
        days=(date.fromisoformat(local_date)-local).days
        return days,local.isoformat()
    except (TypeError,ValueError,ZoneInfoNotFoundError):return None,None


def warnings(snapshot,local_date,zone='UTC'):
    """All declared accounts, independent of the currently logged-in profile."""
    runs=snapshot.get('ownership_runs',{});accounts=snapshot.get('bitaroo_accounts',{})
    latest=max(runs.values(),key=lambda r:r.get('completed_utc',''),default={});settings=latest.get('settings',{})
    result=[]
    for user in snapshot.get('users',[]):
        uid=user['id'];meta=runs.get(uid,{})
        if not meta:continue
        for smsf in (False,True):
            key=uid+(':smsf' if smsf else '')
            active=accounts.get(key,meta.get('family_accounts',{}).get(key))
            if active is None:active=uid not in settings.get('non_bitaroo_smsf' if smsf else 'non_bitaroo',[u['id'] for u in snapshot['users']] if smsf else [])
            if not active:continue
            ledger=meta.get('bitaroo_smsf_data' if smsf else 'bitaroo_data',{})
            stamps=[p.get('end') for p in ledger.get('periods',{}).values() if p.get('end')]
            stamp=max(stamps,default=None) or (meta.get('bitaroo_as_of_date') if not smsf else None)
            age,report_date=statement_age(stamp,local_date,zone)
            if age is None or age<7:continue
            label=user['name']+(' — SMSF' if smsf else '')
            result.append({'account_id':key,'statement_date':stamp,'age_days':age,'report_local_date':report_date,'severity':'red' if age>=10 else 'yellow','text':'Bitaroo statements for '+label+' are '+str(age)+' days out of date. Upload the updated BTC and AUD PDFs in Ownership to refresh this account.','target':'ownership','dismissible':False})
    return result
