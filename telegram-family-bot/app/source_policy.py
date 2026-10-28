"""Pro Kyiv regional notices; schedule mirrors do not cancel emergency notices."""
import hashlib
import re
from datetime import datetime
from .dtek_emergency import affected_places
from .outage_schedule import FALLBACK_MESSAGE


def parse(section, revision, now):
    from .schedule_sources import text
    # Only the introductory regional notice, never the Kyiv-city section or FAQ.
    intro=text(re.split(r'<details\b',section,flags=re.I)[0])
    folded=intro.casefold()
    from .regional_status import district_statuses
    regional=district_statuses(intro)
    from .dtek_emergency import outage_status
    emergency=outage_status(intro,'emergency')
    fault=outage_status(intro,'fault')
    inactive=bool(re.search(r'графік\w*(?:\s+відключ\w*)?\s+(?:тимчасово\s+)?не\s+ді',folded))
    scheduled=bool(re.search(r'(?<!не )\b(?:діють|застосовуються|відновлено)\s+стабілізаційн\w*\s+(?:відключ|графік)',folded)
                   or re.search(r'стабілізаційн\w*\s+(?:графік\w*|відключ\w*)\s+(?:знову\s+)?діють',folded))
    kind=('emergency' if emergency is not None else
          'fault' if fault is not None else
          'scheduled' if inactive or scheduled else None)
    if kind is None and regional:
        kind=next(iter(regional.values()))['kind']
    if not kind:
        return None
    if inactive and emergency is not True and fault is not True:
        kind='scheduled'
    cancelled=(emergency is False if kind=='emergency' else fault is False if kind=='fault' else False)
    inactive=inactive or (kind in {'fault','emergency'} and not cancelled)
    return dict(text=intro,kind=kind,cancelled=cancelled,schedules_invalid=inactive,
                district_statuses=regional,
                revision=revision,checked_at=now.isoformat())


