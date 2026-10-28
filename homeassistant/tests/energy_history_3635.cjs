const assert = require('assert');
const {energyHistory} = require('../dashboard/energy_history.js');
const RealDate = Date;
const ids = ['sensor.energyhub_grid_import_night_total_estimated',
  'sensor.energyhub_grid_import_normal_total_estimated'];
const consumption = 'sensor.powmr_10_2m_daily_house_consumption';

(async () => {
  global.Date = class extends RealDate {
    constructor(...args) { super(...(args.length ? args : ['2026-10-26T12:00:00+02:00'])); }
  };
  const starts = Array.from({length: 7}, (_, i) =>
    RealDate.parse(`2026-10-${20+i}T00:00:00${i < 6 ? '+03:00' : '+02:00'}`));
  let request;
  const response = Object.fromEntries([...ids, consumption].map((id, index) =>
    [id, starts.map((t, i) => ({start: t/1000, change: index === 2 ? 10+i : 2+index+i}))]));
  const hass = {config: {time_zone: 'Europe/Kyiv'}, states: {
    [consumption]: {state: '3.7', last_updated: '2026-10-26T10:00:00Z'}
  }, callWS: async r => {request = r; return response;}};
  let points = await energyHistory('grid', {}, null, null, hass);
  assert.deepStrictEqual(points.map(p => p[1]), starts.map((_, i) => 5+2*i));
  assert.strictEqual((Date.parse(request.end_time)-Date.parse(request.start_time))/3600000, 169);
  assert.strictEqual(points[5][0], starts[5]+12.5*3600000, '25-hour day must retain its own midpoint');
  assert.deepStrictEqual(request.statistic_ids, ids);
  response[ids[1]].splice(5, 1);
  points = await energyHistory('grid', {}, null, null, hass);
  assert.strictEqual(points[5][1], null, 'Missing normal tariff must not become zero');
  response[ids[0]][0].change = -1;
  points = await energyHistory('grid', {}, null, null, hass);
  assert.strictEqual(points[0][1], null, 'Invalid/reset-negative bucket cannot be used');
  points = await energyHistory('consumption', {}, null, null, hass);
  assert.deepStrictEqual(points.map(p => p[1]), [10, 11, 12, 13, 14, 15, 3.7]);
  hass.states[consumption].state = 'unavailable';
  assert.strictEqual((await energyHistory('consumption', {}, null, null, hass))[6][1], null);
  hass.callWS = async () => { throw Error('recorder unavailable'); };
  assert((await energyHistory('grid', {}, null, null, hass)).every(p => p[1] === null));
  global.Date = class extends RealDate {
    constructor(...args) { super(...(args.length ? args : ['2026-03-30T12:00:00+03:00'])); }
  };
  hass.callWS = async r => {request = r; return {};};
  await energyHistory('grid', {}, null, null, hass);
  assert.strictEqual((Date.parse(request.end_time)-Date.parse(request.start_time))/3600000, 167);
  console.log('Canonical history: tariff sum, dates, current header, missing/reset evidence and both DST boundaries passed');
})().catch(err => {console.error(err);process.exitCode=1;}).finally(() => {global.Date=RealDate;});
