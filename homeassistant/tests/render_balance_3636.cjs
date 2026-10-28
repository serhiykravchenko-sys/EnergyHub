const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),assert=require('assert');
(async()=>{
 const root=path.resolve(__dirname,'../..');
 const data=JSON.parse(fs.readFileSync(path.join(root,'homeassistant/live/storage/lovelace.dashboard_powmr1'),'utf8'));
 function find(x,title){if(x && typeof x==='object'){if(x.header?.title===title)return x;for(const v of Object.values(x)){const r=find(v,title);if(r)return r;}}}
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 try {
  for(const scenario of [{title:'Consumption, EV Potential & Grid — 7 days',width:460},...['mixed','positive','negative','zero','gap'].flatMap(kind=>[330,600].map(width=>({title:'SOC & Current — 24h',kind,width})))]) {
   const {title,kind,width}=scenario;
   const context=await browser.newContext({viewport:{width:width+24,height:650},timezoneId:'Europe/Kyiv'});
   const page=await context.newPage(),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.clock.install({time:new Date('2026-10-26T13:00:00+02:00')});
   await page.setContent(`<style>body{font-family:Arial;margin:12px;--primary-text-color:#222;--secondary-text-color:#666;--ha-card-background:white}#mount{width:${width}px}apexcharts-card{display:block;min-width:0}</style><div id="mount"></div>`);
   await page.addScriptTag({path:process.argv[2]});
   await page.evaluate(({cfg,title,kind})=>{
    const states={};
    cfg.series.forEach(s=>{states[s.entity]={entity_id:s.entity,state:'3.7',attributes:{unit_of_measurement:'kWh'},last_changed:new Date().toISOString(),last_updated:new Date().toISOString()};});
    if(title==='SOC & Current — 24h') {
     const values={mixed:[-66,-25,0,38,15,-10],positive:[2,15,38,22,10,2],negative:[-5,-30,-66,-22,-2,-10],zero:[0,0,0,0,0,0],gap:[-20,-10,null,30,10,-10]}[kind];
     cfg.series.forEach((s,i)=>{s.data_generator='return '+JSON.stringify(values.map((v,j)=>[Date.parse('2026-10-25T15:00:00+02:00')+j*4*3600000,i?v:60+j*4]))+';'; states[s.entity].attributes.unit_of_measurement=i?'A':'%';});
    }
    const card=document.createElement('apexcharts-card');card.setConfig(cfg);window.card=card;
    card.hass={states,locale:{language:'en',number_format:'comma_decimal',time_format:'24',first_weekday:'monday'},config:{time_zone:'Europe/Kyiv',unit_system:{length:'km'}},themes:{darkMode:false,themes:{}},localize:x=>x,
     callApi:async()=>[],callWS:async r=>Object.fromEntries((r.statistic_ids||[]).map(id=>[id,
      Array.from({length:7},(_,i)=>({start:new Date(2026,9,20+i).getTime()/1000,end:new Date(2026,9,21+i).getTime()/1000,change:(id.includes('night')?2:id.includes('normal')?3:10)+i}))]))};
    document.querySelector('#mount').appendChild(card);
   },{cfg:find(data,title),title,kind});
   await page.clock.runFor(5000);await page.waitForTimeout(300);
   const result=await page.evaluate(()=>({
    bars:window.card.shadowRoot.querySelectorAll('.apexcharts-bar-area').length,
    headers:window.card._headerState,
    texts:window.card.shadowRoot.textContent,
    rightLabels:[...[...window.card.shadowRoot.querySelectorAll('.apexcharts-yaxis')].at(-1).querySelectorAll('.apexcharts-yaxis-label tspan')].map(n=>n.textContent),
    labels:[...window.card.shadowRoot.querySelectorAll('.apexcharts-yaxis-label tspan')].map(n=>n.textContent),
    strokes:[...window.card.shadowRoot.querySelectorAll('path.apexcharts-line')].map(n=>n.getAttribute('stroke-width')),
    zero:window.card.shadowRoot.querySelectorAll('.apexcharts-yaxis-annotations line').length,
    stops:[...window.card.shadowRoot.querySelectorAll('linearGradient stop')].map(n=>[n.getAttribute('stop-color'),n.getAttribute('offset')]),
    axisColors:[...window.card.shadowRoot.querySelectorAll('.apexcharts-yaxis-label')].map(n=>n.getAttribute('fill')),
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
    assert.strictEqual(result.strokes[0],String(reference[0].stroke_width));
    assert(result.strokes.slice(1).every(w=>w===String(reference[1].stroke_width)));
    assert.strictEqual(result.strokes.length,kind==='gap'?3:2,'Missing data must split the current path');
    const rgba=hex=>`rgba(${[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)).join(',')},1)`;
    assert.strictEqual(result.colors[0],rgba(reference[0].color));
    assert(result.colors[1].startsWith('url('),'Current must use charge/discharge threshold gradient');
    assert(result.rightLabels.includes('0'),'Current axis must include zero: '+result.rightLabels);
    assert(result.zero>=1,'Visible zero reference');
    assert(result.axisColors.includes('#2ecc71') && result.axisColors.includes('#3498db'),'Axis colors match series');
    if(kind==='mixed'||kind==='gap')assert(result.stops.some(s=>s[0].startsWith('#3498db')) && result.stops.some(s=>s[0].startsWith('#e74c3c')),'Both charge/discharge colors render');
    assert(result.labels.length>0 && result.labels.every(v=>!v.includes('.') && !v.includes(',')), 'BMS axes must use whole numbers');
   }
   await page.screenshot({path:path.join(root,'.local/3636/'+(title.startsWith('Consumption')?'energy-balance':`bms-${kind}-${width}`)+'-preview.png')});
   console.log(JSON.stringify({title,kind,width,bars:result.bars,strokes:result.strokes,labels:result.labels}));
   await context.close();
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
