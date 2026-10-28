"""Read-only policy presentation; configuration and hardware remain elsewhere."""
from .report import number, compact_number
from datetime import datetime


def reserve_recovery_message(config, client, state, now):
    """Explain reserve recovery without borrowing a scheduled preparation plan."""
    def row(entity):
        return client.state(entity) or {}
    def value(entity):
        return number(row(entity).get('state'))
    from . import source_policy
    result=['⚡ <b>Відновлюємо резерв батареї за допомогою ДТЕК.</b>']
    if source_policy.suspended(state,'дача'):
        notice=state.get('regional_notices',{}).get('дача') or state.get('pro_notice',{})
        kind='аварійні' if notice.get('kind')=='fault' else 'екстрені'
        place='В Обухівському районі' if getattr(config,'dtek_dacha_district','')=='Obukhiv' else 'На дачі'
        result.append(f'⚠️ {place} діють <b>{kind} відключення</b>.')
    fresh=row(getattr(config,'telemetry_freshness_entity','sensor.energyhub_telemetry_freshness')).get('state')=='fresh'
    target=value(getattr(config,'ahm_minimum_soc_entity','input_number.ahm_minimum_soc'))
    soc=value(getattr(config,'battery_soc_entity','sensor.powmr_10_2m_battery_soc'))
    if not fresh or target is None or not 20<=target<=95 or soc is None or not 0<=soc<=100:
        result.append('ℹ️ Актуальний заряд і резерв батареї уточнюються.')
        return '\n'.join(result)
    change=state.get('reserve_recovery_change') or {}
    try:
        changed_at=datetime.fromisoformat(change['at'])
        recent=0 <= (now-changed_at).total_seconds() <= 1800
    except (KeyError,ValueError,TypeError):
        recent=False
    old=number(change.get('old'))
    if (recent and old is not None and 20<=old<target
            and number(change.get('new'))==target):
        result.append(f'🛡 Мінімальний резерв батареї підвищено: <b>{old:g}% → {target:g}%</b>.')
    else:
        result.append(f'🛡 Мінімальний резерв батареї: <b>{target:g}%</b>.')
    result.append(f'🔋 Заряд зараз: <b>{soc:g}%</b>.')
    pv_row=row('sensor.powmr_10_2m_total_pv_power')
    load_row=row('sensor.powmr_10_2m_output_power')
    def recent_measurement(record):
        try:
            timestamp=datetime.fromisoformat(record.get('last_updated') or record['last_changed'])
            return 0 <= (now-timestamp).total_seconds() <= 90
        except (KeyError,ValueError,TypeError):
            return False
    pv=number(pv_row.get('state'))
    load=number(load_row.get('state'))
    if (pv is not None and load is not None and 0<=pv<load
            and recent_measurement(pv_row) and recent_measurement(load_row)):
        result.append('☀️ Сонце зараз не покриває споживання будинку.')
    if soc < target:
        result.append(f'⚡ Використовуємо ДТЕК, щоб зарядити батарею до <b>{target:g}%</b>.')
    else:
        result.append('✅ Заряд уже досяг мінімального резерву.')
    return '\n'.join(result)


