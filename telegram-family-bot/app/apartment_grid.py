"""Persisted hub availability proxy; no power or hardware control."""
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta


def observe(config,client,state,now):
    entity=getattr(config,'apartment_grid_proxy_entity','')
    if not entity:
        return False
    cloud=getattr(config,'apartment_grid_cloud_enabled',False)
    try:
        if cloud:
            sample=state.get('apartment_cloud_sample') or {}
            at=datetime.fromisoformat(sample['checked_at'])
            if not isinstance(sample.get('online'),bool):
                raise ValueError('Invalid online evidence')
            value={'state': ('on' if sample['online'] else 'unavailable')}
            if not -5 <= (now-at).total_seconds() <= 90:
                value={}
        else:
            value=client.state(entity)
    except (KeyError, ValueError, TypeError):
        record=state.setdefault('apartment_grid',{})
        record.pop('candidate',None);record.pop('since',None)
        return True
    # Missing/unknown entity or failed HA request is unknown, never an outage.
    status=value.get('state') if isinstance(value,dict) else None
    if status not in {'on','off','unavailable'}:
        record=state.setdefault('apartment_grid',{})
        record.pop('candidate',None);record.pop('since',None)
        return True
    online=status!='unavailable'
    record=state.setdefault('apartment_grid',{})
    if record.get('entity')!=entity:
        record.clear();record.update(entity=entity,online=None)
    if cloud:
        previous_tick=record.get('observed_at')
        if previous_tick is not None and not 0<=now.timestamp()-previous_tick<=90:
            record.pop('candidate',None);record.pop('since',None)
    record['observed_at']=now.timestamp()
    if record.get('online') is None and not online and not cloud:
        record.pop('candidate',None);record.pop('since',None)
        return False  # Never turn initial unavailability into a known outage.
    if record.get('online')==online:
        record.pop('candidate',None);record.pop('since',None)
        return False
    if record.get('candidate')!=online:
        record.update(candidate=online,since=now.isoformat())
        return True
    since=datetime.fromisoformat(record['since'])
    if (now-since).total_seconds() < (60 if online else 120):
        return False
    previous=record.get('online')
    record.update(online=online);record.pop('candidate',None);record.pop('since',None)
    if online:
        if previous is None:
            return True
        from .restoration_messages import apartment_text
        started=datetime.fromisoformat(record['outage_started']) if record.get('outage_started') else None
        message=apartment_text(config,state,now,since,started)
        record.pop('outage_started',None)
        record.pop('outage_detected',None)
    else:
        if previous is None:
            record.pop('outage_started',None)
            record['outage_detected']=since.isoformat()
            message=(f'⚡ <b>Квартира: ДТЕК імовірно недоступний</b>'
                     f'\nXiaomi Hub офлайн · виявлено о {since:%H:%M}; початок відключення невідомий.')
        else:
            record['outage_started']=since.isoformat()
            message=f'⚡ <b>Квартира: ДТЕК недоступний</b>\nПочаток відключення: {since:%H:%M}'
    from . import source_policy, outage_schedule
    if not online and getattr(config,'dtek_schedule_enabled',False):
        from .schedule_context import loss_context
        message+=loss_context(state,now,getattr(config,'dtek_apartment_group',''),'квартира',since)
    if not online:
        message+='\nℹ️ За доступністю Xiaomi Hub.'
    record.setdefault('events',[]).append(dict(online=online,at=since.isoformat(),onset_unknown=previous is None and not online))
    record['events']=record['events'][-100:]
    state.setdefault('pending_notifications',[]).append(dict(kind='apartment_grid',message=message,created_at=since.isoformat(),apartment_online=online))
    return True


def observe_read_health(state, now, success, online=None):
    """Qualify technical read health, separately from Hub/grid availability."""
    record=state.setdefault('apartment_cloud_health', {})
    last=record.get('observed_at')
    if last is None or not 0 <= now.timestamp()-last <= 90:
        record.pop('since',None)
        record.pop('candidate',None)
    record['observed_at']=now.timestamp()
    if record.get('candidate') is not success:
        record.update(candidate=success,since=now.isoformat())
        # A recovery before an alert was delivered must remain silent.
        state['pending_notifications']=[i for i in state.get('pending_notifications',[])
            if i.get('kind')!='technical_apartment_cloud']
        record.pop('queued',None)
    seconds=(now-datetime.fromisoformat(record['since'])).total_seconds()
    phase='recovered' if success else 'unavailable'
    if record.get('queued')==phase:
        return
    if (success and (not record.get('alerted') or seconds<300)
            or not success and (record.get('alerted') or seconds<180)):
        return
    message=('✅ Читання доступності Xiaomi Hub у квартирі відновлено. Hub '+
             ('онлайн.' if online else 'офлайн; перевіряємо доступність ДТЕК.') if success else
             '⚠️ Не вдалося перевірити Xiaomi Hub у квартирі протягом 3 хв. Доступність ДТЕК невідома; повідомлення про відключення не формуємо.')
    state.setdefault('pending_notifications',[]).append(dict(kind='technical_apartment_cloud',
        health_phase=phase,message=message,created_at=now.isoformat()))
    record['queued']=phase


