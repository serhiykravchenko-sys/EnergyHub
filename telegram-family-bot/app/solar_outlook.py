"""Compact dated solar outlook; does not change charging policy."""
from datetime import datetime, timedelta
from .report import number, compact_number
from .home_assistant import HomeAssistantError


def today_label(config, client, now, forecast):
    """Only call a changed forecast updated with dated source evidence."""
    try:
        completed = ((client.state('sensor.energyhub_night_charge') or {}).get('attributes') or {}).get('completed') or {}
        old = number(completed.get('solar_kwh'))
        before = datetime.fromisoformat(completed['forecast_at'])
        current = datetime.fromisoformat((client.state(getattr(config, 'solcast_last_success_entity', '') or
            'sensor.solcast_pv_forecast_api_last_polled') or {})['state'].replace('Z', '+00:00'))
        if (completed.get('day') == now.date().isoformat() and before.tzinfo is not None
                and current.tzinfo is not None and before < current <= now
                and (now-current).total_seconds() <= 86400 and old is not None
                and forecast is not None and abs(forecast-old) >= 0.05):
            return 'Оновлений прогноз на сьогодні'
    except (KeyError, ValueError, TypeError, HomeAssistantError, OSError):
        pass
    return 'Прогноз на сьогодні'


def forecast_value(client, entity, now, offset):
    try:
        row = client.state(entity) or {}
    except (HomeAssistantError, OSError):
        return None
    attrs = row.get('attributes') or {}
    value = number(row.get('state'))
    expected = now.date() + timedelta(days=offset)
    if value is None or not 0 <= value <= 1000 or attrs.get('unit_of_measurement') != 'kWh':
        return None
    detail = attrs.get('detailedForecast') or attrs.get('detailed_forecast') or []
    if detail:
        try:
            at = datetime.fromisoformat(detail[0]['period_start'].replace('Z', '+00:00'))
            if at.tzinfo is None or at.astimezone(now.tzinfo).date() != expected:
                return None
        except (ValueError, TypeError, KeyError, IndexError):
            return None
    elif attrs.get('dayname') != expected.strftime('%A'):
        return None
    return value


def lines(config, client, now, *, today=None, average=None):
    today = number(today)
    today = today if today is not None and 0 <= today <= 1000 else None
    tomorrow = forecast_value(client, config.dtek_solar_forecast_tomorrow_entity, now, 1)
    later = forecast_value(client, getattr(config, 'solar_forecast_day3_entity',
                           'sensor.solcast_pv_forecast_forecast_day_3'), now, 2)
    try:
        source = client.state(getattr(config, 'solcast_last_success_entity', '') or
                              'sensor.solcast_pv_forecast_api_last_polled') or {}
        at = datetime.fromisoformat(source['state'].replace('Z', '+00:00'))
        if not 0 <= (now-at).total_seconds() <= 24*3600:
            today = tomorrow = later = None
    except (KeyError, ValueError, TypeError, AttributeError, HomeAssistantError, OSError):
        today = tomorrow = later = None
    def display(value):
        dot = ('🟢 ' if value >= average else '🔴 ') if value is not None and number(average) is not None else ''
        return dot+f'<b>{compact_number(value)} kWh</b>' if value is not None else 'не підтверджено'
    return [f'☀️ Прогноз: сьогодні {display(today)} · завтра {display(tomorrow)} · післязавтра {display(later)}.']
