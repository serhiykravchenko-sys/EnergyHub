"""One HA source for planning assumptions; never writes hardware settings."""
from .report import number

CAPACITY = 'input_number.energyhub_battery_capacity_kwh'
DEMAND = 'input_number.energyhub_house_demand_kw'
FORECAST_AGE = 'input_number.energyhub_forecast_max_age_hours'
OFF_SOC = 'input_number.energyhub_load_off_soc'
ON_SOC = 'input_number.energyhub_load_restore_soc'


def read(client):
    def value(entity, low, high):
        raw = number((client.state(entity) or {}).get('state'))
        return raw if raw is not None and low <= raw <= high else None
    result = dict(capacity_kwh=value(CAPACITY, 1, 1000),
                  house_demand_kw=value(DEMAND, 0.1, 100),
                  forecast_max_age_hours=value(FORECAST_AGE, 1, 24),
                  load_off_soc=value(OFF_SOC, 1, 90),
                  load_restore_soc=value(ON_SOC, 2, 95))
    if (client.state('input_boolean.energyhub_planning_settings_initialized') or {}).get('state') != 'on':
        return dict.fromkeys(result)
    if (result['load_off_soc'] is None or result['load_restore_soc'] is None
            or result['load_off_soc'] >= result['load_restore_soc']):
        result['load_off_soc'] = result['load_restore_soc'] = None
    return result
