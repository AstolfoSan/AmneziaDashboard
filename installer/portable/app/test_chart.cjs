'use strict';
const assert=require('node:assert/strict'),chart=require('./static/traffic-chart.js');
const now=Date.parse('2026-10-24T21:10:00Z')/1000,hour=Math.floor(now/3600)*3600;
const info={window_end:now,started_at:hour-2*3600,sampled_at:now,sample_interval:60};
let count=0;function test(name,fn){fn();count++;console.log('PASS '+name);}
test('keeps the entire rolling period visible even with a short observation history',()=>{
  const m=chart.model([{at:hour,rx:100,tx:250}],info,6);
  assert.equal(m.from,now-6*3600);assert.equal(m.points.length,25);assert.equal(m.step,900);
  assert.equal(m.points[0].known,false);assert.equal(m.availableFrom,info.started_at);
  assert.equal(m.rx,100);assert.equal(m.tx,250);assert.equal(m.points.at(-1).current,true);
});
test('1/6/24h use 5/15/60 minute bins without inventing higher resolution',()=>{
  for(const [hours,step] of [[1,300],[6,900],[24,3600]])assert.equal(chart.model([],info,hours).step,step);
  assert.equal(chart.model([],{...info,sample_interval:3600},1).step,3600);
});
test('pre-observation time is not fabricated zero history',()=>{
  const m=chart.model([],info);assert.equal(m.from,now-6*3600);assert.equal(m.points[0].total,null);
  assert.equal(m.points.at(-1).rx,0);
});
test('no clients and no samples means no data',()=>{
  const m=chart.model([],{window_end:now,started_at:null,sampled_at:0,sample_interval:60});
  assert.equal(m.hasData,false);assert.ok(m.points.every(p=>p.total===null));
});
test('invalid values, old rows and future rows do not corrupt totals',()=>{
  const m=chart.model([{at:hour-26*3600,rx:999,tx:999},{at:now+60,rx:999,tx:999},{at:hour,rx:-1,tx:'oops'}],info);
  assert.equal(m.rx,0);assert.equal(m.tx,0);
});
test('minute samples aggregate once and period selection excludes older traffic',()=>{
  const rows=[{at:hour,rx:10,tx:20},{at:hour+60,rx:30,tx:40},{at:hour-2*3600,rx:100,tx:200}];
  const m=chart.model(rows,info,1);assert.equal(m.rx,40);assert.equal(m.tx,60);
});
test('Moscow interval labels cross midnight correctly',()=>{
  const m=chart.model([{at:hour,rx:10,tx:20}],info);
  assert.match(chart.hourLabel(m.points.at(-1)),/25\.10 00:00–00:10 МСК/);
});
test('stacked byte scale covers download plus upload',()=>{
  for(const n of [0,1,1000,1024,88*1024**2,10*1024**3]){
    const s=chart.scale([{known:true,rx:n,tx:n}]);assert.ok(Number.isFinite(s.top)&&s.top>=2*n&&s.top>0);
    assert.equal(s.ticks.length,5);assert.ok(s.ticks.every((v,i)=>Number.isInteger(v)&&(i===0||v>s.ticks[i-1])));
  }
  assert.equal(chart.formatBytes(1024**2),'1 МБ');
});
test('pointer coordinates select the correct column on narrow and wide views',()=>{
  for(const width of [280,700,1200]){
    const g=chart.geometry(width),box={left:20,width};
    assert.equal(chart.pick(20,box,g,25),0);assert.equal(chart.pick(width+20,box,g,25),24);
    assert.equal(chart.pick(20+g.left+g.plotWidth/2,box,g,25),12);
  }
});
test('no slider; explicit period controls and honest coverage text',()=>{
  chart.setPeriod(6);const html=chart.html([{at:hour,rx:1,tx:2}],info);
  assert.ok(!html.includes('type="range"'));assert.ok(!html.includes('traffic-range'));
  assert.ok(html.includes('data-traffic-hours="1"'));assert.ok(html.includes('Наблюдение началось'));
  assert.ok(html.includes('столбцы по 15 мин'));
});
function fixture(){
  class El{
    constructor(){this.attrs={};this.dataset={};this.events={};this.classes=new Set();this.hidden=false;this.textContent='';this.classList={toggle:(c,on)=>on?this.classes.add(c):this.classes.delete(c)};}
    setAttribute(k,v){this.attrs[k]=String(v);}addEventListener(k,fn){this.events[k]=fn;}focus(){doc.activeElement=this;}
  }
  const doc={activeElement:null,events:{},addEventListener(k,fn){this.events[k]=fn;},removeEventListener(k){delete this.events[k];}};
  const svg=new El(),tip=new El(),bars=Array.from({length:32},()=>new El()),markers=Array.from({length:32},()=>new El());
  const buttons=Object.fromEntries([1,6,24,168,744].map(h=>{const b=new El();b.dataset.trafficHours=String(h);return [h,b];}));
  const selected=Object.fromEntries(['time','note','tx','rx','total'].map(k=>[k,[new El(),new El()]]));
  const find=s=>s==='svg'?svg:s==='.traffic-tooltip'?tip:buttons[s.match(/data-traffic-hours="(\d+)"/)?.[1]];
  svg.getBoundingClientRect=()=>({left:0,width:700});svg.querySelectorAll=s=>s==='.traffic-bar-selection'?markers:bars;
  const root={clientWidth:700,ownerDocument:doc,querySelector:find,
    querySelectorAll:s=>s==='[data-traffic-hours]'?Object.values(buttons):selected[s.match(/="(\w+)"/)[1]],
    contains:t=>t===svg||t===root||Object.values(buttons).includes(t)};
  return {root,svg,tip,bars,markers,buttons,selected,doc};
}
test('hover/touch show real values, no native slider is needed',()=>{
  chart.destroy(true);chart.setPeriod(6);chart.html([{at:hour,rx:100,tx:250}],info);const f=fixture();chart.mount(f.root);
  assert.ok(f.svg.innerHTML.includes('traffic-bar-tx'));assert.ok(f.svg.innerHTML.includes('traffic-bar-rx'));
  f.svg.events.pointermove({pointerType:'mouse',clientX:690});assert.equal(f.tip.hidden,false);assert.equal(f.selected.total[0].textContent,'350 Б');
  f.svg.events.pointerdown({pointerType:'touch',clientX:690});f.svg.events.pointerleave();assert.equal(f.tip.hidden,true);assert.equal(f.selected.tx[0].textContent,'250 Б');
  chart.destroy(true);
});
test('keyboard arrows, Home/End, Escape and outside dismissal work',()=>{
  chart.html([{at:hour,rx:100,tx:250}],info);const f=fixture();chart.mount(f.root);let prevented=0;
  f.svg.events.keydown({key:'Home',preventDefault(){prevented++;}});assert.match(f.selected.time[0].textContent,/18:10/);
  f.svg.events.keydown({key:'End',preventDefault(){prevented++;}});assert.equal(f.selected.total[0].textContent,'350 Б');
  f.svg.events.keydown({key:'ArrowLeft',preventDefault(){prevented++;}});assert.equal(f.selected.total[0].textContent,'0 Б');
  f.svg.events.keydown({key:'Escape'});assert.equal(f.selected.total[0].textContent,'350 Б');assert.equal(prevented,3);
  f.svg.events.pointermove({pointerType:'mouse',clientX:690});f.doc.events.pointerdown({target:{}});assert.equal(f.tip.hidden,true);
  chart.destroy(true);
});
test('period buttons change aggregation and retain keyboard focus',()=>{
  chart.setPeriod(6);chart.html([{at:hour,rx:100,tx:250}],info);const f=fixture();chart.mount(f.root);
  f.buttons[1].events.click();assert.ok(f.root.innerHTML.includes('столбцы по 5 мин'));assert.equal(f.doc.activeElement,f.buttons[1]);
  assert.equal(f.buttons[1].attrs['aria-pressed'],'true');chart.destroy(true);chart.setPeriod(6);
});
test('selection and SVG focus survive auto-refresh; page exit cleans listeners',()=>{
  chart.html([{at:hour,rx:1,tx:2}],info);const first=fixture();chart.mount(first.root);
  first.svg.events.keydown({key:'ArrowLeft',preventDefault(){}});const selected=first.selected.time[0].textContent;first.svg.focus();
  chart.destroy();assert.equal(Object.keys(first.doc.events).length,0);
  chart.html([{at:hour,rx:3,tx:4}],info);const second=fixture();chart.mount(second.root);
  assert.equal(second.selected.time[0].textContent,selected);assert.equal(second.doc.activeElement,second.svg);chart.destroy(true);
});

