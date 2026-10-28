"""Actionable personal digest based on current evidence, not session log counts."""
from datetime import datetime
from .data_incidents import label
from .log_privacy import redact
from .events import format_duration


def build(state, now):
    tick = now.timestamp()
    actions, recovered, watching = [], [], []
    for key, r in state.get('data_incidents', {}).items():
        if not 0 <= tick-r.get('last_seen', 0) <= 90:
            continue
        if r.get('bad_since') is not None:
            if tick-r['bad_since'] < 180:
                continue
            name = label(state, key)
            remedy = ('перевірте живлення й зв’язок насоса; нічне керування не підтверджено'
                      if 'heat_pump' in key else
                      'перевірте Tuya в HA' if 'colorful_pir' in key else
                      'перевірте джерело даних і журнал HA')
            actions.append(f'🔧 {name}: немає даних {format_duration(tick-r["bad_since"])} — {remedy}.')
    recovery = state.get('beacon_recovery', {})
    if recovery.get('status') == 'health_unavailable':
        watching.append('👀 Beacon: стан інтеграції Tuya не вдалося перевірити; автоматичне відновлення призупинене.')
    if recovery.get('status') in {'manual', 'blocked', 'persistence_failed'}:
        actions.append('🔧 Beacon: перевірте інтеграцію Tuya та дозвіл автоматичного відновлення.')
    elif recovery.get('incident'):
        watching.append('👀 Beacon: автоматичне відновлення або перевірка стабільності триває. Поки очікуємо.')
    for r in state.get('data_incident_history', []):
        end = r.get('end', 0)
        key = r.get('key', '')
        active = state.get('data_incidents', {}).get(key)
        if (tick-86400 <= end <= tick and active is None
                and state.get('current_health', {}).get(key) is True):
            item = '✅ '+label(state, key)+': зв’язок відновлено. Втручання не потрібне.'
            if item not in recovered:
                recovered.append(item)
    short_inverter_gaps = sum(1 for r in state.get('data_incident_history', [])
                             if r.get('key') == 'inverter' and tick-86400 <= r.get('end', 0) <= tick)
    if short_inverter_gaps >= 5 and state.get('current_health', {}).get('inverter') is True:
        watching.append(f'👀 Інвертор: повторні перебої даних ({short_inverter_gaps}). Зараз дані є; спостерігаємо за зв’язком.')
    if state.get('soc_anomaly_report_events'):
        watching.append('👀 Були стрибки SOC. Дані збережено; спостерігаємо за зарядом і показниками BMS.')
    status = state.get('current_health_at')
    try:
        known = 0 <= (now-datetime.fromisoformat(status)).total_seconds() <= 90
    except (TypeError, ValueError):
        known = False
    if not known:
        actions.insert(0, '⚠️ Поточний технічний стан не підтверджено. Перевірте доступність HA.')
    lines = ['⚙️ <b>Технічний стан EnergyHub · 24 год</b>']
    lines += actions[:6]+recovered[:3]+watching[:3]
    maintenance = state.get('system_log_monitor', {}).get('xiaomi_maintenance_at')
    if isinstance(maintenance, (int, float)) and 0 <= tick-maintenance <= 86400:
        lines.append('🔧 Xiaomi Miot: є попередження сумісності з майбутніми версіями HA; перевірте оновлення інтеграції.')
    log_status = state.get('core_log_status', {})
    if log_status.get('available') is False:
        lines.append('⚠️ Журнал HA недоступний; оцінка технічного стану неповна.')
    pending = [item for item in state.get('system_log_monitor', {}).get('pending', [])
               if 0 <= tick-item.get('at', 0) <= 86400]
    if pending:
        lines.append(f'⚠️ Журнал HA: повідомлень очікують доставки — {len(pending)}.')
    if len(lines) == 1:
        health = state.get('current_health', {})
        lines.append('✅ Контрольовані джерела даних доступні. Втручання не потрібне за поточними показниками.' if health and all(v is True for v in health.values())
                     else '👀 Частина джерел ще не підтверджена. Перевірте доступність даних у HA.')
    return '\n'.join(lines)


def archive(path, core_log, state, now):
    """One bounded redacted private file per day, seven-day retention."""
    import json
    folder = path.with_name('technical-evidence')
    folder.mkdir(parents=True, exist_ok=True)
    target = folder/(now.date().isoformat()+'.json')
    target.write_text(json.dumps(dict(at=now.isoformat(), core_log=redact(core_log or '')[:250000],
                                    incidents=state.get('data_incidents', {})), ensure_ascii=False, indent=2), encoding='utf-8')
    files = sorted(folder.glob('????-??-??.json'))
    for old in files[:-7]:
        old.unlink()
