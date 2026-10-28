"""Bounded public schedule readers. No OCR, address submission or controls."""
import html
import json
import re
import time
from datetime import datetime, timedelta
from html.parser import HTMLParser
from urllib.request import Request, urlopen

URLS = {
    'dtek_official': 'https://www.dtek-krem.com.ua/ua/shutdowns',
    'alerts_energy': 'https://alerts.energy/kyivska-oblast',
    'pro_kyiv': 'https://pro.kyiv.ua/grafik-vidklyuchennya-svitla/',
}
OPERATOR = 'kyivska_oblast_oblenergo'


def text(body):
    return ' '.join(html.unescape(re.sub(r'<[^>]*>', ' ', body)).split())


def fetch(url, deadline):
    if url not in (URLS['pro_kyiv'], URLS['alerts_energy']):
        raise ValueError('Unapproved source URL')
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Schedule read budget exhausted')
    with urlopen(Request(url, headers={'User-Agent': 'EnergyHub-Schedule/3.6.5'}),
                 timeout=min(12, remaining)) as response:
        if response.geturl() != url:
            raise ValueError('Unexpected source redirect')
        raw = response.read(4_000_001)
    if len(raw) > 4_000_000 or time.monotonic() >= deadline:
        raise ValueError('Source response exceeded bounds')
    return raw.decode('utf-8')


def publication(raw, now):
    at = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    if not at.tzinfo or not -60 <= (now-at).total_seconds() <= 48*3600:
        raise ValueError('Invalid source revision timestamp')
    return at


def intervals(cells, day, now):
    if len(cells) != 24 or any(type(c) is not int or c not in (0, 1, 2, 3) for c in cells):
        raise ValueError('Incomplete or ambiguous hourly coverage')
    begin = datetime.combine(day, datetime.min.time(), now.tzinfo)
    rows = []
    for hour, code in enumerate(cells):
        if code == 0:
            continue
        start = begin + timedelta(hours=hour, minutes=30 if code == 3 else 0)
        end = begin + timedelta(hours=hour+1, minutes=-30 if code == 2 else 0)
        if rows and rows[-1]['end'] == start.isoformat():
            rows[-1]['end'] = end.isoformat()
        else:
            rows.append(dict(start=start.isoformat(), end=end.isoformat()))
    return rows


def assignment(body, name):
    scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', body, re.S | re.I)
    matches = []
    for script in scripts:
        for marker in re.finditer(r'\bDisconSchedule\.'+re.escape(name)+r'\s*=\s*', script):
            value, _ = json.JSONDecoder().raw_decode(script[marker.end():])
            matches.append(value)
    if len(matches) != 1:
        raise ValueError('Missing unique official data assignment')
    return matches[0]


class BannerParser(HTMLParser):
    """Capture only the announcement modal, excluding unrelated/hidden FAQ text."""
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.paragraph = None
        self.paragraphs = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if not self.depth and attrs.get('id') == 'modal-attention':
            self.depth = 1
        elif self.depth:
            if tag not in {'br', 'img', 'input', 'meta', 'link', 'hr', 'path', 'circle'}:
                self.depth += 1
            if tag == 'p':
                self.paragraph = []

    def handle_endtag(self, tag):
        if self.depth:
            if tag == 'p' and self.paragraph is not None:
                self.paragraphs.append(' '.join(''.join(self.paragraph).split()))
                self.paragraph = None
            if tag not in {'br', 'img', 'input', 'meta', 'link', 'hr', 'path', 'circle'}:
                self.depth -= 1

    def handle_data(self, data):
        if self.depth and self.paragraph is not None:
            self.paragraph.append(data)


def official_banner(body, now):
    # The original page explicitly opens this modal. Mere emergency keywords
    # elsewhere (including advice about avoiding emergency cuts) are not status.
    if not re.search(r"MicroModal\.show\(['\"]modal-attention['\"]\)", body):
        return None
    parser = BannerParser(); parser.feed(body); parser.close()
    if not parser.paragraphs:
        return None
    first = parser.paragraphs[0].casefold()
    from .weather_warning import MONTHS
    dates = re.findall(r'\b(\d{1,2})\s+('+'|'.join(MONTHS)+r')\b', first)
    if dates and any(int(d) != now.day or MONTHS[m] != now.month for d, m in dates):
        return None
    from .dtek_emergency import outage_status, notice_type
    status=outage_status(first)
    if status is not None:
        return dict(active=status, notice_type=notice_type(first), text='\n'.join(parser.paragraphs), checked_at=now.isoformat(),
                    url=URLS['dtek_official'])
    if re.search(r'діють\s+стабілізаційн\w*\s+відключ', first):
        return dict(active=False, text='\n'.join(parser.paragraphs), checked_at=now.isoformat(),
                    url=URLS['dtek_official'])
    return None