def acknowledge_read_health(state, item):
    phase=item.get('health_phase')
    if phase in {'unavailable','recovered'}:
        record=state.setdefault('apartment_cloud_health',{})
        record['alerted']=phase=='unavailable'
        record.pop('queued',None)


class CloudMonitor:
    def __init__(self):
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='xiaomi-availability')
        self.future=None; self.due=0

    def poll(self,config,client,state,now):
        if not getattr(config,'apartment_grid_cloud_enabled',False) or not config.apartment_grid_proxy_entity:
            return observe(config,client,state,now)
        if 'apartment_cloud_health' not in state:
            state['apartment_cloud_health']=dict(alerted=state.get('apartment_cloud_failed') is True)
            state['pending_notifications']=[i for i in state.get('pending_notifications',[])
                if i.get('kind')!='technical_apartment_cloud' or i.get('health_phase')]
        changed=False
        if self.future is not None and self.future.done():
            try:
                online=self.future.result()
                if not isinstance(online,bool):
                    raise ValueError('Invalid online evidence')
                state['apartment_cloud_sample']=dict(online=online,checked_at=now.isoformat())
                state.pop('apartment_cloud_failed',False)
                observe_read_health(state,now,True,online)
            except Exception:
                state.pop('apartment_cloud_sample',None)
                record=state.setdefault('apartment_grid',{})
                record.pop('candidate',None);record.pop('since',None)
                observe_read_health(state,now,False)
                state['apartment_cloud_failed']=True
            self.future=None; self.due=now.timestamp()+30; changed=True
        if self.future is None and now.timestamp()>=self.due:
            from .xiaomi_cloud import read
            self.future=self.executor.submit(read,config.apartment_grid_proxy_entity)
        return observe(config,client,state,now) or changed


def morning_lines(state,now,group):
    beginning=(now-timedelta(days=1)).replace(hour=23,minute=0,second=0,microsecond=0)
    lines=[]
    record=state.get('apartment_grid',{})
    events=record.get('events',[])
    sample=state.get('apartment_cloud_sample') or {}
    try:
        fresh_offline=(sample.get('online') is False and
            -5 <= (now-datetime.fromisoformat(sample['checked_at'])).total_seconds() <= 90)
    except (KeyError,ValueError,TypeError):
        fresh_offline=False
    for event in events:
        at=datetime.fromisoformat(event['at'])
        if beginning<=at<=now:
            text=('ДТЕК відновився' if event['online'] else
                  'ДТЕК імовірно недоступний · початок невідомий' if event.get('onset_unknown') else 'ДТЕК недоступний')
            from .source_policy import suspended
            if not event['online'] and event is events[-1] and record.get('online') is False and fresh_offline and not suspended(state,'квартира'):
                from .outage_schedule import context
                text+=context(dict(state,dtek_snapshot=state.get('dtek_raw_snapshot') or {}),now,False,group).replace('\n',' · ')
            lines.append(f'• {at:%H:%M} — {text}.')
    return daily_lines(state, now) + (['\n🏢 <b>Квартира · ДТЕК за ніч:</b>',*lines] if lines else [])


def daily_lines(state, now):
    """Rolling proxy estimate uses observation onset, never delivery timestamps."""
    from .outage_schedule import duration
    begin = now-timedelta(hours=24)
    events = []
    for row in state.get('apartment_grid', {}).get('events', []):
        try:
            at = datetime.fromisoformat(row['at'])
            if not at.tzinfo or at > now or not isinstance(row.get('online'), bool):
                continue
            events.append((at, row['online'], row.get('onset_unknown', False)))
        except (KeyError, ValueError, TypeError):
            continue
    events.sort(key=lambda r: r[0])
    if not events:
        return ['🏢 Квартира: оцінка ДТЕК за 24 год недоступна.',
                'ℹ️ Орієнтовно, за доступністю Xiaomi Hub.']
    prior = [row for row in events if row[0] <= begin]
    if not prior:
        return ['🏢 Квартира: недостатньо історії для оцінки ДТЕК за 24 год.',
                'ℹ️ Орієнтовно, за доступністю Xiaomi Hub.']
    online = prior[-1][1]
    cursor, outage = begin, 0
    for at, value, unknown in [r for r in events if begin < r[0] <= now]:
        if unknown:
            return ['🏢 Квартира: час відключення за 24 год не підтверджено.',
                    'ℹ️ Орієнтовно, за доступністю Xiaomi Hub.']
        if not online:
            outage += (at-cursor).total_seconds()
        cursor, online = at, value
    if not online:
        outage += (now-cursor).total_seconds()
    return [f'🏢 Квартира: ДТЕК за 24 год: доступний <b>{duration(86400-outage)}</b>; '
            f'недоступний <b>{duration(outage)}</b>.',
            'ℹ️ Орієнтовно, за доступністю Xiaomi Hub.']
