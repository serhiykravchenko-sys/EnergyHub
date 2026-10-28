"""Daily schedule monitoring and legacy OCR evidence helpers; no hardware commands."""
import csv
import hashlib
import html
import io
import json
import math
import logging
import time
import re
import subprocess
import tempfile
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .uhmc_source import TelegramPreviewParser
from .weather_warning import MONTHS
from . import bezsvitla
from . import schedule_sources

TOPIC = 'energyhub/input/outage/schedule'
STATUS_ENTITY = 'sensor.energyhub_outage_preparation'
POLL_SECONDS = 1800
SOURCE_MAX_AGE_SECONDS = 2100
FALLBACK_MESSAGE = '🔋 EH управляє зарядом батареї за показником доступності ДТЕК за останні 48 годин.'
LOGGER=logging.getLogger('telegram-family-assistant.dtek')
GROUP_RE = re.compile(r'^[1-6]\.[12]$')
TIMES = re.compile(r'(?:з\s*)?(\d{1,2}[:.]\d{2})\s*(?:до|[-–—])\s*(\d{1,2}[:.]\d{2})')


def daily_date(text, now):
    match = re.search(r'\b([0-3]?\d)\s+('+'|'.join(MONTHS)+r')\b', text.lower())
    if not match or not re.search(r'київщин|київськ.{0,12}обл', text.lower()):
        raise ValueError('Missing Kyiv-region date')
    choices = []
    for year in (now.year-1, now.year, now.year+1):
        try:
            day = now.date().replace(year=year, month=MONTHS[match[2]], day=int(match[1]))
            if -1 <= (day-now.date()).days <= 1:
                choices.append(day)
        except ValueError:
            pass
    if len(choices) != 1:
        raise ValueError('Schedule date outside current daily horizon')
    return choices[0]


def cell_intervals(text, day, tz):
    if re.search(r'світло\s+буде\s+весь\s+день', text, re.I):
        if TIMES.search(text):
            raise ValueError('Conflicting all-day and outage text')
        return []
    if not re.search(r'(?:світло\s+буде\s+відсутн|без\s+світла)', text, re.I):
        raise ValueError('Missing explicit outage marker')
    matches = list(TIMES.finditer(text))
    if not 1 <= len(matches) <= 4:
        raise ValueError('Unreadable outage interval')
    # Reject orphan times instead of silently omitting a second interval.
    remainder = TIMES.sub('', text)
    if re.search(r'\d{1,2}[:.]\d{2}', remainder):
        raise ValueError('Unpaired outage time')
    result = []
    for match in matches:
        left, right = match[1].replace('.', ':'), match[2].replace('.', ':')
        def at(value):
            h, m = map(int, value.split(':'))
            if h == 24 and m == 0:
                return datetime.combine(day+timedelta(days=1), datetime.min.time(), tz)
            if not 0 <= h <= 23 or not 0 <= m <= 59:
                raise ValueError('Invalid clock time')
            candidate=datetime.combine(day, datetime.min.time(), tz)+timedelta(hours=h, minutes=m)
            if (candidate.replace(fold=0).utcoffset()!=candidate.replace(fold=1).utcoffset()
                    or candidate.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)!=candidate.replace(tzinfo=None)):
                raise ValueError('Ambiguous or nonexistent local clock time')
            return candidate
        a, b = at(left), at(right)
        if a == b:
            raise ValueError('Zero-length outage')
        if b < a:
            b += timedelta(days=1)
        if (b-a).total_seconds() > 86400:
            raise ValueError('Outage too long')
        result.append(dict(start=a.isoformat(), end=b.isoformat()))
    result.sort(key=lambda r:r['start'])
    if any(b['start'] < a['end'] for a,b in zip(result,result[1:])):
        raise ValueError('Overlapping intervals')
    return result


def remaining_seconds(deadline):
    remaining=deadline-time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Schedule read exceeded time budget')
    return remaining


def fetch(url, *, image=False, deadline=None):
    host = urlsplit(url).hostname or ''
    if urlsplit(url).scheme != 'https' or (host != 't.me' and not
            (image and re.fullmatch(r'cdn\d*\.telesco\.pe', host))):
        raise ValueError('Unapproved schedule source host')
    limit = 5_000_000 if image else 2_000_000
    timeout=min(12,remaining_seconds(deadline)) if deadline is not None else 12
    with urlopen(Request(url, headers={'User-Agent':'EnergyHub-DTEK-Schedule/3.4'}), timeout=timeout) as response:
        if urlsplit(response.geturl()).hostname != host:
            raise ValueError('Unexpected source redirect')
        data = response.read(limit+1)
    if deadline is not None:
        remaining_seconds(deadline)
    if len(data) > limit:
        raise ValueError('Source response too large')
    return data


def ocr_image(data, caption, now, wanted=None, *, deadline=None):
    """Read independent cells, require two segmentation results to agree."""
    from PIL import Image, ImageOps
    deadline=time.monotonic()+90 if deadline is None else deadline
    remaining_seconds(deadline)
    day = daily_date(caption, now)
    with Image.open(io.BytesIO(data)) as original:
        if original.width > 4000 or original.height > 4000 or original.width < 300:
            raise ValueError('Unsupported chart dimensions')
        image = original.convert('RGB')
    with tempfile.TemporaryDirectory(prefix='eh-dtek-') as temp:
        path = Path(temp)/'chart.png'
        # Yellow badges confuse the full-chart recognizer. Grayscale and
        # enlargement preserve the text while removing the colour boundary.
        scale=3
        ImageOps.grayscale(image).resize((image.width*scale,image.height*scale)).save(path)
        def recognize(path, psm, tsv=False, label=False):
            args=['tesseract', str(path), 'stdout', '-l', 'eng' if label else 'ukr+eng', '--psm', str(psm)]
            if label:
                args.extend(['-c','tessedit_char_whitelist=0123456789.'])
            if tsv:
                args.append('tsv')
            timeout=min(20 if path.name=='chart.png' else 5,remaining_seconds(deadline))
            result=subprocess.run(args, check=True, capture_output=True, timeout=timeout,
                                  env=dict(os.environ,OMP_THREAD_LIMIT='1'),encoding='utf-8').stdout
            remaining_seconds(deadline)
            return result
        words=list(csv.DictReader(io.StringIO(recognize(path, 11, True)), delimiter='\t'))
        header=' '.join(w['text'] for w in words if w['text'].strip())
        if daily_date(header, now) != day:
            raise ValueError('Chart/caption date mismatch')
        anchors=[]
        for word in words:
            text=word['text'].strip()
            # A tiny decimal point can disappear in the full-chart pass.
            # Never insert it by inference: re-read the actual badge twice.
            if (re.fullmatch(r'[1-6][12]',text) and
                    int(word['top']) > image.height*scale*.3):
                x,y,w,h=(int(word[k])/scale for k in ('left','top','width','height'))
                badge=image.crop((max(0,int(x)-2),max(0,int(y)-2),
                                  min(image.width,math.ceil(x+w)+2),
                                  min(image.height,math.ceil(y+h)+2)))
                badge=ImageOps.grayscale(badge).point(lambda p:255 if p>150 else 0)
                badge=ImageOps.expand(badge.resize((badge.width*4,badge.height*4)),20,fill=255)
                label_path=Path(temp)/'label.png';badge.save(label_path)
                labels=[]
                for psm in (6,7):
                    tokens=[r for r in csv.DictReader(io.StringIO(recognize(label_path,psm,True,True)),delimiter='\t') if r['text'].strip()]
                    if len(tokens)!=1 or float(tokens[0]['conf'])<70 or not GROUP_RE.fullmatch(tokens[0]['text']):
                        raise ValueError('Uncertain isolated group label')
                    labels.append(tokens[0]['text'])
                if labels[0]!=labels[1]:
                    raise ValueError('OCR group label disagreement')
                text=labels[0]
            if GROUP_RE.fullmatch(text):
                if float(word['conf']) < 70:
                    raise ValueError('Uncertain group label')
                anchors.append((text, round(int(word['left'])/scale), round(int(word['top'])/scale)))
        if len(anchors) != 6 or len({a[0] for a in anchors}) != 6:
            raise ValueError('Unsupported chart layout or group recognition')
        found_groups={a[0] for a in anchors}
        halves=({f'{g}.{s}' for g in range(1,4) for s in (1,2)},
                {f'{g}.{s}' for g in range(4,7) for s in (1,2)})
        if found_groups not in halves:
            raise ValueError('Unsupported daily chart group set')
        groups={}
        for group,x,y in anchors:
            if wanted is not None and group not in wanted:
                continue
            other_x=sorted({xx for _,xx,yy in anchors if abs(yy-y)<image.height*.08})
            col=min(range(len(other_x)),key=lambda i:abs(other_x[i]-x))
            left=max(0,x-round(image.width*.03))
            right=image.width if col==len(other_x)-1 else other_x[col+1]-round(image.width*.03)
            lower=[yy for _,xx,yy in anchors if abs(xx-x)<image.width*.08 and yy>y+20]
            bottom=min(lower)-5 if lower else image.height
            # Label identity is already validated separately; exclude its row
            # so the cell recognizer sees only the explicit status and times.
            cell=ImageOps.grayscale(image.crop((left,min(bottom,y+20),right,bottom)))
            cell=ImageOps.expand(cell.resize((3*cell.width,3*cell.height)),12,fill=255)
            cell_path=Path(temp)/'cell.png'
            cell.save(cell_path)
            outputs=[cell_intervals(recognize(cell_path, psm),day,now.tzinfo) for psm in (6,11)]
            if outputs[0] != outputs[1]:
                raise ValueError('OCR interval disagreement')
            groups[group]=outputs[0]
    remaining_seconds(deadline)
    return day,groups


