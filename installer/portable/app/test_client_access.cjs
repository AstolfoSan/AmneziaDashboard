'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const A=require('./static/client-access.js');let count=0;
function test(name,fn){fn();count++;console.log('ok - '+name);}
test('empty date means unlimited',()=>{assert.equal(A.input(null),'');assert.equal(A.parse(''),null);});
test('Moscow wall clock roundtrip is independent of client timezone',()=>{
  for(const tz of ['UTC','America/New_York','Asia/Tokyo']){
    process.env.TZ=tz;assert.equal(A.parse('2026-11-01T12:30'),Date.parse('2026-11-01T09:30:00Z')/1000);
    assert.equal(A.input(A.parse('2026-11-01T12:30')),'2026-11-01T12:30');
    assert.ok(A.format(A.parse('2026-11-01T12:30')).includes('12:30'));
  }
});
test('rejects invalid dates, normalised overflows, injection, and unsupported years',()=>{
  for(const value of ['bad','2026-02-30T12:00','2026-13-01T00:00','2026-01-01T24:00','1999-01-01T00:00','2101-01-01T00:00','"><img onerror=x>'])
    assert.throws(()=>A.parse(value));
  assert.equal(A.input(A.parse('2028-02-29T23:59')),'2028-02-29T23:59');
});
test('distinct manual and automatic pause badges',()=>{
  assert.ok(A.badge('paused').includes('Приостановлен'));assert.ok(A.badge('expired').includes('Срок истёк'));assert.equal(A.badge('active'),'');
});
test('legacy remains protected; unlimited/deadline labels are explicit',()=>{
  assert.equal(A.deadline({legacy:true}),'');assert.ok(A.deadline({}).includes('Без срока'));
  assert.ok(A.deadline({expires_at:A.parse('2026-11-01T12:30')}).includes('01.11.2026'));
});
test('expiry-only form preserves optional date and explicitly retains a manual pause',()=>{
  const html=A.expiryForm({manual_paused:1,expires_at:A.parse('2026-11-01T12:30')});
  assert.ok(!html.includes('name="paused"'));assert.ok(html.includes('value="2026-11-01T12:30"'));
  assert.ok(!html.includes(' required'));assert.ok(html.includes('прежний .vpn сохранятся'));
  assert.ok(html.includes('Сейчас включена ручная пауза'));
});

test('access and expiry are explicit independent table cells',()=>{
  assert.ok(A.accessCell({state:'active'}).includes('Разрешён'));
  assert.ok(A.accessCell({state:'paused',manual_paused:1}).includes('Ручная пауза'));
  assert.ok(A.accessCell({state:'active',expires_at:100},200).includes('Срок истёк'));
  assert.ok(A.accessCell({state:'error'}).includes('Не выдан'));
  assert.ok(A.termCell({}).includes('Без срока'));
  assert.ok(A.termCell({legacy:1}).includes('Не задан в панели'));
  assert.ok(A.termCell({expires_at:A.parse('2026-11-01T12:30')},100).includes('01.11.2026'));
});

test('separate pause/resume and expiry buttons keep legacy and incomplete peers protected',()=>{
  const d={id:'synthetic',state:'active',manual_paused:0};
  const html=A.actions(d);assert.ok(html.includes('Приостановить доступ'));assert.ok(html.includes('data-expiry="synthetic"'));
  assert.ok(A.actions({...d,manual_paused:1}).includes('Возобновить доступ'));
  assert.ok(A.actions({...d,manual_paused:1,expires_at:100}).includes('Снять паузу'));
  assert.equal(A.actions({...d,legacy:1}),'');assert.equal(A.actions({...d,state:'revoked'}),'');
  assert.equal((A.actions({...d,state:'pending'}).match(/ disabled/g)||[]).length,3);
});

test('resume of an expired manual pause never promises an expiry extension',()=>{
  const html=A.pauseForm({manual_paused:1,expires_at:100});
  assert.ok(html.includes('Срок доступа уже истёк'));assert.ok(html.includes('Дата окончания доступа не изменится'));
  assert.ok(!html.includes('<input'));assert.ok(!html.includes('<select'));
});
test('UI is integrated before admin and controls use scoped API',()=>{
  const read=f=>fs.readFileSync(path.join(__dirname,'static',f),'utf8');const html=read('admin.html'),js=read('admin.js');
  assert.ok(html.indexOf('/static/client-access.js')<html.indexOf('/static/admin.js'));
  assert.ok(!js.includes('data-access='));assert.ok(js.includes("'/access'"));assert.ok(js.includes('ClientAccess.parse(f.expires_local)'));
  assert.ok(js.includes('<th>Доступ</th><th>Срок доступа</th>'));
});
console.log(count+' client access tests passed');
