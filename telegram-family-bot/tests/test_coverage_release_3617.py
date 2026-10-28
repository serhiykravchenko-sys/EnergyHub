import unittest
from datetime import timedelta
import test_events as fixture
from app.main import observe_grid_hold


class ReleaseMessageTests(unittest.TestCase):
    setUp=fixture.EventObservationTests.setUp

    def run_release(self, age=0, voltage=230, sufficient=True, soc=95, required=94):
        self.config.dtek_schedule_enabled=True
        now=fixture.NOW
        client=fixture.FakeClient(dict(mode='panic_grid_hold',voltage=voltage,
                                       soc=soc,minimum=40,freshness='fresh'))
        state={}
        observe_grid_hold(self.config,client,state,now)
        client.values['sensor.energyhub_outage_preparation']=dict(state='solar',attributes=dict(
            coverage_release=True,coverage_sufficient=sufficient,coverage_required_soc=required,
            checked_at=(now-timedelta(seconds=age)).isoformat()))
        client.values['mode']='solar'
        observe_grid_hold(self.config,client,state,now+timedelta(seconds=1))
        self.assertEqual([],state.get('pending_notifications',[]))
        observe_grid_hold(self.config,client,state,now+timedelta(seconds=11))
        return state,client,now

    def test_acknowledged_debounced_release_explains_coverage_once(self):
        state,client,now=self.run_release()
        text=state['pending_notifications'][0]['message']
        self.assertIn('Будинок працює без допомоги ДТЕК',text)
        self.assertIn('вистачає до кінця планового відключення',text)
        self.assertIn('40%',text)
        observe_grid_hold(self.config,client,state,now+timedelta(seconds=30))
        self.assertEqual(1,len(state['pending_notifications']))

    def test_stale_or_insufficient_evidence_does_not_claim_coverage(self):
        for args in (dict(age=180),dict(sufficient=False)):
            state,_,_=self.run_release(**args)
            self.assertNotIn('вистачає до кінця',state['pending_notifications'][0]['message'])

    def test_grid_absence_never_claims_acknowledged_release(self):
        state,_,_=self.run_release(voltage=0)
        self.assertEqual([],state.get('pending_notifications',[]))

    def test_coverage_release_uses_its_own_margin_instead_of_normal_plus_ten(self):
        state,_,_=self.run_release(soc=45,required=44)
        self.assertIn('Будинок працює без допомоги ДТЕК',state['pending_notifications'][0]['message'])
