"""Bounded official text notices; local telemetry owns restoration confirmation."""
import html
import re
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from .uhmc_source import TelegramPreviewParser
from .outage_schedule import FALLBACK_MESSAGE

URL = 'https://t.me/s/dtek_ua'
LOGGER=logging.getLogger('telegram-family-assistant.dtek-emergency')
DISTRICTS={'Obukhiv':'обухів','Fastiv':'фастів','Brovary':'броварськ',
           'Bucha':'бучанськ','Vyshhorod':'вишгородськ','Boryspil':'бориспільськ',
           'Bila Tserkva':'білоцерківськ'}


def affected_places(text, config=None):
    folded=text.casefold()
    named={name for name,stem in DISTRICTS.items() if stem in folded}
    if not named and 'район' not in folded:
        return ['дача','квартира']
    return [place for place,option in [('дача','dtek_dacha_district'),('квартира','dtek_apartment_district')]
            if getattr(config,option,'') in named]


def notice_type(text):
    return 'fault' if re.search(r'аварійн\w*\s+відключ', text.casefold()) else 'emergency'


def notice_label(kind):
    return 'аварійні відключення' if kind == 'fault' else 'екстрені відключення'


def outage_status(text, kind=None):
    """Require a declaration of this outage type within the same sentence."""
    folded=text.casefold()
    stem={'emergency':'екстрен','fault':'аварійн'}.get(kind,'(?:екстрен|аварійн)')
    outage=stem+r'\w*\s+відключ\w*'
    for sentence in re.split(r'[.!?;\n]+', folded):
        if re.search(outage+r'\s+(?:скасован|припинен)', sentence) or re.search(
                r'(?:скасован|припинен)\w*\s+'+outage, sentence):
            return False
        for match in re.finditer(outage, sentence):
            prefix=sentence[:match.start()]
            # Advice, hypothetical events and explicit negation are not active
            # declarations, even when another outage type is active nearby.
            if re.search(r'уник\w*|запоб\w*|можлив\w*|якщо|у разі|немає|не діють|не застосов', prefix):
                continue
            declarations=list(re.finditer(r'\b(?:застосован\w*|застосовують|запроваджен\w*|введен\w*|діють|зафіксован\w*|сталос\w*|надало\s+команду\s+про\s+застосування)\b', prefix))
            if declarations:
                between=prefix[declarations[-1].end():]
                if len(between)<=140 and not re.search(r'(?:стабілізаційн|екстрен|аварійн)\w*\s+відключ',between):
                    return True
            if re.search(r'графік\w*\s+(?:тимчасово\s+)?не\s+ді',sentence):
                return True
    return None


def classify(text):
    heading=text.casefold().split('\n',1)[0]
    if not re.search(r'київщин|київськ\w*\s+област', heading):
        return None
    return outage_status(text)


def read(now, config=None):
    from urllib.request import Request, urlopen
    with urlopen(Request(URL, headers={'User-Agent':'EnergyHub/3.6.4'}), timeout=12) as response:
        if response.geturl() != URL:
            raise ValueError('Unexpected Telegram redirect')
        raw = response.read(524289)
    if len(raw)>524288:
        raise ValueError('Telegram response too large')
    parser=TelegramPreviewParser('dtek_ua')
    parser.feed(raw.decode('utf-8'))
    parser.close()
    if not parser.posts or parser.missing_publication_time:
        raise ValueError('Incomplete Telegram text feed')
    posts=[]
    for post in parser.posts:
        if not post.published_at or not -60 <= (now-post.published_at).total_seconds() <= 172800:
            continue
        active=classify(post.text)
        if active is not None:
            posts.append(dict(id=post.message_id,active=active,url=post.url,at=post.published_at.isoformat(),
                              places=affected_places(post.text,config),notice_type=notice_type(post.text)))
    return sorted(posts,key=lambda p:p['id'])