test('24 hours is exactly a sliding day, never reset to current-day midnight',()=>{
  const old=now-23*3600,m=chart.model([{at:old,rx:12,tx:34},{at:now-25*3600,rx:999,tx:999}],info,24);
  assert.equal(m.cutoff,now-86400);assert.equal(m.points[0].start,now-86400);
  assert.equal(m.points.at(-1).end,now);assert.equal(m.rx,12);assert.equal(m.tx,34);
  chart.setPeriod(24);const html=chart.html([],info);assert.ok(html.includes('Последние 24 часа'));
  assert.ok(html.includes('24.10 00:10 — 25.10 00:10'));chart.setPeriod(6);
});

test('week is seven completed Moscow days, excludes today and does not mix minute totals',()=>{
  const end=Math.floor((now+10800)/86400)*86400-10800;
  const daily=[{at:end-86400,rx:10,tx:20},{at:end-7*86400,rx:30,tx:40},{at:end,rx:999,tx:999},{at:end-8*86400,rx:999,tx:999}];
  const m=chart.model([{at:now-60,rx:777,tx:777}],{...info,started_at:end-20*86400},168,daily);
  assert.equal(m.points.length,7);assert.equal(m.from,end-7*86400);assert.equal(m.now,end);assert.equal(m.step,86400);
  assert.equal(m.rx,40);assert.equal(m.tx,60);assert.ok(m.points.every(p=>!p.current&&p.end-p.start===86400));
});

