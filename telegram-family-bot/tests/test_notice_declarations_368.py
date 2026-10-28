import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from app import source_policy, dtek_emergency

NOW = datetime(2026,10,9,13,tzinfo=timezone.utc)
CFG = SimpleNamespace(dtek_dacha_district='Obukhiv',dtek_apartment_district='Fastiv')
BANNER = ("За наказом НЕК Укренерго 09.10 діють стабілізаційні відключення електроенергії. "
          "Будь ласка, розумно споживайте електроенергію — це допоможе зменшити навантаження "
          "на мережу та уникнути екстрених відключень. Дякуємо за ваше розуміння!")

class NoticeDeclarationTests(unittest.TestCase):
    def parse(self,text):
        return source_policy.parse(text,NOW.isoformat(),NOW)

    def test_exact_banner_is_stabilization_not_emergency(self):
        notice=self.parse(BANNER)
        self.assertEqual('scheduled',notice['kind'])
        self.assertFalse(notice['schedules_invalid'])
        self.assertIsNone(dtek_emergency.outage_status(BANNER))

    def test_same_sentence_advice_does_not_borrow_stabilization_verb(self):
        notice=self.parse('Діють стабілізаційні відключення, заощаджуйте, щоб уникнути екстрених відключень.')
        self.assertEqual('scheduled',notice['kind'])

    def test_fault_advice_does_not_borrow_stabilization_verb(self):
        notice=self.parse('Діють стабілізаційні відключення. Заощаджуйте, щоб запобігти аварійним відключенням.')
        self.assertEqual('scheduled',notice['kind'])

    def test_actual_emergency_or_fault_declaration_still_suspends(self):
        for text,kind in [('За командою Укренерго застосовані екстрені відключення.','emergency'),
                          ('Через атаку зафіксовані аварійні відключення у Фастівському та Обухівському районах.','fault')]:
            with self.subTest(kind=kind):
                notice=self.parse(text)
                self.assertEqual(kind,notice['kind'])
                self.assertTrue(notice['schedules_invalid'])

    def test_negative_and_future_mentions_do_not_activate(self):
        for text in ['Екстрених відключень немає.', 'Можливі екстрені відключення.',
                     'Екстрені відключення не застосовуються.']:
            with self.subTest(text=text):
                self.assertIsNone(self.parse(text))

    def test_correct_read_repairs_false_persisted_status_same_revision_once(self):
        state={}
        false_notice=dict(text=BANNER,kind='emergency',cancelled=False,schedules_invalid=True,
                          revision=NOW.isoformat(),checked_at=NOW.isoformat())
        source_policy.apply(state,false_notice,CFG,NOW)
        state=json.loads(json.dumps(state))
        self.assertTrue(source_policy.suspended(state,'дача'))
        self.assertTrue(source_policy.apply(state,self.parse(BANNER),CFG,NOW))
        self.assertFalse(source_policy.suspended(state,'дача'))
        self.assertFalse(source_policy.suspended(state,'квартира'))
        self.assertEqual(1,len(state['pending_notifications']))
        self.assertIn('стабілізаційні',state['pending_notifications'][0]['message'])
        self.assertFalse(source_policy.apply(state,self.parse(BANNER),CFG,NOW))

    def test_morning_status_uses_fresh_pro_stabilization_notice(self):
        state={}
        source_policy.apply(state,self.parse(BANNER),CFG,NOW)
        text=source_policy.morning_line(state,NOW)
        self.assertIn('стабілізаційні',text)
        self.assertNotIn('Facebook',text)
        from datetime import timedelta
        self.assertIn('не підтверджено',source_policy.morning_line(state,NOW+timedelta(hours=1)))

    def test_unreadable_status_does_not_claim_emergency_absent(self):
        text=source_policy.morning_line({},NOW)
        self.assertIn('не підтверджено',text)
        self.assertNotIn('немає',text)
        self.assertNotIn('стабілізаційні',text)
