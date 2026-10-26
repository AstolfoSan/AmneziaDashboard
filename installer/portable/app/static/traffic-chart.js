var tr=value=>globalThis.DashboardI18n?globalThis.DashboardI18n.text(value):value;
(function(root,factory){'use strict';const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.TrafficChart=api;})(typeof window==='undefined'?globalThis:window,function(){
  'use strict';
  const HOUR=3600,DAY=86400,ZONE='Europe/Moscow',PERIODS=[1,6,24,168,744];
  const clock=new Intl.DateTimeFormat((globalThis.DashboardI18n?.locale()||'ru-RU'),{timeZone:ZONE,hour:'2-digit',minute:'2-digit'});
  const day=new Intl.DateTimeFormat((globalThis.DashboardI18n?.locale()||'ru-RU'),{timeZone:ZONE,day:'2-digit',month:'2-digit'});
  let rawRows=[],rawDaily=[],rawInfo={},period=6,model=null,active=null,selectedAt=null,pinnedAt=null,hovering=false,restoreFocus=null;
  function number(value){const n=Number(value);return Number.isFinite(n)&&n>=0?n:0;}
  function bytes(value){const n=number(value);if(!n)return tr('0 Б');const k=Math.min(4,Math.floor(Math.log(n)/Math.log(1024)));return(n/1024**k).toLocaleString((globalThis.DashboardI18n?.locale()||'ru-RU'),{maximumFractionDigits:k?1:0})+' '+[tr('Б'),tr('КБ'),tr('МБ'),tr('ГБ'),tr('ТБ')][k];}
  function time(value){return clock.format(new Date(value*1000));}
  function date(value){return day.format(new Date(value*1000));}
  function validPeriod(value){const n=Number(value);return PERIODS.includes(n)?n:6;}
  function build(rows,info={},hours=6,dailyRows=[]){
    hours=validPeriod(hours);
    const liveNow=number(info.window_end)||Math.floor(Date.now()/1000),daily=hours>24;
    const now=daily?Math.floor((liveNow+10800)/DAY)*DAY-10800:liveNow,cutoff=now-hours*HOUR;
    const sourceStep=daily?DAY:Math.max(60,Math.min(HOUR,number(info.sample_interval)||HOUR));
    const step=daily?DAY:Math.max(sourceStep,hours===1?300:hours===6?900:HOUR);
    const valid=(daily?dailyRows:rows||[]).filter(r=>number(r.at)>0&&(daily?number(r.at)<now:number(r.at)<=now)&&number(r.at)+sourceStep>cutoff);
    const observed=number(info.started_at)||(valid.length?Math.min(...valid.map(r=>number(r.at))):null);
    const sampled=Object.hasOwn(info,'sampled_at')?number(info.sampled_at):now;
    const from=cutoff,availableFrom=observed===null?null:Math.max(cutoff,observed);
    const first=daily?cutoff:Math.floor(from/step)*step,last=daily?now-step:Math.floor(now/step)*step,map=new Map();
    for(const row of valid){
      const sample=number(row.at);if(sample+sourceStep<=from)continue;
      const at=daily?Math.floor((sample+10800)/DAY)*DAY-10800:Math.floor(sample/step)*step,old=map.get(at)||{rx:0,tx:0};
      map.set(at,{rx:old.rx+number(row.rx),tx:old.tx+number(row.tx)});
    }
    const points=[];
    for(let at=first;at<=last;at+=step){
      const start=Math.max(at,from),end=Math.min(at+step,now),r=map.get(at);
      const known=Boolean(r)||(observed!==null&&sampled>0&&end>observed&&start<=sampled&&end>start);
      const current=!daily&&at===last,partial=current||start>at||(observed!==null&&observed>start&&observed<end)||(sampled>start&&sampled<end);
      const rx=known?number(r?.rx):null,tx=known?number(r?.tx):null;
      points.push({at,start,end,rx,tx,total:known?rx+tx:null,known,current,partial});
    }
    return {hours,daily,step,sourceStep,cutoff,from,now,liveNow,observed,availableFrom,sampled,points,limited:observed!==null&&observed>cutoff+60,hasData:points.some(p=>p.known),
      rx:points.reduce((s,p)=>s+(p.rx||0),0),tx:points.reduce((s,p)=>s+(p.tx||0),0)};
  }
  function scale(points){
    const peak=Math.max(0,...points.filter(p=>p.known).map(p=>number(p.rx)+number(p.tx)));
    const value=peak||1024,unit=1024**Math.max(0,Math.min(4,Math.floor(Math.log(value)/Math.log(1024))));
    const raw=value/unit/4,power=10**Math.floor(Math.log10(raw)),fraction=raw/power;
    const nice=[1,2,2.5,5,10].find(n=>n>=fraction)||10,step=Math.max(1,Math.ceil(nice*power*unit));
    return {top:step*4,ticks:Array.from({length:5},(_,i)=>i*step)};
  }
  function geometry(width){const w=Math.max(220,Math.round(width));return {width:w,height:270,left:60,right:12,top:14,bottom:46,plotWidth:w-72,plotHeight:210};}
  function selectionMarkup(x,width,base,height){
    const h=number(height),attrs='class="traffic-bar-selection" fill="none" opacity="0" pointer-events="none" aria-hidden="true"';
    if(!h)return '<line '+attrs+' x1="'+(x-1)+'" x2="'+(x+width+1)+'" y1="'+(base+3)+'" y2="'+(base+3)+'"/>';
    return '<rect '+attrs+' x="'+(x-1)+'" y="'+(base-h-1)+'" width="'+(width+2)+'" height="'+(h+2)+'" rx="2"/>';
  }
  function pick(clientX,box,g,count){const x=(clientX-box.left)/Math.max(1,box.width)*g.width;return Math.max(0,Math.min(count-1,Math.floor((x-g.left)/g.plotWidth*count)));}
  function label(point){if(point.end-point.start===DAY)return date(point.start)+tr(' · 00:00–24:00 МСК');const start=date(point.start)+' '+time(point.start),end=point.current&&point.end-point.start<60?tr('сейчас'):(date(point.start)===date(point.end)?'':date(point.end)+' ')+time(point.end);return start+'–'+end+tr(' МСК');}
  function note(point,m){
    if(!point.known)return m.observed===null||point.end<=m.observed?tr('За этот период данные ещё не накапливались'):tr('Нет свежего замера за этот интервал');
    if(point.current)return tr('Текущий интервал · данные ещё поступают');
    return point.partial?(m.daily?tr('Неполный день наблюдения'):tr('Неполный интервал')):m.daily?tr('Суточный итог'):tr('Объём за ')+Math.round(m.step/60)+tr(' мин');
  }
  function valuesMarkup(){return tr('<div class="traffic-values"><span class="traffic-down">↓ Скачано<strong data-selection="tx">—</strong></span><span class="traffic-up">↑ Отправлено<strong data-selection="rx">—</strong></span><span>Всего<strong data-selection="total">—</strong></span></div>');}
  function contents(m){
    const periodLabel=h=>h===168?tr('7 дней'):h===744?tr('31 день'):h===1?tr('1 час'):h===24?tr('24 часа'):tr('6 часов');
    const buttons=PERIODS.map(h=>'<button type="button" class="small traffic-period" data-traffic-hours="'+h+'" aria-pressed="'+(h===m.hours)+'">'+periodLabel(h)+'</button>').join('');
    const caption=tr('Объём трафика · ')+(m.daily?tr('столбцы по дням'):tr('столбцы по ')+Math.round(m.step/60)+tr(' мин'));
    const range=m.daily?date(m.cutoff)+'–'+date(m.now-DAY)+tr(' МСК. Сегодня не включено.'):date(m.cutoff)+' '+time(m.cutoff)+' — '+date(m.now)+' '+time(m.now)+tr(' МСК.');
    const coverage=(m.daily?(m.hours===744?tr('Последний 31 завершённый день. '):tr('Последние 7 завершённых дней. ')):m.hours===1?tr('Последний час. '):tr('Последние ')+periodLabel(m.hours)+'. ')+range+
      (m.limited?tr(' Наблюдение началось ')+date(m.observed)+tr(' в ')+time(m.observed)+tr(' МСК; до этого данных нет.'):'');
    return '<figcaption class="traffic-toolbar"><span class="traffic-caption">'+caption+tr('</span><div class="traffic-periods" role="group" aria-label="Период графика">')+buttons+'</div></figcaption>'+
      tr('<div class="traffic-summary"><span class="traffic-down">● Скачано<strong>')+(m.hasData?bytes(m.tx):'—')+tr('</strong></span><span class="traffic-up">● Отправлено<strong>')+(m.hasData?bytes(m.rx):'—')+tr('</strong></span><span>Всего за показанный период<strong>')+(m.hasData?bytes(m.rx+m.tx):'—')+'</strong></span></div>'+
      '<p class="traffic-coverage">'+coverage+tr('</p><div class="traffic-stage"><svg class="traffic-svg" tabindex="0" role="img" aria-label="Объём трафика: скачано и отправлено. Стрелки выбирают интервал." aria-describedby="traffic-help"></svg>')+
      '<div class="traffic-tooltip" hidden><strong data-selection="time"></strong>'+valuesMarkup()+'<small data-selection="note"></small></div></div>'+
      '<div class="traffic-readout" role="status" aria-live="polite" aria-atomic="true"><strong data-selection="time"></strong>'+valuesMarkup()+'<small data-selection="note"></small></div>'+
      tr('<p class="help" id="traffic-help">Наведите мышь или нажмите на столбец. С клавиатуры — стрелки, Home и End; Escape сбрасывает выбор. Время МСК. Это объём трафика, не скорость.</p>');
  }
  function html(rows,info,dailyRows){rawRows=rows||[];rawDaily=dailyRows||[];rawInfo=info||{};model=build(rawRows,rawInfo,period,rawDaily);return '<figure class="traffic-chart" data-traffic-chart>'+contents(model)+'</figure>';}
  function destroy(reset=false){
    if(active){
      const focus=active.root.ownerDocument.activeElement;
      if(focus===active.root.querySelector('svg'))restoreFocus='svg';
      else if(focus?.dataset?.trafficHours)restoreFocus=focus.dataset.trafficHours;
      else restoreFocus=null;
      active.observer?.disconnect();active.root.ownerDocument.removeEventListener('pointerdown',active.outside);active=null;
    }
    if(reset){selectedAt=null;pinnedAt=null;hovering=false;restoreFocus=null;}
  }
  function mount(root){
    if(!root||!model)return;destroy();
    const m=model,svg=root.querySelector('svg'),tip=root.querySelector('.traffic-tooltip'),s=scale(m.points);
    let g,index=-1,lastPopup=false,width=0;
    const latest=()=>{for(let i=m.points.length-1;i>=0;i--)if(m.points[i].known)return i;return m.points.length-1;};
    const indexOf=at=>m.points.findIndex(p=>p.at===at);
    if(indexOf(pinnedAt)<0)pinnedAt=null;
    function show(i,popup=false,force=false){
      i=Math.max(0,Math.min(m.points.length-1,i));if(!force&&i===index&&popup===lastPopup)return;
      index=i;lastPopup=popup;const p=m.points[i];selectedAt=p.at;
      const text={time:label(p),note:note(p,m),tx:p.known?bytes(p.tx):'—',rx:p.known?bytes(p.rx):'—',total:p.known?bytes(p.total):'—'};
      for(const [key,value] of Object.entries(text))root.querySelectorAll('[data-selection="'+key+'"]').forEach(el=>{el.textContent=value;});
      svg.setAttribute('aria-label',text.time+tr('. Скачано ')+text.tx+tr(', отправлено ')+text.rx+tr(', всего ')+text.total+'. '+text.note);
      tip.hidden=!popup;tip.classList.toggle('align-left',i>=m.points.length/2);
      svg.querySelectorAll('.traffic-bar-hit').forEach((el,j)=>el.classList.toggle('is-selected',j===i));
      svg.querySelectorAll('.traffic-bar-selection').forEach((el,j)=>el.classList.toggle('is-selected',j===i));
    }
    function draw(){
      if(active?.root!==root)return;
      const next=Math.round(root.clientWidth);if(next===width&&g)return;width=next;g=geometry(next);svg.setAttribute('viewBox','0 0 '+g.width+' '+g.height);
      let out=tr('<title>Объём трафика по интервалам. Оранжевый — скачано, голубой — отправлено; высота столбца — сумма.</title>');
      for(const tick of s.ticks){const y=g.top+g.plotHeight-tick/s.top*g.plotHeight;out+='<line class="traffic-gridline" x1="'+g.left+'" x2="'+(g.width-g.right)+'" y1="'+y+'" y2="'+y+'"/><text class="traffic-axis-text" text-anchor="end" x="'+(g.left-9)+'" y="'+(y+4)+'">'+bytes(tick)+'</text>';}
      const n=m.points.length,slot=g.plotWidth/n,bar=Math.max(2,Math.min(40,slot*.66));
      const marks=[...new Set((g.width<520?[0,.5,1]:[0,.25,.5,.75,1]).map(f=>Math.round(f*(n-1))))];
      for(const i of marks){const p=m.points[i],t=!m.daily&&i===n-1?m.now:p.start,x=g.left+(i+.5)*slot,anchor=i===0?'start':i===n-1?'end':'middle';out+='<text class="traffic-axis-text" text-anchor="'+anchor+'" x="'+x+'" y="'+(g.top+g.plotHeight+21)+'">'+(m.daily?date(t):time(t)+'<tspan x="'+x+'" dy="14">'+date(t)+'</tspan>')+'</text>';}
      m.points.forEach((p,i)=>{
        const x=g.left+(i+.5)*slot-bar/2,base=g.top+g.plotHeight;
        if(p.known){
          const tx=p.tx/s.top*g.plotHeight,rx=p.rx/s.top*g.plotHeight;
          out+='<rect class="traffic-bar traffic-bar-tx" x="'+x+'" y="'+(base-tx)+'" width="'+bar+'" height="'+tx+'"/><rect class="traffic-bar traffic-bar-rx" x="'+x+'" y="'+(base-tx-rx)+'" width="'+bar+'" height="'+rx+'"/>';
          if(!p.total)out+='<line class="traffic-zero" x1="'+x+'" x2="'+(x+bar)+'" y1="'+base+'" y2="'+base+'"/>';
        }else out+='<line class="traffic-missing" x1="'+x+'" x2="'+(x+bar)+'" y1="'+base+'" y2="'+base+'"/>';
        // Full-height hit zones remain transparent. Only outline actual data;
        // empty/missing intervals get a baseline marker, never a fake tall bar.
        out+=selectionMarkup(x,bar,base,p.known?p.total/s.top*g.plotHeight:0);
        out+='<rect class="traffic-bar-hit" x="'+(g.left+i*slot+1)+'" y="'+g.top+'" width="'+Math.max(1,slot-2)+'" height="'+g.plotHeight+'" rx="3"/>';
      });
      if(!m.hasData)out+='<text class="traffic-axis-text" text-anchor="middle" x="'+(g.left+g.plotWidth/2)+tr('" y="110">Нет данных за этот период</text>');
      svg.innerHTML=out;let i=indexOf(selectedAt);if(i<0)i=latest();show(i,hovering||pinnedAt!==null,true);
    }
    root.querySelectorAll('[data-traffic-hours]').forEach(button=>{
      button.setAttribute('aria-pressed',String(Number(button.dataset.trafficHours)===m.hours));
      button.addEventListener('click',()=>{
        period=validPeriod(button.dataset.trafficHours);selectedAt=pinnedAt=null;hovering=false;destroy();restoreFocus=null;
        model=build(rawRows,rawInfo,period,rawDaily);root.innerHTML=contents(model);mount(root);
        root.querySelector('[data-traffic-hours="'+period+'"]')?.focus({preventScroll:true});
      });
    });
    svg.addEventListener('pointermove',e=>{if(e.pointerType==='touch')return;hovering=true;show(pick(e.clientX,svg.getBoundingClientRect(),g,m.points.length),true);});
    svg.addEventListener('pointerdown',e=>{const i=pick(e.clientX,svg.getBoundingClientRect(),g,m.points.length);pinnedAt=m.points[i].at;show(i,true);});
    svg.addEventListener('pointerleave',()=>{hovering=false;const i=indexOf(pinnedAt);if(i>=0)show(i,false);else{selectedAt=null;show(latest(),false);}});
    svg.addEventListener('keydown',e=>{
      let i=index<0?latest():index;
      if(e.key==='Escape'){pinnedAt=null;hovering=false;show(latest(),false);return;}
      if(e.key==='ArrowLeft')i--;else if(e.key==='ArrowRight')i++;else if(e.key==='Home')i=0;else if(e.key==='End')i=m.points.length-1;else return;
      e.preventDefault();i=Math.max(0,Math.min(m.points.length-1,i));pinnedAt=m.points[i].at;show(i,false);
    });
    const outside=e=>{if(!root.contains(e.target)){pinnedAt=null;hovering=false;show(latest(),false);}};
    root.ownerDocument.addEventListener('pointerdown',outside);
    const observer=typeof ResizeObserver==='function'?new ResizeObserver(draw):null;active={root,observer,outside};draw();observer?.observe(root);
    if(restoreFocus){const focus=restoreFocus;restoreFocus=null;root.querySelector(focus==='svg'?'svg':'[data-traffic-hours="'+focus+'"]')?.focus({preventScroll:true});}
  }
  function setPeriod(hours){period=validPeriod(hours);return period;}
  return {html,mount,destroy,model:build,scale,geometry,pick,selectionMarkup,formatBytes:bytes,hourLabel:label,setPeriod};
});
