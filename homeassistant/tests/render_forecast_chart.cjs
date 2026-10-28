const {chromium}=require('playwright');
const fs=require('fs'),assert=require('assert');
(async()=>{
 const bundle=process.argv[2];
 if (!bundle) throw new Error('Usage: node homeassistant/tests/render_forecast_chart.cjs <installed-apexcharts-card.js>');
 const root=require('path').resolve(__dirname,'../..');
 const dashboard=JSON.parse(fs.readFileSync(require('path').join(root,'homeassistant/live/storage/lovelace.dashboard_powmr1'),'utf8'));
 function find(n){if(n && typeof n==='object'){if(n.header?.title==='Solar forecast — 5 days') return n;for(const v of Object.values(n)){const r=find(v);if(r) return r}}}
 const cfg=find(dashboard); assert(cfg);
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 try {
  for(const [width,date,resize,lowSolar] of [[330,'2026-10-23T13:30:00+03:00',false],[600,'2026-10-23T13:30:00+03:00',false],[390,'2026-10-25T10:00:00+02:00',false],[330,'2026-10-23T13:30:00+03:00',true],[390,'2026-10-26T13:30:00+02:00',false,true]]){
  const context=await browser.newContext({viewport:{width:width+24,height:420},timezoneId:'Europe/Kyiv'});
  const page=await context.newPage();const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('console',msg=>{if(msg.type()==='error') errors.push(msg.text())});
  await page.clock.install({time:new Date(date)});
  await page.setContent('<html><head><style>body{margin:0;background:#fff;font-family:Arial;--primary-text-color:#222;--secondary-text-color:#666;--ha-card-background:white;--divider-color:#ddd}#mount{display:grid;grid-template-columns:minmax(0,1fr);width:'+(resize?600:width)+'px;margin:12px}apexcharts-card{display:block;min-width:0}</style></head><body><div id="mount"></div></body></html>');
  await page.addScriptTag({path:bundle});

  await page.evaluate(({cfg,lowSolar})=>{
   const now=new Date(),today=new Date(now);today.setHours(0,0,0,0);
   const states={'sensor.solcast_pv_forecast_api_last_polled':{state:now.toISOString(),attributes:{}}};
   const ids=['sensor.solcast_pv_forecast_forecast_today','sensor.solcast_pv_forecast_forecast_tomorrow',...[3,4,5,6,7].map(d=>'sensor.solcast_pv_forecast_forecast_day_'+d)];
   ids.forEach((id,i)=>{const d=new Date(today);d.setDate(d.getDate()+i);states[id]={entity_id:id,state:String((lowSolar?[9.3,8.1,9,6,6,5,5]:[7.4,3.4,8.1,9.6,26.2,12,8.5])[i]),attributes:{unit_of_measurement:'kWh',dayname:d.toLocaleDateString('en-US',{weekday:'long'})},last_changed:now.toISOString(),last_updated:now.toISOString()}});
   states['sensor.energyhub_ahm_weather_buffer']={entity_id:'sensor.energyhub_ahm_weather_buffer',state:'ready',attributes:{consumption_samples:[1,2,3].map(n=>{let d=new Date(today);d.setDate(d.getDate()-n);return {date:[d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-'),kwh:13+n}})},last_updated:now.toISOString(),last_changed:now.toISOString()};
   const card=document.createElement('apexcharts-card');
   window.testCard=card;
   card.setConfig(cfg);
   card.hass=window.testHass={states,locale:{language:'en',number_format:'comma_decimal',time_format:'24',first_weekday:'monday'},config:{time_zone:'Europe/Kyiv',unit_system:{length:'km'}},themes:{darkMode:false,themes:{}},localize:x=>x,callWS:async()=>[]};
   document.querySelector('#mount').appendChild(card);
  },{cfg,lowSolar});
  await page.clock.runFor(4000);
  await page.waitForTimeout(250);
  if(resize){
   await page.evaluate(width=>{document.querySelector('#mount').style.width=width+'px'},width);
   await page.waitForTimeout(150);
   await page.clock.runFor(3000);await page.waitForTimeout(350);
  }
  const result=await page.evaluate(()=>{
   const shadow=window.testCard.shadowRoot;
   const labels=[...shadow.querySelectorAll('.apexcharts-xaxis-label')].filter(n=>n.querySelector('tspan')?.textContent);
   const bars=[...shadow.querySelectorAll('.apexcharts-bar-area')];
   const line=shadow.querySelector('.apexcharts-yaxis-annotations line');
   const grid=shadow.querySelector('.apexcharts-grid');
   const center=n=>{const r=n.getBoundingClientRect();return r.x+r.width/2};
   const today=new Date();today.setHours(0,0,0,0);
   const expected=Array.from({length:5},(_,i)=>{const d=new Date(today);d.setDate(d.getDate()+i);return String(d.getDate()).padStart(2,'0')+'.'+String(d.getMonth()+1).padStart(2,'0')});
   const rect=n=>{const r=n.getBoundingClientRect();return {left:r.left,right:r.right,width:r.width}};
   return {dates:labels.map(n=>n.querySelector('tspan').textContent),expected,bars:bars.length,line:rect(line),grid:rect(grid),lineStroke:line.getAttribute('stroke-width'),offsets:bars.map((b,i)=>center(b)-center(labels[i])),card:rect(shadow.querySelector('ha-card')),parent:rect(document.querySelector('#mount')),bounds:[...bars,...labels].map(rect)};
  });
  assert.deepStrictEqual(errors,[]);
  assert.deepStrictEqual(result.dates,result.expected);
  assert.strictEqual(result.bars,5);
  assert.strictEqual(Number(result.lineStroke),4);
  assert(Math.abs(result.line.left-result.grid.left)<1,'Average line must start at Y axis: '+JSON.stringify(result));
  assert(Math.abs(result.line.right-result.grid.right)<1,'Average line must span plot width: '+JSON.stringify(result));
  assert(result.offsets.every(n=>Math.abs(n)<1),'Bar/date center mismatch: '+JSON.stringify(result.offsets));
  assert(result.bounds.every(r=>r.left>=result.card.left && r.right<=result.card.right), 'Chart content clipped: '+JSON.stringify(result));
  assert(result.bounds.every(r=>r.left>=result.parent.left && r.right<=result.parent.right), 'Chart exceeds parent width: '+JSON.stringify(result));
  // Missing/stale values must remain unknown; never fabricate zero generation.
  const dataChecks=await page.evaluate(cfg=>{
   const hass=window.testHass;
   const solar=new Function('entity','hass',cfg.series[0].data_generator);
   const mean=new Function('entity','hass',cfg.series[1].data_generator);
   const entity=hass.states[cfg.series[0].entity];
   hass.states['sensor.solcast_pv_forecast_forecast_day_4'].state='unavailable';
   const missing=solar(entity,hass);
   hass.states['sensor.solcast_pv_forecast_api_last_polled'].state=new Date(Date.now()-86400001).toISOString();
   const stale=solar(entity,hass);
   const average=mean(hass.states[cfg.series[1].entity],hass);
   hass.states[cfg.series[1].entity].attributes.consumption_samples[0].complete=false;
   const incomplete=mean(hass.states[cfg.series[1].entity],hass);
   return {missing:missing.map(p=>p[1]),stale:stale.map(p=>p[1]),average:average.map(p=>p[1]),incomplete};
  },cfg);
  assert.strictEqual(dataChecks.missing[3],null);
  assert.strictEqual(dataChecks.missing.filter(v=>v!==null).length,4);
  assert(dataChecks.stale.every(v=>v===null));
  assert.deepStrictEqual(dataChecks.average,Array(7).fill(15));
  assert.deepStrictEqual(dataChecks.incomplete,[]);
  console.log(JSON.stringify({width,date,resize,...result,guards:'passed'}));
  if(resize) {
   const oldY=await page.evaluate(()=>Number(window.testCard.shadowRoot.querySelector('.apexcharts-yaxis-annotations line').getAttribute('y1')));
   const setMean=async valid=>{
    await page.evaluate(valid=>{
     const id='sensor.energyhub_ahm_weather_buffer', old=window.testHass;
     const rows=old.states[id].attributes.consumption_samples.map((row,i)=>({...row,complete:valid,kwh:15+i}));
     const states={...old.states,[id]:{...old.states[id],last_updated:new Date().toISOString(),attributes:{...old.states[id].attributes,consumption_samples:rows}},'sensor.solcast_pv_forecast_api_last_polled':{state:new Date().toISOString(),attributes:{}}};
     window.testHass={...old,states};window.testCard.hass=window.testHass;
    },valid);
    await page.clock.runFor(65000);await page.waitForTimeout(200);
   };
   await setMean(false);
   assert.strictEqual(await page.evaluate(()=>window.testCard.shadowRoot.querySelectorAll('.apexcharts-yaxis-annotations line').length),0,'Unknown consumption must remove the full-width mean');
   await setMean(true);
   const newY=await page.evaluate(()=>Number(window.testCard.shadowRoot.querySelector('.apexcharts-yaxis-annotations line').getAttribute('y1')));
   assert(newY<oldY,'Average reference must follow updated consumption');
   await page.screenshot({path:require('path').join(root,'.local/3633-forecast-preview.png')});
   // A rebuilt card must replace its observer; a removed card must release it.
   const lifecycle=await page.evaluate(async cfg=>{
    const old=window.testCard.__ehForecastResizeObserver;
    window.testCard.setConfig(cfg);
    return {hadObserver:!!old};
   },cfg);
   assert(lifecycle.hadObserver);
   await page.clock.runFor(4000);await page.waitForTimeout(200);
   await page.evaluate(()=>window.testCard.remove());
   await page.waitForTimeout(150);await page.clock.runFor(1000);
   assert.deepStrictEqual(errors,[]);
  }
  await context.close();
  }
 } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
