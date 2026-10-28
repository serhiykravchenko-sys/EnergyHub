import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from app.reserve_policy_text import reserve_recovery_message
from test_schedule_sources import NOW


class ReserveRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.config=SimpleNamespace(dtek_dacha_district='Obukhiv')
        self.rows={
            'sensor.energyhub_telemetry_freshness':dict(state='fresh'),
            'input_number.ahm_minimum_soc':dict(state='80'),
            'sensor.powmr_10_2m_battery_soc':dict(state='72'),
            'sensor.powmr_10_2m_total_pv_power':dict(state='880',last_updated=NOW.isoformat()),
            'sensor.powmr_10_2m_output_power':dict(state='2460',last_updated=NOW.isoformat())}
        self.client=SimpleNamespace(state=lambda entity:self.rows.get(entity))
        self.state=dict(reserve_recovery_change=dict(old=40,new=80,at=NOW.isoformat()))

    def text(self):
        return reserve_recovery_message(self.config,self.client,self.state,NOW)

    def test_actual_transition_soc_target_and_measured_solar_deficit(self):
        text=self.text()
        for expected in ['40% → 80%','72%','не покриває','до <b>80%</b>']:
            self.assertIn(expected,text)
        self.assertNotIn('95%',text)
        self.assertNotIn('планового',text)
        self.assertNotIn('48 годин',text)

    def test_stale_changed_or_unknown_previous_reserve_not_a_new_increase(self):
        for change in [dict(old=40,new=80,at=(NOW-timedelta(hours=1)).isoformat()),
                       dict(old=40,new=60,at=NOW.isoformat()),{},
                       dict(old=90,new=80,at=NOW.isoformat())]:
            self.state['reserve_recovery_change']=change
            self.assertNotIn('→',self.text())
            self.assertIn('80%',self.text())

    def test_solar_cover_or_stale_measurements_do_not_claim_shortfall(self):
        self.rows['sensor.powmr_10_2m_total_pv_power']['state']='3000'
        self.assertNotIn('не покриває',self.text())
        self.rows['sensor.powmr_10_2m_total_pv_power']['state']='880'
        self.rows['sensor.powmr_10_2m_total_pv_power']['last_updated']=(NOW-timedelta(minutes=2)).isoformat()
        self.assertNotIn('не покриває',self.text())
        self.rows.pop('sensor.powmr_10_2m_total_pv_power')
        self.assertNotIn('не покриває',self.text())

    def test_missing_current_telemetry_does_not_invent_soc(self):
        self.rows['sensor.energyhub_telemetry_freshness']['state']='stale'
        self.assertIn('уточнюються',self.text())
        self.assertNotIn('72%',self.text())

    def test_target_reached_while_queued_does_not_claim_further_charging(self):
        self.rows['sensor.powmr_10_2m_battery_soc']['state']='81'
        self.assertIn('уже досяг',self.text())
        self.assertNotIn('щоб зарядити',self.text())

    def test_emergency_and_fault_are_local_and_do_not_discard_schedule(self):
        for kind,label in [('emergency','екстрені'),('fault','аварійні')]:
            self.state['regional_notices']={'дача':dict(kind=kind,places=['дача'])}
            self.assertIn('В Обухівському районі',self.text())
            self.assertIn(label,self.text())
            self.assertNotIn('не використовуємо',self.text())

    def test_delivery_uses_reserve_message_and_preparation_keeps_its_notice(self):
        from app.main import deliver_pending_notifications
        from app.outage_schedule import STATUS_ENTITY
        self.config.destination_chat_id='family'
        self.config.timezone='Europe/Kyiv'
        self.config.telemetry_freshness_entity='sensor.energyhub_telemetry_freshness'
        self.config.ahm_minimum_soc_entity='input_number.ahm_minimum_soc'
        self.config.battery_soc_entity='sensor.powmr_10_2m_battery_soc'
        from grid_fixture_3623 import rows
        self.rows.update(rows(NOW))
        telegram=SimpleNamespace(send_message=lambda chat,text:sent.append((chat,text)))
        sent=[]
        item=dict(kind='battery_reserve_charging',message='old generic',created_at=NOW.isoformat())
        self.state['pending_notifications']=[dict(item)]
        with patch('app.restoration_messages.mode_action',return_value='send'), \
             patch('app.outage_schedule.preparation_for_state',return_value=''), \
             patch('app.reserve_policy_text.lines',return_value=[]):
            deliver_pending_notifications(self.config,telegram,self.state,NOW,self.client)
        self.assertEqual('family',sent[0][0])
        self.assertIn('Відновлюємо резерв',sent[0][1])
        self.assertIn('40% → 80%',sent[0][1])
        # A confirmed scheduled preparation has its own richer notification.
        sent.clear()
        self.rows[STATUS_ENTITY]=dict(state='charging')
        self.state['pending_notifications']=[dict(item)]
        with patch('app.restoration_messages.mode_action',return_value='send'), \
             patch('app.outage_schedule.preparation_for_state',return_value='scheduled preparation'):
            deliver_pending_notifications(self.config,telegram,self.state,NOW,self.client)
        self.assertEqual([],sent)
