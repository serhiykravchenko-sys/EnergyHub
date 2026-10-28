// Source embedded into the Daily Energy Balance card's async data generators.
// Calendar boundaries use HA's timezone, including 23/25-hour local days.
async function energyHistory(kind, entity, start, end, hass) {
  const zone = hass.config.time_zone;
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'
  });
  const parts = at => Object.fromEntries(formatter.formatToParts(at)
    .filter(p => p.type !== 'literal').map(p => [p.type, Number(p.value)]));
  const key = at => {
    const p = parts(at);
    return `${p.year}-${String(p.month).padStart(2, '0')}-${String(p.day).padStart(2, '0')}`;
  };
  const dayOffset = (day, n) => {
    const d = new Date(`${day}T00:00:00Z`);
    d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  };
  const boundary = day => {
    const wanted = Date.parse(`${day}T00:00:00Z`);
    let at = wanted;
    for (let i = 0; i < 4; i++) {
      const p = parts(new Date(at));
      at += wanted - Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
    }
    return at;
  };
  const today = key(new Date());
  const days = Array.from({length: 7}, (_, i) => dayOffset(today, i - 6));
  const ids = kind === 'grid'
    ? ['sensor.energyhub_grid_import_night_total_estimated',
       'sensor.energyhub_grid_import_normal_total_estimated']
    : ['sensor.powmr_10_2m_daily_house_consumption'];
  let response = {};
  try {
    response = await hass.callWS({
      type: 'recorder/statistics_during_period',
      start_time: new Date(boundary(days[0])).toISOString(),
      end_time: new Date(boundary(dayOffset(today, 1))).toISOString(),
      statistic_ids: ids, period: 'day', types: ['change'], units: {energy: 'kWh'}
    }) || {};
  } catch (_) { /* Missing recorder history remains null, never zero. */ }
  const perEntity = ids.map(id => {
    const map = new Map();
    for (const row of response[id] || []) {
      const at = typeof row.start === 'number'
        ? new Date(row.start * (row.start < 1e11 ? 1000 : 1)) : new Date(row.start);
      if (!Number.isFinite(at.getTime()) || typeof row.change !== 'number'
          || !Number.isFinite(row.change) || row.change < 0) continue;
      const day = key(at);
      // Never sum misaligned or partial sub-day records as a complete day.
      if (Math.abs(at.getTime() - boundary(day)) > 1000) continue;
      map.set(day, row.change);
    }
    return map;
  });
  return days.map(day => {
    const left = boundary(day), right = boundary(dayOffset(day, 1));
    const values = perEntity.map(m => m.get(day));
    let value = values.every(Number.isFinite) ? values.reduce((a, b) => a + b, 0) : null;
    if (kind === 'consumption' && day === today) {
      const live = hass.states[ids[0]];
      const at = new Date(live?.last_reported || live?.last_updated || '');
      const parsed = Number(live?.state);
      value = live && live.state !== '' && Number.isFinite(parsed) && parsed >= 0
        && Number.isFinite(at.getTime()) && key(at) === today ? parsed : null;
    }
    return [(left + right) / 2, value];
  });
}

if (typeof module !== 'undefined') module.exports = {energyHistory};