def read_snapshot(now, cache, wanted=None):
    deadline=time.monotonic()+90
    body=fetch('https://t.me/s/dtek_ua',deadline=deadline).decode('utf-8')
    parser=TelegramPreviewParser('dtek_ua')
    parser.feed(body)
    parser.close()
    remaining_seconds(deadline)
    if not parser.posts or parser.missing_publication_time:
        raise ValueError('Incomplete public channel preview')
    groups, dates, links, latest={},[],[],None
    relevant=[]
    for post in parser.posts:
        if (re.search(r'київщин|київськ.{0,12}обл',post.text,re.I)
                and re.search(r'графік.{0,30}відключ',post.text,re.I)):
            try:
                day=daily_date(post.text,now)
            except ValueError:
                continue
            # Yesterday's expired image must not invalidate today's chart.
            if day>=now.date():
                relevant.append((post,day))
    newest_schedule=max((post.message_id for post,_ in relevant),default=-1)
    for post in sorted(parser.posts,key=lambda p:p.message_id,reverse=True):
        if (post.message_id>newest_schedule
                and 0 <= (now-post.published_at).total_seconds() <= 86400
                and re.search(r'київщин|київськ.{0,12}обл',post.text,re.I)
                and re.search(r'екстрен.{0,30}відключ|графік.{0,30}(?:не ді|скасован)|скасован.{0,30}графік',post.text,re.I)):
            remaining_seconds(deadline)
            return dict(schema=1,source='dtek_ua',region='kyiv_region',validated=False,
                source_status='suspended',checked_at=now.isoformat(),published_at=post.published_at.isoformat(),
                groups={},dates=[],source_url=post.url,
                notice='📅 За повідомленням ДТЕК, добові графіки Київщини не діють. EH використовує звичайний резерв.',
                suspension_id=post.message_id)
    if not relevant:
        remaining_seconds(deadline)
        if min(post.published_at for post in parser.posts).astimezone(now.tzinfo).date() >= now.date():
            raise ValueError('Preview does not cover the start of today')
        return dict(schema=1,source='dtek_ua',region='kyiv_region',validated=False,
                    source_status='no_schedule',checked_at=now.isoformat(),groups={},dates=[],
                    source_url='https://t.me/s/dtek_ua')
    # Latest revision of each date wins; an unreadable replacement invalidates
    # the read, rather than falling back to an older same-day chart.
    by_day={day:post for post,day in sorted(relevant,key=lambda p:p[0].message_id)}
    for day,post in sorted(by_day.items()):
        marker=f'data-post="dtek_ua/{post.message_id}"'
        segment=body.split(marker,1)[1].split('data-post=',1)[0]
        urls=re.findall(r"background-image:url\('([^']+)'\)",segment)
        urls=[html.unescape(u) for u in urls if 'telesco.pe/file/' in u]
        if not 1 <= len(urls) <= 2:
            raise ValueError('Missing daily chart images')
        daily={}
        for url in urls:
            remaining_seconds(deadline)
            data=fetch(url,image=True,deadline=deadline)
            key=hashlib.sha256(b'grayscale-label-v2'+data+post.text.encode()+str(sorted(wanted) if wanted is not None else 'all').encode()).hexdigest()
            if key not in cache:
                found_day,found=ocr_image(data,post.text,now,wanted,deadline=deadline)
                cache[key]=dict(day=found_day.isoformat(),groups=found)
            found=cache[key]
            if found['day'] != day.isoformat() or daily.keys() & found['groups'].keys():
                raise ValueError('Conflicting chart groups')
            daily.update(found['groups'])
            if wanted is not None and set(daily)==set(wanted):
                break
        required=set(wanted) if wanted is not None else {f'{g}.{s}' for g in range(1,7) for s in (1,2)}
        if set(daily) != required:
            raise ValueError('Incomplete daily schedule')
        for group,rows in daily.items():
            groups.setdefault(group,[]).extend(rows)
        dates.append(day.isoformat())
        links.append(post.url)
        latest=max(latest,post.published_at) if latest else post.published_at
    # Bound the persisted OCR cache.
    while len(cache)>8:
        del cache[next(iter(cache))]
    remaining_seconds(deadline)
    return dict(schema=1,source='dtek_ua',region='kyiv_region',validated=True,
                source_status='fresh',checked_at=now.isoformat(),published_at=latest.isoformat(),
                groups=groups,dates=dates,source_url=links[-1],source_urls=links)


def relevant_signature(snapshot, groups):
    def normalized(rows):
        # Invalid documents still need a stable signature for source recovery;
        # they must not raise here or silently become a valid empty schedule.
        if not isinstance(rows,list) or any(not isinstance(r,dict) or not {'start','end'} <= r.keys() for r in rows):
            return rows
        return sorted({(r['start'],r['end']) for r in rows})
    value=dict(status=snapshot.get('source_status'),suspension=snapshot.get('suspension_id'),
               dates=sorted(snapshot.get('dates',[])),groups={g:normalized(snapshot.get('groups',{}).get(g,[])) for g in groups})
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def duration(seconds):
    minutes=round(seconds/60)
    hours,mins=divmod(minutes,60)
    return f'{hours} год'+(f' {mins} хв' if mins else '') if hours else f'{mins} хв'


def message(snapshot, mappings, now, selected_day=None, remaining=False):
    lines=[]
    for day in snapshot['dates']:
        if day < now.date().isoformat() or (selected_day is not None and day != selected_day):
            continue
        date=datetime.fromisoformat(day)
        month=next(name for name,n in MONTHS.items() if n==date.month)
        lines.append(f'⚡ <b>ДТЕК · графік відключень · {date.day} {month}{" · до кінця дня" if remaining else ""}</b>')
        for group,label in mappings:
            rows=[r for r in snapshot['groups'].get(group,[]) if r['start'][:10]==day
                  and (not remaining or datetime.fromisoformat(r['end']) > now)]
            pieces=[]
            for row in rows:
                a,b=datetime.fromisoformat(row['start']),datetime.fromisoformat(row['end'])
                window=f"{a:%H:%M}–{('24:00' if b.date()>a.date() and b.hour==0 and b.minute==0 else b.strftime('%H:%M'))}"
                active=remaining and a <= now < b
                length=duration((b-(now if active else a)).total_seconds())
                label_time='до планового відновлення ' if active else ''
                pieces.append(f'<b>{window}</b> · {label_time}<b>{length}</b>')
            icon='🏠' if label=='дача' else '🏢'
            lines.append(f'{icon} {html.escape(label.capitalize())} · <b>{html.escape(group)}</b>: '+
                         ('; '.join(pieces)+'.' if rows else
                          ('планових відключень до кінця дня немає.' if remaining else 'планових відключень немає.')))
    metadata=snapshot.get('day_sources',{}).get(selected_day,{})
    source={'bezsvitla':'BezSvitla · дані ДТЕК','alerts_energy':'Alerts.energy · дані ДТЕК',
            'pro_kyiv':'Pro Kyiv · дані ДТЕК','schedule_sources':'перевірені графіки ДТЕК'}.get(metadata.get('source',snapshot.get('source')),'ДТЕК')
    url=metadata.get('url') or next((u for u in snapshot.get('source_urls',[]) if selected_day and u.endswith(selected_day)),snapshot['source_url'])
    lines.append(f'<a href="{html.escape(url,quote=True)}">Джерело — {source}</a>. Графік може змінитися.')
    return '\n'.join(lines)


