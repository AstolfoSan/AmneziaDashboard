'use strict';
const assert=require('node:assert/strict'),A=require('./static/client-access.js');let count=0;
function test(name,fn){fn();count++;console.log('PASS '+name)}
test('quota units and decimal comma become exact integer bytes',()=>{
  assert.equal(A.parseTraffic('10','gb'),10*1024**3);assert.equal(A.parseTraffic('1,5','gb'),1.5*1024**3);
  assert.equal(A.parseTraffic('0.001','mb'),1049);assert.equal(A.parseTraffic('1','tb'),1024**4);
  assert.equal(A.parseTraffic('','gb'),null);assert.equal(A.parseTraffic(' ','mb'),null);
});
test('unsafe values, injections, zero and unsupported units cannot become a quota',()=>{
  for(const amount of ['0','-1','1e3','NaN','Infinity','1.2345','<img>','999999999999999999999'])assert.throws(()=>A.parseTraffic(amount,'gb'));
  assert.throws(()=>A.parseTraffic('1','unknown'));assert.throws(()=>A.parseTraffic('0.001','b'));
});
test('existing byte thresholds round-trip without lossy display rounding',()=>{
  for(const limit of [1,299,1049,1024**2,1.5*1024**3,A.parseTraffic('0.1','gb'),2**53-1]){
    const input=A.trafficInputs(limit);assert.equal(A.parseTraffic(input.amount,input.unit),limit);
  }
});
test('quota form is optional and explains lifetime usage and periodic enforcement',()=>{
  const html=A.trafficForm({traffic_limit_bytes:null,rx:100,tx:200},n=>n+' Б');
  assert.ok(html.includes('300 Б'));assert.ok(html.includes('type="button" id="traffic-unlimited"'));
  assert.ok(html.includes('каждые 15 секунд'));assert.ok(html.includes('Расход не обнуляется'));assert.ok(!html.includes(' required'));
});
test('quota progress uses both directions and clamps the visual bar without truncating totals',()=>{
  const d={rx:100,tx:200,traffic_limit_bytes:250},summary=A.trafficSummary(d,n=>n+' Б');
  assert.ok(summary.includes('Всего 300 Б из 250 Б'));assert.ok(summary.includes('value="250"'));
  assert.ok(A.quotaExceeded(d));assert.ok(A.accessCell({...d,state:'limited'}).includes('Лимит трафика'));
  assert.equal(A.trafficSummary({...d,legacy:1},n=>n),'');
});
test('manual pause and expiry retain priority, and limited clients keep their controls',()=>{
  const d={id:'test',state:'limited',traffic_limit_bytes:100,rx:100,tx:0};
  assert.ok(A.actions(d).includes('data-traffic="test"'));assert.ok(A.manageable(d));
  assert.ok(A.accessCell({...d,manual_paused:1}).includes('Ручная пауза'));
  assert.ok(A.accessCell({...d,expires_at:100}).includes('Срок истёк'));
  assert.ok(A.pauseForm({...d,manual_paused:1}).includes('Лимит трафика исчерпан'));
});
console.log(count+' traffic quota model tests passed');
