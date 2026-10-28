import unittest
from datetime import timedelta
import test_outage_preparation as fixtures


class WindowTests(unittest.TestCase):
    def setUp(self):
        f=fixtures.OutageTests();f.setUp()
        self.plan,self.doc,self.args=f.plan,f.document,f.args
        self.plan.evaluate(**self.args)
        self.start=fixtures.NOW+timedelta(hours=2)

    def tick(self, seconds, **kwargs):
        now=self.start+timedelta(seconds=seconds)
        self.doc['checked_at']=now.isoformat()
        self.plan.update(self.doc)
        args=dict(self.args,now=now,mode='solar',soc=96,current_target=None)
        args.update(kwargs)
        return self.plan.evaluate(**args)

    def test_late_cut_keeps_window_active_and_reduces_remaining_target(self):
        initial=self.tick(0,soc=90)
        self.assertTrue(initial['control_active'])
        self.assertEqual('charging',initial['phase'])
        late=self.tick(9000,soc=64)
        self.assertTrue(late['window_active'])
        self.assertEqual(90,late['remaining_window_minutes'])
        self.assertEqual(70,late['target_soc'])
        self.assertEqual('charging',late['phase'])
        self.assertFalse(late.get('outage_not_started',False))
        offline=self.tick(9001,soc=64,grid_online=False)
        self.assertFalse(offline['control_active'])
        self.assertIsNone(offline['request'])
        self.assertEqual('waiting_for_grid',offline['phase'])

    def test_early_restoration_protects_remaining_window_and_second_cut(self):
        self.tick(0)
        self.tick(60,grid_online=False)
        result=self.tick(120,soc=60)
        self.assertTrue(result['window_active'])
        self.assertEqual('panic',result['request'])
        self.assertTrue(result['control_active'])
        self.tick(900,grid_online=False)
        self.assertTrue(self.tick(1000,soc=60)['control_active'])

    def test_mid_window_restart_and_old_completed_journal_do_not_skip_window(self):
        self.plan.active_context['completed_windows']=[self.start.isoformat()+'/'+(self.start+timedelta(hours=4)).isoformat()]
        result=self.tick(9000,soc=60)
        self.assertTrue(result['window_active'])
        self.assertEqual('charging',result['phase'])

    def test_target_surplus_releases_owned_hold_before_window_end(self):
        result=self.tick(9000,soc=96,mode='panic_grid_hold',current_target=95)
        self.assertEqual(95,result['target_soc'])
        self.assertTrue(result['control_active'])
        self.assertEqual('solar',result['request'])
        self.assertEqual('solar',self.tick(9001,soc=95,mode='panic_grid_hold',current_target=95)['phase'])
        self.assertEqual('solar',self.tick(9002,soc=94,mode='panic_grid_hold',current_target=95)['request'])

    def test_complete_forecast_credits_remaining_window_only(self):
        now=self.start+timedelta(hours=2)
        self.doc.update(forecast_at=now.isoformat(),forecast=[dict(start=(now+timedelta(hours=i)).isoformat(),
            end=(now+timedelta(hours=i+1)).isoformat(),pv_kw=8) for i in range(2)])
        r=self.tick(7200,soc=60,solar_w=8000,load_w=1000,charge_a=120)
        self.assertTrue(r['outage_forecast_complete'])
        self.assertEqual(40,r['target_soc'])
        self.assertEqual('solar',r['phase'])
        self.doc['forecast'].pop()
        r=self.tick(7201,soc=60,solar_w=8000,charge_a=120)
        self.assertFalse(r['outage_forecast_complete'])
        self.assertEqual(80,r['target_soc'])
        self.assertEqual('charging',r['phase'])

    def test_current_solar_cannot_replace_remaining_window_coverage(self):
        r=self.tick(9000,soc=69,solar_w=8000,load_w=1000,charge_a=120)
        self.assertEqual('charging',r['phase'])
        r=self.tick(9001,soc=69,solar_w=8000,charge_a=0)
        self.assertEqual('charging',r['phase'])

    def test_window_expires_only_at_end_and_selects_future_plan(self):
        self.doc['groups']['1.1'].append(dict(start=(self.start+timedelta(hours=6)).isoformat(),end=(self.start+timedelta(hours=8)).isoformat()))
        self.assertTrue(self.tick(14399)['window_active'])
        r=self.tick(14400)
        self.assertFalse(r['window_active'])
        self.assertEqual(self.doc['groups']['1.1'][1]['start'],r['start'])

    def test_unknown_grid_manual_and_stale_never_issue_control(self):
        for args in ({'automatic':False},{'telemetry_valid':False},{'grid_online':None},{'voltage':None}):
            with self.subTest(args=args):
                r=self.tick(9000,soc=60,**args)
                self.assertFalse(r['control_active'])
                self.assertIsNone(r['request'])

    def test_fifteen_forty_five_slots(self):
        for minute, expected in ((0,15),(15,45),(30,45),(45,15)):
            self.assertEqual(expected,self.plan._next_slot(self.start.replace(minute=minute)).minute)