def apply(state, notice, config, now, snapshot=None):
    if notice is None:
        return False
    places=affected_places(notice['text'],config)
    from .regional_status import household_records
    regional=household_records(notice,config)
    if notice.get('district_statuses'):
        places=list(regional)
    record=state.setdefault('pro_notice',{})
    previous_records = dict(state.get('regional_notices', {}))
    if record.get('revision') and datetime.fromisoformat(notice['revision']) < datetime.fromisoformat(record['revision']):
        return False
    signature_data=sorted((p,r['kind'],r['cancelled'],r['schedules_invalid'], concise_description(r, config, p))
                          for p in places for r in [regional.get(p) or notice])
    signature=hashlib.sha256(str(signature_data).encode()).hexdigest()
    changed=signature!=record.get('signature')
    if record.get('signature') and record.get('signature_schema') != 3:
        previous_data = sorted((p,r.get('kind'),r.get('cancelled'),r.get('schedules_invalid'),
                                concise_description(r, config, p))
                               for p in record.get('places', [])
                               for r in [previous_records.get(p) or record])
        if previous_data == signature_data:
            changed = False  # A signature-format upgrade is not a new notice.
    # Missing notice text cannot clear saved status. A newer explicit status can.
    if changed and notice['schedules_invalid']:
        record['invalid_since']=notice['revision']
        record['invalid_groups']=(snapshot or state.get('dtek_raw_snapshot') or {}).get('groups')
    record.update(notice,places=places,signature=signature,signature_schema=3)
    records=state.setdefault('regional_notices',{})
    for place in places:
        previous=records.get(place) or {}
        if not previous or datetime.fromisoformat(notice['revision'])>=datetime.fromisoformat(previous['revision']):
            replacement=regional.get(place) or dict(notice,places=places)
            previous_scope = household_records(previous, config).get(place)
            prior_active = (previous_scope is not None and previous_scope.get('kind') == previous.get('kind')
                            and previous_scope.get('schedules_invalid') is True)
            # Global evidence is valid only if its own notice has no named
            # unrelated district. Reparse legacy text rather than trusting a
            # historically mis-scoped saved places list.
            if previous and not previous.get('district_statuses'):
                reparsed = parse(previous.get('text',''), previous.get('revision', now.isoformat()), now)
                if reparsed:
                    scoped = household_records(reparsed,config).get(place)
                    prior_active = (scoped.get('schedules_invalid') is True if scoped else
                                    not reparsed.get('district_statuses') and place in affected_places(previous.get('text',''),config)
                                    and previous.get('schedules_invalid') is True)
            if (prior_active and previous.get('kind') in {'fault','emergency'} and not previous.get('cancelled')
                    and (replacement.get('cancelled') or (replacement.get('kind')=='scheduled' and not replacement.get('schedules_invalid')))):
                replacement=dict(replacement,cleared_kind=previous['kind'],clear_confirmed=True)
            elif (previous.get('clear_confirmed') is True and previous.get('kind') == replacement.get('kind')
                  and previous.get('cancelled') == replacement.get('cancelled')
                  and previous.get('schedules_invalid') == replacement.get('schedules_invalid')):
                replacement=dict(replacement,cleared_kind=previous.get('cleared_kind'),clear_confirmed=True)
            records[place]=replacement
    state['pro_policy_enabled']=True
    if changed:
        state['pending_notifications']=[i for i in state.get('pending_notifications',[]) if i.get('kind') not in {'dtek_emergency','dtek_suspension','pro_notice'}]
    document = snapshot or state.get('dtek_raw_snapshot') or {}
    groups = document.get('groups') or {}
    # Group identifiers, not district names, select schedule rows.
    selected = [(p, sorted({(r.get('start'),r.get('end')) for r in groups.get(getattr(config,field,''),[])}))
                for p,field in [('дача','dtek_dacha_group'),('квартира','dtek_apartment_group')]]
    schedule_signature = hashlib.sha256(str((sorted(document.get('dates') or []),selected)).encode()).hexdigest()
    schedule_changed = bool(any(suspended(state,p) for p in places)
                            and schedule_signature != record.get('schedule_signature'))
    record['schedule_signature'] = schedule_signature
    meaningful_status = changed and any(
        suspended(state,p) or (state.get('regional_notices',{}).get(p) or {}).get('cleared_kind')
        or (previous_records.get(p,{}).get('kind') == 'scheduled'
            and previous_records.get(p,{}).get('schedules_invalid') is True
            and (state.get('regional_notices',{}).get(p) or {}).get('kind') == 'scheduled')
        for p in places)
    if (meaningful_status or schedule_changed) and places:
        state['pending_notifications']=[i for i in state.get('pending_notifications',[]) if i.get('kind')!='pro_notice']
        message=notification_text(config,state,now,snapshot)
        state.setdefault('pending_notifications',[]).append(dict(kind='pro_notice',message=message,created_at=now.isoformat(),
            policy_schema=2,notice_signature=signature,schedule_signature=schedule_signature))
    return changed


def status_lines(state, now, places=('дача','квартира'), only_active=False):
    """Status belongs to household districts, never an unrelated local fault."""
    grouped={}
    for place in places:
        record=(state.get('regional_notices',{}).get(place) or state.get('pro_notice',{}))
        if place not in record.get('places',[]):
            continue
        active=suspended(state,place)
        if only_active and not active:
            continue
        kind=record.get('kind')
        if active:
            label={'emergency':'екстрені відключення','fault':'аварійні відключення'}.get(kind,'обмеження відключень')
            suffix=' — графіки можуть не витримуватись.'
            icon='⚠️'
        elif kind=='scheduled' and record.get('schedules_invalid') is False:
            label='стабілізаційні відключення'
            suffix='.';icon='🟢'
        elif record.get('cancelled'):
            label={'emergency':'екстрені відключення скасовано','fault':'аварійні відключення скасовано'}.get(kind,'обмеження скасовано')
            suffix='.';icon='🟢'
        else:
            continue
        try:
            fresh=-60 <= (now-datetime.fromisoformat(record['checked_at'])).total_seconds() <= 2100
        except (KeyError,ValueError,TypeError):
            fresh=False
        stale='' if fresh else ' (останній підтверджений статус)'
        grouped.setdefault((icon,label,suffix,stale),[]).append(place)
    result=[]
    for (icon,label,suffix,stale),group in grouped.items():
        title='Дача та квартира' if len(group)==2 else group[0].capitalize()
        result.append(f'{icon} <b>{title}: {label}</b>{suffix}{stale}')
    return result


