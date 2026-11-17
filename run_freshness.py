"""CGT freshness derives only from a successfully published shared report."""
from datetime import date,datetime,time,timezone
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from report_store import ReportStore

PAGES={'history','setup','totals','notifications'}

def warning(config,snapshot,local_date,zone='UTC',*,now=None):
    try:
        today=date.fromisoformat(local_date);tz=ZoneInfo(zone)
    except (TypeError,ValueError,ZoneInfoNotFoundError):
        raise ValueError('Invalid local date or timezone.') from None
    def parsed(stamp):
        try:
            value=datetime.fromisoformat(stamp.replace('Z','+00:00'))
            return value.astimezone(timezone.utc) if value.tzinfo else None
        except (AttributeError,ValueError):return None
    stamp=parsed(snapshot.get('cgt_completed_utc')) or parsed(ReportStore(config)._index().get('completed_utc'))
    if stamp is None:return None
    # Production uses the Server clock, not the browser's claimed date.
    current=now or datetime.now(timezone.utc)
    age=(current-stamp).total_seconds()/86400
    if age<=7:return None
    return {'kind':'run_freshness','run_kind':'cgt','run_stamp':stamp.isoformat(),'age_days':int(age),'severity':'red' if age>30 else 'yellow','text':'Warning. Capital Gains data may be out of date. CGT report last run on '+stamp.strftime('%d/%m/%Y %H:%M:%S UTC'),'target':'setup','dismissible':False,'read':False}
