"""One short energy section; historical planning is not current generation."""
from .report import number, compact_number


def lines(*, consumption, average, sample_count, hp_lines, forecast=None, forecast_label=None,
          night_summary=None, completed=None, day=None):
    result = ['⚡ <b>Споживання та генерація</b>']
    parts = []
    if number(consumption) is not None and consumption >= 0:
        parts.append(f'Учора: <b>{compact_number(consumption)} kWh</b>')
    if number(average) is not None and average >= 0 and sample_count:
        parts.append(f'середнє за {sample_count} дні: <b>{compact_number(average)} kWh</b>')
    result.append('🏠 '+' · '.join(parts)+'.' if parts else '🏠 Споживання не підтверджено.')
    result.extend(hp_lines)
    return result