def notification_text(config,state,now,snapshot=None):
    notice=state.get('pro_notice',{})
    places=notice.get('places',[])
    if not places:
        return '\n'.join(status_lines(state,now))
    regional=[(state.get('regional_notices',{}).get(p) or {}) for p in places]
    from .published_schedule import lines as published_lines
    schedule=published_lines(config,state,now,snapshot)
    label={'fault':'аварійні','emergency':'екстрені','scheduled':'стабілізаційні'}[notice['kind']]
    scope='Дача та квартира' if len(places)==2 else places[0].capitalize()
    message=f'{"🟢" if notice["kind"] == "scheduled" and not notice["schedules_invalid"] else "⚠️"} <b>{scope}: {label} відключення.</b>'
    if notice['kind']=='scheduled' and notice['schedules_invalid']:
        message=f'⚠️ <b>{scope}: стабілізаційні графіки не діють.</b>'
    if notice['cancelled']:
        message=f'🟢 <b>{scope}: {label} відключення скасовані.</b>'
    blocked=[p for p in places if suspended(state,p,snapshot)]
    if blocked:
        message+='\nГрафіки можуть не витримуватись.'
        message+='\n'+'\n'.join(schedule)
    elif notice['kind']=='fault' and not notice['cancelled']:
        message+='\nМожливі затримки відновлення. Графік використовуємо після перевірки актуальності.'
    if not blocked:
        message+='\n'+'\n'.join(schedule)
    if regional and any(r.get('district_statuses') for r in regional):
        headings=status_lines(state,now,places)
        cleared={}
        for place,r in zip(places,regional):
            if r.get('cleared_kind'):
                cleared.setdefault(r['cleared_kind'],[]).append(place)
        cancellations=[]
        for kind,group in sorted(cleared.items()):
            scope='Дача та квартира' if len(group)==2 else group[0].capitalize()
            cancellations.append(scope+': '+('Екстрені' if kind=='emergency' else 'Аварійні')+' відключення скасовано.')
        message='\n'.join(headings+cancellations+schedule)
    from html import escape
    descriptions = []
    for place, record in zip(places, regional):
        description = concise_description(record or notice, config, place)
        if description and description not in descriptions:
            descriptions.append(description)
    if descriptions:
        message += '\n'+'\n'.join(escape(value) for value in descriptions)
    message+='\n<a href="'+escape(notice.get('source_url','https://pro.kyiv.ua/grafik-vidklyuchennya-svitla/'),quote=True)+'">Джерело — '+escape(notice.get('source_label','Pro Kyiv · дані ДТЕК'))+'</a>'
    return message


def concise_description(notice, config, place):
    """Preserve factual scope; discard restoration boilerplate, never infer it."""
    if notice.get('kind') not in {'fault', 'emergency'} or notice.get('cancelled'):
        return ''
    from .dtek_emergency import DISTRICTS
    district = getattr(config, 'dtek_dacha_district' if place == 'дача' else 'dtek_apartment_district', '')
    stem = DISTRICTS.get(district)
    if not stem:
        return ''
    sentences = re.split(r'(?<=[.!?])\s+|\n+', notice.get('text', ''))
    result = []
    previous_applicable = False
    for sentence in sentences:
        folded = sentence.casefold()
        applicable = stem in folded and bool(re.search(r'аварі|екстрен|без\s+світла|зникло\s+світло', folded))
        restoration_time = previous_applicable and not any(
            other in folded for key, other in DISTRICTS.items() if key != district
        ) and bool(re.search(r'віднов\w*.*\b\d{1,2}:\d{2}\b', folded))
        previous_applicable = applicable
        if not applicable and not restoration_time:
            continue
        # An informational copy keeps qualifiers and original district names.
        # Never rewrite "part of the district" as the household losing power.
        sentence = re.sub(r'\s+', ' ', sentence).strip()
        partial = re.fullmatch(r'[УВ] частині (.+? районів) зникло світло через локальну аварію в мережі\.?', sentence, flags=re.I)
        if partial:
            sentence = 'Локальна аварія: без світла частина '+partial[1].replace(' і ', ' та ')+'.'
        if sentence and len(sentence) <= 1000:
            result.append(sentence)
    return ' '.join(result[:2])


