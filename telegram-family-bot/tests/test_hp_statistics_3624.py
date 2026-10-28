import json
import unittest
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import Mock,patch
from zoneinfo import ZoneInfo
from app import hp_daily_energy
from app.home_assistant import HomeAssistantClient,HomeAssistantError

NOW=datetime(2026,10,20,8,tzinfo=ZoneInfo('Europe/Kyiv'))


class DailyHpStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.config=SimpleNamespace(heat_pump_floor_1_energy_entity='sensor.hp1',
            heat_pump_floor_2_energy_entity='sensor.hp2',
            heat_pump_floor_3_energy_entity='sensor.hp3_energy_calculated')

    def report(self,values,now=NOW):
        def statistics(start,end,ids):
            self.assertEqual(3,len(ids))
            self.assertEqual(0,start.astimezone(now.tzinfo).hour)
            self.assertEqual(0,end.astimezone(now.tzinfo).hour)
            self.bounds=(start,end)
            return {entity:[{'start':start.timestamp()*1000,'end':end.timestamp()*1000,'change':value}]
                    for entity,value in zip(ids,values)}
        self.client=SimpleNamespace(daily_energy_statistics=statistics,
            import_history=Mock(side_effect=AssertionError('Raw history must not be read')))
        return hp_daily_energy.lines(self.config,self.client,now)

    def test_reuses_recorded_daily_values_for_three_floors(self):
        lines=self.report([6.78,0.25,0.3])
        self.assertEqual(3,len(lines))
        self.assertIn('6.78 kWh',lines[0])
        self.assertIn('0.25 kWh',lines[1])
        self.assertIn('виміряною потужністю',lines[2])
        self.client.import_history.assert_not_called()

    def test_standby_and_threshold_are_hidden(self):
        self.assertEqual([],self.report([0,0.01,0.1]))
        self.assertEqual(1,len(self.report([0.101,0,0])))

    def test_missing_or_negative_change_is_not_hidden(self):
        lines=self.report([None,-1,float('nan')])
        self.assertEqual(3,len(lines))
        self.assertTrue(all('недостатньо' in line for line in lines))

    def test_local_calendar_day_including_dst(self):
        for day,hours in [(NOW,24),(datetime(2026,3,30,8,tzinfo=NOW.tzinfo),23),
                          (datetime(2026,10,26,8,tzinfo=NOW.tzinfo),25)]:
            self.report([0,0,0],day)
            a,b=self.bounds
            self.assertEqual(hours*3600,(b-a).total_seconds())
            self.assertEqual(day.date()-timedelta(days=1),a.astimezone(day.tzinfo).date())

    def test_no_nearby_or_duplicate_bucket_substitution(self):
        self.report([0,0,0]);a,b=self.bounds
        row={'start':a.timestamp()*1000,'end':b.timestamp()*1000,'change':5}
        self.assertEqual(5,hp_daily_energy.daily_value([row],a,b))
        self.assertIsNone(hp_daily_energy.daily_value([row,row],a,b))
        self.assertIsNone(hp_daily_energy.daily_value([dict(row,start=(a-timedelta(days=1)).timestamp()*1000)],a,b))

    def test_statistics_failure_is_explicit(self):
        client=SimpleNamespace(daily_energy_statistics=Mock(side_effect=HomeAssistantError('Unavailable')))
        self.assertEqual(3,len(hp_daily_energy.lines(self.config,client,NOW)))


class StatisticsClientTests(unittest.TestCase):
    def test_exact_read_only_request_and_dict_response(self):
        client=HomeAssistantClient('http://localhost:8123/api',token='test-token')
        start=NOW.replace(hour=0)-timedelta(days=1);end=NOW.replace(hour=0)
        result={'sensor.hp1':[{'start':start.timestamp()*1000,'end':end.timestamp()*1000,'change':2}]}
        connection=Mock()
        connection.recv.side_effect=[json.dumps({'type':'auth_required'}),json.dumps({'type':'auth_ok'}),
            json.dumps({'id':1,'success':True,'result':result})]
        with patch('websocket.create_connection',return_value=connection):
            self.assertEqual(result,client.daily_energy_statistics(start.astimezone(timezone.utc),end.astimezone(timezone.utc),['sensor.hp1']))
        request=json.loads(connection.send.call_args_list[1].args[0])
        self.assertEqual('recorder/statistics_during_period',request['type'])
        self.assertEqual('day',request['period'])
        self.assertEqual(['change'],request['types'])
        self.assertEqual({'energy':'kWh'},request['units'])
        connection.close.assert_called_once()

    def test_invalid_read_scope_is_rejected_before_connection(self):
        client=HomeAssistantClient('http://localhost:8123/api')
        with self.assertRaises(HomeAssistantError):client.websocket_read('call_service')
        with self.assertRaises(HomeAssistantError):client.websocket_read('recorder/statistics_during_period')
        with self.assertRaises(HomeAssistantError):client.daily_energy_statistics(NOW-timedelta(hours=26),NOW,['sensor.hp1'])
        with self.assertRaises(HomeAssistantError):client.daily_energy_statistics(NOW-timedelta(days=1),NOW,[])
