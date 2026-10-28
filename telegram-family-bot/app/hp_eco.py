"""Read-only, acknowledged Eco notices; native HA automation owns control."""
import json
from datetime import datetime
from .report import number

HP = 'climate.first_floor_heat_pump'
ECO = 'switch.first_floor_heat_pump_eco'


def failure(client,now):
    if client is None:
        return None
    def row(entity):return client.state(entity) or {}
    try:
        grid=row('binary_sensor.energyhub_grid_confirmed')
        attrs=grid.get('attributes') or {}
        budget=json.loads(row('input_text.energyhub_hp1_eco_budget').get('state','{}'))
        overrides=json.loads(row('input_text.energyhub_hp1_night_overrides').get('state','{}'))
        confirmed=grid.get('state')
        stamp=number(attrs.get('transition_at'))
        checked=number(attrs.get('checked_at'))
        at=number(budget.get('at'))
        desired='on' if confirmed=='off' else 'off'
        if (row('input_select.energyhub_climate_policy').get('state')!='Smart'
                or row(HP).get('state') not in {'heat','cool'}
                or row('sensor.energyhub_telemetry_freshness').get('state')!='fresh'
                or row('input_boolean.energyhub_hp1_manual_hold').get('state')=='on'
                or confirmed not in {'on','off'} or stamp is None or stamp<=0
                or checked is None or not 0<=now.timestamp()-checked<=30
                or attrs.get('transition_pending') is not False
                or attrs.get('episode_persisted') is not True
                or (number(attrs.get('confirmation_seconds')) or 0)<180
                or budget.get('e')!=f'{confirmed}:{int(stamp)}' or budget.get('t')!=desired
                or (number(budget.get('n')) or 0)<3 or at is None or not 30<=now.timestamp()-at
                or (number(overrides.get('eco_until')) or 0)>now.timestamp()
                or row(ECO).get('state')==desired):
            return None
        action='Увімкнення' if desired=='on' else 'Вимкнення'
        return dict(fingerprint=f"{budget['e']}:{desired}",
            message=f'⚠️ <b>{action} Eco не підтверджено після трьох спроб.</b> Перевірте зв’язок із тепловим насосом і стан Eco. EH припинив повтори для цього періоду живлення.')
    except (TypeError,ValueError,AttributeError):
        return None


def sample(client, now):
    def row(entity):
        return client.state(entity) or {}
    if row('input_select.energyhub_climate_policy').get('state') != 'Smart':
        return None
    if row(HP).get('state') not in {'heat', 'cool'}:
        return None
    if row('sensor.energyhub_telemetry_freshness').get('state') != 'fresh':
        return None
    grid = number(row('sensor.powmr_10_2m_grid_voltage').get('state'))
    eco = row(ECO)
    if grid is None or not 0 <= grid <= 300 or eco.get('state') not in {'on', 'off'}:
        return None
    confirmed=row('binary_sensor.energyhub_grid_confirmed').get('state')
    if confirmed in {'unknown','unavailable'}:
        return None
    online = confirmed=='on' if confirmed in {'on','off'} else grid > 180
    desired = 'off' if online else 'on'
    reason = 'grid' if online else 'battery'
    try:
        requests = json.loads(row('input_text.energyhub_hp1_profile_requests').get('state', '{}'))
        request = requests.get('eco', {})
        at = number(request.get('at'))
        changed_at = datetime.fromisoformat(eco['last_changed'])
        if changed_at.tzinfo is None:
            return None
        changed = changed_at.timestamp()
        overrides = json.loads(row('input_text.energyhub_hp1_night_overrides').get('state', '{}'))
        until = number(overrides.get('eco_until')) or 0
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    # A request is not acknowledgement. Require matching actual feedback after
    # a bounded native request, and reject HA user-attributed changes.
    if (at is None or request.get('t') != desired or eco['state'] != desired
            or not 0 <= now.timestamp()-at <= 600 or changed < at-2
            or changed > now.timestamp()+2 or until > now.timestamp()
            or (eco.get('context') or {}).get('user_id')):
        return None
    fingerprint = f"{eco['state']}:{reason}"
    text = {
        'battery': '🍃 Тепловий насос перейшов в Eco — ДТЕК відсутній.',
        'grid': '♨️ Eco вимкнено — ДТЕК доступний.',
    }[reason]
    return dict(fingerprint=fingerprint, reason=reason, message=text)