test('31 days means 31 full days, not a calendar month or a rolling partial day',()=>{
  const end=Math.floor((now+10800)/86400)*86400-10800;
  const m=chart.model([],{...info,started_at:end-100*86400},744,[{at:end-31*86400,rx:1,tx:2},{at:end-32*86400,rx:999,tx:999}]);
  assert.equal(m.points.length,31);assert.equal(m.points[0].at,end-31*86400);assert.equal(m.points.at(-1).at,end-86400);
  assert.equal(m.rx,1);assert.equal(m.tx,2);assert.match(chart.hourLabel(m.points.at(-1)),/24\.10 · 00:00–24:00 МСК/);
});

test('current-day-only observation is missing data, not a zero-filled historical week',()=>{
  const end=Math.floor((now+10800)/86400)*86400-10800;
  const m=chart.model([],{...info,started_at:end+1},168,[]);
  assert.equal(m.hasData,false);assert.ok(m.points.every(p=>p.total===null));
});

test('first observed day is partial while older days remain unknown',()=>{
  const end=Math.floor((now+10800)/86400)*86400-10800,started=end-3*86400+3600;
  const m=chart.model([],{...info,started_at:started},168,[{at:end-3*86400,rx:1,tx:2}]);
  assert.equal(m.points[3].known,false);assert.equal(m.points[4].partial,true);assert.equal(m.points[5].partial,false);
});

test('all five periods are labelled and daily view discloses exclusion of today',()=>{
  chart.setPeriod(744);const html=chart.html([],info,[]);
  for(const h of [1,6,24,168,744])assert.ok(html.includes('data-traffic-hours="'+h+'"'));
  assert.ok(html.includes('31 день'));assert.ok(html.includes('столбцы по дням'));assert.ok(html.includes('Сегодня не включено'));
  chart.setPeriod(6);
});

