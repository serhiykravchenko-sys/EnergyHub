"""Compare a dated daily snapshot with observed generation, never missing=zero."""
from datetime import datetime, timedelta, timezone
from .report import number
from .home_assistant import HomeAssistantError
from .hp_daily_energy import daily_value


def collect(client, now):
    yesterday=(now.date()-timedelta(days=1)).isoformat()
    # These attributes are published atomically: a changed date cannot be paired
    # with scalar states from the preceding MQTT publication cycle.
    data=(client.state('sensor.energyhub_daily_solar_forecast') or {}).get('attributes') or {}
    result=dict(date=yesterday,battery_full=None,forecast_kwh=None,actual_kwh=None)
    history = []
    for row in data.get('history') or []:
        if not isinstance(row, dict):
            continue
        try:
            date = datetime.fromisoformat(str(row['date'])).date()
        except (KeyError, ValueError, TypeError):
            continue
        if not now.date()-timedelta(days=70) <= date < now.date():
            continue
        forecast, actual = number(row.get('forecast_kwh')), number(row.get('actual_kwh'))
        history.append(dict(date=date.isoformat(), battery_full=row.get('battery_full') if type(row.get('battery_full')) is bool else None,
                            forecast_kwh=forecast if forecast is not None and forecast >= 0 else None,
                            actual_kwh=actual if actual is not None and actual >= 0 else None))
    result['history'] = history
    if data.get('date') != yesterday:
        result['missing']='dated_snapshot'
        data = {}
    result['battery_full']=data.get('battery_full') if type(data.get('battery_full')) is bool else None
    forecast=number(data.get('forecast_kwh'))
    actual=number(data.get('actual_kwh'))
    result['consumption_kwh']=None
    result['forecast_kwh']=forecast if forecast is not None and forecast>=0 else None
    result['actual_kwh']=actual if actual is not None and actual>=0 else None
    # Prefer the completed native calendar-day meter over the 23:51 snapshot.
    meter=(client.state('sensor.total_solar_generated_today') or {}).get('attributes') or {}
    try:
        reset=datetime.fromisoformat(meter['last_reset']).astimezone(now.tzinfo)
        midnight=now.replace(hour=0,minute=0,second=0,microsecond=0)
        value=number(meter.get('last_period'))
        unit=meter.get('unit_of_measurement')
        if (0 <= (reset-midnight).total_seconds() <= 120 and value is not None
                and value>=0 and unit in {'Wh','kWh'}):
            result['actual_kwh']=value/(1000 if unit=='Wh' else 1)
            result['actual_source']='completed_native_day'
    except (KeyError,TypeError,ValueError):
        pass
    # Consumption comes from the same completed recorder buckets as the chart.
    try:
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        left = end-timedelta(days=70)
        entity = 'sensor.powmr_10_2m_daily_house_consumption'
        solar_entity = 'sensor.total_solar_generated_today'
        statistics = client.daily_energy_statistics(left.astimezone(timezone.utc), end.astimezone(timezone.utc), [entity, solar_entity])
        for row in [*history, result]:
            a = datetime.fromisoformat(row['date']).replace(tzinfo=now.tzinfo)
            b = a+timedelta(days=1)
            row['consumption_kwh'] = daily_value(statistics.get(entity, []), a.astimezone(timezone.utc), b.astimezone(timezone.utc))
            actual = daily_value(statistics.get(solar_entity, []), a.astimezone(timezone.utc), b.astimezone(timezone.utc))
            if actual is not None:
                row['actual_kwh'] = actual
                row['actual_source'] = 'completed_recorder_day'
    except (HomeAssistantError, AttributeError, OSError, TypeError, ValueError):
        pass
    return result


def weekly(state, now, observation):
    """Retain dated daily evidence; Monday compares only eligible prior-week days."""
    days = state.setdefault('forecast_quality_days', {})
    yesterday = (now.date()-timedelta(days=1)).isoformat()
    if isinstance(observation, dict):
        for row in observation.get('history') or []:
            if isinstance(row, dict) and now.date().isoformat() > str(row.get('date','')) >= (now.date()-timedelta(days=70)).isoformat():
                previous = days.get(row['date']) or {}
                merged = dict(previous, **row)
                if previous.get('actual_source') in {'completed_native_day','completed_recorder_day'} and row.get('actual_source') not in {'completed_native_day','completed_recorder_day'}:
                    merged['actual_kwh'] = previous['actual_kwh']
                    merged['actual_source'] = previous['actual_source']
                if row.get('consumption_kwh') is None and previous.get('consumption_kwh') is not None:
                    merged['consumption_kwh'] = previous['consumption_kwh']
                days[row['date']] = merged
    if isinstance(observation, dict) and observation.get('date') == yesterday:
        days[yesterday] = {k:v for k,v in observation.items() if k != 'history'}
    oldest = (now.date()-timedelta(days=70)).isoformat()
    for day in list(days):
        if day < oldest:
            days.pop(day)
    windows = []
    if now.weekday() == 0:
        windows.append((now.date()-timedelta(days=7), now.date(), 'за тиждень'))
    if now.day == 1:
        windows.append(((now.date().replace(day=1)-timedelta(days=1)).replace(day=1), now.date(), 'за місяць'))
    result = []
    for left, right, label in windows:
        period = [row for day, row in days.items() if left.isoformat() <= day < right.isoformat()
                  and isinstance(row, dict)]
        eligible = [r for r in period if r.get('battery_full') is False
                    and number(r.get('forecast_kwh')) is not None and r['forecast_kwh'] > 0
                    and number(r.get('actual_kwh')) is not None and r['actual_kwh'] >= 0]
        if eligible:
            forecast = sum(number(r['forecast_kwh']) for r in eligible)
            actual = sum(number(r['actual_kwh']) for r in eligible)
            result.append(f'🎯 Прогноз {label} · {len(eligible)} дн. без 100% SOC: '
                          f'прогноз {forecast/len(eligible):.1f} · генерація {actual/len(eligible):.1f} kWh/день '
                          f'({(actual/forecast-1)*100:+.1f}%).')
        else:
            result.append(f'🎯 Прогноз {label}: недостатньо даних без обмеження генерації.')
        paired = [r for r in period if number(r.get('forecast_kwh')) is not None and r['forecast_kwh'] >= 0
                  and number(r.get('consumption_kwh')) is not None and r['consumption_kwh'] >= 0]
        expected = (right-left).days
        if paired:
            above = sum(r['forecast_kwh'] > r['consumption_kwh'] for r in paired)
            line = f'☀️ Прогноз генерації вище споживання: <b>{above} із {len(paired)} днів</b>.'
            if len(paired) < expected:
                line += f' Дані за {len(paired)} із {expected} днів.'
            result.append(line)
        else:
            result.append(f'☀️ Порівняння прогнозу зі споживанням {label}: даних недостатньо.')
    return result
