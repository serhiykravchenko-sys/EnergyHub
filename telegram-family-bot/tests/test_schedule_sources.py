import json
import unittest
from datetime import datetime,timedelta
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo
from app import schedule_sources as sources,dtek_emergency as emergency

NOW=datetime(2026,10,8,17,30,tzinfo=ZoneInfo('Europe/Kyiv'))
GROUPS={'1.1','2.2'}
CFG=SimpleNamespace(dtek_dacha_district='Obukhiv',dtek_apartment_district='Fastiv')


def official(banner='За наказом НЕК Укренерго 8 жовтня діють стабілізаційні відключення електроенергії'):
    data={}
    for day in (NOW.date(),(NOW+timedelta(days=1)).date()):
        start=datetime.combine(day,datetime.min.time(),NOW.tzinfo)
        data[str(int(start.timestamp()))]={'GPV'+g:{str(h+1):('second' if h==10 else 'first' if h==17 else 'no' if 11<=h<=16 else 'yes') for h in range(24)} for g in GROUPS}
    fact=dict(data=data,update='08.10.2026 16:16',today=int(NOW.replace(hour=0,minute=0).timestamp()))
    preset=dict(sch_names={'GPV'+g:'Черга '+g for g in GROUPS},time_zone={str(h+1):[f'{h:02d}-{h+1:02d}',f'{h:02d}:00',f'{h+1:02d}:00'] for h in range(24)})
    return ('<script>DisconSchedule.fact = '+json.dumps(fact)+'; DisconSchedule.preset = '+json.dumps(preset)+
            '; MicroModal.show("modal-attention");</script><div id="modal-attention"><div><p>'+banner+
            '</p><p>Уникайте екстрених відключень.</p></div></div>')


def alerts():
    rows=[]
    for g in GROUPS:
        row=dict(initiator=sources.OPERATOR,queue=g)
        for label,day in [('today',NOW.date()),('tomorrow',(NOW+timedelta(days=1)).date())]:
            row.update({label:[0]*10+[3]+[1]*6+[2]+[0]*6,label+'Status':'ScheduleApplies',label+'Date':day.isoformat(),
                        label+'Possible':[0]*24,label+'CheckedAt':NOW.isoformat(),label+'SourceSlug':sources.OPERATOR+'_web'})
        rows.append(row)
    return '<script id="ng-state" type="application/json">'+json.dumps({'key':dict(b=rows,s=200,u='http://localhost:4302/api/v1/source-registry/areas/kyivska-oblast/shutdowns')})+'</script>'


def pro():
    headings='<th>Часові проміжки</th>'+''.join(f'<th><span>{h:02d}-{h+1:02d}</span></th>' for h in range(24))
    rows=''.join('<tr><td>Черга '+g+'</td>'+''.join('<td class="c'+(' second' if h==10 else ' first' if h==17 else ' off' if 11<=h<=16 else '')+'"></td>' for h in range(24))+'</tr>' for g in GROUPS)
    details=''.join(f'<details><summary>Графік відключень у Київській області на {d} жовтня</summary><table><thead><tr>'+headings+'</tr></thead><tbody>'+rows+'</tbody></table></details>' for d in (8,9))
    return ('<p>Екстрені відключення в Києві.</p><h2>Відключення в Київській області</h2><p>'+sources.URLS['dtek_official']+
            ' на 8 жовтня. Оновлено 08.10.2026 16:16.</p>'+details)