def suspended(state,place,snapshot=None):
    record=state.get('regional_notices',{}).get(place) or state.get('pro_notice',{})
    if place not in record.get('places',[]) or record.get('cancelled'):
        return False
    if record.get('kind') in {'emergency','fault'}:
        return True
    if not record.get('schedules_invalid'):
        return False
    # Charts may remain visible or change while the status explicitly invalidates
    # them. Only a newer explicit operating-status notice may clear this record.
    return True


def authority(snapshot,state,now):
    record=state.get('regional_notices',{}).get('дача') or state.get('pro_notice',{})
    explicit_clear=('дача' in record.get('places',[]) and
                    (record.get('cancelled') is True or
                     (record.get('kind')=='scheduled' and record.get('schedules_invalid') is False)))
    snapshot=dict(snapshot,emergency_notice_active=suspended(state,'дача',snapshot),
                  emergency_notice_confirmed_clear=explicit_clear,
                  emergency_grid_state='offline' if state.get('grid_online') is False else 'online' if state.get('grid_online') is True else 'unknown')
    if schedule_blocked(state,'дача',snapshot):
        snapshot.update(validated=False,source_status='suspended',notice='⚠️ Графік для дачі тимчасово не використовуємо.\n'+FALLBACK_MESSAGE)
    return snapshot


def schedule_blocked(state, place, snapshot=None):
    """Emergency status adds reserve; fresh published rows remain usable.

    Callers still validate date/age/group before any preparation or message.
    This helper never turns an invalid or stale document into a valid one.
    """
    if not suspended(state, place, snapshot):
        return False
    document = snapshot if snapshot is not None else state.get('dtek_snapshot') or state.get('dtek_raw_snapshot') or {}
    return not (document.get('validated') is True and document.get('source_status') == 'fresh')


def morning_line(state, now):
    """Report the observed regional notice; failed reads never imply all clear."""
    record=state.get('pro_notice',{})
    try:
        fresh=(-60 <= (now-datetime.fromisoformat(record['checked_at'])).total_seconds() <= 2100
               and record.get('source_url','https://pro.kyiv.ua/grafik-vidklyuchennya-svitla/')
               == 'https://pro.kyiv.ua/grafik-vidklyuchennya-svitla/')
    except (KeyError,TypeError,ValueError):
        fresh=False
    if not fresh:
        return 'ℹ️ Актуальний статус відключень на Pro Kyiv не підтверджено; зберігаємо останній підтверджений режим.'
    if record.get('district_statuses'):
        lines=status_lines(state,now)
        if lines:
            return '\n'.join(lines)
    blocked=[place for place in ('дача','квартира') if suspended(state,place)]
    if blocked:
        kind=record.get('kind')
        label={'emergency':'екстрені відключення','fault':'аварійні відключення'}.get(kind,'обмеження відключень')
        return '⚠️ За повідомленням Pro Kyiv, у Київській області діють <b>'+label+'</b>. Графіки можуть не витримуватись; до опублікованих відключень також готуємося.'
    if record.get('kind')=='scheduled' and not record.get('schedules_invalid'):
        snapshot=state.get('dtek_raw_snapshot') or {}
        try:
            schedule_fresh=(snapshot.get('validated') and
                -60 <= (now-datetime.fromisoformat(snapshot['checked_at'])).total_seconds() <= 2100)
        except (KeyError,TypeError,ValueError):
            schedule_fresh=False
        return 'ℹ️ Pro Kyiv: діють стабілізаційні відключення. '+(
            'EH працює за актуальним графіком.' if schedule_fresh else 'Актуальний графік ще не підтверджено.')
    return 'ℹ️ Pro Kyiv: для наших районів підтверджений графік відключень використовується після перевірки актуальності.'
