import json
import unittest
from types import SimpleNamespace
from app.services.daily_summary import DailySummaryService
from app.mqtt.publisher import publish_daily_summary,publish_daily_summary_discovery


class ForecastSnapshotTests(unittest.TestCase):
    def service(self,full=None):
        service=DailySummaryService.__new__(DailySummaryService)
        service.last_snapshot=dict(date='2026-10-16',source_timestamp='snapshot-time',house_consumption_kwh=12.6,
            solar_forecast_kwh=3.33,solar_actual_kwh=5.221,battery_full=full,solar_surplus_estimated_kwh=0,
            grid_availability_24h_percent=70)
        return service

    def test_unknown_full_status_is_not_off_or_a_valid_forecast_error(self):
        values=self.service().mqtt_values()
        self.assertEqual('unknown',values['daily_battery_reached_full'])
        self.assertEqual('unknown',values['daily_solar_forecast_error_percent'])
        self.assertEqual('off',self.service(False).mqtt_values()['daily_battery_reached_full'])

    def test_atomic_dated_attributes_are_published_for_all_comparison_entities(self):
        calls=[]
        client=SimpleNamespace(publish=lambda topic,payload,**kwargs:calls.append((topic,payload)))
        publish_daily_summary(client,self.service(False))
        attrs=json.loads(next(payload for topic,payload in calls if topic.endswith('/daily_summary/attributes')))
        self.assertEqual('2026-10-16',attrs['date'])
        self.assertEqual(3.33,attrs['forecast_kwh'])
        self.assertEqual(5.221,attrs['actual_kwh'])
        self.assertIs(attrs['battery_full'],False)
        calls.clear();publish_daily_summary_discovery(client)
        for key in ('daily_solar_forecast','daily_solar_actual','daily_solar_forecast_error_percent','daily_battery_reached_full'):
            config=json.loads(next(payload for topic,payload in calls if topic.endswith('/energyhub_'+key+'/config')))
            self.assertTrue(config['json_attributes_topic'].endswith('/daily_summary/attributes'))
