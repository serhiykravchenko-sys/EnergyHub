"""Fresh published intervals for messages; no control or grid qualification."""
from datetime import datetime,timedelta


def rows(state,now,group):
    document=state.get('dtek_raw_snapshot') or state.get('dtek_snapshot') or {}
    try:
        if (document.get('validated') is not True or document.get('source_status')!='fresh'
                or not -60 <= (now-datetime.fromisoformat(document['checked_at'])).total_seconds() <= 2100):
            return None
        result=[]
        for row in document.get('groups',{}).get(group,[]):
            a,b=datetime.fromisoformat(row['start']),datetime.fromisoformat(row['end'])
            if not a.tzinfo or not b.tzinfo or not 0<(b-a).total_seconds()<=86400:
                return None
            if a.date().isoformat() not in document.get('dates',[]):
                return None
            result.append((a,b))
        return sorted(result)
    except (KeyError,TypeError,ValueError):
        return None


def interval(state,now,group,at=None,early_minutes=0):
    values=rows(state,now,group)
    at=at or now
    if values is None:
        return None
    current=next(((a,b) for a,b in values if a<=at<b and b>now),None)
    return current or next(((a,b) for a,b in values
                           if at<a<=at+timedelta(minutes=early_minutes) and a.date()==at.date() and b>now),None)


def loss_context(state,now,group,place,at=None):
    if not group:
        return ''
    from .source_policy import status_lines
    matched=interval(state,now,group,at,early_minutes=5)
    lines=[]
    if matched:
        a,b=matched
        lines=[f'📅 За графіком: <b>{a:%H:%M}–{b:%H:%M}</b>.',
               f'🕒 Відновлення за графіком — <b>{b:%H:%M}</b>.']
    context = status_lines(state,now,[place],only_active=True)
    context = [line.replace(place.capitalize()+': ', '', 1) for line in context]
    lines += context
    return '\n'+'\n'.join(lines) if lines else ''


def delivery_gate(state,now):
    """A website read may defer schedule reminders, never physical events."""
    pending=state.get('dtek_read_pending')
    if not isinstance(pending,dict):
        return 'send'
    try:
        elapsed=now.timestamp()-float(pending['since'])
    except (KeyError,TypeError,ValueError):
        return 'drop'
    return 'defer' if 0<=elapsed<90 else 'drop'
