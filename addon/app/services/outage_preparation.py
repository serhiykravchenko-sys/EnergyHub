"""Bounded outage planning. Only the existing controller may execute intents."""
import json
import math
import threading
from pathlib import Path
from app.utils.json_store import atomic_write_json
from functools import wraps
from app.services.battery_discharge_window import BatteryDischargeWindow, checked_start
from datetime import datetime, timedelta, timezone
from app.services.preparation_demand import PreparationDemand


TOPIC = 'energyhub/input/outage/schedule'
STATUS_TOPIC = 'energyhub/outage/preparation'


def grid_headroom(solar_charge_a, grid_limit_a=60, combined_limit_a=120):
    """Battery-side currents, never PV string amperes or an AC input limit."""
    return min(grid_limit_a,max(0,combined_limit_a-solar_charge_a))


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def stamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def forecast_period_key(row):
    """Order instants, not local timestamp text across a DST clock change."""
    at = stamp(row['start'])
    if at is None:
        raise ValueError('Forecast period requires an aware start timestamp')
    return at.timestamp()


def synchronized(method):
    @wraps(method)
    def call(self,*args,**kwargs):
        with self.lock:
            return method(self,*args,**kwargs)
    return call


class OutagePreparation:
    def __init__(self, options, path=None):
        self.lock=threading.RLock()
        self.enabled = options.get('outage_preparation_enabled') is True
        self.group = str(options.get('outage_group', ''))
        self.capacity = None  # HA helper is the sole runtime capacity source.
        self.heating_rate = None  # Derived SOC/hour, not another user setting.
        self.grid_a = None
        self.total_a = number(options.get('outage_combined_charge_a', 120))
        self.margin = number(options.get('outage_preparation_margin_minutes', 30))
        self.snapshot = None
        self.forecast_document = {}
        self.source_status = 'unavailable'
        self.source_checked_at = None
        self.emergency_notice_active = False
        self.emergency_grid_state = 'unknown'
        self.phase = 'inactive'
        self.last = {}
        self.path = Path(path) if path is not None else None
        self.active_context = {}
        self.next_assessment = None
        self.assessment_plan = None
        self.previous_grid = None
        self.current_from_ha = self.grid_a
        self.soc_for_forecast = None
        self.discharge_window = BatteryDischargeWindow()
        self.planning_settings = {}
        self.forecast_age_seconds = 0
        self.window_observation = {}
        self.preparation_demand = PreparationDemand()
        if self.path is not None:
            try:
                saved = json.loads(self.path.read_text(encoding='utf-8'))
                self.active_context = saved if isinstance(saved, dict) and saved.get('schema') == 1 else {}
            except (OSError, ValueError):
                pass

    def _remember(self, context):
        if context.get('start') == self.active_context.get('start'):
            for key in ('charging_started_at','ownership_released'):
                if key not in context and key in self.active_context:
                    context=dict(context,**{key:self.active_context[key]})
        context = dict(context, completed_windows=context.get('completed_windows',
                       self.active_context.get('completed_windows', []))[-12:])
        if self.path is not None:
            try:
                atomic_write_json(self.path, context, ensure_ascii=False, indent=2)
            except Exception:
                return False
        self.active_context = context
        return True

    @staticmethod
    def _next_slot(now):
        at = now.replace(second=0, microsecond=0)
        return at + timedelta(minutes=(15-now.minute) % 30 or 30)

    @synchronized
    def update(self, payload):
        # Invalid/new unavailable evidence replaces old evidence, never silently
        # retains an older superseded schedule as a confirmed charging plan.
        self.snapshot = None
        self.capacity = None
        self.planning_settings = {}
        self.forecast_age_seconds = 0
        self.forecast_document = {}
        self.source_status = 'unavailable'
        self.source_checked_at = None
        self.emergency_notice_active = False
        self.emergency_grid_state = 'unknown'
        try:
            item = json.loads(payload) if isinstance(payload, str) else payload
            if not isinstance(item, dict) or item.get('schema') != 1:
                return False
            self.planning_checked_at = item.get('planning_checked_at')
            if item.get('region') != 'kyiv_region' or item.get('source') not in {
                    'bezsvitla','dtek_official','alerts_energy','pro_kyiv','schedule_sources'}:
                return False
            # Solar forecast authority is independent of schedule suspension.
            self.forecast_document = {key: item.get(key) for key in ('checked_at', 'forecast_at', 'forecast', 'night_forecasts', 'hp_running', 'hp_state', 'hp_state_since', 'heating_checked_at', 'forecast_max_age_hours')}
            self.current_from_ha = number(item.get('grid_charge_current_a'))
            self.grid_a = self.current_from_ha
            self.planning_settings = {k: number(item.get(k)) for k in (
                'capacity_kwh', 'house_demand_kw', 'forecast_max_age_hours',
                'load_off_soc', 'load_restore_soc')}
            self.capacity = self.planning_settings['capacity_kwh']
            demand = self.planning_settings['house_demand_kw']
            self.heating_rate = demand/self.capacity*100 if demand is not None and self.capacity and self.capacity>0 else None
            age = self.planning_settings['forecast_max_age_hours']
            self.forecast_age_seconds = age*3600 if age is not None and 1 <= age <= 24 else 0
            self.source_status = item.get('source_status', 'unavailable')
            self.source_checked_at = item.get('checked_at') if stamp(item.get('checked_at')) else None
            self.emergency_notice_active = item.get('emergency_notice_active') is True
            self.emergency_grid_state = item.get('emergency_grid_state', 'unknown')
            if not stamp(item.get('checked_at')) or not stamp(item.get('published_at')):
                return False
            if item.get('source_status') != 'fresh' or item.get('validated') is not True:
                return False
            intervals = item.get('groups', {}).get(self.group)
            if not isinstance(intervals, list) or len(intervals) > 12:
                return False
            parsed = []
            for row in intervals:
                start, end = stamp(row.get('start')), stamp(row.get('end'))
                if not start or not end or not 0 < (end-start).total_seconds() <= 86400:
                    return False
                parsed.append((start, end))
            parsed.sort()
            if any(b[0] < a[1] for a, b in zip(parsed, parsed[1:])):
                return False
            self.snapshot = dict(item, intervals=parsed)
            return True
        except (ValueError, TypeError, AttributeError):
            return False

    @synchronized
    def evaluate(self, *, now, soc, voltage, charge_a, solar_w, load_w,
                 grid_online, mode, automatic, base_reserve, telemetry_valid, current_target=None, weather_modifier=0, weather_days=None,
                 ownership_allowed=None):
        measured_preparation_kw = self.preparation_demand.observe(now, load_w, telemetry_valid)
        result = dict(phase='inactive', control_active=False, target_soc=None,
                      checked_at=now.isoformat(), request=None,
                      source_status=self.source_status, source_checked_at=self.source_checked_at,
                      enabled=self.enabled)
        result.update(emergency_notice_active=self.emergency_notice_active,
                      emergency_grid_state=self.emergency_grid_state)
        observed_discharge = self.discharge_window.average_kw(now)
        result.update(observed_net_discharge_kw=observed_discharge,
                      discharge_window_minutes=60,
                      discharge_check_source='rolling battery flow' if observed_discharge is not None else 'configured planning fallback')
        result['forecast_source_at']=self.forecast_document.get('forecast_at')
        periods = self.forecast_document.get('forecast')
        result['forecast_period_count'] = len(periods) if isinstance(periods, list) else None
        result['forecast_first_period'] = periods[0].get('start') if isinstance(periods, list) and periods and isinstance(periods[0], dict) else None
        result['forecast_last_period'] = periods[-1].get('end') if isinstance(periods, list) and periods and isinstance(periods[-1], dict) else None
        self.last = result
        # Missing HA settings must not hand an owned charging episode to an
        # unrelated controller. Retain its last persisted intent, send no write.
        saved_end = stamp(self.active_context.get('end'))
        saved_target = number(self.active_context.get('target_soc'))
        if (self.active_context.get('schema') == 1 and saved_target is not None
                and self.active_context.get('ownership_released') is not True
                and self.snapshot is not None
                and any(a.isoformat() == self.active_context.get('start') and now < b
                        for a,b in self.snapshot.get('intervals', []))
                and 20 <= saved_target <= 95 and mode in {'panic','panic_grid_hold'}
                and (automatic if ownership_allowed is None else ownership_allowed)
                and (saved_end is None or now < saved_end)):
            result.update(control_active=True, target_soc=saved_target)
        config = (self.capacity, self.heating_rate, self.grid_a, self.total_a, self.margin)
        if (not self.enabled or not all(number(x) is not None for x in config)
                or not 0 < self.capacity <= 1000 or not self.heating_rate > 0
                or not 0 < self.grid_a <= 60 or not self.grid_a <= self.total_a <= 120
                or not 0 <= self.margin <= 120):
            result.update(phase='guarded', coverage_reason='Valid HA planning settings are required')
            return result
        fixed_demand = self.planning_settings.get('house_demand_kw')
        if fixed_demand is None or not 0.1 <= fixed_demand <= 100 or not self.forecast_age_seconds:
            result.update(phase='guarded', coverage_reason='Set valid HA battery capacity, house demand and forecast age')
            return result
        document = self.snapshot
        if not document:
            result['phase'] = 'source_unavailable'
            return result
        age = (now-stamp(document['checked_at'])).total_seconds()
        publication_age = (now-stamp(document['published_at'])).total_seconds()
        if not -60 <= age <= 2100 or not -60 <= publication_age <= 48*3600:
            result['phase'] = 'source_stale'
            return result
        # A scheduled window remains relevant until its end. Neither a late
        # start nor an early restoration proves that further cuts cannot occur.
        current = next(((a, b) for a, b in document['intervals'] if a <= now < b), None)
        upcoming = [(a, b) for a, b in document['intervals']
                    if now < a <= now+timedelta(hours=24)]
        if not current and not upcoming:
            result['phase'] = 'no_upcoming_outage'
            return result
        start, end = current or upcoming[0]
        # Missing telemetry must not hand an already owned preparation to the
        # ordinary reserve controller. Retain intent, issue no new command.
        context = self.active_context
        owned = (context.get('schema') == 1
                 and number(context.get('target_soc')) is not None
                 and 20 <= number(context.get('target_soc')) <= 95
                 and context.get('start') == start.isoformat()
                 and context.get('ownership_released') is not True
                 and mode in {'panic', 'panic_grid_hold'}
                 and (automatic if ownership_allowed is None else ownership_allowed))
        if owned:
            result.update(control_active=True, target_soc=context['target_soc'],
                          start=start.isoformat(), end=end.isoformat())
        planning_start = now if current else start
        result.update(window_active=current is not None,
                      remaining_window_minutes=math.ceil((end-planning_start).total_seconds()/60))
        planning_voltage=number(voltage)
        if planning_voltage is None or not 40 <= planning_voltage <= 65:
            result['phase']='guarded'
            return result
        if self.current_from_ha is None or not 0 < self.current_from_ha <= 60:
            result.update(phase='guarded', coverage_reason='Set the verified grid DC charging current on the dashboard')
            return result
        self.grid_a = self.current_from_ha
        result['grid_charge_current_a'] = self.grid_a
        grid_kw=self.grid_a*planning_voltage/1000*0.9
        heating_at=stamp(document.get('heating_checked_at'))
        selection=document.get('heating_policy')
        heating_known=(heating_at is not None and -60 <= (now-heating_at).total_seconds() <= 120
                       and selection in {'Smart','Solar-only','Off'})
        smart=selection=='Smart' if heating_known else True
        rate=fixed_demand/self.capacity*100
        self.planning_demand=fixed_demand
        observed_demand = None
        hp_running = heating_known and document.get('hp_running') is True
        hp_since=stamp(document.get('hp_state_since'))
        hp_baseline=hp_running and hp_since is not None and (now-hp_since).total_seconds()>=10800
        hp_known=heating_known and document.get('hp_state') in {'off','heat','cool'}
        result.update(observed_house_demand_kw=observed_demand,
                      demand_source='HA configured total house demand (includes HP)',
                      hp_start_permitted=False)
        hours=(end-planning_start).total_seconds()/3600
        weather=(20 if start.astimezone(now.tzinfo).date().isoformat() in weather_days else 0) if weather_days is not None else number(weather_modifier)
        if weather not in (0,20):
            result['phase']='guarded'
            return result
        demand=self.planning_demand
        observed_load=number(load_w)
        self.soc_for_forecast = number(soc)
        deficit=self._outage_deficit(document,now,planning_start,end,planning_voltage,demand,solar_w,charge_a) if telemetry_valid else None
        required=deficit['peak_kwh'] if deficit is not None else demand*hours
        base=number(base_reserve)
        # Applied BR already owns schedule/weather/emergency allowances. Only
        # a newly applicable future-day weather increment may be added once.
        current_weather = number(weather_modifier) or 0
        planning_reserve = min(95, (base or 20) + max(0, weather-current_weather))
        raw_target=planning_reserve+required/self.capacity*100
        target=min(95,max(math.ceil(raw_target),base or 20))
        if current and owned:
            # Retain the acquired command target across offline/restart gaps.
            # Remaining-window coverage below may release this ownership;
            # the latched target is never proof that a hold is still needed.
            target = max(target, number(context.get('target_soc')) or target)
        result.update(start=start.isoformat(),end=end.isoformat(),target_soc=target,
                      capacity_shortfall_soc=max(0, raw_target-95),
                      coverage_capacity_insufficient=raw_target>95,
                      uncapped_target_soc=raw_target,weather_modifier_percent=weather,capacity_kwh=self.capacity,
                      capacity_is_assumption=True,energy_kwh=demand*hours,
                      outage_forecast_complete=deficit is not None,
                      outage_credited_solar_kwh=deficit['solar_kwh'] if deficit else 0,
                      outage_required_battery_kwh=required,
                      outage_planning_load_kw=demand,
                      soc_per_outage_hour=rate,smart_heating=smart,
                      heating_evidence_confirmed=heating_known,source_url=document.get('source_url'))
        release_required=raw_target+5
        result.update(coverage_required_soc=release_required, release_margin_percent=5,
                      ordinary_reserve_soc=base, coverage_sufficient=False,
                      coverage_release=False,
                      coverage_reason='Waiting for valid telemetry and control authority')
        values = tuple(number(x) for x in (soc, voltage, charge_a, solar_w, load_w))
        if (not telemetry_valid or any(x is None for x in values)
                or not 0 <= values[0] <= 100 or not 40 <= values[1] <= 65
                or not 0 <= values[2] <= 200 or min(values[3:]) < 0
                or base is None or not 20 <= base <= 95 or not automatic
                or mode not in {'solar', 'panic', 'panic_grid_hold'}):
            result['phase'] = 'guarded'
            if owned:
                result['target_soc'] = context['target_soc']
                result['reason'] = 'Owned preparation awaiting valid control evidence'
            return result
        soc, voltage, charge_a, solar_w, load_w = values
        result['current_soc']=soc
        # Assess the entire path from now through the outage, not only the
        # daily total or the deficit after its start. Grid state is not an
        # energy assumption; confirmed telemetry/authority still guard writes.
        bridge=self._outage_deficit(document,now,now,end,voltage,demand,solar_w,charge_a)
        floor=planning_reserve
        minimum=soc-bridge['peak_kwh']/self.capacity*100 if bridge else None
        if bridge and observed_discharge is not None and observed_discharge > 0:
            coverage_at=stamp(bridge.get('coverage_at'))
            if coverage_at:
                observed_bridge=observed_discharge*max(0,(coverage_at-now).total_seconds()/3600)
                minimum=min(minimum,soc-observed_bridge/self.capacity*100)
        solar_safe=((not smart or hp_known)
                    and bridge is not None and bridge.get('coverage_at') is not None
                    and minimum>floor+5)
        result.update(solar_bridge_safe=solar_safe, predicted_minimum_soc=minimum,
                      hp_start_permitted=solar_safe and smart and document.get('hp_state')=='off',
                      house_planning_demand_kw=demand,
                      solar_covers_house_at=bridge.get('coverage_at') if bridge else None)
        if solar_safe and not current:
            intent=dict(schema=1,start=start.isoformat(),end=end.isoformat(),target_soc=target,
                        ownership_released=True,charging_started_at=None,
                        completed_windows=self.active_context.get('completed_windows', []))
            if intent != self.active_context and not self._remember(intent):
                result.update(phase='guarded',control_active=owned,request=None,
                              reason='Preparation intent persistence failed')
                return result
            releasing=mode in {'panic','panic_grid_hold'}
            result.update(phase='solar',control_active=releasing,request='solar' if releasing else None,
                          coverage_release=True,coverage_sufficient=True,
                          coverage_required_soc=floor+5+bridge['peak_kwh']/self.capacity*100,
                          release_margin_percent=5,solar_forecast_complete=True,
                          reason='Accepted solar forecast and configured house demand cover the battery bridge',
                          coverage_reason='Forecast minimum remains above active reserve plus five points')
            return result
        result.update(coverage_sufficient=soc>=release_required,
                      coverage_reason=('Battery covers the remaining outage plus reserve and margin'
                                       if soc>=release_required else
                                       'Battery does not cover the remaining outage plus reserve and margin'))
        remaining=max(0,target-soc)/100*self.capacity
        completion=now if current else start-timedelta(minutes=self.margin)
        preparation_kw = measured_preparation_kw if measured_preparation_kw is not None else self.planning_demand
        result.update(preparation_house_demand_kw=preparation_kw,
                      preparation_demand_source='rolling measured hour' if measured_preparation_kw is not None else 'configured fallback',
                      preparation_house_kwh=max(0,(start-now).total_seconds()/3600)*preparation_kw,
                      preparation_forecast_until=start.isoformat())
        self.preparation_gross_solar_kwh = None
        budget=self._forecast_budget(document,now,completion,voltage,preparation_kw,solar_w,charge_a)
        budget_reason = self.preparation_solar_reason
        # Explain gross generation to the advertised deadline; control still
        # credits only the earlier completion budget with its existing margin.
        display_budget = self._forecast_budget(document,now,start,voltage,preparation_kw,solar_w,charge_a) if not current else None
        result['preparation_solar_reason'] = budget_reason
        result['preparation_generation_reason'] = self.preparation_solar_reason if not current else 'window_started'
        result['preparation_gross_solar_kwh'] = self.preparation_gross_solar_kwh if display_budget is not None else None
        solar_energy=sum(row[2]*(row[1]-row[0]).total_seconds()/3600 for row in budget) if budget is not None else 0
        grid_energy=max(0,remaining-solar_energy)
        # Work backward through forecast periods using grid headroom under the
        # combined limit. Missing forecast never credits promised solar.
        rows=budget if budget is not None else [(now,max(now,completion),0,grid_kw)]
        needed=grid_energy
        charge_start=completion
        grid_hours=0.0
        for a,b,solar_kw,available_grid_kw in reversed(rows):
            hours=max(0,(b-a).total_seconds()/3600)
            use=min(hours,needed/available_grid_kw) if available_grid_kw>0 else 0
            if use>0:
                charge_start=b-timedelta(hours=use)
                grid_hours+=use
                needed=max(0,needed-available_grid_kw*use)
            if needed<=1e-9:
                break
        if needed>1e-9:
            charge_start=now
        original_start = charge_start
        charge_start, waiting_loss = checked_start(
            now=now, completion=completion, planned_start=charge_start,
            gap_kwh=remaining, solar_kwh=solar_energy, rows=rows,
            discharge_kw=observed_discharge, soc=soc, reserve=base,
            capacity=self.capacity)
        result.update(discharge_check_advanced_start=charge_start < original_start,
                      predicted_waiting_discharge_kwh=waiting_loss,
                      configured_grid_start=original_start.isoformat())
        # Include the additional waiting depletion in the communicated estimate.
        if waiting_loss:
            grid_energy=max(0,remaining+waiting_loss-solar_energy)
            needed=grid_energy
            grid_hours=0.0
            for a,b,_,available_grid_kw in reversed(rows):
                hours=max(0,(b-max(a,charge_start)).total_seconds()/3600)
                use=min(hours,needed/available_grid_kw) if available_grid_kw>0 else 0
                grid_hours+=use
                needed=max(0,needed-available_grid_kw*use)
        interval = dict(start=start.isoformat(), end=end.isoformat())
        context = self.active_context
        # Ownership follows the persisted window and control authority, not
        # target equality. Planner/controller persistence can straddle a restart.
        started = owned
        authorized_at=stamp(context.get('charging_started_at'))
        # Legacy journals can contain the old reserve-boundary acquisition.
        # Revalidate only with full fresh control authority and actual grid;
        # ordinary BR then owns any immediate recovery/hold. Never discard an
        # explicitly authorized new episode or release during an outage/gap.
        if (started and not current and (authorized_at is None or authorized_at>now)
                and now < charge_start and grid_online is True and automatic):
            intent=dict(context,ownership_released=True)
            if not self._remember(intent):
                result.update(phase='guarded',control_active=True,target_soc=context['target_soc'],
                              reason='Preparation handback persistence failed',request=None)
                return result
            context=self.active_context
            started=owned=False
            result.update(control_active=False,legacy_ownership_released=True)
        plan_key = (start.isoformat(), end.isoformat(), target, document.get('forecast_at'),
                    self.capacity, self.planning_demand, self.grid_a, self.forecast_age_seconds)
        restored = grid_online and self.previous_grid is False
        assessment_due = (self.next_assessment is None or now >= self.next_assessment
                          or self.assessment_plan != plan_key or restored)
        if assessment_due:
            self.next_assessment = self._next_slot(now)
            self.assessment_plan = plan_key
        self.previous_grid = grid_online
        result.update(assessment_due=assessment_due, next_assessment_at=self.next_assessment.isoformat(),
                      observed_charge_a=charge_a)
        enough_solar=budget is not None and solar_energy>=remaining+waiting_loss
        if current:
            # Charging is capped; remaining-window coverage is never capped.
            # Instantaneous sunshine cannot replace the deficit/coverage check.
            solar_safe=soc>=release_required
            if grid_online is True and solar_safe:
                intent=dict(schema=1, **interval, target_soc=target,
                            ownership_released=True,charging_started_at=None,
                            completed_windows=self.active_context.get('completed_windows', []))
                if intent != self.active_context and not self._remember(intent):
                    result.update(phase='guarded',reason='Preparation intent persistence failed',
                                  control_active=owned, request=None,
                                  target_soc=context['target_soc'] if owned else target)
                    return result
                releasing=mode in {'panic','panic_grid_hold'}
                result.update(phase='solar',control_active=releasing,battery_ready=True,
                              coverage_release=True,
                              reason='Remaining outage covered; resume ordinary Battery Reserve',
                              request='solar' if releasing else None)
                self.phase='solar'
                self.last_start=start.isoformat()
                return result
        # A sufficient battery does not acquire grid ownership. Reassess at
        # :15/:45; the existing margin and actual latest-safe start stay bounded.
        result.update(solar_forecast_complete=budget is not None,forecast_net_solar_kwh=solar_energy,
                      required_grid_kwh=grid_energy,estimated_grid_minutes=math.ceil((grid_hours+needed/grid_kw)*60),
                      planned_grid_start=charge_start.isoformat(),charge_deadline=completion.isoformat(),
                      preparation_time_insufficient=needed>1e-9,
                      estimated_grid_current_headroom_a=grid_headroom(charge_a if solar_w>load_w else 0,self.grid_a,self.total_a))
        need_grid=bool(current) or started or (grid_energy>0 and not enough_solar and (
            now>=charge_start or (assessment_due and self.next_assessment>=charge_start)))
        if not current and not started and remaining<=0 and not need_grid:
            result.update(phase='waiting', battery_ready=True)
            self.phase='waiting'
            self.last_start=start.isoformat()
            return result
        if grid_online is not True:
            result['phase'] = 'waiting_for_grid'
            result['coverage_reason']='Grid availability is unconfirmed or offline; no new strategy command'
            # Preserve validated preparation ownership during supply loss. Do
            # not issue a charging command or let ordinary reserve replace its
            # target solely because one raw voltage sample is offline.
            result['control_active'] = started
            if started:
                intent=dict(schema=1, **interval, target_soc=target,
                            charging_started_at=context.get('charging_started_at'),
                            ownership_released=context.get('ownership_released',False),
                            completed_windows=context.get('completed_windows', []))
                if intent != self.active_context and not self._remember(intent):
                    result.update(phase='guarded', reason='Preparation intent persistence failed',
                                  target_soc=context['target_soc'], request=None)
            return result
        if started or need_grid:
            intent=dict(schema=1, **interval, target_soc=target,
                        charging_started_at=(context['charging_started_at'] if started and authorized_at is not None and authorized_at<=now else now.isoformat()),
                        ownership_released=False,
                        completed_windows=self.active_context.get('completed_windows', []))
            if intent != self.active_context and not self._remember(intent):
                result.update(phase='guarded', reason='Preparation intent persistence failed',
                              control_active=owned, request=None,
                              target_soc=context['target_soc'] if owned else target)
                return result
            if remaining <= 0:
                result.update(phase='holding', control_active=True,
                              request='panic_grid_hold' if mode != 'panic_grid_hold' or number(current_target)!=target else None)
            else:
                result.update(phase='charging', control_active=True,
                              request='panic' if mode != 'panic' or number(current_target)!=target else None)
        else:
            result['phase'] = 'solar' if enough_solar else 'waiting'
        self.phase = result['phase']
        self.last_start = start.isoformat()
        return result

    def _outage_deficit(self,document,now,start,end,voltage,demand,actual_pv_w,charge_a):
        """Peak deficit, never credit future sunshine against an earlier shortfall."""
        at=stamp(document.get('forecast_at'))
        source=document.get('forecast')
        pv=number(actual_pv_w);amps=number(charge_a)
        if (not at or not -60 <= (now-at).total_seconds() <= self.forecast_age_seconds
                or not isinstance(source,list) or not source or len(source)>100
                or pv is None or pv<0 or amps is None or not 0<=amps<=200):
            return None
        try:
            rows=[];scale=1.0
            for row in sorted(source,key=forecast_period_key):
                a,b,kw=stamp(row['start']),stamp(row['end']),number(row['pv_kw'])
                if not a or not b or kw is None or not 0<=kw<=30 or not 0<(b-a).total_seconds()<=3600:
                    return None
                rows.append((a,b,kw))
                if a<=now<b and kw>0.1 and (self.soc_for_forecast is None or self.soc_for_forecast<95):
                    scale=min(1,pv/1000/kw)
            if any(b[0]<a[1] for a,b in zip(rows,rows[1:])):
                return None
            cursor=start;deficit=peak=solar=covered=0.0
            coverage_at=None
            for a,b,kw in rows:
                if self.last.get('observed_house_demand_kw') is not None:
                    a,b=a+timedelta(minutes=30),b+timedelta(minutes=30)
                if b<=cursor:continue
                if a>cursor:return None
                right=min(b,end)
                hours=(right-cursor).total_seconds()/3600
                credited=kw*scale*0.8
                # PV first covers the house; remaining charge respects hardware limit.
                surplus=min(max(0,credited-demand),self.total_a*voltage/1000*0.9)
                net=(max(0,demand-credited)/(0.9 if self.last.get('observed_house_demand_kw') is not None else 1))-surplus
                deficit=max(0,deficit+net*hours)
                peak=max(peak,deficit);solar+=credited*hours
                covered=covered+hours if credited>=demand else 0
                if covered>=1 and coverage_at is None:
                    coverage_at=(right-timedelta(hours=covered)).isoformat()
                cursor=right
                if cursor>=end:
                    return dict(peak_kwh=peak,solar_kwh=solar,coverage_at=coverage_at)
        except (KeyError,TypeError,ValueError):
            return None
        return None

    def _forecast_budget(self,document,now,until,voltage,demand,actual_pv_w,charge_a):
        self.preparation_solar_reason = 'invalid_periods'
        def unavailable(reason):
            self.preparation_solar_reason = reason
            return None
        evidence_at=stamp(document.get('forecast_at'))
        if not evidence_at:
            return unavailable('missing_refresh_time')
        if not -60 <= (now-evidence_at).total_seconds() <= self.forecast_age_seconds:
            return unavailable('stale_forecast')
        if until<=now:
            return unavailable('window_started')
        source=document.get('forecast',[])
        if not isinstance(source,list) or len(source)>100:
            return None
        if not source:
            return unavailable('missing_hourly_forecast')
        cursor=now
        result=[]
        gross_energy=0.0
        scale=1.0
        try:
            parsed=[]
            for row in sorted(source,key=forecast_period_key):
                a,b,kw=stamp(row['start']),stamp(row['end']),number(row['pv_kw'])
                if not a or not b or kw is None or not 0<=kw<=30 or not 0<(b-a).total_seconds()<=3600:
                    return None
                parsed.append((a,b,kw))
                if a<=now<b and kw>0.1 and (self.soc_for_forecast is None or self.soc_for_forecast<95):
                    # Compare gross PV with the current forecast; midnight zero
                    # forecast permits future sunrise energy, while observed
                    # daytime underperformance advances the grid deadline.
                    if number(actual_pv_w) is None:
                        self.preparation_solar_reason = 'missing_current_pv'
                    scale=min(1,actual_pv_w/1000/kw)
            if any(b[0]<a[1] for a,b in zip(parsed,parsed[1:])):
                return unavailable('overlapping_periods')
            for a,b,kw in parsed:
                if b<=cursor:continue
                if a>cursor:return unavailable('coverage_gap')
                right=min(b,until)
                gross_energy += kw*scale*(right-cursor).total_seconds()/3600
                solar=min(max(0,kw*scale-demand)*0.8,self.total_a*voltage/1000*0.9)
                solar_a=solar*1000/voltage
                grid=grid_headroom(solar_a,self.grid_a,self.total_a)*voltage/1000*0.9
                result.append((cursor,right,solar,grid))
                cursor=right
                if cursor>=until:
                    self.preparation_solar_reason = 'complete'
                    self.preparation_gross_solar_kwh = gross_energy
                    return result
        except (KeyError,TypeError,ValueError):
            return None
        return unavailable('incomplete_coverage')