def parse_official(body, now, wanted):
    if 'DisconSchedule.fact' not in body:
        raise ValueError('Official page blocked or missing data')
    fact = assignment(body, 'fact')
    preset = assignment(body, 'preset')
    at = publication(datetime.strptime(fact['update'], '%d.%m.%Y %H:%M')
                     .replace(tzinfo=now.tzinfo).isoformat(), now)
    today = datetime.fromtimestamp(fact['today'], now.tzinfo)
    if today.date() != now.date() or today.hour or today.minute:
        raise ValueError('Official current date mismatch')
    slots = official_slots(preset.get('time_zone'))
    codes = {'yes': 0, 'no': 1, 'first': 2, 'second': 3}
    result = {}
    errors = {}
    for day in (now.date(), now.date()+timedelta(days=1)):
        try:
            midnight = datetime.combine(day, datetime.min.time(), now.tzinfo)
            data = fact['data'][str(int(midnight.timestamp()))]
            rows = {}
            for group in wanted:
                key = 'GPV'+group
                if preset.get('sch_names', {}).get(key) != 'Черга '+group:
                    raise ValueError('Official group identity mismatch')
                cells = data[key]
                if set(cells) != {key for key, _, _ in slots}:
                    raise ValueError('Missing official hour')
                rows[group] = []
                for key, a, b in slots:
                    code = codes[cells[key]]
                    if code == 0:
                        continue
                    middle = (a+b)/2
                    start = midnight+timedelta(minutes=middle if code == 3 else a)
                    end = midnight+timedelta(minutes=middle if code == 2 else b)
                    if rows[group] and rows[group][-1]['end'] == start.isoformat():
                        rows[group][-1]['end'] = end.isoformat()
                    else:
                        rows[group].append(dict(start=start.isoformat(), end=end.isoformat()))
            result[day.isoformat()] = dict(groups=rows, published_at=at.isoformat())
        except (KeyError, ValueError, TypeError) as exc:
            errors[day.isoformat()] = type(exc).__name__
    if not result:
        raise ValueError('No official daily schedule validated')
    return result, errors, official_banner(body, now)


def official_slots(mapping):
    if not isinstance(mapping, dict) or len(mapping) not in (24, 48):
        raise ValueError('Unknown official slot coverage')
    slots = []
    def minutes(value):
        if not isinstance(value, str) or not re.fullmatch(r'(?:[01][0-9]|2[0-4]):[0-5][0-9]', value):
            raise ValueError('Invalid official slot clock')
        hour, minute = map(int, value.split(':'))
        if hour == 24 and minute:
            raise ValueError('Invalid day end')
        return hour*60+minute
    for key, row in mapping.items():
        if not isinstance(row, list) or len(row) != 3:
            raise ValueError('Invalid official slot metadata')
        a, b = minutes(row[1]), minutes(row[2])
        if b-a != 1440/len(mapping):
            raise ValueError('Ambiguous official slot width')
        slots.append((key, a, b))
    slots.sort(key=lambda row: row[1])
    if slots[0][1] != 0 or slots[-1][2] != 1440 or any(a[2] != b[1] for a,b in zip(slots, slots[1:])):
        raise ValueError('Incomplete official day coverage')
    return slots