class SourceTests(unittest.TestCase):

    def test_all_sources_decode_half_hours_and_both_dates(self):
        for parser,body in [(sources.parse_official,official()),(sources.parse_alerts,alerts()),(sources.parse_pro,pro())]:
            with self.subTest(parser=parser.__name__):
                days,errors,_=parser(body,NOW,GROUPS)
                self.assertEqual(['2026-10-08','2026-10-09'],sorted(days));self.assertFalse(errors)
                row=days['2026-10-08']['groups']['1.1'][0]
                self.assertEqual('10:30',row['start'][11:16]);self.assertEqual('17:30',row['end'][11:16])

    def test_blocked_official_and_city_only_backup_rejected(self):
        with self.assertRaises(ValueError):sources.parse_official('<iframe>CAPTCHA</iframe>',NOW,GROUPS)
        with self.assertRaises(ValueError):sources.parse_pro(pro().replace('Відключення в Київській області','Відключення в Києві'),NOW,GROUPS)
        with self.assertRaises(ValueError):sources.parse_alerts(alerts().replace(sources.OPERATOR,'kyiv_city'),NOW,GROUPS)

    def test_incomplete_unknown_and_conflicting_cells_rejected(self):
        for cells in ([0]*23,[0]*23+[4],[0]*23+[True]):
            with self.assertRaises(ValueError):sources.intervals(cells,NOW.date(),NOW)
        with self.assertRaises(ValueError):sources.parse_pro(pro().replace('class="c second"','class="c first second"'),NOW,GROUPS)

    def test_missing_tomorrow_keeps_today_and_marks_unconfirmed(self):
        body=alerts().replace('2026-10-09','2026-10-10')
        days,errors,_=sources.parse_alerts(body,NOW,GROUPS)
        self.assertEqual(['2026-10-08'],list(days));self.assertIn('2026-10-09',errors)


    def test_blocked_primary_uses_fresh_mirror_and_records_failure(self):
        with patch.object(sources,'fetch',side_effect=lambda u,d:alerts() if u==sources.URLS['alerts_energy'] else '<iframe>challenge</iframe>'):
            doc=sources.read_snapshot(NOW,wanted=GROUPS)
        self.assertEqual('alerts_energy',doc['source']);self.assertIn('pro_kyiv',doc['source_failures'])
        self.assertIsNone(doc['official_banner'])

    def test_failure_never_means_no_outages(self):
        with patch.object(sources,'fetch',return_value='<p>unavailable</p>'):
            with self.assertRaises(ValueError):sources.read_snapshot(NOW)

    def test_older_backup_cannot_replace_newer_accepted_revision(self):
        old=dict(day_sources={d:dict(source='alerts_energy',published_at=(NOW+timedelta(minutes=1)).isoformat()) for d in ('2026-10-08','2026-10-09')})
        with patch.object(sources,'fetch',side_effect=lambda u,d:alerts() if u==sources.URLS['alerts_energy'] else '<p>blocked</p>'):
            with self.assertRaises(ValueError):sources.read_snapshot(NOW,old)

    def test_stale_and_future_revision_rejected(self):
        for at in (NOW-timedelta(days=3),NOW+timedelta(hours=1)):
            with self.assertRaises(ValueError):sources.publication(at.isoformat(),NOW)

    def test_all_day_on_is_explicit_empty_coverage(self):
        self.assertEqual([],sources.intervals([0]*24,NOW.date(),NOW))

    def test_emergency_word_in_advice_is_not_activation(self):
        _,_,notice=sources.parse_official(official(),NOW,GROUPS)
        self.assertFalse(notice['active'])
        self.assertIsNone(sources.official_banner(official().replace('8 жовтня','7 жовтня'),NOW))
        self.assertIsNone(sources.official_banner(official().replace('MicroModal.show','NotOpened'),NOW))


class BannerTests(unittest.TestCase):
    def notice(self,text='Введені екстрені відключення електроенергії'):
        return dict(active=True,text=text,checked_at=NOW.isoformat(),url=sources.URLS['dtek_official'])

    def test_scope_names_and_whole_oblast(self):
        for text,expected in [('Обухівський район',['дача']),('Фастів',['квартира']),('Броварський район',[]),('Вся Київська область',['дача','квартира'])]:
            self.assertEqual(expected,emergency.affected_places(text,CFG))

    def test_notice_online_information_offline_suspend_restoration_no_rearm(self):
        state={'grid_online':True}
        notice=self.notice();emergency.apply_banner(state,notice,CFG,NOW)
        self.assertFalse(emergency.place_active(state,'дача'))
        state['grid_online']=False;self.assertTrue(emergency.place_active(state,'дача'))
        emergency.restore(state);state['grid_online']=True;self.assertTrue(emergency.restore(state))
        emergency.apply_banner(state,notice,CFG,NOW+timedelta(minutes=30))
        state['grid_online']=False;self.assertFalse(emergency.place_active(state,'дача'))
        self.assertTrue(emergency.place_active(state,'квартира'))

    def test_restart_and_identical_telegram_banner_do_not_duplicate(self):
        state={'grid_online':False}
        emergency.apply(state,[dict(id=1,active=True,places=['дача','квартира'],url='https://t.me/dtek_ua/1',at=(NOW-timedelta(minutes=1)).isoformat())],NOW)
        emergency.apply_banner(state,self.notice(),CFG,NOW)
        self.assertEqual(1,len(state['pending_notifications']))
        state=json.loads(json.dumps(state));emergency.apply_banner(state,self.notice(),CFG,NOW)
        self.assertEqual(1,len(state['pending_notifications']))

    def test_latest_banner_exclusion_replaces_older_whole_region_notice(self):
        state={'grid_online':False}
        emergency.apply(state,[dict(id=1,active=True,places=['дача','квартира'],url='https://t.me/dtek_ua/1',at=(NOW-timedelta(hours=1)).isoformat())],NOW)
        emergency.apply_banner(state,self.notice('Броварський район: введені екстрені відключення'),CFG,NOW)
        self.assertFalse(emergency.place_active(state,'дача'));self.assertFalse(emergency.place_active(state,'квартира'))

    def test_later_telegram_notice_can_replace_site_scope(self):
        state={'grid_online':False}
        emergency.apply_banner(state,self.notice('Обухівський район'),CFG,NOW)
        emergency.apply(state,[dict(id=2,active=True,places=['квартира'],url='https://t.me/dtek_ua/2',at=(NOW+timedelta(minutes=1)).isoformat())],NOW+timedelta(minutes=2))
        self.assertFalse(emergency.place_active(state,'дача'));self.assertTrue(emergency.place_active(state,'квартира'))
        refreshed=dict(self.notice('Обухівський район'),checked_at=(NOW+timedelta(minutes=30)).isoformat())
        emergency.apply_banner(state,refreshed,CFG,NOW+timedelta(minutes=30))
        self.assertFalse(emergency.place_active(state,'дача'));self.assertTrue(emergency.place_active(state,'квартира'))


