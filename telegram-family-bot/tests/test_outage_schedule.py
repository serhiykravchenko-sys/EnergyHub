import unittest
import io
from unittest.mock import patch
from types import SimpleNamespace
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from app import outage_schedule as dtek

NOW=datetime(2026,10,6,21,tzinfo=ZoneInfo('Europe/Kyiv'))


class ScheduleTests(unittest.TestCase):
    def test_http_budget_is_clamped_and_late_response_rejected(self):
        response=SimpleNamespace(geturl=lambda:'https://t.me/s/dtek_ua',read=lambda _:b'preview')
        from unittest.mock import MagicMock
        manager=MagicMock();manager.__enter__.return_value=response
        with patch.object(dtek.time,'monotonic',return_value=100),patch.object(dtek,'urlopen',return_value=manager) as opened:
            self.assertEqual(b'preview',dtek.fetch('https://t.me/s/dtek_ua',deadline=103))
            self.assertEqual(3,opened.call_args.kwargs['timeout'])
        with patch.object(dtek.time,'monotonic',side_effect=[100,104]),patch.object(dtek,'urlopen',return_value=manager):
            with self.assertRaises(TimeoutError):dtek.fetch('https://t.me/s/dtek_ua',deadline=103)
        with patch.object(dtek.time,'monotonic',return_value=104),patch.object(dtek,'urlopen') as opened:
            with self.assertRaises(TimeoutError):dtek.fetch('https://t.me/s/dtek_ua',deadline=103)
            opened.assert_not_called()

    def test_successful_channel_check_without_daily_schedule_is_not_error(self):
        old=NOW-timedelta(days=2)
        body=f'<div class="tgme_widget_message" data-post="dtek_ua/10"><div class="tgme_widget_message_text">Київщина: ремонтні роботи</div><time datetime="{old.isoformat()}"></time></div>'
        with patch.object(dtek,'fetch',return_value=body.encode()):
            document=dtek.read_snapshot(NOW,{})
        self.assertEqual('no_schedule',document['source_status'])
        cfg=SimpleNamespace(dtek_schedule_enabled=True)
        text=dtek.morning_lines(cfg,{'dtek_snapshot':document},NOW,None)[0]
        self.assertIn('не опубліковано',text)
        self.assertIn('останні 48 годин',text)
        with patch.object(dtek,'fetch',return_value=b'<html>unreadable</html>'):
            with self.assertRaises(ValueError):dtek.read_snapshot(NOW,{})

    def test_source_recovery_once_private_and_thirty_minute_polling(self):
        from concurrent.futures import Future
        cfg=SimpleNamespace(dtek_schedule_enabled=True,dtek_dacha_group='1.1',dtek_apartment_group='2.2',solar_forecast_entity='forecast')
        class Client:
            def state(self,_):return None
            def publish_mqtt(self,*args,**kwargs):pass
        monitor=dtek.ScheduleMonitor()
        state={'dtek_source_error':True}
        document=dict(source_status='no_schedule',source_url='https://t.me/s/dtek_ua',checked_at=NOW.isoformat(),dates=[],groups={})
        for offset in (0,1):
            future=Future();future.set_result((document,{}));monitor.future=future
            monitor.poll(cfg,Client(),state,NOW+timedelta(minutes=offset))
        self.assertEqual(['technical_dtek_recovered'],[i['kind'] for i in state['pending_notifications']])
        self.assertEqual(dtek.next_poll(NOW+timedelta(minutes=1)).timestamp(),monitor.due)
        self.assertFalse(state['dtek_source_error'])
        monitor.executor.shutdown(wait=False)

    def test_region_date_and_year_rollover(self):
        self.assertEqual('2026-10-07',str(dtek.daily_date('Київщина | 7 жовтня',NOW)))
        late=NOW.replace(month=12,day=31)
        self.assertEqual('2027-01-01',str(dtek.daily_date('Київщина | 1 січня',late)))
        for text in ('Київ | 7 жовтня','Одещина | 7 жовтня','Київщина | 15 жовтня'):
            with self.assertRaises(ValueError):dtek.daily_date(text,NOW)

    def test_real_group_intervals_and_total(self):
        day=NOW.date()+timedelta(days=1)
        a=dtek.cell_intervals('1.1 Черга Світло буде відсутнє з 15:00 до 17:30',day,NOW.tzinfo)
        b=dtek.cell_intervals('2.2 Черга Світло буде відсутнє з 03:00 до 07:00 з 13:30 до 17:30',day,NOW.tzinfo)
        doc=dict(dates=[str(day)],groups={'1.1':a,'2.2':b},source_url='https://t.me/dtek_ua/4569')
        text=dtek.message(doc,[('1.1','дача'),('2.2','квартира')],NOW)
        self.assertIn('2 год 30 хв',text)
        self.assertEqual(2,text.count('4 год'))
        self.assertIn('03:00–07:00',text)
        self.assertIn('13:30–17:30',text)

    def test_midnight_and_24_end(self):
        rows=dtek.cell_intervals('без світла 23:00–01:00',NOW.date(),NOW.tzinfo)
        self.assertEqual(7200,(datetime.fromisoformat(rows[0]['end'])-datetime.fromisoformat(rows[0]['start'])).total_seconds())
        rows=dtek.cell_intervals('без світла 20:00–24:00',NOW.date(),NOW.tzinfo)
        self.assertEqual('2026-10-07T00:00',rows[0]['end'][:16])

    def test_dst_ambiguous_clock_requires_review(self):
        day=NOW.date().replace(day=25)
        with self.assertRaises(ValueError):dtek.cell_intervals('без світла 03:30–06:00',day,NOW.tzinfo)
        rows=dtek.cell_intervals('без світла 02:00–06:00',day,NOW.tzinfo)
        self.assertEqual(5*3600,(datetime.fromisoformat(rows[0]['end'])-datetime.fromisoformat(rows[0]['start'])).total_seconds())

    def test_ambiguous_cells_are_rejected(self):
        for text in ('без світла 03:00','без світла 03:00–07:00 та 13:30',
                     'без світла 07:00–07:00','без світла 25:00–27:00',
                     'Світло буде весь день 03:00–07:00',
                     'без світла 03:00–07:00 06:00–08:00'):
            with self.assertRaises(ValueError,msg=text):dtek.cell_intervals(text,NOW.date(),NOW.tzinfo)

    def test_all_day_explicit_and_missing_time_not_zero_outages(self):
        self.assertEqual([],dtek.cell_intervals('Світло буде весь день',NOW.date(),NOW.tzinfo))
        with self.assertRaises(ValueError):dtek.cell_intervals('',NOW.date(),NOW.tzinfo)

    def test_revision_signature_excludes_poll_time_and_unrelated_groups(self):
        a=dict(groups={'1.1':[],'2.2':[],'4.1':[]},checked_at=NOW.isoformat())
        b=dict(a,checked_at='other',groups={'1.1':[],'2.2':[],'4.1':['changed']})
        self.assertEqual(dtek.relevant_signature(a,['1.1','2.2']),dtek.relevant_signature(b,['1.1','2.2']))
        b['groups']['1.1']=['new']
        self.assertNotEqual(dtek.relevant_signature(a,['1.1','2.2']),dtek.relevant_signature(b,['1.1','2.2']))

    def test_restore_time_is_expected_and_stale_evidence_omitted(self):
        doc=dict(validated=True,dates=[NOW.date().isoformat()],source_status='fresh',checked_at=NOW.isoformat(),groups={'1.1':[dict(start=(NOW-timedelta(hours=1)).isoformat(),end=(NOW+timedelta(hours=1)).isoformat())]})
        self.assertIn('Відновлення за графіком',dtek.context({'dtek_snapshot':doc},NOW,False,'1.1'))
        doc['checked_at']=(NOW-timedelta(minutes=36)).isoformat()
        self.assertNotIn('Час відновлення',dtek.context({'dtek_snapshot':doc},NOW,False,'1.1'))

    def test_no_charge_promise_before_mode_acknowledgement(self):
        data=dict(phase='charging',target_soc=90,start=(NOW+timedelta(hours=2)).isoformat(),checked_at=NOW.isoformat(),control_active=True)
        class Client:
            def state(self,entity):
                from grid_fixture_3623 import rows
                return rows(NOW).get(entity,dict(state=data['phase'],attributes=data))
        self.assertEqual('',dtek.preparation_line(Client(),NOW))
        data.update(acknowledged=True,current_soc=50,observed_charge_a=10,end=(NOW+timedelta(hours=6)).isoformat())
        self.assertIn('50% → 90%',dtek.preparation_line(Client(),NOW))
        class OfflineClient:
            def state(self,_):return dict(state='unavailable',attributes=data)
        self.assertEqual('',dtek.preparation_line(OfflineClient(),NOW))
        self.assertIsNone(dtek.active_preparation(OfflineClient(),NOW))

    def test_source_fetch_rejects_unapproved_hosts_before_network(self):
        for url in ('http://t.me/s/dtek_ua','https://example.com/image','https://127.0.0.1/data'):
            with self.assertRaises(ValueError):dtek.fetch(url,image=True)

    def test_precharge_message_quantifies_only_valid_solar_credit(self):
        data=dict(capacity_kwh=16, solar_forecast_complete=True,
                  forecast_net_solar_kwh=1, required_grid_kwh=6.68)
        total, split=dtek.preparation_energy_details(data,47,95)
        self.assertIn('≈7.7 kWh',total)
        self.assertIn('≈1.0 kWh',split)
        self.assertIn('≈6.7 kWh',split)
        data['solar_forecast_complete']=False
        self.assertIn('не підтверджено (не враховано)',dtek.preparation_energy_details(data,47,95)[1])
        data['capacity_kwh']=None
        self.assertEqual(('',''),dtek.preparation_energy_details(data,47,95))

    def test_chart_cells_are_read_individually_and_disagreement_rejected(self):
        from PIL import Image
        data=io.BytesIO()
        Image.new('RGB',(900,700),'white').save(data,format='PNG')
        columns=('text','conf','left','top')
        words=[('Київщина','99',0,0),('7','99',300,0),('жовтня','99',360,0)]
        words += [(group,'99',x,y) for group,x,y in (
            ('1.1',180,600),('1.2',1080,600),('2.1',1980,600),
            ('2.2',180,1260),('3.1',1080,1260),('3.2',1980,1260))]
        tsv='\t'.join(columns)+'\n'+'\n'.join('\t'.join(map(str,row)) for row in words)
        def recognize(args,**kwargs):
            text=tsv if args[-1]=='tsv' else 'Світло буде відсутнє з 15:00 до 17:30'
            return SimpleNamespace(stdout=text)
        with patch.object(dtek.subprocess,'run',side_effect=recognize):
            day,groups=dtek.ocr_image(data.getvalue(),'Київщина: графіки на 7 жовтня',NOW)
            self.assertEqual('2026-10-07',str(day))
            self.assertEqual(6,len(groups))
        with patch.object(dtek.subprocess,'run',side_effect=recognize) as calls:
            _,groups=dtek.ocr_image(data.getvalue(),'Київщина: графіки на 7 жовтня',NOW,{'1.1','2.2'})
            self.assertEqual({'1.1','2.2'},set(groups))
            self.assertEqual(5,calls.call_count)
            self.assertEqual(20,calls.call_args_list[0].kwargs['timeout'])
            self.assertTrue(all(call.kwargs['timeout']==5 for call in calls.call_args_list[1:]))
        with patch.object(dtek.time,'monotonic',return_value=100),patch.object(dtek.subprocess,'run',side_effect=recognize) as calls:
            dtek.ocr_image(data.getvalue(),'Київщина: графіки на 7 жовтня',NOW,{'1.1','2.2'},deadline=102)
            self.assertTrue(all(call.kwargs['timeout']==2 for call in calls.call_args_list))
        # A subprocess returning after the aggregate deadline cannot yield a
        # validated schedule, even if its mocked output is otherwise readable.
        with patch.object(dtek.time,'monotonic',side_effect=[100,100,103]),patch.object(dtek.subprocess,'run',side_effect=recognize) as calls:
            with self.assertRaises(TimeoutError):dtek.ocr_image(data.getvalue(),'Київщина: графіки на 7 жовтня',NOW,deadline=102)
            self.assertEqual(1,calls.call_count)
        def mismatch(args,**kwargs):
            text=tsv if args[-1]=='tsv' else ('без світла 15:00–17:30' if args[-1]=='6' else 'без світла 15:00–18:30')
            return SimpleNamespace(stdout=text)
        with patch.object(dtek.subprocess,'run',side_effect=mismatch):
            with self.assertRaises(ValueError):dtek.ocr_image(data.getvalue(),'Київщина: графіки на 7 жовтня',NOW)

    def test_morning_stale_schedule_is_not_replayed(self):
        cfg=SimpleNamespace(dtek_schedule_enabled=True,dtek_dacha_group='1.1',dtek_apartment_group='2.2')
        state=dict(dtek_snapshot=dict(source_status='fresh',checked_at=(NOW-timedelta(hours=1)).isoformat()))
        self.assertIn('не вдалося перевірити',dtek.morning_lines(cfg,state,NOW,None)[0])

    def test_reader_failure_invalidates_previous_plan_and_warns_once(self):
        from concurrent.futures import Future
        cfg=SimpleNamespace(dtek_schedule_enabled=True,dtek_dacha_group='1.1',dtek_apartment_group='2.2',solar_forecast_entity='forecast')
        published=[]
        class Client:
            def state(self,_):return None
            def publish_mqtt(self,topic,payload,retain=True):published.append(payload)
        monitor=dtek.ScheduleMonitor()
        state={'dtek_snapshot':{'source_status':'fresh'}}
        for i in range(2):
            failed=Future()
            failed.set_exception(ValueError('Unclear chart'))
            monitor.future=failed
            monitor.poll(cfg,Client(),state,NOW+timedelta(minutes=i))
        self.assertEqual('unavailable',state['dtek_snapshot']['source_status'])
        self.assertEqual(1,len(state['pending_notifications']))
        self.assertFalse(published[-1]['validated'])
        monitor.executor.shutdown(wait=False)

    def test_disabled_reader_clears_retained_plan_once_per_start(self):
        published=[]
        class Client:
            def state(self, entity): return None
            def publish_mqtt(self,topic,payload,retain=True):published.append(payload)
        monitor=dtek.ScheduleMonitor()
        cfg=SimpleNamespace(dtek_schedule_enabled=False)
        monitor.poll(cfg,Client(),{},NOW)
        monitor.poll(cfg,Client(),{},NOW)
        self.assertEqual(1,len(published))
        self.assertEqual('disabled',published[0]['source_status'])
        monitor.executor.shutdown(wait=False)

    def test_official_emergency_notice_suspends_planning_without_old_chart(self):
        body=f'<div class="tgme_widget_message" data-post="dtek_ua/20"><div class="tgme_widget_message_text">Київщина: екстрені відключення, графіки не діють.</div><time datetime="{NOW.isoformat()}"></time></div>'
        with patch.object(dtek,'fetch',return_value=body.encode()):
            document=dtek.read_snapshot(NOW,{})
        self.assertEqual('suspended',document['source_status'])
        self.assertFalse(document['validated'])
        self.assertIsInstance(dtek.context({'dtek_snapshot':document},NOW,False,'1.1'),str)
        cfg=SimpleNamespace(dtek_schedule_enabled=True)
        self.assertIn('не діють',dtek.morning_lines(cfg,{'dtek_snapshot':document},NOW,None)[0])

    def test_latest_current_regional_schedule_skips_expired_and_city_posts(self):
        now=NOW.replace(day=7,hour=14)
        def post(number,text):
            return (f'<div class="tgme_widget_message" data-post="dtek_ua/{number}">'
                    f'<div class="tgme_widget_message_text">{text}</div>'
                    f'<a style="background-image:url(\'https://cdn4.telesco.pe/file/{number}.jpg\')"></a>'
                    f'<time datetime="{NOW.isoformat()}"></time></div>')
        body=''.join((post(4566,'Київщина: графіки відключень на 6 жовтня'),
                      post(4569,'Київщина: графіки відключень на 7 жовтня'),
                      post(4571,'Київ: графіки відключень на 7 жовтня'),
                      post(4572,'Київщина: ремонтні роботи на 7 жовтня')))
        fetched=[]
        def fetch(url,**kwargs):
            fetched.append(url)
            return body.encode() if url.endswith('/s/dtek_ua') else b'chart'
        with patch.object(dtek,'fetch',side_effect=fetch), patch.object(dtek,'ocr_image',return_value=(now.date(),{'1.1':[],'2.2':[]})):
            document=dtek.read_snapshot(now,{}, {'1.1','2.2'})
        self.assertEqual('https://t.me/dtek_ua/4569',document['source_url'])
        self.assertEqual(['2026-10-07'],document['dates'])
        self.assertEqual(['https://t.me/s/dtek_ua','https://cdn4.telesco.pe/file/4569.jpg'],fetched)
        with patch.object(dtek.time,'monotonic',return_value=100),patch.object(dtek,'fetch',side_effect=fetch) as requests,patch.object(dtek,'ocr_image',return_value=(now.date(),{'1.1':[],'2.2':[]})) as ocr:
            dtek.read_snapshot(now,{}, {'1.1','2.2'})
            self.assertEqual(190,ocr.call_args.kwargs['deadline'])
            self.assertTrue(all(call.kwargs['deadline']==190 for call in requests.call_args_list))
        # An unreadable newer revision cannot resurrect the older chart.
        body+=post(4573,'Київщина: графіки відключень на 7 жовтня')
        with patch.object(dtek,'fetch',side_effect=fetch), patch.object(dtek,'ocr_image',side_effect=ValueError('Unreadable new chart')):
            with self.assertRaises(ValueError):dtek.read_snapshot(now,{}, {'1.1','2.2'})
        self.assertTrue(fetched[-1].endswith('/4573.jpg'))

    def test_fused_group_label_requires_two_confident_isolated_reads(self):
        from PIL import Image
        data=io.BytesIO();Image.new('RGB',(900,700),'white').save(data,format='PNG')
        columns='text\tconf\tleft\ttop\twidth\theight\n'
        rows=[('Київщина',99,0,0,200,30),('7',99,300,0,30,30),('жовтня',99,360,0,200,30)]
        rows += [(group,99,x,y,90,75) for group,x,y in (
            ('11',180,750),('1.2',1080,750),('2.1',1980,750),
            ('2.2',180,1260),('3.1',1080,1260),('3.2',1980,1260))]
        tsv=columns+'\n'.join('\t'.join(map(str,row)) for row in rows)
        for second,conf,valid in [('1.1',99,True),('1.2',99,False),('1.1',45,False),('11',99,False)]:
            def recognize(args,**kwargs):
                if 'tessedit_char_whitelist=0123456789.' in args:
                    text='1.1' if args[args.index('--psm')+1]=='6' else second
                    return SimpleNamespace(stdout=columns+f'{text}\t{conf}\t0\t0\t90\t75\n')
                return SimpleNamespace(stdout=tsv if args[-1]=='tsv' else 'Світло буде відсутнє з 15:00 до 17:30')
            with patch.object(dtek.subprocess,'run',side_effect=recognize):
                if valid:
                    _,groups=dtek.ocr_image(data.getvalue(),'Київщина: графіки відключень на 7 жовтня',NOW,{'1.1','2.2'})
                    self.assertEqual({'1.1','2.2'},set(groups))
                else:
                    with self.assertRaises(ValueError):dtek.ocr_image(data.getvalue(),'Київщина: графіки відключень на 7 жовтня',NOW)

if __name__=='__main__':unittest.main()