def parse_alerts(body, now, wanted):
    matches = re.findall(r'<script\b[^>]*id="ng-state"[^>]*>(.*?)</script>', body, re.S)
    if len(matches) != 1:
        raise ValueError('Missing unique backup state')
    state = json.loads(matches[0])
    entries = [v for v in state.values() if isinstance(v, dict) and
               str(v.get('u', '')).endswith('/source-registry/areas/kyivska-oblast/shutdowns')]
    if len(entries) != 1 or entries[0].get('s') != 200:
        raise ValueError('Missing Kyiv-region schedule response')
    data = entries[0]['b']
    selected = {}
    for row in data:
        if row.get('initiator') == OPERATOR and row.get('queue') in wanted:
            if row['queue'] in selected:
                raise ValueError('Duplicate backup group')
            selected[row['queue']] = row
    if set(selected) != set(wanted):
        raise ValueError('Configured DTEK groups absent')
    result = {}; errors = {}
    for label, day in [('today', now.date()), ('tomorrow', now.date()+timedelta(days=1))]:
        try:
            rows = {}; times = []
            for group, row in selected.items():
                if (row.get(label+'Date') != day.isoformat() or
                        row.get(label+'Status') != 'ScheduleApplies' or
                        row.get(label+'SourceSlug') != OPERATOR+'_web' or
                        row.get(label+'Possible') != [0]*24):
                    raise ValueError('Unconfirmed backup day or operator')
                times.append(publication(row[label+'CheckedAt'], now))
                rows[group] = intervals(row[label], day, now)
            result[day.isoformat()] = dict(groups=rows, published_at=min(times).isoformat())
        except (KeyError, ValueError, TypeError) as exc:
            errors[day.isoformat()] = type(exc).__name__
    if not result:
        raise ValueError('No backup daily schedule validated')
    return result, errors, None


def pro_context(body, now):
    # Match the normalized heading, never city tables or incidental FAQ text.
    sections = [section for heading, section in re.findall(
        r'<h2\b[^>]*>(.*?)</h2>(.*?)(?=<h2\b|\Z)', body, re.S | re.I)
        if text(heading).casefold() in {'відключення в київській області',
            'відключення світла київська область'}]
    if len(sections) != 1:
        raise ValueError('Missing unique Kyiv-region section')
    section = sections[0]
    if 'https://www.dtek-krem.com.ua/ua/shutdowns' not in section:
        raise ValueError('Wrong official operator link')
    updates = sorted(set(re.findall(r'Оновлено\s+(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2})', text(section))))
    if len(updates) != 1:
        raise ValueError('Missing backup revision')
    at = datetime.strptime(updates[0], '%d.%m.%Y %H:%M').replace(tzinfo=now.tzinfo)
    publication(at.isoformat(), now)
    return section,at


def parse_pro(body, now, wanted):
    section,at=pro_context(body,now)
    from .weather_warning import MONTHS
    heading = re.search(r'на (\d{1,2}) ('+'|'.join(MONTHS)+r')', text(section))
    if not heading or int(heading[1]) != now.day or MONTHS[heading[2]] != now.month or at.year != now.year:
        raise ValueError('Backup schedule date mismatch')
    days = {}; errors = {}
    details = re.findall(r'<details\b[^>]*>(.*?)</details>', section, re.S)
    for day in (now.date(),now.date()+timedelta(days=1)):
        label=f'Графік відключень у Київській області на {day.day} '+next(m for m,n in MONTHS.items() if n==day.month)
        matches=[d for d in details if re.search(r'<summary\b[^>]*>(.*?)</summary>',d,re.S) and
                 text(re.search(r'<summary\b[^>]*>(.*?)</summary>',d,re.S)[1])==label]
        try:
            if len(matches)!=1:
                raise ValueError('Missing unique daily backup section')
            days[day.isoformat()]=dict(groups=pro_table(matches[0],day,now,wanted),published_at=at.isoformat())
        except (KeyError,TypeError,ValueError) as exc:
            errors[day.isoformat()]=type(exc).__name__
    if not days:
        raise ValueError('No backup coverage validated')
    from . import source_policy
    return days,errors,source_policy.parse(section,at.isoformat(),now)


