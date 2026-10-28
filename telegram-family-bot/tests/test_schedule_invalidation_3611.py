import json
import unittest
from datetime import timedelta
from app import source_policy, outage_schedule, schedule_sources
from test_schedule_sources import NOW, CFG, pro

BANNER=('Чергова атака призвела до нових масштабних відключень. '
        'Стабілізаційні графіки не діють. Енергетики вже працюють, '
        'щоб якомога швидше покращити ситуацію і повернути світло.')


class InvalidationTests(unittest.TestCase):
    def test_exact_banner_keeps_risk_notice_and_usable_timetable_separate(self):
        notice=source_policy.parse(BANNER,NOW.isoformat(),NOW)
        self.assertIsNotNone(notice)
        self.assertEqual('scheduled',notice['kind'])
        self.assertTrue(notice['schedules_invalid'])
        state={}
        source_policy.apply(state,notice,CFG,NOW)
        for place in ('дача','квартира'):
            self.assertTrue(source_policy.suspended(state,place))
        snapshot=source_policy.authority(dict(validated=True,source_status='fresh'),state,NOW)
        self.assertTrue(snapshot['validated'])
        self.assertEqual('fresh',snapshot['source_status'])
        self.assertTrue(snapshot['emergency_notice_active'])
        text=state['pending_notifications'][0]['message']
        self.assertIn('стабілізаційні графіки не діють',text)
        self.assertNotIn('екстрені',text)
        self.assertNotIn('аварійні',text)

    def test_new_chart_restart_or_failed_read_cannot_clear_suspension(self):
        state={}
        notice=source_policy.parse(BANNER,NOW.isoformat(),NOW)
        source_policy.apply(state,notice,CFG,NOW)
        state=json.loads(json.dumps(state))
        newer=dict(validated=True,groups={'1.1':[dict(start='different',end='chart')]},
                   day_sources={'today':dict(published_at=(NOW+timedelta(hours=1)).isoformat())})
        self.assertTrue(source_policy.suspended(state,'дача',newer))
        self.assertFalse(source_policy.apply(state,None,CFG,NOW))
        self.assertFalse(source_policy.apply(state,notice,CFG,NOW))
        self.assertEqual(1,len(state['pending_notifications']))
        restored=source_policy.parse('Стабілізаційні графіки діють.',(NOW+timedelta(hours=2)).isoformat(),NOW+timedelta(hours=2))
        source_policy.apply(state,restored,CFG,NOW+timedelta(hours=2))
        self.assertFalse(source_policy.suspended(state,'дача'))
        self.assertFalse(source_policy.suspended(state,'квартира'))

    def test_region_intro_selected_and_table_cannot_hide_notice(self):
        body=pro().replace('<details>', '<p>'+BANNER+'</p><details>',1)
        section,at=schedule_sources.pro_context(body,NOW)
        notice=source_policy.parse(section,at.isoformat(),NOW)
        self.assertTrue(notice['schedules_invalid'])
        self.assertNotIn('Екстрені відключення в Києві',notice['text'])

    def test_invalid_schedule_evening_warning_does_not_invent_emergency(self):
        from test_messages_3611 import MessageTests
        f=MessageTests();f.setUp()
        state=f.state
        now=f.rows[outage_schedule.STATUS_ENTITY]['attributes']['checked_at']
        from datetime import datetime
        now=datetime.fromisoformat(now)
        notice=source_policy.parse(BANNER,now.isoformat(),now)
        source_policy.apply(state,notice,CFG,now)
        day=(now.date()+timedelta(days=1)).isoformat()
        doc=state['dtek_snapshot']
        doc.update(dates=[day],source_status='fresh',validated=True,
                   source_url='https://pro.kyiv.ua/grafik-vidklyuchennya-svitla/')
        state['dtek_raw_snapshot']=doc
        mappings=[(f.cfg.dtek_dacha_group,'дача'),(f.cfg.dtek_apartment_group,'квартира')]
        item=dict(kind='dtek_tomorrow',day=day,signature=outage_schedule.day_signature(doc,mappings,day))
        text=outage_schedule.evening_text(f.cfg,f.client,state,now,item)
        self.assertIn('Стабілізаційні графіки не діють',text)
        self.assertNotIn('Є повідомлення про екстрені',text)
