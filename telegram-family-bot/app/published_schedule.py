"""Informational published rows never grant outage-control authority."""
from datetime import datetime


def lines(config, state, now, document=None):
    document = document if document is not None else state.get('dtek_raw_snapshot') or {}
    from .outage_schedule import SOURCE_MAX_AGE_SECONDS
    try:
        checked = datetime.fromisoformat(document['checked_at'])
        if (document.get('validated') is not True or document.get('source_status') != 'fresh'
                or not -60 <= (now-checked).total_seconds() <= SOURCE_MAX_AGE_SECONDS
                or now.date().isoformat() not in document.get('dates', [])):
            raise ValueError('Unconfirmed published schedule')
        result = ['📅 <b>Опублікований графік · до кінця дня:</b>']
        for group, label in ((getattr(config, 'dtek_dacha_group', ''), '🏠 Дача'),
                             (getattr(config, 'dtek_apartment_group', ''), '🏢 Квартира')):
            rows = document['groups'][group]
            windows = []
            for row in rows:
                a, b = datetime.fromisoformat(row['start']), datetime.fromisoformat(row['end'])
                if b <= a:
                    raise ValueError('Invalid interval')
                if a.date() <= now.date() and b > now:
                    end = '24:00' if b.date() > a.date() and b.hour == b.minute == 0 else f'{b:%H:%M}'
                    windows.append(f'{a:%H:%M}–{end}')
            result.append(f'{label}: <b>'+(' та '.join(windows) if windows else 'планових відключень до кінця дня немає')+'</b>')
        return result
    except (KeyError, TypeError, ValueError):
        return ['📅 Опублікований графік на сьогодні ще не підтверджено.']