def pro_table(section,day,now,wanted):
    tables = re.findall(r'<table\b[^>]*>(.*?)</table>', section, re.S)
    if len(tables) != 1:
        raise ValueError('Missing unique backup coverage table')
    hours = re.findall(r'<th\b[^>]*>(.*?)</th>', tables[0], re.S)
    if [text(h) for h in hours[1:]] != [f'{h:02d}-{h+1:02d}' for h in range(24)]:
        raise ValueError('Backup hour mapping changed')
    groups = {}
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', tables[0], re.S):
        cells = re.findall(r'<td\b([^>]*)>(.*?)</td>', row, re.S)
        if not cells:
            continue
        label = re.fullmatch(r'Черга ([1-6]\.[12])', text(cells[0][1]))
        if not label or label[1] not in wanted:
            continue
        group = label[1]
        if group in groups:
            raise ValueError('Duplicate backup coverage')
        states = []
        for attrs, content in cells[1:]:
            found = re.search(r'class="([^"]+)"', attrs)
            flags = set(found[1].split()) if found else set()
            if not flags <= {'c', 'off', 'first', 'second'} or 'c' not in flags or text(content):
                raise ValueError('Unknown backup cell state')
            status = flags-{'c'}
            if len(status) > 1:
                raise ValueError('Conflicting backup cell state')
            states.append({'off': 1, 'first': 2, 'second': 3}.get(next(iter(status), ''), 0))
        groups[group] = intervals(states, day, now)
    if set(groups) != set(wanted):
        raise ValueError('Missing configured backup group')
    return groups


class ScheduleReadError(ValueError):
    def __init__(self, banner):
        super().__init__('No current schedule source could be validated')
        self.official_banner=banner


def retire_official_state(state):
    """Retire transport diagnostics without claiming source recovery."""
    state.get('schedule_source_failures', {}).pop('dtek_official', None)
    state['pending_notifications']=[item for item in state.get('pending_notifications', [])
        if not (item.get('kind') == 'technical_dtek_sources'
                and 'Офіційний сайт ДТЕК' in str(item.get('message', '')))]


def read_snapshot(now, previous=None, wanted=None, official_trial=False):
    # Retired option is accepted for migration only; it cannot enable requests.
    wanted = set(wanted or {'1.1', '2.2'})
    deadline = time.monotonic()+90
    candidates = {}; failures = {}; banner = None
    for source, parser in [('pro_kyiv', parse_pro), ('alerts_energy', parse_alerts)]:
        try:
            body=fetch(URLS[source], deadline)
            if source == 'pro_kyiv':
                from . import source_policy
                section,at=pro_context(body,now)
                banner=source_policy.parse(section,at.isoformat(),now)
            days, errors, notice = parser(body, now, wanted)
            candidates[source] = days
            if source == 'pro_kyiv':
                banner = notice
        except Exception as exc:
            failures[source] = type(exc).__name__+': '+str(exc)[:120]
    selected = {}; day_errors = {}; previous = previous or {}
    for day in (now.date().isoformat(), (now.date()+timedelta(days=1)).isoformat()):
        available = [(source, days[day]) for source, days in candidates.items() if day in days]
        # Primary and fallback priority is explicit; revision rollback remains
        # rejected even when the primary source becomes reachable again.
        priority = {'pro_kyiv': 1, 'alerts_energy': 0}
        available.sort(key=lambda item: (priority[item[0]], datetime.fromisoformat(item[1]['published_at'])), reverse=True)
        old = previous.get('day_sources', {}).get(day)
        for source, data in available:
            if old and datetime.fromisoformat(data['published_at']) < datetime.fromisoformat(old['published_at']):
                continue
            selected[day] = dict(data, source=source, url=URLS[source]); break
        if day not in selected:
            day_errors[day] = 'Unconfirmed'
    if not selected:
        error = ScheduleReadError(banner)
        raise error
    groups = {group: [] for group in wanted}
    for day in sorted(selected):
        for group in wanted:
            groups[group].extend(selected[day]['groups'][group])
    sources = {d['source'] for d in selected.values()}
    result = dict(schema=1, source=next(iter(sources)) if len(sources) == 1 else 'schedule_sources',
                region='kyiv_region', validated=True, source_status='fresh', checked_at=now.isoformat(),
                published_at=min(d['published_at'] for d in selected.values()), groups=groups,
                dates=sorted(selected), day_sources={day: {k: d[k] for k in ('source', 'published_at', 'url')} for day, d in selected.items()},
                source_url=selected[min(selected)]['url'], source_urls=list(dict.fromkeys(d['url'] for d in selected.values())),
                source_failures=failures, day_errors=day_errors, source_notice=banner, official_banner=None)
    return result
