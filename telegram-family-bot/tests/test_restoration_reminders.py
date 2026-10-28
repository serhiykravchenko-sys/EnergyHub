import unittest
from datetime import timedelta
import test_outage_reminders as fixtures
from app import outage_schedule as schedule

NOW=fixtures.NOW

class RestorationTests(unittest.TestCase):
    def setUp(self):
        fixtures.ReminderTests.setUp(self)
        self.now=NOW+timedelta(hours=4,minutes=45)
        self.state['dtek_snapshot']['checked_at']=self.now.isoformat()
        from grid_fixture_3623 import rows
        self.rows.update(rows(self.now, online=False))
        self.state['apartment_grid']={'online':False, 'observed_at':self.now.timestamp()}
        self.rows['climate.first_floor_heat_pump']={'state':'heat'}
        self.rows['switch.first_floor_heat_pump_eco']={'state':'on'}

    def test_restore_once_with_live_house_soc_and_hp(self):
        self.assertTrue(schedule.queue_restoration_reminders(self.cfg,self.client,self.state,self.now))
        queue=self.state['pending_notifications']
        self.assertEqual(2,len(queue))
        self.assertIn('15 хв',queue[0]['message'])
        self.assertIn('78%',queue[0]['message'])
        self.assertIn('Eco',queue[0]['message'])
        self.assertNotIn('🔋',queue[1]['message'])
        self.assertFalse(schedule.queue_restoration_reminders(self.cfg,self.client,self.state,self.now))
        self.rows['soc']['state']='39'
        self.rows['climate.first_floor_heat_pump']['state']='off'
        refreshed=schedule.restoration_text(self.cfg,self.client,self.state,self.now,queue[0])
        self.assertIn('39%',refreshed); self.assertIn('вимкнено',refreshed)
        self.assertNotIn('Eco',refreshed)
        self.assertNotIn('для збереження',refreshed)  # OFF alone does not establish cause.

    def test_restored_grid_cancelled_schedule_and_expiry_drop_notice(self):
        schedule.queue_restoration_reminders(self.cfg,self.client,self.state,self.now)
        item=self.state['pending_notifications'][0]
        self.rows['sensor.powmr_10_2m_grid_voltage']['state']='220'
        self.assertEqual('',schedule.restoration_text(self.cfg,self.client,self.state,self.now,item))
        self.rows['sensor.powmr_10_2m_grid_voltage']['state']='0'
        self.state['dtek_snapshot']['groups']['1.1']=[]
        self.assertEqual('',schedule.restoration_text(self.cfg,self.client,self.state,self.now,item))
        self.state['dtek_snapshot']['groups']['1.1']=[self.interval]
        self.assertEqual('',schedule.restoration_text(self.cfg,self.client,self.state,self.now+timedelta(minutes=15),item))

    def test_source_revision_not_timestamp_changes_signature(self):
        doc=self.state['dtek_snapshot']
        signature=schedule.relevant_signature(doc,['1.1','2.2'])
        doc['checked_at']=(self.now+timedelta(minutes=1)).isoformat()
        self.assertEqual(signature,schedule.relevant_signature(doc,['1.1','2.2']))
        doc['groups']['1.1']=[]
        self.assertNotEqual(signature,schedule.relevant_signature(doc,['1.1','2.2']))