test('switching to week uses daily totals and keeps daily selection through refresh',()=>{
  const end=Math.floor((now+10800)/86400)*86400-10800,daily=[{at:end-86400,rx:10,tx:20}];
  chart.setPeriod(6);chart.html([{at:hour,rx:999,tx:999}],info,daily);const f=fixture();chart.mount(f.root);
  f.buttons[168].events.click();assert.ok(f.root.innerHTML.includes('столбцы по дням'));assert.equal(f.selected.total[0].textContent,'30 Б');
  f.svg.events.keydown({key:'ArrowLeft',preventDefault(){}});const selected=f.selected.time[0].textContent;chart.destroy();
  chart.html([],info,daily);const next=fixture();chart.mount(next.root);assert.equal(next.selected.time[0].textContent,selected);
  chart.destroy(true);chart.setPeriod(6);
});
test('selection outlines only the actual combined bar height, never the full plot',()=>{
  const html=chart.selectionMarkup(100,20,224,37);
  assert.match(html,/<rect /);assert.match(html,/y="186"/);assert.match(html,/height="39"/);
  assert.match(html,/width="22"/);assert.match(html,/fill="none"/);assert.match(html,/pointer-events="none"/);
  assert.ok(!html.includes('height="210"'));
});
test('zero and missing intervals use a short baseline marker without invented volume',()=>{
  for(const h of [0,null,NaN,-1]){
    const html=chart.selectionMarkup(100,20,224,h);assert.match(html,/<line /);
    assert.match(html,/y1="227"/);assert.match(html,/y2="227"/);assert.ok(!html.includes('<rect'));
  }
});
test('full-height pointer hit zones stay invisible even when selected',()=>{
  const css=require('node:fs').readFileSync(require('node:path').join(__dirname,'static/style.css'),'utf8');
  assert.match(css,/\.traffic-bar-hit,\.traffic-bar-hit\.is-selected\{fill:transparent;stroke:none;/);
  assert.ok(!/\.traffic-bar-hit\.is-selected\{[^}]*fill:var\(--orange-soft\)/.test(css));
  assert.match(css,/\.traffic-bar-selection\{[^}]*fill:none;[^}]*pointer-events:none;/);
  assert.match(css,/\.traffic-bar-selection\.is-selected\{opacity:1\}/);
});
test('selection marker follows hover, touch, keyboard and dismissal independently of hit boxes',()=>{
  chart.destroy(true);chart.setPeriod(6);chart.html([{at:hour,rx:100,tx:250}],info);const f=fixture();chart.mount(f.root);
  const selected=()=>f.markers.flatMap((el,i)=>el.classes.has('is-selected')?[i]:[]);
  assert.equal(selected().length,1);
  f.svg.events.keydown({key:'Home',preventDefault(){}});assert.deepEqual(selected(),[0]);
  f.svg.events.pointermove({pointerType:'mouse',clientX:690});assert.deepEqual(selected(),[24]);
  f.svg.events.pointerdown({pointerType:'touch',clientX:350});assert.deepEqual(selected(),[11]);
  f.doc.events.pointerdown({target:{}});assert.deepEqual(selected(),[24]);chart.destroy(true);
});
test('empty selected intervals keep zero values and receive no full-height visible shape',()=>{
  chart.destroy(true);chart.setPeriod(6);chart.html([{at:hour,rx:100,tx:250}],info);const f=fixture();chart.mount(f.root);
  f.svg.events.keydown({key:'ArrowLeft',preventDefault(){}});assert.equal(f.selected.total[0].textContent,'0 Б');
  assert.equal((f.svg.innerHTML.match(/class="traffic-bar-selection"/g)||[]).length,25);
  assert.ok(f.svg.innerHTML.includes('<line class="traffic-bar-selection"'));chart.destroy(true);
});
console.log(JSON.stringify({javascript_chart_tests_passed:count}));