def apply(state, posts, now):
    if not posts:
        return False
    monitor=state.setdefault('dtek_emergency', {})
    post=max(posts,key=lambda item:item['id'])
    last_id=monitor.get('last_id',0)
    if post['id'] < last_id:
        return False
    reconcile=monitor.get('selection_version') != 2
    if post['id'] == last_id and not reconcile:
        return False
    places=post.get('places',['дача','квартира'])
    house_active=post['active'] and 'дача' in places
    try:
        # A confirmed restoration after this notice prevents historical replay.
        restored_at=datetime.fromisoformat(state['grid_restored_at'])
        if restored_at > datetime.fromisoformat(post['at']):
            house_active=False
    except (KeyError,ValueError,TypeError):
        pass
    monitor.update(last_id=post['id'],selection_version=2,notice_type=post.get('notice_type','emergency'),source_url=post['url'],
                   source_at=post.get('at',now.isoformat()),
                   house_source_url=post['url'],active=house_active,
                   apartment_active=post['active'] and 'квартира' in places,
                   seen_grid_off=house_active and state.get('grid_online') is False)
    if selected_monitor(state) is not monitor:
        # A later successfully observed official banner owns current scope.
        return True
    # Remove any undelivered 3.6.1 notice that described obsolete authority.
    state['pending_notifications']=[item for item in state.get('pending_notifications',[])
        if item.get('kind') not in {'dtek_emergency','dtek_suspension'}]
    if 'dtek_raw_snapshot' in state:
        state['dtek_snapshot']=authority(state['dtek_raw_snapshot'],state,now)
    # Same-ID migration repairs state without forwarding the notice twice.
    if not places or (reconcile and post['id']==last_id):
        return True
    effective_places=[place for place in places if place!='дача' or not post['active'] or house_active]
    if not effective_places:
        return True
    scope='Київська область' if effective_places==['дача','квартира'] else 'Київська область · '+effective_places[0]
    if post['active']:
        message=f'🚨 <b>{scope}: {notice_label(monitor.get("notice_type"))}.</b>'
        if 'дача' in effective_places:
            if state.get('grid_online') is False:
                message+='\nНа дачі ДТЕК недоступний. Графік тимчасово не використовуємо.\n'+FALLBACK_MESSAGE
            elif state.get('grid_online') is True:
                message+='\nНа дачі ДТЕК доступний. Повідомлення для інформації; підготовку за графіком продовжуємо.'
            else:
                message+='\nДоступність ДТЕК на дачі не підтверджена; очікуємо актуальні вимірювання.'
        if 'квартира' in effective_places:
            message+='\nДля квартири час відновлення за графіком не підтверджено.'
    else:
        message=f'🟢 <b>{scope}: {notice_label(monitor.get("notice_type"))} скасовані.</b>\nПовертаємося до графіків після їх перевірки.'
    state.setdefault('pending_notifications',[]).append(dict(kind='dtek_emergency',
        message=message+f'\n<a href="{html.escape(post["url"],quote=True)}">Повідомлення ДТЕК</a>',created_at=now.isoformat()))
    return True


def restore(state):
    if state.get('pro_policy_enabled'):
        return False
    changed=False
    for key in ('dtek_emergency','dtek_site_emergency'):
        monitor=state.setdefault(key,{})
        if not monitor.get('active'):
            continue
        if state.get('grid_online') is False:
            monitor['seen_grid_off']=True
        elif state.get('grid_online') is True and monitor.get('seen_grid_off'):
            monitor['active']=False
            changed=True
    if changed and 'dtek_raw_snapshot' in state:
        state['dtek_snapshot']=dict(state['dtek_raw_snapshot'])
    return changed


def selected_monitor(state):
    telegram=state.get('dtek_emergency',{})
    site=state.get('dtek_site_emergency',{})
    try:
        if datetime.fromisoformat(site['source_at']) >= datetime.fromisoformat(telegram.get('source_at','')):
            return site
    except (KeyError,ValueError,TypeError):
        if site.get('source_at') and not telegram.get('source_at'):
            return site
    return telegram


