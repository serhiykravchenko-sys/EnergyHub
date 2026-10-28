import unittest
from datetime import datetime,timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from app.forecast_quality import collect
from app.report import build_report

NOW=datetime(2026,10,17,8,tzinfo=ZoneInfo('Europe/Kyiv'))


def report(data):
    return build_report(weather_lines=[],solar_forecast=None,solar_window=None,threshold_w=300,
                        consumption=None,snapshot={},night_import=None,forecast_accuracy=data,compact=True)


class ForecastQualityTests(unittest.TestCase):
    def rows(self):
        return {'sensor.energyhub_daily_solar_forecast':dict(state='3.33',attributes=dict(
            date='2026-10-16',forecast_kwh=3.33,actual_kwh=None,battery_full=False)),
            'sensor.total_solar_generated_today':dict(state='3.037',attributes=dict(last_period='5.221',
                last_reset='2026-10-17T00:00:00.005789+03:00',unit_of_measurement='kWh'))}

    def test_missing_actual_snapshot_is_recovered_from_completed_native_day(self):
        rows=self.rows()
        data=collect(SimpleNamespace(state=lambda key:rows.get(key)),NOW)
        self.assertEqual(5.221,data['actual_kwh'])
        text=report(data)
        self.assertIn('Учора батарея не досягла 100%',text)
        self.assertIn('5.2 kWh',text)
        self.assertIn('+56.8% до прогнозу',text)

    def test_no_error_sensor_is_required(self):
        text=report(dict(battery_full=False,forecast_kwh=10,actual_kwh=7))
        self.assertIn('-30% до прогнозу',text)

    def test_today_or_stale_snapshot_cannot_be_reported_as_yesterday(self):
        for day in ('2026-10-17','2026-10-15',None):
            rows=self.rows();rows['sensor.energyhub_daily_solar_forecast']['attributes']['date']=day
            text=report(collect(SimpleNamespace(state=lambda key:rows.get(key)),NOW))
            self.assertIn('недостатньо підтверджених даних',text)
            self.assertNotIn('5.2 kWh',text)

    def test_missing_data_is_explicit_not_a_zero_or_silent_omission(self):
        for actual,forecast,full in ((None,10,False),(0,0,False),(5,10,None)):
            text=report(dict(actual_kwh=actual,forecast_kwh=forecast,battery_full=full))
            self.assertIn('недостатньо підтверджених даних',text)
            self.assertNotIn('% до прогнозу',text)

    def test_full_battery_day_is_omitted(self):
        self.assertNotIn('🎯',report(dict(actual_kwh=7,forecast_kwh=10,battery_full=True)))

    def test_wrong_day_or_manual_midday_reset_does_not_supply_last_period(self):
        for reset in ('2026-10-16T00:00:00+03:00','2026-10-17T06:00:00+03:00'):
            rows=self.rows();rows['sensor.total_solar_generated_today']['attributes']['last_reset']=reset
            data=collect(SimpleNamespace(state=lambda key:rows.get(key)),NOW)
            self.assertIsNone(data['actual_kwh'])

    def test_wh_and_genuine_zero_generation_are_valid(self):
        rows=self.rows();attrs=rows['sensor.total_solar_generated_today']['attributes']
        attrs.update(last_period='5221',unit_of_measurement='Wh')
        data=collect(SimpleNamespace(state=lambda key:rows.get(key)),NOW)
        self.assertEqual(5.221,data['actual_kwh'])
        attrs['last_period']='0'
        self.assertIn('-100% до прогнозу',report(collect(SimpleNamespace(state=lambda key:rows.get(key)),NOW)))


if __name__=='__main__':
    unittest.main()
