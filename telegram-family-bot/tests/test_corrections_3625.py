import copy
import unittest
from datetime import timedelta
from types import SimpleNamespace
from app import source_policy, published_schedule, night_charge, outage_schedule
from app.report import overnight_family_event_lines
import test_corrections_3621 as legacy

NOW=legacy.NOW


class MorningAndScheduleTests(unittest.TestCase):
    def setUp(self):
        fixture=legacy.CorrectionTests();fixture.setUp()
        self.cfg,self.doc=fixture.cfg,fixture.document

    def test_unrelated_emergency_does_not_apply_or_cancel_for_household(self):
        state={}
        notice=source_policy.parse('У Бучанському районі діють екстрені відключення. В решті районів діють стабілізаційні відключення.',NOW.isoformat(),NOW)
        source_policy.apply(state,notice,self.cfg,NOW,self.doc)
        for p in ('дача','квартира'):self.assertFalse(source_policy.suspended(state,p))
        self.assertFalse(state.get('pending_notifications'))
        text=source_policy.notification_text(self.cfg,state,NOW,self.doc)
        self.assertNotIn('скасовано',text)
        self.assertNotIn('відновлюємо',text)

    def test_legacy_misscoped_notice_is_repaired_without_false_cancellation(self):
        old=dict(text='У Бучанському районі діють екстрені відключення.',kind='emergency',
                 schedules_invalid=True,cancelled=False,places=['дача','квартира'],revision=NOW.isoformat())
        state=dict(regional_notices={'дача':old,'квартира':old})
        n=source_policy.parse('В усіх районах діють стабілізаційні відключення.',NOW.isoformat(),NOW)
        source_policy.apply(state,n,self.cfg,NOW,self.doc)
        self.assertNotIn('скасовано',source_policy.notification_text(self.cfg,state,NOW,self.doc))
        self.assertFalse(state.get('pending_notifications'))

    def test_refresh_layout_change_elapsed_window_and_proxy_offline_are_silent(self):
        state=dict(apartment_grid={'online':False})
        n=source_policy.parse('В усіх районах діють стабілізаційні відключення.',NOW.isoformat(),NOW)
        source_policy.apply(state,n,self.cfg,NOW,self.doc)
        later=NOW+timedelta(hours=3)
        self.doc['checked_at']=later.isoformat()
        n=source_policy.parse('У Бучанському районі зникло світло через локальну аварію в мережі. В решті районів діють стабілізаційні відключення.',later.isoformat(),later)
        source_policy.apply(state,n,self.cfg,later,self.doc)
        self.assertFalse(state.get('pending_notifications'))
        self.assertFalse(state['apartment_grid']['online'])

    def test_published_rows_omit_past_keep_current_and_future(self):
        start=NOW.replace(hour=6,minute=0);end=NOW.replace(hour=8,minute=30)
        self.doc['groups']['2.2']=[dict(start=start.isoformat(),end=end.isoformat()),*self.doc['groups']['2.2']]
        text='\n'.join(published_schedule.lines(self.cfg,{},NOW,self.doc))
        self.assertIn('до кінця дня',text);self.assertNotIn('06:00',text);self.assertIn('15:00–19:00',text)
        later=NOW.replace(hour=19,minute=0);self.doc['checked_at']=later.isoformat()
        text='\n'.join(published_schedule.lines(self.cfg,{},later,self.doc))
        self.assertNotIn('15:00–19:00',text);self.assertIn('немає',text)

    def test_completion_survives_delayed_freshness_and_forecast_revision(self):
        now=NOW.replace(hour=8,minute=0)
        completed=dict(day=now.date().isoformat(),end=now.replace(hour=7).isoformat(),
            finished_at=now.replace(hour=7,second=5).isoformat(),finished=True,source='fresh',
            start_soc=66,end_soc=66,target_soc=49.69,reserve_soc=40,capacity_kwh=16,
            consumption_kwh=13.107,solar_kwh=11.5569,deficit_kwh=1.55,hold_confirmed=True)
        client=SimpleNamespace(state=lambda _:dict(attributes=dict(checked_at=(now+timedelta(seconds=30)).isoformat(),completed=completed)))
        text=night_charge.morning(client,now)
        # Consumption is displayed once by the enclosing overnight report.
        for value in ('прогноз','11.6','1.6 kWh','Ціль:'):self.assertIn(value,text)
        completed['day']='2020-01-01'
        self.assertIn('не підтверджено',night_charge.morning(client,now))

    def test_release_threshold_never_becomes_measured_soc(self):
        event=dict(kind='grid_hold_released',created_at=NOW.isoformat(),release_soc=50,soc=66)
        text='\n'.join(overnight_family_event_lines([event]))
        self.assertIn('66%',text);self.assertNotIn('50%',text)
        event.pop('soc')
        self.assertNotIn('50%','\n'.join(overnight_family_event_lines([event])))

    def test_preparation_explains_gross_solar_and_house_use(self):
        data=dict(capacity_kwh=16,forecast_net_solar_kwh=1.3,required_grid_kwh=3.66,
            preparation_gross_solar_kwh=4,preparation_house_kwh=2.5,
            preparation_forecast_until=NOW.replace(hour=13,minute=30).isoformat())
        energy,text=outage_schedule.preparation_energy_details(data,64,95)
        for value in ('4.0 kWh','3.7 kWh','2.5 kWh','13:30'):self.assertIn(value,text)
        self.assertIn('5.0 kWh',energy);self.assertNotIn('надлишок сонця',text)