def context(state, now, online, group):
    if not online:
        from .schedule_context import loss_context
        return loss_context(state,now,group,'дача')
    document=state.get('dtek_snapshot') or {}
    try:
        checked=datetime.fromisoformat(document['checked_at'])
        if document.get('source_status')=='suspended' and -60 <= (now-checked).total_seconds() <= SOURCE_MAX_AGE_SECONDS:
            return '\n'+document['notice']
        if document.get('source_status')!='fresh' or not -60 <= (now-checked).total_seconds() <= SOURCE_MAX_AGE_SECONDS:
            return ''
        rows=document['groups'][group]
        current=[r for r in rows if datetime.fromisoformat(r['start'])<=now<datetime.fromisoformat(r['end'])]
        upcoming=[r for r in rows if datetime.fromisoformat(r['start'])>now]
        if not online and current:
            end=datetime.fromisoformat(current[0]['end'])
            return f'\n🕒 Відновлення за графіком — <b>{end:%H:%M}</b>.'
        if online and current:
            end=datetime.fromisoformat(current[0]['end'])
            return f'\n📅 Вікно планових відключень — до <b>{end:%H:%M}</b>. Можливе повторне відключення.'
        if online and upcoming:
            row=min(upcoming,key=lambda r:r['start'])
            a,b=datetime.fromisoformat(row['start']),datetime.fromisoformat(row['end'])
            date = 'завтра ' if a.date() == now.date()+timedelta(days=1) else f'{a:%d.%m} ' if a.date() != now.date() else ''
            today = '\n📅 На сьогодні відключень більше не заплановано.' if a.date() > now.date() and now.date().isoformat() in document.get('dates', []) else ''
            return today+f'\n📅 Наступне планове відключення: <b>{date}{a:%H:%M}–{b:%H:%M} · {duration((b-a).total_seconds())}</b>.'
        if online and now.date().isoformat() in document.get('dates', []):
            return '\n📅 На сьогодні відключень більше не заплановано.'
    except (ValueError,KeyError,TypeError):
        pass
    return ''


def morning_lines(config,state,now,client):
    if not getattr(config,'dtek_schedule_enabled',False):
        return []
    document=state.get('dtek_snapshot') or {}
    try:
        checked=datetime.fromisoformat(document['checked_at'])
        if document.get('source_status')=='suspended' and -60 <= (now-checked).total_seconds() <= SOURCE_MAX_AGE_SECONDS:
            from . import source_policy, published_schedule
            status=source_policy.morning_line(state,now) if state.get('pro_notice') else document['notice']
            return [status, *published_schedule.lines(config,state,now),
                    '⚠️ Фактичні відключення можливі в інший час.',
                    '🔋 Резерв визначаємо за доступністю ДТЕК за останні 48 годин; додатково <b>+20 п.п.</b>, максимум <b>95%</b>.',
                    f'<a href="{html.escape(document["source_url"],quote=True)}">Повідомлення та графік — Pro Kyiv · дані ДТЕК</a>.']
        if not -60 <= (now-checked).total_seconds() <= SOURCE_MAX_AGE_SECONDS:
            return ['⚠️ ДТЕК: графік на сьогодні не вдалося перевірити.\n'+FALLBACK_MESSAGE]
        if document.get('source_status')=='no_schedule':
            return ['📅 ДТЕК: графік відключень на сьогодні не опубліковано.\n'+FALLBACK_MESSAGE]
        if document.get('source_status')!='fresh':
            return ['⚠️ ДТЕК: графік на сьогодні не вдалося перевірити.\n'+FALLBACK_MESSAGE]
        if now.date().isoformat() not in document.get('dates',[]):
            return ['⚠️ ДТЕК: графік на сьогодні не вдалося перевірити.\n'+fallback(config,client)]
        from .dtek_emergency import place_active
        mappings=[(g,label) for g,label in [(config.dtek_dacha_group,'дача'),(config.dtek_apartment_group,'квартира')]
                  if not place_active(state,label)]
        lines=[message(document,mappings,now,selected_day=now.date().isoformat(),remaining=True)]
        from . import source_policy
        if any(source_policy.suspended(state,place) for place in ('дача','квартира')):
            lines.insert(0,source_policy.morning_line(state,now))
        if place_active(state,'квартира'):
            lines.append('⚠️ Квартира: графік тимчасово не діє.')
        return lines
    except (KeyError,TypeError,ValueError):
        return ['⚠️ ДТЕК: графік на сьогодні не вдалося перевірити.\n'+FALLBACK_MESSAGE]


def fallback(config, client):
    from .report import number
    row = client.state(getattr(config,'ahm_minimum_soc_entity','input_number.ahm_minimum_soc')) or {}
    minimum = number(row.get('state'))
    return FALLBACK_MESSAGE + (f'\nМінімальний рівень заряду: <b>{minimum:g}%</b>.'
                               if minimum is not None and 0 <= minimum <= 100 else '')


def day_signature(document, mappings, day, now=None):
    rows = {g:sorted({(r['start'],r['end']) for r in document.get('groups',{}).get(g,[])
               if r['start'][:10]==day and (now is None or datetime.fromisoformat(r['end'])>now)})
            for g,_ in mappings}
    return json.dumps(dict(available=day in document.get('dates',[]),groups=rows),sort_keys=True)


def evening_text(config, client, state, now, item):
    day = (now.date()+timedelta(days=1)).isoformat()
    if item.get('day') != day:
        return ''
    doc = state.get('dtek_raw_snapshot') or state.get('dtek_snapshot') or {}
    try:
        valid = (doc.get('source_status')=='fresh' and doc.get('validated') is True
                 and day in doc.get('dates',[])
                 and -60 <= (now-datetime.fromisoformat(doc['checked_at'])).total_seconds() <= SOURCE_MAX_AGE_SECONDS)
    except (KeyError,ValueError,TypeError):
        valid = False
    if item['kind']=='dtek_tomorrow_missing':
        date=datetime.fromisoformat(day)
        month=next(name for name,n in MONTHS.items() if n==date.month)
        today_doc = state.get('dtek_snapshot') or {}
        from .source_policy import schedule_blocked
        try:
            today_valid = (today_doc.get('source_status') == 'fresh'
                and today_doc.get('validated') is True
                and now.date().isoformat() in today_doc.get('dates', [])
                and -60 <= (now-datetime.fromisoformat(today_doc['checked_at'])).total_seconds() <= SOURCE_MAX_AGE_SECONDS
                and not schedule_blocked(state, 'дача', today_doc))
        except (KeyError, ValueError, TypeError):
            today_valid = False
        explanation = ('📅 На сьогодні графік підтверджено — продовжуємо працювати за ним.\n'
                       '🔋 Відсутність графіка на завтра сама по собі не підвищує резерв батареї.'
                       if today_valid else fallback(config, client))
        return '' if valid else (f'⚠️ <b>Не вдалося отримати графік ДТЕК на завтра, {date.day} {month}.</b>\n'+explanation
                                +'\nПеревірку повторюватимемо кожні 30 хвилин.')
    if not valid:
        return ''
    mappings=[(config.dtek_dacha_group,'дача'),(config.dtek_apartment_group,'квартира')]
    if item.get('signature') != day_signature(doc,mappings,day):
        return ''
    result = message(doc,mappings,now,selected_day=day)
    from .source_policy import suspended
    if any(suspended(state, place) for place in ('дача', 'квартира')):
        records=state.get('regional_notices',{})
        declared=any((records.get(place) or state.get('pro_notice',{})).get('kind') in {'fault','emergency'}
                     for place in ('дача','квартира') if suspended(state,place))
        warning=('Є повідомлення про екстрені / аварійні відключення. Графіки можуть не діяти.' if declared
                 else 'Стабілізаційні графіки не діють. Час відключень не підтверджено.')
        result += ('\n⚠️ <b>'+warning+'</b>'
                   '\n🔋 До підтверджених відключень готуємося за графіком; додатковий резерв +20 п.п.')
    if not any(r['start'][:10]==day for g,_ in mappings for r in doc.get('groups',{}).get(g,[])):
        result += '\n'+fallback(config,client)
    return result


