const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),assert=require('assert');
(async()=>{
 const root=path.resolve(__dirname,'../..');
 const data=JSON.parse(fs.readFileSync(path.join(root,'homeassistant/live/storage/lovelace.dashboard_powmr1'),'utf8'));
 function find(x,title){if(x && typeof x==='object'){if(x.header?.title===title)return x;for(const v of Object.values(x)){const r=find(v,title);if(r)return r;}}}
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 try {
  for(const title of ['Consumption, EV Potential & Grid — 7 days','SOC & Current — 24h']) {
   const context=await browser.newContext({viewport:{width:500,height:650},timezoneId:'Europe/Kyiv'});
   const page=await context.newPage(),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.clock.install({time:new Date('2026-10-26T13:00:00+02:00')});
   await page.setContent('<style>body{font-family:Arial;margin:12px;--primary-text-color:#222;--secondary-text-color:#666;--ha-card-background:white}#mount{width:460px}apexcharts-card{display:block;min-width:0}</style><div id="mount"></div>');
   await page.addScriptTag({path:process.argv[2]});
   await page.evaluate(({cfg,title})=>{
    const states={};
    cfg.series.forEach(s=>{states[s.entity]={entity_id:s.entity,state:'3.7',attributes:{unit_of_measurement:'kWh'},last_changed:new Date().toISOString(),last_updated:new Date().toISOString()};});
    if(title==='SOC & Current — 24h') {
     cfg.series.forEach((s,i)=>{s.data_generator=`return [[Date.now()-3600000,${i?'-10.5':'65'}],[Date.now()-120000,${i?'73.6':'80'}]];`;});
    }
    const card=document.createElement('apexcharts-card');card.setConfig(cfg);window.card=card;
    card.hass={states,locale:{language:'en',number_format:'comma_decimal',time_format:'24',first_weekday:'monday'},config:{time_zone:'Europe/Kyiv',unit_system:{length:'km'}},themes:{darkMode:false,themes:{}},localize:x=>x,
     callApi:async()=>[],callWS:async r=>Object.fromEntries((r.statistic_ids||[]).map(id=>[id,
      Array.from({length:7},(_,i)=>({start:new Date(2026,9,20+i).getTime()/1000,end:new Date(2026,9,21+i).getTime()/1000,change:(id.includes('night')?2:id.includes('normal')?3:10)+i}))]))};
    document.querySelector('#mount').appendChild(card);
   },{cfg:find(data,title),title});
   await page.clock.runFor(5000);await page.waitForTimeout(300);
   const result=await page.evaluate(()=>({
    bars:window.card.shadowRoot.querySelectorAll('.apexcharts-bar-area').length,
    headers:window.card._headerState,
    texts:window.card.shadowRoot.textContent,
    labels:[...window.card.shadowRoot.querySelectorAll('.apexcharts-yaxis-label tspan')].map(n=>n.textContent),
    strokes:[...window.card.shadowRoot.querySelectorAll('path.apexcharts-line')].map(n=>n.getAttribute('stroke-width')),
    colors:[...window.card.shadowRoot.querySelectorAll('path.apexcharts-line')].map(n=>n.getAttribute('stroke')),
   }));
   assert.deepStrictEqual(errors,[]);
   if(title.startsWith('Consumption')) {
    assert.strictEqual(result.bars,14,'Seven historical/current consumption and combined-tariff bars');
    assert(result.texts.includes('3.7'),'Current live consumption must render');
    assert.strictEqual(Number(result.headers[3]),3.7,'Live header and today consumption must agree');
   } else {
    const main=find(data,'Energy Flow — 24h');
    const reference=['Battery SOC','House Load'].map(name=>main.series.find(s=>s.name===name));
    assert.deepStrictEqual(result.strokes,reference.map(s=>String(s.stroke_width)));
    const rgba=hex=>`rgba(${[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)).join(',')},1)`;
    assert.deepStrictEqual(result.colors,reference.map(s=>rgba(s.color)));
    assert(result.labels.length>0 && result.labels.every(v=>!v.includes('.') && !v.includes(',')), 'BMS axes must use whole numbers');
   }
   await page.screenshot({path:path.join(root,'.local/3635/'+(title.startsWith('Consumption')?'energy-balance':'bms')+'-preview.png')});
   console.log(JSON.stringify({title,bars:result.bars,strokes:result.strokes,labels:result.labels}));
   await context.close();
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