def apply_banner(state, notice, config, now):
    """Current official modal observations replace older notice scope once."""
    import hashlib
    active=notice['active'] is True
    places=affected_places(notice['text'],config) if active else []
    kind=notice.get('notice_type','emergency')
    fingerprint=hashlib.sha256((str(active)+'|'+','.join(places)+'|'+kind).encode()).hexdigest()
    monitor=state.setdefault('dtek_site_emergency',{})
    legacy_fingerprint=hashlib.sha256((str(active)+'|'+','.join(places)).encode()).hexdigest()
    if monitor.get('fingerprint')==legacy_fingerprint and kind=='emergency':
        monitor.update(fingerprint=fingerprint,notice_type=kind)
        return False
    if monitor.get('fingerprint')==fingerprint:
        # An unchanged banner is not a new notice. It cannot supersede a later
        # Telegram update or rearm an outage cleared by local restoration.
        return False
    before=selected_monitor(state)
    previous=(bool(before.get('active')),bool(before.get('apartment_active')))
    previous_kind=before.get('notice_type','emergency')
    monitor.update(fingerprint=fingerprint,notice_type=kind,source_at=notice['checked_at'],source_url=notice['url'],
        active=active and 'дача' in places,apartment_active=active and 'квартира' in places,
        seen_grid_off=active and 'дача' in places and state.get('grid_online') is False)
    current=(monitor['active'],monitor['apartment_active'])
    if previous==current and previous_kind==kind:
        return True
    state['pending_notifications']=[i for i in state.get('pending_notifications',[]) if i.get('kind') not in {'dtek_emergency','dtek_suspension'}]
    if active and places:
        scope='Київська область' if len(places)==2 else 'Київська область · '+places[0]
        message=f'🚨 <b>{scope}: {notice_label(monitor.get("notice_type"))}.</b>'
        if 'дача' in places:
            if state.get('grid_online') is False:
                message+='\nНа дачі ДТЕК недоступний. Графік тимчасово не використовуємо.\n'+FALLBACK_MESSAGE
            elif state.get('grid_online') is True:
                message+='\nНа дачі ДТЕК доступний. Повідомлення для інформації; підготовку за графіком продовжуємо.'
            else:
                message+='\nДоступність ДТЕК на дачі не підтверджена; очікуємо актуальні вимірювання.'
        if 'квартира' in places:
            message+='\nДля квартири час відновлення за графіком не підтверджено.'
    elif any(previous):
        message='🟢 <b>ДТЕК: поточне повідомлення більше не підтверджує позапланові відключення для наших районів.</b>\nВикористовуємо перевірений графік.'
    else:
        return True
    state.setdefault('pending_notifications',[]).append(dict(kind='dtek_emergency',
        message=message+f'\n<a href="{html.escape(notice["url"],quote=True)}">Офіційний сайт ДТЕК</a>',created_at=now.isoformat()))
    return True


def authority(snapshot, state, now):
    if state.get('pro_policy_enabled'):
        from . import source_policy
        return source_policy.authority(snapshot,state,now)
    monitor=selected_monitor(state)
    notice_active=monitor.get('active') is True
    snapshot=dict(snapshot,emergency_notice_active=notice_active,
                  emergency_grid_state='offline' if state.get('grid_online') is False else 'online' if state.get('grid_online') is True else 'unknown')
    if not place_active(state,'дача'):
        if snapshot.get('source_status') == 'suspended':
            # A legacy suspended wrapper is not a validated raw schedule.
            snapshot.update(validated=False,source_status='unavailable',notice='')
        return snapshot
    return dict(snapshot,validated=False,source_status='suspended',checked_at=now.isoformat(),
                notice='🚨 Дача: '+notice_label(monitor.get('notice_type'))+'. Графік тимчасово не використовуємо.\n'+FALLBACK_MESSAGE,
                source_url=monitor.get('house_source_url',monitor.get('source_url',URL)))


def place_active(state, place):
    if state.get('pro_policy_enabled'):
        from . import source_policy
        return source_policy.schedule_blocked(state,place)
    monitor=selected_monitor(state)
    return (monitor.get('active',False) and state.get('grid_online') is False
            if place=='дача' else monitor.get('apartment_active',False))


class Monitor:
    def __init__(self):
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='dtek-emergency')
        self.future=None
        self.due=0

    def poll(self, config, state, now):
        if not getattr(config,'dtek_schedule_enabled',False):
            return False
        changed=restore(state)
        if not all(getattr(config,key,'') in DISTRICTS for key in ('dtek_dacha_district','dtek_apartment_district')) and not state.get('dtek_district_configuration_notified'):
            state.setdefault('pending_notifications',[]).append(dict(kind='technical_dtek_districts',
                message='⚠️ ДТЕК: налаштуйте райони будинку та квартири для повідомлень про локальні екстрені відключення. Невідомий район не вважаємо підтвердженим збігом.',created_at=now.isoformat()))
            state['dtek_district_configuration_notified']=True
            changed=True
        if self.future is not None and self.future.done():
            try:
                changed |= apply(state,self.future.result(),now)
                if state.pop('dtek_emergency_error',False):
                    state.setdefault('pending_notifications',[]).append(dict(kind='technical_dtek_emergency',
                        message='✅ Читання текстових повідомлень ДТЕК відновлено.',created_at=now.isoformat()))
            except Exception as exc:
                LOGGER.warning('Official DTEK text read failed: %s: %s',type(exc).__name__,str(exc)[:160])
                if not state.get('dtek_emergency_error'):
                    state.setdefault('pending_notifications',[]).append(dict(kind='technical_dtek_emergency',
                        message='⚠️ Не вдалося прочитати текстові повідомлення ДТЕК. Повторимо через 30 хвилин. Стан екстрених відключень не змінено.',created_at=now.isoformat()))
                state['dtek_emergency_error']=True
            self.future=None; self.due=now.timestamp()+1800; changed=True
        if self.future is None and now.timestamp()>=self.due:
            self.future=self.executor.submit(read,now,config)
        return changed