def queue_evening(config, client, state, now):
    if now.hour < 20:
        return False
    day=(now.date()+timedelta(days=1)).isoformat()
    doc=state.get('dtek_snapshot') or {}
    mappings=[(config.dtek_dacha_group,'дача'),(config.dtek_apartment_group,'квартира')]
    item=dict(kind='dtek_tomorrow',day=day,signature=day_signature(doc,mappings,day),created_at=now.isoformat())
    text=evening_text(config,client,state,now,item)
    if text:
        state.setdefault('schedule_evening',{})['succeeded']=True
        if state.get('tomorrow_private_failed')==day:
            state.setdefault('pending_notifications',[]).append(dict(kind='technical_dtek_tomorrow',
                message='✅ Графік ДТЕК на завтра прочитано.',created_at=now.isoformat()))
            state.pop('tomorrow_private_failed',None)
    elif state.get('tomorrow_private_failed')!=day:
        state.setdefault('pending_notifications',[]).append(dict(kind='technical_dtek_tomorrow',
            message='⚠️ Не вдалося підтвердити графік ДТЕК на завтра. Повторимо перевірку о 20:30 / 21:00 або на найближчому регулярному опитуванні.',created_at=now.isoformat()))
        state['tomorrow_private_failed']=day
    key=day+'/'+item['signature']
    if text and state.get('tomorrow_announced')!=key:
        state['pending_notifications']=[i for i in state.get('pending_notifications',[]) if i.get('kind') not in {'dtek_tomorrow','dtek_tomorrow_missing'}]
        state['pending_notifications'].append(dict(item,message=text))
        state['tomorrow_announced']=key
        return True
    return False


def next_poll(now):
    """Next local :10/:40 slot, independent of app startup or request duration."""
    start=math.floor(now.timestamp()/60)*60
    for minutes in range(1,31):
        candidate=datetime.fromtimestamp(start+minutes*60,now.tzinfo)
        if candidate.minute in (10,40):
            return candidate