class FaultNoticeTests(unittest.TestCase):
    def test_post_4582_suspends_with_correct_type(self):
        text='Київська область: через атаку ворога також сталось аварійне відключення\nГрафіки тимчасово не діють.'
        self.assertTrue(emergency.classify(text))
        state={'grid_online':False}
        emergency.apply(state,[dict(id=4582,active=True,notice_type=emergency.notice_type(text),places=emergency.affected_places(text,CFG),url='https://t.me/dtek_ua/4582',at=NOW.isoformat())],NOW)
        self.assertTrue(emergency.place_active(state,'дача'))
        self.assertIn('аварійні',state['pending_notifications'][0]['message'])
        self.assertNotIn('екстрені',state['pending_notifications'][0]['message'])

    def test_fault_banner_matches_our_districts_and_not_others(self):
        for districts,expected in [('Фастівському, Обухівському і Бучанському',['дача','квартира']),('Бучанському',[])]:
            body="<script>MicroModal.show('modal-attention')</script><div id=\"modal-attention\"><p>Через атаку на Київщині зафіксовані аварійні відключення у "+districts+" районах. В інших районах можливі затримки із включенням по графіку.</p></div>"
            notice=sources.official_banner(body,NOW)
            self.assertEqual('fault',notice['notice_type'])
            self.assertEqual(expected,emergency.affected_places(notice['text'],CFG))

    def test_notice_survives_invalid_pro_schedule(self):
        body=pro().replace('<details>', '<broken>').replace('</details>', '</broken>')
        body=body.replace(' на 8 жовтня.', ' На Київщині зафіксовані аварійні відключення у Обухівському районі. на 8 жовтня.')
        with patch.object(sources,'fetch',side_effect=lambda u,d:body if u==sources.URLS['pro_kyiv'] else alerts()):
            doc=sources.read_snapshot(NOW)
        self.assertEqual('fault',doc['source_notice']['kind'])
        with patch.object(sources,'fetch',return_value=body):
            with self.assertRaises(sources.ScheduleReadError) as caught:sources.read_snapshot(NOW)
        self.assertEqual('fault',caught.exception.official_banner['kind'])

    def test_advice_other_region_and_cancellation(self):
        self.assertIsNone(emergency.classify('Київська область: розумно споживайте, щоб уникнути аварійних відключень.'))
        self.assertIsNone(emergency.classify('Донеччина: введені аварійні відключення'))
        self.assertFalse(emergency.classify('Київська область: аварійні відключення скасовані'))

    def test_legacy_fingerprint_does_not_rearm_restored_house(self):
        import hashlib
        notice=dict(active=True,text='Введені екстрені відключення',checked_at=NOW.isoformat(),url=sources.URLS['dtek_official'])
        fingerprint=hashlib.sha256('True|дача,квартира'.encode()).hexdigest()
        state={'grid_online':False,'dtek_site_emergency':dict(fingerprint=fingerprint,active=False,apartment_active=True,source_at=NOW.isoformat())}
        self.assertFalse(emergency.apply_banner(state,notice,CFG,NOW))
        self.assertFalse(emergency.place_active(state,'дача'))
