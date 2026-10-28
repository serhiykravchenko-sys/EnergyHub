"""Evaluate actual policy predicates for grid/SOC transitions and stale inputs."""
import json
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
import yaml
from jinja2.nativetypes import NativeEnvironment

ROOT=Path(__file__).resolve().parents[2]
SOC='sensor.powmr_10_2m_battery_soc'
GRID='binary_sensor.energyhub_grid_confirmed'
VOLT='sensor.powmr_10_2m_grid_voltage'

class States:
    def __init__(self,values,at):self.values=values;self.at=at
    def __call__(self,entity):return self.values.get(entity,'unknown')
    def __getitem__(self,entity):return SimpleNamespace(last_reported=self.at)

class GridBatteryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.by_id={str(r['id']):r for r in yaml.safe_load((ROOT/'homeassistant/live/config/automations.yaml').read_text(encoding='utf-8'))}
        cls.env=NativeEnvironment()

    def context(self,rule,soc,grid,*,age=0,pending=False,voltage=None,fresh='fresh',sensor_age=0,cause=None,before=None):
        now=datetime(2026,10,23,12,tzinfo=timezone.utc)
        values={SOC:str(soc),GRID:grid,VOLT:str(voltage if voltage is not None else 230 if grid=='on' else 0),
                'sensor.energyhub_telemetry_freshness':fresh}
        states=States(values,now-timedelta(seconds=sensor_age))
        attrs=dict(checked_at=now.timestamp()-age,confirmation_seconds=180,transition_pending=pending)
        ctx=dict(states=states,is_state=lambda e,s:states(e)==s,now=lambda:now,
                 state_attr=lambda e,k:attrs.get(k),
                 as_timestamp=lambda value,default=0:value.timestamp() if hasattr(value,'timestamp') else default)
        low=rule['triggers'][0]['below'];high=rule['triggers'][1]['above']
        if cause is None:
            try:n=float(soc)
            except (ValueError,TypeError):n=high+1
            cause='grid_returned' if grid=='on' else 'low_soc' if n<low else 'recovered_soc'
        if before is None:before={'grid_returned':'off','grid_lost':'on','low_soc':str(low),'recovered_soc':str(high)}.get(cause,'unavailable')
        after=grid if cause in {'grid_lost','grid_returned'} else str(soc)
        ctx['trigger']=SimpleNamespace(id=cause,from_state=SimpleNamespace(state=before),to_state=SimpleNamespace(state=after))
        for name,source in rule['variables'].items():ctx[name]=self.env.from_string(source).render(**ctx)
        return ctx

    def decisions(self,group,soc,grid,**kwargs):
        r=self.by_id['energyhub_fridge_battery_protection' if group=='fridge' else 'energyhub_battery_discharge_protection']
        ctx=self.context(r,soc,grid,**kwargs)
        valid=bool(ctx['grid_valid']) and all(bool(self.env.from_string(c['value_template']).render(**ctx)) for c in r['conditions'])
        return tuple(valid and bool(self.env.from_string(b['conditions'][0]['value_template']).render(**ctx))
                     for b in r['actions'][-1]['choose'])

    def test_user_fridge_outage_solar_and_grid_return_scenario(self):
        self.assertEqual((True,False),self.decisions('fridge',19,'off'))
        self.assertEqual((False,False),self.decisions('fridge',25,'off'))
        self.assertEqual((False,True),self.decisions('fridge',25,'on'))

    def test_outage_already_below_threshold_and_grid_recovery(self):
        for group,soc in [('fridge',15),('plugs',35)]:
            self.assertEqual((False,True),self.decisions(group,soc,'on'))
            self.assertEqual((True,False),self.decisions(group,soc,'off'))

    def test_strict_boundaries_and_hysteresis(self):
        for group,low,high in [('fridge',20,30),('plugs',40,50)]:
            for soc in (low,low+5,high):self.assertEqual((False,False),self.decisions(group,soc,'off'))
            self.assertEqual((True,False),self.decisions(group,low-1,'off'))
            self.assertEqual((False,True),self.decisions(group,high+1,'off'))

    def test_stale_unknown_pending_or_contradictory_grid_never_switches(self):
        for group in ('fridge','plugs'):
            for grid,kwargs in [('unknown',{}),('unavailable',{}),('on',{'age':31}),
                                ('off',{'pending':True}),('off',{'voltage':230}),
                                ('on',{'voltage':0}),('on',{'fresh':'stale'})]:
                with self.subTest(group=group,grid=grid,kwargs=kwargs):
                    self.assertEqual((False,False),self.decisions(group,10,grid,**kwargs))

    def test_unknown_soc_cannot_switch_on_battery_but_grid_can_restore(self):
        for group in ('fridge','plugs'):
            self.assertEqual((False,False),self.decisions(group,'unavailable','off'))
            self.assertEqual((False,True),self.decisions(group,'unavailable','on'))

    def test_only_real_grid_transitions_and_soc_triggers_exist(self):
        for ident in ('energyhub_fridge_battery_protection','energyhub_battery_discharge_protection'):
            triggers=self.by_id[ident]['triggers']
            self.assertEqual({'on','off'},{t['to'] for t in triggers if t.get('entity_id')==GRID})
            self.assertFalse(any(t.get('id')=='telemetry_recovered' for t in triggers))
            self.assertEqual({('on','off'),('off','on')},{(t['from'],t['to']) for t in triggers if t.get('entity_id')==GRID})

    def test_xiaomi_boiler_off_stays_off_after_sensor_recovery_at_67(self):
        for cause,before in [('grid_lost','unavailable'),('recovered_soc','unavailable'),('telemetry_recovered','stale')]:
            self.assertEqual((False,False),self.decisions('plugs',67,'off',cause=cause,before=before))
        for group in ('fridge','plugs'):
            for before in ('unknown','unavailable'):
                self.assertEqual((False,False),self.decisions(group,67,'on',cause='grid_returned',before=before))

    def test_grid_loss_above_off_threshold_never_restores_manual_off(self):
        for group,soc in [('fridge',67),('plugs',67),('plugs',45)]:
            self.assertEqual((False,False),self.decisions(group,soc,'off',cause='grid_lost',before='on'))
        for group,soc in [('fridge',19),('plugs',39)]:
            self.assertEqual((True,False),self.decisions(group,soc,'off',cause='grid_lost',before='on'))

    def test_grid_return_inside_hysteresis_still_restores(self):
        self.assertEqual((False,True),self.decisions('fridge',25,'on',cause='grid_returned',before='off'))
        self.assertEqual((False,True),self.decisions('plugs',45,'on',cause='grid_returned',before='off'))

    def test_unknown_to_low_soc_does_not_become_a_crossing(self):
        for group,soc in [('fridge',19),('plugs',39)]:
            for before in ('unknown','unavailable','', '-1','101'):
                self.assertEqual((False,False),self.decisions(group,soc,'off',cause='low_soc',before=before))

    def test_soc_crossings_while_grid_available_do_not_override_manual_off(self):
        self.assertEqual((False,False),self.decisions('plugs',51,'on',cause='recovered_soc',before='50'))
        self.assertEqual((False,False),self.decisions('plugs',39,'on',cause='low_soc',before='40'))

    def test_retained_overload_executor_allows_confirmed_grid_at_low_soc(self):
        executor = self.by_id['energyhub_load_control_executor']
        self.assertEqual({'heat_pump_floor_1'},set(executor['actions'][0]['variables']['mapping']))
        self.assertNotIn('native_restore_allowed',executor['actions'][0]['variables'])

    def test_retained_overload_snapshot_has_the_same_grid_aware_interlock(self):
        source=next(a['data']['payload'] for a in self.by_id['energyhub_load_control_snapshot']['actions']
                    if a.get('action')=='mqtt.publish')
        for grid,soc,expected in [('on',25,True),('off',25,False),('off',51,True),('unknown',51,False)]:
            ctx=self.context(self.by_id['energyhub_battery_discharge_protection'],soc,grid)
            ctx['states'].values['automation.energyhub_battery_discharge_protection']='on'
            ctx.update(bridge_ready=True,hp_settings={},hp_normal=False)
            result=self.env.from_string(source).render(**ctx)
            if isinstance(result,str):result=json.loads(result)
            selected={'water_pump','water_boiler','heat_pump_floor_2','heat_pump_floor_3'}
            actual={r['key']:r['restore_allowed'] for r in result['loads'] if r['key'] in selected}
            self.assertEqual({},actual)  # Non-HP1 participants no longer use the Python bridge.