def observe(state, client, now):
    monitor = state.setdefault('hp_eco_notifications', {})
    diagnostic=failure(client,now)
    changed=False
    if diagnostic and monitor.get('failure_reported')!=diagnostic['fingerprint']:
        queue=state.setdefault('pending_notifications',[])
        queue[:]=[item for item in queue if item.get('kind')!='technical_hp_eco_unconfirmed']
        queue.append(dict(kind='technical_hp_eco_unconfirmed',message=diagnostic['message'],
                          created_at=now.isoformat(),eco_failure=diagnostic['fingerprint']))
        monitor['failure_reported']=diagnostic['fingerprint']
        changed=True
    current = sample(client, now)
    if not monitor.get('initialized'):
        monitor.update(initialized=True, reported=current['fingerprint'] if current else None)
        return True
    if current is None:
        monitor.pop('candidate', None)
        return changed
    fingerprint = current['fingerprint']
    if monitor.get('reported') == fingerprint:
        return changed
    # Do not replay a historical transition at app startup. Subsequent native
    # requests/feedback remain observable, including after temporary HA gaps.
    candidate = monitor.get('candidate')
    if (not candidate or candidate['fingerprint'] != fingerprint
            or not 0 <= now.timestamp()-candidate['last'] <= 90):
        monitor['candidate'] = dict(fingerprint=fingerprint, since=now.timestamp(), last=now.timestamp())
        return True
    candidate['last'] = now.timestamp()
    if now.timestamp()-candidate['since'] < 30:
        return False
    # Eco diagnostics have their own private destination, including when a
    # family grid notice is pending.
    if state.get('grid_candidate') is not None:
        return False
    _queue_private(state, current, now)
    monitor.update(reported=fingerprint)
    monitor.pop('candidate', None)
    return True


def _queue_private(state, current, now):
    queue = state.setdefault('pending_notifications', [])
    queue[:] = [item for item in queue if item.get('kind') != 'hp_eco_change']
    queue.append(dict(kind='hp_eco_change', message=current['message'],
                      created_at=now.isoformat(), hp_eco_ack=current['fingerprint']))


def refresh(item, client, now):
    """Drop stale queued transitions instead of announcing old Eco state."""
    current = sample(client, now)
    if current is None or current['fingerprint'] != item.get('hp_eco_ack'):
        return None
    return current['message']


def acknowledge_grid(state, item, client, now):
    kind = item.get('kind')
    if kind not in {'grid_lost', 'grid_recovered'}:
        return
    current = sample(client, now)
    if current and ((kind == 'grid_recovered') == (current['reason'] == 'grid')):
        monitor = state.setdefault('hp_eco_notifications', {})
        if monitor.get('initialized') and monitor.get('reported') != current['fingerprint']:
            _queue_private(state, current, now)
        monitor.update(initialized=True, reported=current['fingerprint'])


def recovery_detail(client, now):
    if (client.state('input_select.energyhub_climate_policy') or {}).get('state') != 'Smart':
        return ''
    hp = (client.state(HP) or {}).get('state')
    eco = (client.state(ECO) or {}).get('state')
    if hp in {None, 'unknown', 'unavailable'} or eco in {None, 'unknown', 'unavailable'}:
        return '\n⚠️ Тепловий насос недоступний для керування в HA. Зміну Eco не підтверджено.'
    if hp == 'off':
        return ''
    current = sample(client, now)
    if current and current['reason'] == 'grid':
        return '\n'+current['message']
    if eco == 'on':
        return '\n🍃 Eco ще увімкнено; повернення до звичайного режиму не підтверджено.'
    return ''
