"""Explicit district scopes in mixed Kyiv-region operating-status bulletins."""
import re
from .dtek_emergency import DISTRICTS, outage_status


def district_statuses(text):
    folded=text.casefold()
    named={key for key,stem in DISTRICTS.items() if stem in folded}
    result={}
    # Do not split calendar dates such as 17.10 into unrelated clauses.
    for sentence in re.split(r'[!?;\n]|\.(?:\s+|$)',folded):
        local={key for key,stem in DISTRICTS.items() if stem in sentence}
        complement=bool(re.search(r'(?:в|у)\s+(?:решті|інших)\s+район',sentence))
        stable=bool(re.search(r'\b(?:діють|застосовуються|відновлено)\s+стабілізаційн\w*\s+(?:відключ|графік)',sentence)
                    or re.search(r'стабілізаційн\w*\s+(?:графік\w*|відключ\w*)\s+(?:знову\s+)?діють',sentence))
        if stable and not re.search(r'не\s+(?:діють|застосовуються)|графік\w*\s+не\s+ді',sentence):
            all_districts=bool(re.search(r'(?:в|у)\s+усіх\s+район|по\s+всій\s+област|на\s+всій\s+території',sentence))
            scope=(set(DISTRICTS)-named) if complement and named else set(DISTRICTS) if all_districts else local
            if scope:
                for district in scope:
                    result[district]=dict(kind='scheduled',cancelled=False,schedules_invalid=False)
        for kind in ['emergency','fault']:
            active=outage_status(sentence,kind)
            if (kind=='fault' and active is None and local
                    and not re.search(r'можлив|якщо|у\s+разі',sentence)
                    and re.search(r'(?:через\s+локальн\w*\s+аварі|через\s+аварі\w*\s+(?:в|у)\s+мереж)',sentence)):
                active=True
            if active is not None:
                for district in local:
                    result[district]=dict(kind=kind,cancelled=not active,schedules_invalid=active)
    return result


def household_records(notice,config):
    mapping=notice.get('district_statuses') or {}
    return {place:dict(notice,**mapping[district],places=[place])
            for place,field in [('дача','dtek_dacha_district'),('квартира','dtek_apartment_district')]
            if (district:=getattr(config,field,'')) in mapping}
