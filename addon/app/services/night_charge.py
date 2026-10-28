"""Persisted tariff intents; only the existing inverter controller executes them."""
import json
import threading
from datetime import datetime, time, timedelta
from pathlib import Path

from app.services.outage_preparation import number, stamp
from app.utils.json_store import atomic_write_json

STATUS_TOPIC = 'energyhub/night/charge'


class NightCharge:
    def __init__(self, path, enabled=True):
        self.path = Path(path)
        self.enabled = enabled
        self.lock = threading.RLock()
        self.saved = {}
        self.document = {}
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            if (isinstance(value, dict) and value.get('schema') == 1
                    and isinstance(value.get('current', {}), dict)
                    and isinstance(value.get('last_valid', {}), dict)
                    and type(value.get('missing_nights', 0)) is int
                    and 0 <= value.get('missing_nights', 0) <= 10000):
                self.saved = value
        except (OSError, ValueError):
            pass

    def update(self, document):
        with self.lock:
            self.document = dict(document) if isinstance(document, dict) else {}

    def _save(self, saved):
        try:
            atomic_write_json(self.path, saved, ensure_ascii=False, indent=2)
        except OSError:
            return False
        self.saved = saved
        return True

    def _guarded(self, result, day, mode, allowed, reason):
        prior = self.saved.get('current') or {}
        hold = number(prior.get('hold_soc'))
        end, checked = stamp(prior.get('end')), stamp(result.get('checked_at'))
        retained = (allowed and prior.get('day') == day and prior.get('acquired') is True
                    and mode in {'panic', 'panic_grid_hold'} and hold is not None and 20 <= hold <= 95
                    and end is not None and checked is not None and checked < end)
        return dict(result, phase='guarded', request=None, control_active=bool(retained),
                    target_soc=hold if retained else None, day=prior.get('day'),
                    start=prior.get('start'), end=prior.get('end'), reason=reason)

    @staticmethod
    def window(now):
        day = now.date() + timedelta(days=1) if now.time() >= time(23, 50) else now.date()
        end = datetime.combine(day, time(7), now.tzinfo)
        start = datetime.combine(day - timedelta(days=1), time(23, 50), now.tzinfo)
        return start, end

    def _budget(self, now, day, samples):
        doc = self.document
        checked, forecast_at = stamp(doc.get('planning_checked_at')), stamp(doc.get('forecast_at'))
        age = number(doc.get('forecast_max_age_hours'))
        if (not checked or not forecast_at or age is None or not 1 <= age <= 24
                or not 0 <= (now-checked).total_seconds() <= 120
                or not 0 <= (now-forecast_at).total_seconds() <= age*3600):
            return None
        values = []
        dates = set()
        for sample in samples:
            at = stamp(str(sample.get('date'))+'T00:00:00'+now.strftime('%z'))
            value = number(sample.get('kwh'))
            if sample.get('complete') is True and at and at.date() < now.date() and 0 < (day-at.date()).days <= 7 and value is not None and value > 0:
                if at.date() in dates:
                    return None
                dates.add(at.date())
                values.append(value)
        if len(values) != 3:
            return None
        # Explicit source-day totals are the tariff policy's primary input.
        totals = doc.get('night_forecasts') or {}
        total = number(totals.get(day.isoformat())) if isinstance(totals, dict) else None
        if total is not None and 0 <= total <= 1000:
            average = sum(values)/3
            return dict(consumption_kwh=round(average, 3), solar_kwh=total,
                        deficit_kwh=round(max(0, average-total), 3),
                        forecast_at=forecast_at.isoformat(), evidence_day=day.isoformat())
        return None

    def evaluate(self, *, now, soc, reserve, capacity, samples, grid_online,
                 automatic, telemetry_valid, mode, current_target, ownership_allowed=None):
        with self.lock:
            return self._evaluate(now=now, soc=soc, reserve=reserve, capacity=capacity,
                samples=samples, grid_online=grid_online, automatic=automatic,
                telemetry_valid=telemetry_valid, mode=mode, current_target=current_target,
                ownership_allowed=automatic if ownership_allowed is None else ownership_allowed)

    def _evaluate(self, *, now, soc, reserve, capacity, samples, grid_online,
                  automatic, telemetry_valid, mode, current_target, ownership_allowed):
        result = dict(phase='inactive', checked_at=now.isoformat(), control_active=False,
                      request=None, target_soc=None, grid_online=grid_online,
                      completed=self.saved.get('completed'))
        current = self.saved.get('current') or {}
        previous_end = stamp(current.get('end'))
        if previous_end and now >= previous_end and not current.get('finished'):
            finished = dict(current, finished=True, end_soc=soc if telemetry_valid and (now-previous_end).total_seconds() <= 90 else None,
                            finished_at=now.isoformat())
            if not self._save(dict(self.saved, current=finished, completed=finished)):
                return dict(result, phase='guarded', reason='Night completion persistence failed')
            result['completed'] = finished
        start, end = self.window(now)
        if not self.enabled or not start <= now < end:
            return result
        day = end.date()
        key = day.isoformat()
        current = self.saved.get('current') or {}
        first = current.get('day') != key
        stage = 'correction' if now.time() < time(7) and now.time() >= time(5) else 'initial'
        reassess = not first and stage == 'correction' and current.get('stage') != stage
        if first or reassess:
            budget = self._budget(now, day, samples)
            saved = dict(self.saved, schema=1)
            source = 'fresh'
            if budget is not None:
                saved['last_valid'] = budget
                saved['missing_nights'] = 0
            elif reassess:
                # An intranight failed refresh is not another missing night.
                budget = {k: current.get(k) for k in ('consumption_kwh', 'solar_kwh', 'deficit_kwh', 'forecast_at')}
                source = current.get('source', 'unavailable')
            else:
                count = int(saved.get('missing_nights', 0)) + 1
                saved['missing_nights'] = count
                old = saved.get('last_valid') or {}
                at = stamp(str(old.get('evidence_day'))+'T00:00:00'+now.strftime('%z'))
                old_gap, old_demand, old_solar = [number(old.get(k)) for k in ('deficit_kwh', 'consumption_kwh', 'solar_kwh')]
                valid_old = (old_gap is not None and old_gap >= 0 and old_demand is not None and old_demand > 0
                             and old_solar is not None and old_solar >= 0
                             and abs(old_gap-max(0,old_demand-old_solar)) < 0.01)
                if count < 3 and at and 0 < (day-at.date()).days < 3 and valid_old:
                    budget, source = old, 'fallback'
                else:
                    budget, source = {}, 'unavailable'
            current = dict(day=key, start=start.isoformat(), end=end.isoformat(),
                decision_at=now.isoformat() if first else current.get('decision_at'),
                stage=stage, source=source, start_soc=current.get('start_soc') if not first else soc if telemetry_valid else None,
                hold_soc=current.get('hold_soc') if not first else None,
                operations=current.get('operations', {}) if not first else {},
                acquired=current.get('acquired', False) if not first else False,
                hold_confirmed=current.get('hold_confirmed', False) if not first else False,
                deficit_kwh=budget.get('deficit_kwh'), consumption_kwh=budget.get('consumption_kwh'),
                solar_kwh=budget.get('solar_kwh'), forecast_at=budget.get('forecast_at'),
                missing_nights=saved.get('missing_nights', 0), finished=False)
            saved['current'] = current
            if not self._save(saved):
                return self._guarded(result, key, mode, ownership_allowed, 'Night decision persistence failed')
        result.update(current)
        result.update(completed=self.saved.get('completed'), checked_at=now.isoformat(), current_soc=soc)
        gap = number(current.get('deficit_kwh'))
        if gap is None:
            return dict(result, phase='skipped', reason='Forecast or three complete consumption days unavailable')
        soc, reserve, capacity = number(soc), number(reserve), number(capacity)
        if (not automatic or not telemetry_valid or soc is None or reserve is None or capacity is None
                or not 0 <= soc <= 100 or not 20 <= reserve <= 95 or not 1 <= capacity <= 1000
                or mode not in {'solar', 'panic', 'panic_grid_hold'}):
            return self._guarded(result, key, mode, ownership_allowed, 'Fresh automatic BR and telemetry required')
        target = min(95, round(reserve+gap/capacity*100, 2))
        result.update(target_soc=target, planned_target_soc=target, reserve_soc=reserve, capacity_kwh=capacity)
        if gap <= 0 and current.get('acquired') is not True:
            return dict(result, phase='not_needed')
        hold = target  # Initial SOC is history, never an extra recharge target.
        if (current.get('hold_soc') != hold or current.get('target_soc') != target
                or current.get('capacity_kwh') != capacity or current.get('reserve_soc') != reserve):
            current = dict(current, hold_soc=hold, target_soc=target, reserve_soc=reserve, capacity_kwh=capacity)
            if not self._save(dict(self.saved, current=current)):
                return self._guarded(result, key, mode, ownership_allowed, 'Night target persistence failed')
        result['target_soc'] = hold
        if grid_online is not True:
            return dict(result, phase='waiting_for_grid', control_active=current.get('acquired') is True)
        if current.get('acquired') is not True:
            if not self._save(dict(self.saved, current=dict(current, acquired=True))):
                return dict(result, phase='guarded', reason='Night ownership persistence failed')
        phase = 'charging' if soc < hold else 'holding'
        request = 'panic' if phase == 'charging' else 'panic_grid_hold'
        if (mode == 'panic_grid_hold' and number(current_target) == hold
                and current.get('hold_confirmed') is not True):
            current = dict(self.saved.get('current') or current, hold_confirmed=True)
            if not self._save(dict(self.saved, current=current)):
                return self._guarded(result,key,mode,ownership_allowed,'Night acknowledgement persistence failed')
        return dict(result, phase=phase, control_active=True,
                    request=None if mode == request and number(current_target) == hold else request)


    def record_operation(self, *, now, soc, preparation, night, owner, charge_a, grid_online):
        """Bounded observed charging evidence, distinct from plans and SOC endpoints."""
        with self.lock:
            current = self.saved.get('current') or {}
            end = stamp(current.get('end'))
            value, amps = number(soc), number(charge_a)
            if (current.get('finished') or end is None or now >= end or value is None
                    or not 0 <= value <= 100 or owner is None or grid_online is not True
                    or owner.get('phase') not in {'charging', 'holding'} or owner.get('acknowledged') is not True):
                return
            key = 'night' if owner is night else 'scheduled'
            operations = dict(current.get('operations') or {})
            prior = operations.get(key) or {}
            if owner.get('phase') == 'holding':
                if not prior or number(owner.get('target_soc')) is None or value < number(owner.get('target_soc')):
                    return
            elif amps is None or amps <= 0:
                return
            at = stamp(prior.get('observed_at'))
            if at and (now-at).total_seconds() < 60:
                return
            operations[key] = dict(prior, start_soc=prior.get('start_soc', value),
                start_at=prior.get('start_at', now.isoformat()), observed_at=now.isoformat(),
                end_soc=max(value, number(prior.get('end_soc')) or value), target_soc=owner.get('target_soc'), outage_start=preparation.get('start') if key == 'scheduled' else None)
            self._save(dict(self.saved, current=dict(current, operations=operations)))


def choose_owner(scheduled, night):
    """Only due owners compete; a future informational target owns nothing."""
    owners = [p for p in (scheduled, night) if p.get('control_active') is True]
    return max(owners, key=lambda p: number(p.get('target_soc')) or 0) if owners else None