class ScheduleMonitor:
    """One background website read at a time, independent of report delivery."""
    def __init__(self):
        from concurrent.futures import ThreadPoolExecutor
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='dtek-reader')
        self.future=None
        self.due=0
        self.disabled_published=False
        self.disabled_due=0
        self.evening_request=False

    def poll(self, config, client, state, now):
        if not getattr(config,'dtek_schedule_enabled',False):
            state.pop('dtek_read_pending',None)
            if not self.disabled_published or now.timestamp() >= self.disabled_due:
                client.publish_mqtt(TOPIC,planning_document(config,client,now,
                    dict(schema=1,source='bezsvitla',region='kyiv_region',
                         validated=False,source_status='disabled',checked_at=now.isoformat())),retain=True)
                self.disabled_published=True
                self.disabled_due=now.timestamp()+60
            return False
        from . import dtek_emergency
        raw=state.get('dtek_raw_snapshot') or state.get('dtek_snapshot') or {}
        state['dtek_snapshot']=dtek_emergency.authority(raw,state,now)
        mappings=[(config.dtek_dacha_group,'дача'),(config.dtek_apartment_group,'квартира')]
        if not all(GROUP_RE.fullmatch(g) for g,_ in mappings):
            client.publish_mqtt(TOPIC,dict(schema=1,source='bezsvitla',region='kyiv_region',
                validated=False,source_status='invalid_configuration'),retain=True)
            if not state.get('dtek_configuration_error'):
                state.setdefault('pending_notifications',[]).append(dict(kind='technical_dtek_configuration',
                    message='⚠️ ДТЕК: перевірте налаштування груп будинку та квартири. Моніторинг графіків призупинено.',created_at=now.isoformat()))
                state['dtek_configuration_error']=True
                return True
            return False
        state['dtek_configuration_error']=False
        changed=False
        checkpoint=now.date().isoformat()
        evening=state.setdefault('schedule_evening', {})
        if now.hour>=20 and evening.get('date')!=checkpoint:
            evening.clear(); evening.update(date=checkpoint,attempts=0,slots=[])
        slot=min((now.hour*60+now.minute-1200)//30,2)
        if now.hour>=20 and not evening.get('succeeded') and slot not in evening.get('slots',[]) and self.future is None:
            self.due=0
            self.evening_request=True
            state['schedule_evening_check']=checkpoint
            evening.setdefault('slots',[]).append(slot)
            changed=True
        if self.future is not None and self.future.done():
            try:
                snapshot,cache=self.future.result()
                LOGGER.info('Schedule read accepted: source=%s status=%s dates=%s source_failures=%s day_errors=%s',
                            snapshot.get('source'),snapshot.get('source_status'),snapshot.get('dates'),snapshot.get('source_failures',{}),snapshot.get('day_errors',{}))
                from . import source_policy
                state['pro_policy_enabled']=True
                source_policy.apply(state,snapshot.get('source_notice'),config,now,snapshot)
                failures=snapshot.get('source_failures',{})
                failure_keys=sorted(failures)
                previous_failure_keys=sorted(state.get('schedule_source_failures',{}))
                if failure_keys != previous_failure_keys:
                    names={'alerts_energy':'Alerts.energy','pro_kyiv':'Pro Kyiv','schedule_sources':'перевірені резервні джерела'}
                    failed=', '.join('<a href="'+schedule_sources.URLS[key]+'">'+names.get(key,key)+'</a>' for key in failure_keys)
                    state.setdefault('pending_notifications',[]).append(dict(kind='technical_dtek_sources',
                        message=('⚠️ Не вдалося прочитати: '+failed+'. Інформацію про графік взято з '+('<a href="'+schedule_sources.URLS[snapshot['source']]+'">'+names.get(snapshot['source'],snapshot['source'])+'</a>')+'. Повторимо перевірку через 30 хвилин.'
                                 if failures else '✅ Читання джерел графіка ДТЕК відновлено.'),created_at=now.isoformat()))
                state['schedule_source_failures']=failures
                state['dtek_raw_snapshot']=snapshot
                snapshot=dtek_emergency.authority(snapshot,state,now)
                state['dtek_ocr_cache']=cache
                signature=relevant_signature(snapshot,[g for g,_ in mappings])
                if signature != state.get('dtek_signature'):
                    state['dtek_publish_due']=0
                    # Remove superseded requests immediately; delivery also
                    # revalidates every remaining interval and current state.
                    state['pending_notifications']=[i for i in state.get('pending_notifications',[])
                        if i.get('kind') not in {'dtek_reminder','dtek_restoration','dtek_preparation'}
                        or (i.get('kind')=='dtek_preparation' and any(row['start']==i.get('start')
                            for row in snapshot.get('groups',{}).get(config.dtek_dacha_group,[])))
                        or dict(start=i.get('start'),end=i.get('end')) in snapshot.get('groups',{}).get(i.get('group'),[])]
                    state['pending_notifications']=[i for i in state.get('pending_notifications',[]) if i.get('kind') not in {'dtek_schedule','dtek_suspension'}]
                    suspended=snapshot.get('source_status')=='suspended'
                    revised=(state.get('dtek_snapshot') or {}).get('source_status')=='fresh'
                    text=snapshot['notice'] if suspended else message(snapshot,mappings,now,selected_day=now.date().isoformat(),remaining=True)
                    if revised and not suspended:
                        text='📅 <b>Графік відключень оновлено.</b>\n'+text
                    today_changed=day_signature(snapshot,mappings,now.date().isoformat(),now)!=day_signature(state.get('dtek_snapshot') or {},mappings,now.date().isoformat(),now)
                    if (snapshot.get('source_status')!='no_schedule' and today_changed
                            and now.date().isoformat() in snapshot.get('dates',[])
                            and not any(i.get('kind')=='pro_notice' for i in state.get('pending_notifications',[]))):
                        state.setdefault('pending_notifications',[]).append(dict(kind='dtek_suspension' if suspended else 'dtek_schedule',
                            message=text,created_at=now.isoformat(),signature=signature))
                        state['dtek_schedule_revised']=revised
                    state['dtek_signature']=signature
                state['dtek_snapshot']=snapshot
                if state.get('dtek_source_error'):
                    state['pending_notifications']=[i for i in state.get('pending_notifications',[]) if i.get('kind')!='technical_dtek_source']
                    state.setdefault('pending_notifications',[]).append(dict(kind='technical_dtek_recovered',
                        message='✅ Перевірку графіка ДТЕК відновлено.'+(
                            '\nГрафік на сьогодні не опубліковано.\n'+FALLBACK_MESSAGE
                            if snapshot.get('source_status')=='no_schedule' else '\nАктуальну інформацію прочитано.'),created_at=now.isoformat()))
                state['dtek_source_error']=False
                state.pop('dtek_source_error_detail',None)
            except Exception as exc:
                if getattr(exc,'official_banner',None) is not None:
                    from . import source_policy
                    state['pro_policy_enabled']=True
                    source_policy.apply(state,exc.official_banner,config,now)
                LOGGER.warning('DTEK schedule read rejected: %s: %s',type(exc).__name__,str(exc)[:180])
                state['dtek_source_error_detail']=dict(type=type(exc).__name__,message=str(exc)[:180])
                state['dtek_snapshot']=dict(schema=1,source='bezsvitla',region='kyiv_region',
                    validated=False,source_status='unavailable',checked_at=now.isoformat())
                state['dtek_raw_snapshot']=dict(state['dtek_snapshot'])
                state['dtek_snapshot']=dtek_emergency.authority(state['dtek_raw_snapshot'],state,now)
                if not state.get('dtek_source_error'):
                    state.setdefault('pending_notifications',[]).append(dict(kind='technical_dtek_source',
                    message='⚠️ Не вдалося перевірити графік ДТЕК у доступних джерелах.\n'+FALLBACK_MESSAGE+'\nПовторимо перевірку через 30 хвилин.',created_at=now.isoformat()))
                state['dtek_source_error']=True
            self.future=None
            state.pop('dtek_read_pending',None)
            if self.evening_request:
                evening['completed']=evening.get('attempts',0)
            self.evening_request=False
            self.due=next_poll(now).timestamp()
            changed=True
        if self.future is None and evening.get('completed',0)>0:
            changed |= queue_evening(config,client,state,now)
        if self.future is None and now.timestamp() >= self.due:
            previous=dict(state.get('dtek_raw_snapshot',{}))
            def read():
                return schedule_sources.read_snapshot(now,previous,{g for g,_ in mappings}),{}
            self.future=self.executor.submit(read)
            state['dtek_read_pending']=dict(since=now.timestamp())
            if self.evening_request:
                evening['attempts']=evening.get('attempts',0)+1
        if now.timestamp() >= state.get('dtek_publish_due',0):
            snapshot=dict(state.get('dtek_snapshot') or dict(schema=1,source='bezsvitla',region='kyiv_region',validated=False,source_status='starting'))
            snapshot = planning_document(config, client, now, snapshot)
            client.publish_mqtt(TOPIC,snapshot,retain=True)
            state['dtek_publish_due']=now.timestamp()+60
            changed=True
        changed |= queue_reminders(config,client,state,now)
        changed |= queue_restoration_reminders(config,client,state,now)
        preparation=client.state(STATUS_ENTITY) or {}
        line=preparation_for_state(config,client,state,now)
        attributes=preparation.get('attributes',{})
        changed |= rearm_waiting_preparation(state,attributes,now)
        from .soc_interval import preparation_notice
        completion=preparation_notice(state,client,now,attributes)
        if completion:
            state.setdefault('pending_notifications',[]).append(dict(kind='dtek_precharge_complete',
                message=completion,created_at=now.isoformat(),start=attributes.get('start')))
            changed=True
        if (attributes.get('solar_bridge_safe') is True and line == ''
                and (client.state('sensor.energyhub_operating_mode') or {}).get('state')=='solar'):
            try:
                fresh=0 <= (now-datetime.fromisoformat(attributes['checked_at'])).total_seconds() <= 120
                key=attributes['start']+'/solar_bridge'
                at=datetime.fromisoformat(attributes['solar_covers_house_at'])
                minimum=float(attributes['predicted_minimum_soc'])
                reserve=float(attributes['ordinary_reserve_soc'])
                announced=state.setdefault('dtek_preparation_announced',[])
                if fresh and key not in announced and now<datetime.fromisoformat(attributes['start']):
                    solar_notice=('☀️ <b>Готуємося до відключення без дозаряджання від ДТЕК.</b>'
                             f'\n🕒 За прогнозом, від <b>{at:%H:%M}</b> сонце покриватиме споживання будинку.'
                             f'\n🔋 Очікуємо заряд не нижче <b>{math.floor(minimum)}%</b> · резерв <b>{reserve:g}%</b>.'
                             '\n⚡ Допомога ДТЕК наразі не потрібна. Стежимо за генерацією та зарядом.')
                    state.setdefault('pending_notifications',[]).append(dict(kind='dtek_solar_bridge',message=solar_notice,created_at=now.isoformat(),start=attributes['start']))
                    announced.append(key)
                    state['dtek_preparation_announced']=announced[-20:]
                    changed=True
            except (KeyError,ValueError,TypeError):
                pass
        key = str(attributes.get('start'))+'/'+str(attributes.get('end'))
        phase=attributes.get('phase')
        if line and phase == 'charging':
            key=str(attributes.get('start'))+'/'+str(attributes.get('end'))+'/'+phase
            announced=state.setdefault('dtek_preparation_announced',[])
            # Old solar notices did not announce acknowledged grid charging.
            if key not in announced:
                state['pending_notifications']=[i for i in state.get('pending_notifications',[]) if i.get('kind')!='dtek_preparation']
                state.setdefault('pending_notifications',[]).append(dict(kind='dtek_preparation',
                    message=line.strip(),created_at=now.isoformat(),start=attributes.get('start')))
                announced.append(key)
                state['dtek_preparation_announced']=announced[-20:]
                changed=True
        return changed


def rearm_waiting_preparation(state,data,now):
    """A released early episode must not suppress the real later charge notice."""
    try:
        if (data.get('phase')!='waiting' or data.get('control_active') is not False
                or data.get('source_status')!='fresh'
                or not 0<=(now-datetime.fromisoformat(data['checked_at'])).total_seconds()<=120
                or not now<datetime.fromisoformat(data['start'])<datetime.fromisoformat(data['end'])):
            return False
    except (KeyError,TypeError,ValueError):
        return False
    key=data['start']+'/'+data['end']+'/charging'
    announced=state.get('dtek_preparation_announced',[])
    changed=key in announced
    if changed:
        state['dtek_preparation_announced']=[item for item in announced if item!=key]
    session=state.get('precharge_soc_session')
    if isinstance(session,dict) and session.get('key')==data['start']:
        state.pop('precharge_soc_session');changed=True
    return changed


def preparation_energy_details(data, soc, target):
    capacity = number_value(data.get('capacity_kwh'))
    if capacity is None or not 0 < capacity <= 1000 or target <= soc:
        return '', ''
    needed = (target - soc) * capacity / 100
    total = f' (≈{needed:.1f} kWh)'
    solar = number_value(data.get('forecast_net_solar_kwh'))
    grid = number_value(data.get('required_grid_kwh'))
    gross = number_value(data.get('preparation_gross_solar_kwh'))
    house = number_value(data.get('preparation_house_kwh'))
    try:
        deadline = datetime.fromisoformat(data['preparation_forecast_until'])
    except (KeyError, TypeError, ValueError):
        deadline = None
    if (deadline is not None and deadline.tzinfo is not None and gross is not None and gross >= 0
            and house is not None and house >= 0 and grid is not None and grid >= 0):
        return total, (f'\n☀️ До <b>{deadline:%H:%M}</b> очікуємо генерацію <b>≈{gross:.1f} kWh</b>.'
                       f'\n⚡ Від ДТЕК на заряд батареї: <b>≈{grid:.1f} kWh</b>.'
                       f'\n🏠 Споживання будинку до <b>{deadline:%H:%M}</b> — <b>≈{house:.1f} kWh</b>.')
    if (data.get('solar_forecast_complete') is True and solar is not None
            and solar >= 0 and grid is not None and grid >= 0
            and abs(max(0, needed - solar) - grid) <= 0.1):
        solar = min(needed, solar)
        return total, (f'\n⚡ ДТЕК: <b>≈{needed-solar:.1f} kWh</b> · '
                       f'☀️ надлишок сонця: <b>≈{solar:.1f} kWh</b>.')
    reasons = {
        'missing_refresh_time': 'час оновлення прогнозу невідомий',
        'stale_forecast': 'погодинний прогноз застарів',
        'missing_hourly_forecast': 'немає погодинного прогнозу',
        'missing_current_pv': 'немає підтвердженої поточної генерації',
        'coverage_gap': 'погодинний прогноз має пропуски',
        'incomplete_coverage': 'погодинний прогноз не покриває весь час підготовки',
        'overlapping_periods': 'погодинні дані неузгоджені',
        'invalid_periods': 'погодинні дані неузгоджені',
    }
    reason = reasons.get(data.get('preparation_solar_reason'))
    return total, (f'\n⚡ ДТЕК: <b>≈{needed:.1f} kWh</b> · '
                   '☀️ надлишок сонця: не підтверджено (не враховано).'
                   + (' '+reason.capitalize()+'.' if reason else ''))


def charging_heading(client):
    confirmed = client.state('binary_sensor.energyhub_grid_confirmed') or {}
    if confirmed.get('state') == 'off' or (confirmed.get('attributes') or {}).get('unstable') is True:
        return '⚡ <b>Готуємось до відключення</b> · заряджаємо, коли ДТЕК доступний'
    return '⚡ <b>Готуємось до відключення</b> · заряджання від ДТЕК'


def charging_estimate(data):
    minutes = number_value(data.get('estimated_grid_minutes'))
    if minutes is None or not 0 < minutes <= 7*24*60:
        return ''
    return ' ≈<b>'+duration(math.ceil(minutes)*60)+'</b>.'


def coverage_release_text(config, client, state, now):
    """Explain confirmed Solar coverage, never a pending intent or grid loss."""
    data=(client.state(STATUS_ENTITY) or {}).get('attributes',{})
    try:
        soc=number_value(data.get('current_soc'))
        reserve=number_value(data.get('ordinary_reserve_soc'))
        end=datetime.fromisoformat(data['end'])
        grid=number_value((client.state(config.grid_voltage_entity) or {}).get('state'))
        if (data.get('phase')!='solar' or data.get('coverage_release') is not True
                or not 0 <= (now-datetime.fromisoformat(data['checked_at'])).total_seconds() <= 120
                or end<=now or soc is None or reserve is None
                or not 0<=soc<=100 or not 20<=reserve<=95
                or grid is None or not 180<grid<=300
                or (client.state(config.telemetry_freshness_entity) or {}).get('state')!='fresh'
                or (client.state(config.operating_mode_entity) or {}).get('state')!='solar'):
            return ''
        reason=('☀️ <b>Сонця та заряду батареї вистачає до кінця планового відключення.</b>'
                if data.get('solar_bridge_safe') else
                '✅ <b>Заряду вистачає до кінця планового відключення.</b>')
        return (reason+f'\n🔋 Заряд: <b>{soc:g}%</b> · резерв: <b>{reserve:g}%</b>.'+
                f'\n📅 Планове відключення — до <b>{end:%H:%M}</b>.'+
                '\n🏠 <b>Будинок працює без допомоги ДТЕК.</b>')
    except (KeyError,TypeError,ValueError):
        return ''


def preparation_line(client, now, config=None):
    entity=client.state(STATUS_ENTITY) or {}
    data=entity.get('attributes',{})
    if entity.get('state') not in {'solar','charging','holding'}:
        return ''
    try:
        checked=datetime.fromisoformat(data['checked_at'])
        start=datetime.fromisoformat(data['start'])
        end=datetime.fromisoformat(data['end'])
        if not -60 <= (now-checked).total_seconds() <= 120 or end<=now:
            return ''
        from .grid_evidence import qualified
        if qualified(config, client, now) is not True:
            return ''
        if start<=now:
            soc=number_value(data.get('current_soc'))
            target=number_value(data.get('target_soc'))
            if (data.get('phase') == 'holding' and data.get('acknowledged') is True
                    and soc is not None and target is not None and 20 <= target <= 95 and target <= soc <= 100):
                return ''  # Scheduled entry while already holding is silent.
            if not charging_confirmed(data) or soc is None or target is None or not 0<=soc<=100 or not 20<=target<=95:
                return ''
            energy, split = preparation_energy_details(data, soc, target)
            return (f'\n📅 <b>Планове вікно відключень триває до {end:%H:%M}.</b>'
                    '\n🔌 ДТЕК зараз доступний; можливі повторні відключення.'
                    f'\n🔋 Дозаряджаємо від ДТЕК: <b>{soc:g}% → {target:g}%</b>{energy}.'
                    f'\n🛡 Після дозаряджання підтримуватимемо близько <b>{target:g}% до {end:%H:%M}</b>, поки ДТЕК доступний.')
        target=float(data['target_soc'])
        if not math.isfinite(target) or not 20<=target<=95:
            return ''
        if data.get('phase') in {'charging','holding'} and data.get('acknowledged') is True:
            soc=number_value(data.get('current_soc'))
            end=datetime.fromisoformat(data['end'])
            if soc is None or not 0<=soc<=100 or end<=start:
                return ''
            if data['phase']=='holding':
                if soc<target: return ''
                return ('\n✅ <b>Батарея готова до планового відключення.</b>'
                        f'\n🕒 Дача: <b>{start:%H:%M}–{end:%H:%M}</b>.'
                        f'\n🔋 Заряд: <b>{soc:g}%</b> · потрібний рівень: <b>{target:g}%</b>.')
            if not charging_confirmed(data):
                return ''
            energy, split = preparation_energy_details(data, soc, target)
            target_line = f'🔋 Потреба заряду батареї: <b>{soc:g}% → {target:g}%</b> · {energy.strip().strip("()") }.'
            timing = preparation_timing(data, now)
            return (f'\n⚡ Заряджаємо перед відключенням о <b>{start:%H:%M}</b>.'
                    f'\n📅 За графіком: <b>{start:%H:%M}–{end:%H:%M}</b>.'+
                    '\n'+target_line+timing+split)
    except (KeyError,TypeError,ValueError):
        pass
    return ''


def charging_confirmed(data):
    amps=number_value(data.get('observed_charge_a'))
    return data.get('phase') == 'charging' and data.get('acknowledged') is True and amps is not None and amps > 0


def preparation_timing(data, now):
    """Presentation only: margin shortfall is not an outage-deadline failure."""
    minutes = number_value(data.get('estimated_grid_minutes'))
    if minutes is None or not 0 < minutes <= 7*24*60:
        return ''
    try:
        start = datetime.fromisoformat(data['start'])
        if start.tzinfo is None or start <= now:
            return ''
        finish = now+timedelta(minutes=minutes)
        # Grid duration alone cannot claim target completion before credited
        # solar surplus arrives. Keep the forecast planning endpoint in that case.
        if (number_value(data.get('forecast_net_solar_kwh')) or 0) > 0:
            deadline = datetime.fromisoformat(data['charge_deadline'])
            if deadline.tzinfo is None:
                return ''
            finish = max(finish, deadline)
        text = f'\n⏱ Від ДТЕК орієнтовно <b>{duration(math.ceil(minutes)*60)}</b>; завершення близько <b>{finish:%H:%M}</b>.'
        if finish > start+timedelta(minutes=5):
            text += f'\n⚠️ За поточним розрахунком до <b>{start:%H:%M}</b> часу може не вистачити.'
        return text
    except (KeyError, ValueError, TypeError):
        return ''


def preparation_for_state(config,client,state,now):
    if not getattr(config,'dtek_schedule_enabled',False):
        return ''
    document=state.get('dtek_snapshot') or {}
    data=(client.state(STATUS_ENTITY) or {}).get('attributes',{})
    try:
        if (document.get('validated') is not True or document.get('source_status')!='fresh'
                or not -60<=(now-datetime.fromisoformat(document['checked_at'])).total_seconds()<=SOURCE_MAX_AGE_SECONDS
                or dict(start=data['start'],end=data['end']) not in document['groups'][config.dtek_dacha_group]):
            return ''
    except (KeyError,ValueError,TypeError):
        return ''
    text = preparation_line(client,now,config)
    from . import source_policy
    if text and source_policy.suspended(state, 'дача'):
        district = {'Obukhiv':'Обухівському', 'Fastiv':'Фастівському'}.get(getattr(config,'dtek_dacha_district',''), '')
        notice = state.get('regional_notices',{}).get('дача') or state.get('pro_notice',{})
        kind = 'аварійні' if notice.get('kind') == 'fault' else 'екстрені'
        warning = f'⚠️ {"В "+district+" районі" if district else "У районі дачі"} діють <b>{kind} відключення</b> — графіки можуть не витримуватись.'
        parts=text.strip().splitlines()
        text='\n'+'\n'.join([parts[0],warning,*parts[1:]])
    return text


def active_preparation(client,now):
    entity=client.state(STATUS_ENTITY) or {}
    if entity.get('state') not in {'charging','holding'}:
        return None
    data=entity.get('attributes',{})
    try:
        if (data.get('control_active') is True
                and 20<=float(data['target_soc'])<=95
                and -60 <= (now-datetime.fromisoformat(data['checked_at'])).total_seconds() <= 120
                and datetime.fromisoformat(data['start'])>now):
            return data
    except (KeyError,TypeError,ValueError):
        pass
    return None


def recovery_context(config,client,state,now):
    # Preparation-start notice has one owner (ScheduleMonitor); grid-return
    # context supplies the next cut, without replaying a charging announcement.
    detail=context(state,now,True,getattr(config,'dtek_dacha_group',''))
    notice=state.get('pro_notice',{})
    if notice.get('kind')=='fault' and 'дача' in notice.get('places',[]) and not notice.get('cancelled'):
        district={'Obukhiv':'Обухівський район','Fastiv':'Фастівський район'}.get(getattr(config,'dtek_dacha_district',''),'Дача')
        detail='\n⚠️ '+district+': аварійні відключення; графік тимчасово не використовуємо.'+detail
    return detail


def recovery_plan(config,client,state,now):
    """Preparation target, never replace it with the protective base reserve."""
    if not getattr(config,'dtek_schedule_enabled',False): return ''
    from .source_policy import schedule_blocked
    if schedule_blocked(state,'дача'): return ''
    document=state.get('dtek_snapshot') or {}
    data=(client.state(STATUS_ENTITY) or {}).get('attributes',{})
    try:
        if (document.get('validated') is not True or document.get('source_status')!='fresh'
                or not -60<=(now-datetime.fromisoformat(document['checked_at'])).total_seconds()<=SOURCE_MAX_AGE_SECONDS):
            return ''
        group_rows=document.get('groups',{}).get(config.dtek_dacha_group,[])
        active=next((r for r in group_rows if datetime.fromisoformat(r['start'])<=now<datetime.fromisoformat(r['end'])),None)
        if active:
            begin=datetime.fromisoformat(active['start'])
            end=datetime.fromisoformat(active['end'])
            result=f'\n🕒 За графіком: <b>{begin:%H:%M}–{end:%H:%M} · {duration((end-begin).total_seconds())}</b>.'
            soc=number_value((client.state(config.battery_soc_entity) or {}).get('state'))
            target=number_value(data.get('target_soc'))
            if (soc is not None and target is not None and data.get('start')==active['start']
                    and (client.state(config.telemetry_freshness_entity) or {}).get('state')=='fresh'
                    and -60<=(now-datetime.fromisoformat(data['checked_at'])).total_seconds()<=120):
                result+=f'\n🔋 Заряд: <b>{soc:g}%</b> · ціль підготовки: <b>{target:g}%</b>.'
            return result+'\n🔄 Відключимо ДТЕК, коли заряду батареї вистачатиме до кінця планового відключення.'
        rows=[r for r in group_rows if datetime.fromisoformat(r['start'])>now]
        result='\n📅 EH керує зарядом за графіком відключень.'
        if not rows:
            if now.date().isoformat() in document.get('dates',[]):
                return result+'\nНа сьогодні відключень більше не заплановано.'
            return ''
        row=min(rows,key=lambda r:r['start'])
        start,end=datetime.fromisoformat(row['start']),datetime.fromisoformat(row['end'])
        date='завтра ' if start.date()==now.date()+timedelta(days=1) else f'{start:%d.%m} ' if start.date()!=now.date() else ''
        if start.date()>now.date() and now.date().isoformat() in document.get('dates', []):
            result+='\nНа сьогодні відключень більше не заплановано.'
        result+=f'\nНаступне планове відключення: <b>{date}{start:%H:%M}–{end:%H:%M} · {duration((end-start).total_seconds())}</b>.'
        target=number_value(data.get('target_soc'))
        if (data.get('start')==row['start'] and data.get('end')==row['end'] and target is not None and 20<=target<=95
                and -60<=(now-datetime.fromisoformat(data['checked_at'])).total_seconds()<=120):
            result+=f'\n🔋 Потрібний заряд до {start:%H:%M}: <b>{target:g}%</b>.'
            result+='\n⚡ За потреби EH завчасно дозарядить батарею від ДТЕК.'
        else:
            result+='\n🔋 Ціль підготовки ще уточнюється.'
        return result
    except (KeyError,TypeError,ValueError): return ''


def number_value(value):
    try:
        number=float(value)
        return number if math.isfinite(number) else None
    except (TypeError,ValueError):
        return None


def reminder_text(config,client,state,now,item):
    document=state.get('dtek_raw_snapshot') or state.get('dtek_snapshot') or {}
    from .dtek_emergency import place_active
    if place_active(state,item.get('place')):
        return ''
    try:
        checked=datetime.fromisoformat(document['checked_at'])
        start=datetime.fromisoformat(item['start'])
        end=datetime.fromisoformat(item['end'])
        if (not getattr(config,'dtek_schedule_enabled',False) or document.get('source_status')!='fresh' or document.get('validated') is not True
                or not -60<=(now-checked).total_seconds()<=SOURCE_MAX_AGE_SECONDS or start<=now):
            return ''
        if dict(start=item['start'],end=item['end']) not in document['groups'][item['group']]:
            return ''
        left=(start-now).total_seconds()
        when='через годину' if 3300<=left<=3600 else 'через '+duration(left)
        label='Дача' if item['place']=='дача' else 'Квартира'
        text=(f'📅 <b>{label}: планове відключення ДТЕК {when}.</b>'
              f'\n🕒 За графіком: <b>{start:%H:%M}–{end:%H:%M} · {duration((end-start).total_seconds())}</b>.')
        if item['place']=='дача':
            entity=client.state(STATUS_ENTITY) or {}
            data=entity.get('attributes',{})
            target=number_value(data.get('target_soc'))
            try:
                valid_plan=(entity.get('state') not in {'unknown','unavailable'} and data.get('start')==item['start']
                            and target is not None and 40<=target<=95
                            and -60<=(now-datetime.fromisoformat(data['checked_at'])).total_seconds()<=120)
            except (KeyError,TypeError,ValueError):
                valid_plan=False
            soc=number_value((client.state(config.battery_soc_entity) or {}).get('state'))
            fresh=(client.state(config.telemetry_freshness_entity) or {}).get('state')=='fresh'
            if fresh and soc is not None and 0<=soc<=100 and valid_plan:
                grid=number_value((client.state(getattr(config,'grid_voltage_entity','sensor.powmr_10_2m_grid_voltage')) or {}).get('state'))
                from .grid_evidence import qualified
                supply = qualified(config,client,now)
                if soc<target and charging_confirmed(data) and supply is True and grid is not None and 180<grid<=300:
                    text+=f'\n🔋 Заряд: <b>{soc:g}%</b> · дозаряджаємо від ДТЕК до <b>{target:g}%</b>.'
                else:
                    text+=f'\n🔋 Заряд: <b>{soc:g}%</b> · ціль підготовки: <b>{target:g}%</b>.'
                if soc>=target:
                    text+='\n✅ Заряд досяг цілі підготовки.'
                elif supply is not True:
                    text += ('\n⚡ ДТЕК зараз недоступний.' if supply is False
                             else '\n⚡ Живлення ДТЕК не підтверджено.')
                    text += f' Дозаряджання до <b>{target:g}%</b> заплановано після відновлення.'
                    minutes = number_value(data.get('estimated_grid_minutes'))
                    if minutes is not None and 0 < minutes <= 7*24*60:
                        text += f'\n⏱ Орієнтовна тривалість заряджання — <b>{duration(math.ceil(minutes)*60)}</b>.'
                elif 'часу може не вистачити' in preparation_timing(data, now):
                    text+=preparation_timing(data, now)
                elif charging_confirmed(data):
                    pass
                elif data.get('phase')=='solar' and data.get('solar_forecast_complete') is True:
                    text+='\n☀️ Очікуємо поповнення від сонця; EH перевіряє готовність.'
                else:
                    text+='\n⚡ За потреби дозарядимо від ДТЕК.'
            elif fresh and soc is not None and 0<=soc<=100:
                text+=f'\n🔋 Заряд: <b>{soc:g}%</b> · ціль підготовки не підтверджено.'
                from .grid_evidence import qualified
                if qualified(config,client,now) is False:
                    text+='\n⚡ Очікуємо відновлення ДТЕК; ціль дозаряджання уточнюється.'
            else:
                text+='\n🔋 Поточний заряд і ціль підготовки не підтверджено.'
        return text
    except (KeyError,TypeError,ValueError):
        return ''


def queue_reminders(config,client,state,now):
    document=state.get('dtek_raw_snapshot') or state.get('dtek_snapshot') or {}
    from .dtek_emergency import place_active
    try:
        if (not getattr(config,'dtek_schedule_enabled',False) or document.get('source_status')!='fresh' or document.get('validated') is not True
                or not -60<=(now-datetime.fromisoformat(document['checked_at'])).total_seconds()<=SOURCE_MAX_AGE_SECONDS):
            return False
        announced=state.setdefault('dtek_reminders_announced',[])
        changed=False
        for group,place in [(config.dtek_dacha_group,'дача'),(config.dtek_apartment_group,'квартира')]:
            if place_active(state,place):
                continue
            for row in document['groups'].get(group,[]):
                start=datetime.fromisoformat(row['start'])
                if not 0<(start-now).total_seconds()<=3600:
                    continue
                key=f"{place}/{group}/{row['start']}"
                if key in announced:continue
                item=dict(kind='dtek_reminder',place=place,group=group,start=row['start'],end=row['end'],created_at=now.isoformat())
                text=reminder_text(config,client,state,now,item)
                if not text:continue
                item['message']=text
                queue=state.setdefault('pending_notifications',[])
                queue.append(item)
                announced.append(key)
                changed=True
        state['dtek_reminders_announced']=announced[-48:]
        return changed
    except (KeyError,TypeError,ValueError):
        return False


def restoration_text(config,client,state,now,item):
    document=state.get('dtek_raw_snapshot') or state.get('dtek_snapshot') or {}
    from .dtek_emergency import place_active
    if place_active(state,item.get('place')):
        return ''
    try:
        start=datetime.fromisoformat(item['start']); end=datetime.fromisoformat(item['end'])
        if (not getattr(config,'dtek_schedule_enabled',False) or document.get('validated') is not True
                or document.get('source_status')!='fresh'
                or not -60 <= (now-datetime.fromisoformat(document['checked_at'])).total_seconds() <= SOURCE_MAX_AGE_SECONDS
                or not start<=now<end or not 0<(end-now).total_seconds()<=900
                or dict(start=item['start'],end=item['end']) not in document['groups'].get(item['group'],[])):
            return ''
        house=item['place']=='дача'
        fresh=(client.state(config.telemetry_freshness_entity) or {}).get('state')=='fresh'
        grid=number_value((client.state(getattr(config,'grid_voltage_entity','sensor.powmr_10_2m_grid_voltage')) or {}).get('state'))
        if house:
            from .grid_evidence import qualified
            if qualified(config, client, now) is not False:
                return ''
        else:
            proxy = state.get('apartment_grid') or {}
            observed = number_value(proxy.get('observed_at'))
            if (proxy.get('online') is not False or proxy.get('candidate') is not None
                    or observed is None or not 0 <= now.timestamp()-observed <= 90):
                return ''
        label='Дача' if house else 'Квартира'
        text=(f'📅 <b>{label}: до завершення планового відключення ДТЕК — {duration((end-now).total_seconds())}.</b>'
              f'\n🕒 Відновлення за графіком — о <b>{end:%H:%M}</b>.'
              '\nБудь ласка, врахуйте це у своїх планах.')
        if house:
            soc=number_value((client.state(config.battery_soc_entity) or {}).get('state'))
            text+=(f'\n🔋 Поточний заряд батареї: <b>{soc:g}%</b>.'
                   if fresh and soc is not None and 0<=soc<=100 else '\n🔋 Поточний заряд батареї не підтверджено.')
            hp=(client.state('climate.first_floor_heat_pump') or {}).get('state')
            eco=(client.state('switch.first_floor_heat_pump_eco') or {}).get('state')
            if hp=='off':
                text+='\n♨️ Тепловий насос вимкнено.'
            elif hp in {'heat','cool'} and eco=='on':
                text+='\n🍃 Тепловий насос працює в режимі Eco.'
            elif hp in {'heat','cool'}:
                text+='\n♨️ Тепловий насос працює; Eco не підтверджено.'
            else:
                text+='\n⚠️ Стан теплового насоса в HA не підтверджено.'
        return text
    except (KeyError,TypeError,ValueError):
        return ''


def queue_restoration_reminders(config,client,state,now):
    document=state.get('dtek_raw_snapshot') or state.get('dtek_snapshot') or {}
    from .dtek_emergency import place_active
    announced=state.setdefault('dtek_restoration_announced',[])
    changed=False
    for group,place in [(config.dtek_dacha_group,'дача'),(config.dtek_apartment_group,'квартира')]:
        if place_active(state,place):
            continue
        for row in document.get('groups',{}).get(group,[]):
            item=dict(kind='dtek_restoration',place=place,group=group,start=row['start'],end=row['end'],created_at=now.isoformat())
            key=f"{place}/{group}/{row['start']}/{row['end']}"
            if key in announced:
                continue
            message=restoration_text(config,client,state,now,item)
            if message:
                item['message']=message
                state.setdefault('pending_notifications',[]).append(item)
                announced.append(key); changed=True
    state['dtek_restoration_announced']=announced[-48:]
    return changed


def planning_document(config, client, now, base):
    """Publish tariff inputs even when schedule reading is disabled/unavailable."""
    snapshot = dict(base)
    from .planning_settings import read as read_planning_settings
    snapshot.update(read_planning_settings(client))
    snapshot['planning_checked_at'] = now.isoformat()
    snapshot['heating_policy']=(client.state('input_select.energyhub_climate_policy') or {}).get('state')
    snapshot['heating_checked_at']=now.isoformat()
    hp=client.state('climate.first_floor_heat_pump') or {}
    snapshot['hp_state']=hp.get('state')
    snapshot['hp_state_since']=hp.get('last_changed')
    snapshot['hp_running']=hp.get('state') in {'heat','cool'}
    from .report import number
    current=number((client.state('input_number.energyhub_reference_grid_charge_limit') or {}).get('state'))
    snapshot['grid_charge_current_a']=current if current is not None and 0<current<=60 else None
    snapshot['forecast']=[]
    timestamps=[]
    entities=[getattr(config,'solar_forecast_entity',''),getattr(config,'dtek_solar_forecast_tomorrow_entity','')]
    snapshot['night_forecasts'] = {}
    for offset, entity_id in enumerate(entities):
        value = number((client.state(entity_id) or {}).get('state')) if entity_id else None
        if value is not None and 0 <= value <= 1000:
            snapshot['night_forecasts'][(now.date()+timedelta(days=offset)).isoformat()] = value
    for entity_id in entities:
        if not entity_id:
            continue
        forecast=client.state(entity_id) or {}
        raw=forecast.get('attributes',{}).get('detailedHourly',[])
        if not isinstance(raw,list) or forecast.get('state') in (None,'unknown','unavailable'):
            continue
        if raw or number(forecast.get('state')) is not None:
            from .service_incidents import source_refresh
            entity=getattr(config,'solcast_last_success_entity','') or 'sensor.solcast_pv_forecast_api_last_polled'
            refresh=source_refresh({entity: client.state(entity) or {}} if entity else {}, config, now)
            timestamps.append(datetime.fromtimestamp(refresh,now.tzinfo).isoformat() if refresh is not None else '')
        for row in raw[:100]:
            try:
                a=datetime.fromisoformat(row['period_start'])
                if not a.tzinfo:
                    continue
                snapshot['forecast'].append(dict(start=a.isoformat(),end=(a+timedelta(hours=1)).isoformat(),pv_kw=float(row['pv_estimate'])))
            except (KeyError,ValueError,TypeError):
                continue
    snapshot['forecast_at']=min(timestamps) if timestamps else None
    rows=sorted(snapshot['forecast'],key=lambda r:datetime.fromisoformat(r['start']).timestamp())
    starts=[datetime.fromisoformat(r['start']) for r in rows]
    steps=[(b-a).total_seconds() for a,b in zip(starts,starts[1:]) if 0<(b-a).total_seconds()<=3600]
    step=min(steps) if steps else 3600
    if len(set(starts))!=len(starts):
        snapshot['forecast']=[]
    else:
        snapshot['forecast']=[dict(r,end=(a+timedelta(seconds=step)).isoformat()) for r,a in zip(rows,starts)]
    return snapshot
