"""Family delivery preferences, independent of heat-pump control windows."""


def minutes(value):
    hour, minute = map(int, value.split(':'))
    return hour*60+minute


def quiet_phase(now, config=None, *, report_buffer_minutes=1):
    current = now.hour*60+now.minute
    report = minutes(getattr(config, 'send_time', '08:00'))
    start = minutes(getattr(config, 'family_quiet_start', '23:00'))
    end = minutes(getattr(config, 'family_quiet_end', '08:01'))
    # Keep the report first when other notifications are ready at the same time.
    if (current-report) % 1440 <= report_buffer_minutes:
        return 'morning_buffer'
    inside = (start <= current < end if start < end else
              current >= start or current < end if start > end else False)
    return 'overnight' if inside else None
