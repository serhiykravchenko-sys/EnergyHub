import unittest
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch
from app import bezsvitla as source

NOW=datetime(2026,10,7,20,tzinfo=ZoneInfo('Europe/Kyiv'))

def page(day, off=True):
    cards=[]
    for group in ('1.1','2.2'):
        slots=[]
        for clock,status in [('00:00 – 15:00','on'),('15:00 – 17:30','off' if off else 'on'),('17:30 – 24:00','on')]:
            label='Без світла' if status=='off' else 'Є світло'
            slots.append(f'<div class="bz-schedule-slot bz-schedule-slot--{status}"><span class="bz-schedule-slot__time">{clock}</span><span aria-label="{label}"></span></div>')
        cards.append(f'<article class="bz-schedule-card"><strong>Черга {group}</strong>'+''.join(slots)+'<span>Оновлено 07.10.2026 18:35</span></article>')
    return (f'<h1>Графік у Київській області на {day:%d.%m.%Y}</h1>'
            '<script type="application/ld+json">{"@graph":[{"@type":"WebPage","dateModified":"2026-10-07T18:35:00+03:00"}]}</script>'+''.join(cards))

class SourceTests(unittest.TestCase):
    def test_today_tomorrow_off_only_and_source_identity(self):
        with patch.object(source,'fetch',side_effect=lambda url,deadline:page(datetime.fromisoformat(url[-10:]).date())):
            doc=source.read_snapshot(NOW,{}, {'1.1','2.2'})
        self.assertEqual('bezsvitla',doc['source'])
        self.assertEqual(['2026-10-07','2026-10-08'],doc['dates'])
        self.assertEqual(2,len(doc['groups']['1.1']))
        self.assertEqual('15:00',doc['groups']['1.1'][0]['start'][11:16])

    def test_rejects_wrong_date_status_gap_duplicate_and_stale_revision(self):
        body=page(NOW.date())
        for changed in [body.replace('на 07.10.2026','на 08.10.2026'),
                        body.replace('aria-label="Без світла"','aria-label="Є світло"'),
                        body.replace('17:30 – 24:00','18:00 – 24:00'),
                        body.replace('Черга 2.2','Черга 1.1'),
                        body.replace('07.10.2026 18:35','01.10.2026 18:35')]:
            with self.assertRaises(ValueError):source.parse_page(changed,NOW.date(),NOW,{'1.1','2.2'})

    def test_explicit_all_day_on_is_valid_empty_outage_list(self):
        rows,_,valid=source.parse_page(page(NOW.date(),False),NOW.date(),NOW,{'1.1','2.2'})
        self.assertTrue(valid); self.assertEqual([],rows['1.1'])

    def test_missing_markup_does_not_mean_no_outages(self):
        body=page(NOW.date()).split('<article')[0]
        with self.assertRaises(ValueError):source.parse_page(body,NOW.date(),NOW,{'1.1','2.2'})

    def test_adjacent_off_slots_merge(self):
        body=page(NOW.date()).replace('15:00 – 17:30','15:00 – 17:00')
        body=body.replace('<div class="bz-schedule-slot bz-schedule-slot--on"><span class="bz-schedule-slot__time">17:30',
            '<div class="bz-schedule-slot bz-schedule-slot--off"><span class="bz-schedule-slot__time">17:00').replace('17:00 – 24:00</span><span aria-label="Є світло"','17:00 – 24:00</span><span aria-label="Без світла"')
        rows,_,_=source.parse_page(body,NOW.date(),NOW,{'1.1','2.2'})
        self.assertEqual(1,len(rows['1.1']))
        self.assertTrue(rows['1.1'][0]['end'].endswith('00:00:00+03:00'))