def lines(config, client, state, now):
    from . import outage_schedule, source_policy
    def row(entity):return client.state(entity) or {}
    mode=row(getattr(config,'operating_mode_entity','sensor.energyhub_operating_mode')).get('state')
    fresh=row(getattr(config,'telemetry_freshness_entity','sensor.energyhub_telemetry_freshness')).get('state')=='fresh'
    source=row('sensor.energyhub_panic_target_source').get('state','')
    if fresh and mode in {'panic','panic_grid_hold'} and str(source).startswith('Manual Panic:'):
        return ['🛑 <b>Режим Panic — батарея як павербанк.</b>',
                '🔋 Ціль: <b>95%</b>. Інша логіка керування резервом призупинена.']
    reserve=row(getattr(config,'weather_buffer_entity','sensor.energyhub_ahm_weather_buffer')).get('attributes',{})
    if reserve.get('management_mode') in {'manual','dry_run'}:
        target=number(reserve.get('recommended_soc'))
        text='👥 Резерв батареї встановлюється вручну.'
        return [text]+([f'🔋 Рекомендація EH: <b>{target:g}%</b>.'] if target is not None else [])
    blocked=source_policy.suspended(state,'дача')
    result=[]
    if blocked:
        notice=state.get('regional_notices',{}).get('дача') or state.get('pro_notice',{})
        label='аварійні' if notice.get('kind')=='fault' else 'екстрені' if notice.get('kind')=='emergency' else 'обмеження'
        result.append(f'⚠️ Обухівський район: {label} відключення. Графіки можуть не витримуватись.'
                      if getattr(config,'dtek_dacha_district','')=='Obukhiv' else
                      f'⚠️ Дача: {label} відключення. Графіки можуть не витримуватись.')
    plan=outage_schedule.recovery_plan(config,client,state,now)
    if plan:
        soc=number(row(getattr(config,'battery_soc_entity','sensor.powmr_10_2m_battery_soc')).get('state'))
        selected=number(row(getattr(config,'ahm_minimum_soc_entity','input_number.ahm_minimum_soc')).get('state'))
        status=([f'🔋 Заряд: <b>{soc:g}%</b> · резерв: <b>{selected:g}%</b>.']
                if fresh and soc is not None and 0 <= soc <= 100 and selected is not None and 20 <= selected <= 95 else [])
        return result+plan.strip().split('\n')+status
    if fresh and reserve.get('reserve_planning_source') == 'dtek_schedule':
        return result+['📅 EH керує зарядом за графіком відключень.', '🔋 Деталі наступного відключення ще уточнюються.']
    if getattr(config,'dtek_schedule_enabled',False):
        result.append('ℹ️ Актуальний графік підготовки не підтверджено.')
    result.append('🔋 EH керує резервом за доступністю ДТЕК протягом останніх 48 годин.')
    if (number(reserve.get('schedule_suspension_modifier_percent')) or 0)>0:
        result.append('🛡 Позапланові відключення: додатковий резерв <b>+20 п.п.</b>; максимум <b>95%</b>.')
    selected=number(row(getattr(config,'ahm_minimum_soc_entity','input_number.ahm_minimum_soc')).get('state'))
    if selected is not None and 20<=selected<=95:
        result.append(f'Мінімальний резерв: <b>{compact_number(selected)}%</b>.')
        soc=number(row(getattr(config,'battery_soc_entity','sensor.powmr_10_2m_battery_soc')).get('state'))
        if fresh and soc is not None and 0 <= soc <= 100:
            result.append(f'🔋 Заряд: <b>{soc:g}%</b> · резерв: <b>{selected:g}%</b>.')
    else:result.append('Мінімальний резерв ще не підтверджено.')
    return result


def context(config,client,state,now):
    return '\n'+'\n'.join(lines(config,client,state,now))


def supply_line(config,client,now=None):
    """Describe supply only with fresh grid voltage and a recognized strategy."""
    fresh=(client.state(getattr(config,'telemetry_freshness_entity','sensor.energyhub_telemetry_freshness')) or {}).get('state')=='fresh'
    voltage=number((client.state(getattr(config,'grid_voltage_entity','sensor.powmr_10_2m_grid_voltage')) or {}).get('state'))
    mode=(client.state(getattr(config,'operating_mode_entity','sensor.energyhub_operating_mode')) or {}).get('state')
    if not fresh or voltage is None or not 0<=voltage<=300:
        return ''
    if voltage<=180 or mode=='solar':
        supply='без допомоги'
    elif mode in {'panic','panic_grid_hold','hybrid_charging','hybrid_grid_hold'}:
        from .grid_evidence import qualified
        if now is None or qualified(config, client, now) is not True:
            return ''
        supply='з допомогою'
    else:return ''
    at=f'О {now:%H:%M} ' if now else ''
    noun='будинок' if now else 'Будинок'
    if now is not None and supply == 'з допомогою':
        from . import outage_schedule
        plan = client.state(outage_schedule.STATUS_ENTITY) or {}
        data = plan.get('attributes') or {}
        try:
            checked, start = [datetime.fromisoformat(data[k]) for k in ('checked_at', 'start')]
            soc, target = [number(data.get(k)) for k in ('current_soc', 'target_soc')]
            if (0 <= (now-checked).total_seconds() <= 120 and now < start
                    and outage_schedule.charging_confirmed(data)
                    and soc is not None and target is not None and 0 <= soc < target <= 95):
                return (f'⚡ Заряджаємо батарею від ДТЕК: <b>{soc:g}% → {target:g}%</b>'
                        f' перед відключенням о <b>{start:%H:%M}</b>.')
            if (0 <= (now-checked).total_seconds() <= 120 and now < start
                    and data.get('phase') == 'holding'
                    and data.get('control_active') is True and data.get('acknowledged') is True
                    and soc is not None and target is not None and 0 <= target <= soc <= 100):
                return (f'⚡ Утримуємо заряд батареї за допомогою ДТЕК: <b>{soc:g}%</b>'
                        f' · ціль <b>{target:g}%</b> перед відключенням о <b>{start:%H:%M}</b>.')
        except (ValueError, TypeError, KeyError):
            pass
    return f'🏠 {at}{noun} працює <b>{supply} ДТЕК</b>.'
