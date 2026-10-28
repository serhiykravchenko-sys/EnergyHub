"""Bounded public HTML reader. No address submission, OCR or control commands."""
import html
import json
import re
import time
from datetime import datetime, timedelta
from urllib.request import Request, urlopen

BASE = 'https://bezsvitla.com.ua/kyivska-oblast'


def text(fragment):
    return ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', fragment)).split())


def fetch(url, deadline):
    remaining = deadline-time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Schedule read exceeded time budget')
    if not re.fullmatch(re.escape(BASE)+r'/grafik-na-\d{4}-\d{2}-\d{2}', url):
        raise ValueError('Unapproved schedule URL')
    with urlopen(Request(url, headers={'User-Agent':'EnergyHub-Schedule/3.6'}), timeout=min(12,remaining)) as response:
        if response.geturl() != url:
            raise ValueError('Unexpected schedule redirect')
        data=response.read(2_000_001)
    if time.monotonic() >= deadline:
        raise TimeoutError('Schedule read exceeded time budget')
    if len(data)>2_000_000:
        raise ValueError('Schedule response too large')
    return data.decode('utf-8')


def parse_page(body, day, now, wanted):
    from .outage_schedule import cell_intervals
    headings=re.findall(r'<h1\b[^>]*>(.*?)</h1>',body,re.S|re.I)
    if len(headings)!=1 or 'Київській області' not in text(headings[0]):
        raise ValueError('Missing Kyiv-region heading')
    if day.strftime('%d.%m.%Y') not in text(headings[0]):
        raise ValueError('Schedule date mismatch')
    published=[]
    for raw in re.findall(r'<script\b[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',body,re.S):
        document=json.loads(raw)
        for node in document.get('@graph',[]) if isinstance(document,dict) else []:
            if node.get('@type')=='WebPage' and node.get('dateModified'):
                at=datetime.fromisoformat(node['dateModified'])
                if at.tzinfo is None or not -60 <= (now-at).total_seconds() <= 48*3600:
                    raise ValueError('Schedule publication is stale or future')
                published.append(at)
    if len(published)!=1:
        raise ValueError('Missing unique publication timestamp')
    cards=re.findall(r'<article\b[^>]*class="bz-schedule-card"[^>]*>(.*?)</article>',body,re.S)
    if not cards:
        # Missing markup is a source failure, not proof that there are no cuts.
        grid=re.search(r'<section\b[^>]*class="bz-schedule-grid"[^>]*>(.*?)</section>',body,re.S)
        if grid and re.search(r'графік.{0,40}не опубліковано',text(grid[1]),re.I):
            return {}, published[0], False
        raise ValueError('Missing explicit schedule cards')
    result={}
    for card in cards:
        labels=re.findall(r'<strong>Черга ([1-6]\.[12])</strong>',card)
        if len(labels)!=1:
            raise ValueError('Uncertain group identity')
        group=labels[0]
        if group not in wanted:
            continue
        if group in result:
            raise ValueError('Duplicate group')
        updates=re.findall(r'Оновлено\s+(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2})',text(card))
        if len(updates)!=1:
            raise ValueError('Missing group revision timestamp')
        at=datetime.strptime(updates[0],'%d.%m.%Y %H:%M').replace(tzinfo=now.tzinfo)
        if not -60 <= (now-at).total_seconds() <= 48*3600:
            raise ValueError('Group revision is stale or future')
        published.append(at)
        slots=re.findall(r'<div\b[^>]*class="([^"]*\bbz-schedule-slot\b[^"]*)"[^>]*>(.*?)</div>',card,re.S)
        coverage=[]; outages=[]
        for classes,slot in slots:
            flags=set(classes.split()) & {'bz-schedule-slot--on','bz-schedule-slot--off'}
            if len(flags)!=1:
                raise ValueError('Uncertain power status')
            off='bz-schedule-slot--off' in flags
            label='Без світла' if off else 'Є світло'
            if f'aria-label="{label}"' not in slot:
                raise ValueError('Conflicting power status')
            clocks=re.findall(r'<span class="bz-schedule-slot__time">(.*?)</span>',slot,re.S)
            if len(clocks)!=1:
                raise ValueError('Uncertain interval')
            rows=cell_intervals('Без світла '+text(clocks[0]),day,now.tzinfo)
            if len(rows)!=1:
                raise ValueError('Unexpected interval count')
            row=rows[0]
            if row['start'][:10]!=day.isoformat():
                raise ValueError('Wrong interval date')
            coverage.append(row)
            if off:
                outages.append(row)
        begin=datetime.combine(day,datetime.min.time(),now.tzinfo).isoformat()
        end=datetime.combine(day+timedelta(days=1),datetime.min.time(),now.tzinfo).isoformat()
        if (not coverage or coverage[0]['start']!=begin or coverage[-1]['end']!=end
                or any(a['end']!=b['start'] for a,b in zip(coverage,coverage[1:]))):
            raise ValueError('Incomplete or overlapping daily coverage')
        # Adjacent OFF fragments are one outage, including source revisions.
        merged=[]
        for row in outages:
            if merged and merged[-1]['end']==row['start']:
                merged[-1]['end']=row['end']
            else:
                merged.append(dict(row))
        result[group]=merged
    if result.keys()!=wanted:
        raise ValueError('Missing configured group')
    return result,min(published),True


def read_snapshot(now, cache=None, wanted=None):
    wanted=set(wanted or {'1.1','2.2'})
    deadline=time.monotonic()+90
    groups={g:[] for g in wanted}; dates=[]; links=[]; published=[]; errors={}
    for day in (now.date(),now.date()+timedelta(days=1)):
        url=BASE+'/grafik-na-'+day.isoformat()
        try:
            rows,at,available=parse_page(fetch(url,deadline),day,now,wanted)
        except Exception as exc:
            errors[day.isoformat()]=type(exc).__name__
            continue
        published.append(at)
        if available:
            dates.append(day.isoformat()); links.append(url)
            for group in wanted:
                groups[group].extend(rows[group])
    if time.monotonic()>=deadline:
        raise TimeoutError('Schedule read exceeded time budget')
    if not published:
        raise ValueError('Neither daily schedule could be validated')
    return dict(day_errors=errors,schema=1,source='bezsvitla',region='kyiv_region',validated=bool(dates),
                source_status='fresh' if dates else 'no_schedule',checked_at=now.isoformat(),
                published_at=min(published).isoformat(),groups=groups,dates=dates,
                source_url=links[0] if links else BASE,source_urls=links)
