"""Read-only morning forecast assessment; the controller owns all commands."""
from datetime import timedelta
from app.services.outage_preparation import number, stamp, forecast_period_key


def assess(document, *, now, soc, reserve, load_w, solar_w, capacity,
           heating_rate, telemetry_valid, grid_confirmed, authority_fresh, demand_kw=None):
    result = dict(safe=False, reason='Fresh bridge evidence is unavailable')
    observed = number(demand_kw)
    if not telemetry_valid or not authority_fresh or (observed is None and grid_confirmed is not True):
        return result
    raw_values = (soc, reserve, load_w, solar_w, capacity, heating_rate)
    if any(isinstance(v, bool) for v in raw_values):
        return result
    values = [number(v) for v in raw_values]
    if any(v is None for v in values):
        return result
    soc, reserve, load_w, solar_w, capacity, heating_rate = values
    if (not 0 <= soc <= 100 or not 20 <= reserve < 95 or load_w < 0
            or solar_w < 0 or not 1 <= capacity <= 1000 or not 0 < heating_rate <= 100
            or (observed is None and not 5 <= now.hour < 12)):
        return result
    max_age = number(document.get('forecast_max_age_hours'))
    if max_age is None or not 1 <= max_age <= 24:
        return result
    checked, forecast_at = stamp(document.get('checked_at')), stamp(document.get('forecast_at'))
    if (not checked or not forecast_at or not 0 <= (now-checked).total_seconds() <= 2100
            or not 0 <= (now-forecast_at).total_seconds() <= max_age*3600):
        return result
    source = document.get('forecast')
    if not isinstance(source, list) or not 1 <= len(source) <= 100:
        return result
    try:
        rows = []
        scale = 1.0
        for row in sorted(source, key=forecast_period_key):
            a, b, kw = stamp(row['start']), stamp(row['end']), number(row['pv_kw'])
            if not a or not b or kw is None or not 0 <= kw <= 30 or not 0 < (b-a).total_seconds() <= 3600:
                return result
            rows.append((a, b, kw))
            if a <= now < b and kw > 0.1 and soc < 95:
                scale = min(1, solar_w / 1000 / kw)
        if any(b[0] < a[1] for a, b in zip(rows, rows[1:])):
            return result
        demand = observed if observed is not None else capacity * heating_rate / 100
        # Credit solar half an hour late, and reduce it by 20%. No future
        # surplus may repay an earlier breach of the reserve floor.
        cursor = now
        deficit = peak = covered = 0.0
        limit = now + timedelta(hours=4)
        for a, b, kw in rows:
            a, b = a + timedelta(minutes=30), b + timedelta(minutes=30)
            if b <= cursor:
                continue
            if a > cursor:
                return result
            right = min(b, limit)
            hours = (right-cursor).total_seconds() / 3600
            credited = kw * scale * 0.8
            net = (demand-credited)/0.9 if credited<demand else (demand-credited)*0.9
            deficit = max(0, deficit + net*hours)
            peak = max(peak, deficit)
            covered = covered + hours if credited >= demand else 0
            cursor = right
            if covered >= 1:
                minimum = soc - peak / capacity * 100
                return dict(safe=minimum > reserve + 5, minimum_soc=round(minimum, 2),
                            reserve_soc=reserve, margin_soc=5, coverage_at=cursor.isoformat(),
                            reason=f'Forecast minimum SOC={minimum:.1f}%; active reserve={reserve:g}% + 5-point margin')
            if cursor >= limit:
                break
    except (KeyError, TypeError, ValueError, OverflowError):
        pass
    return result
