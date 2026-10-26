'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Groups = require('./static/device-groups.js');
let passed = 0;
function test(name, fn) { fn(); passed++; console.log('ok - ' + name); }
const groups = [
  {id: 1, owner_id: 1, name: 'Семья', owner_name: 'Анна'},
  {id: 2, owner_id: 1, name: 'Друзья', owner_name: 'Анна'},
  {id: 3, owner_id: 2, name: 'Семья', owner_name: 'Борис'},
  {id: 4, owner_id: 2, name: 'Пустая', owner_name: 'Борис'}
];
const devices = [
  {id: 'a', group_id: 1, name: 'Телефон', state: 'active'},
  {id: 'b', group_id: '1', name: 'Ноутбук', state: 'pending'},
  {id: 'c', group_id: 2, name: 'Планшет', state: 'active'},
  {id: 'd', group_id: 3, name: 'Телефон', state: 'active'},
  {id: 'e', group_id: 2, name: 'Отозван', state: 'revoked'}
];
test('groups by stable ID, not name or owner', () => {
  const result = Groups.model(devices, groups);
  assert.deepEqual(result.map(g => g.devices.map(d => d.id)), [['a','b'],['c'],['d'],[]]);
  assert.deepEqual(result.map(g => g.total), [2,1,1,0]);
});
test('does not modify API input or copy invitation secrets', () => {
  const before = JSON.stringify({devices, groups});
  Groups.model(devices, [...groups, {id:5, name:'Secret', link:'must-not-copy', token_enc:'secret'}]);
  assert.equal(JSON.stringify({devices, groups}), before);
  assert.ok(!JSON.stringify(Groups.model([], [{id:5,name:'X',link:'secret'}])).includes('secret'));
});
test('device search preserves group and full count', () => {
  const result = Groups.model(devices, groups, '  ТЕЛЕФОН  ');
  assert.deepEqual(result.map(g => [g.id, g.devices.length, g.total]), [[1,1,2],[3,1,1]]);
});
test('group name search includes every member, without merging duplicate names', () => {
  assert.deepEqual(Groups.model(devices, groups, 'семья').map(g => g.devices.map(d=>d.id)), [['a','b'],['d']]);
});
test('owner search finds only the supplied visible administrator groups', () => {
  assert.deepEqual(Groups.model(devices, groups, 'борис').map(g=>g.id), [3,4]);
  assert.equal(Groups.model(devices, groups.slice(0,2), 'борис').length, 0);
});
test('empty groups are clear, revoked clients stay hidden', () => {
  assert.equal(Groups.model(devices, groups, 'отозван').length, 0);
  assert.equal(Groups.model([], groups, 'пустая')[0].devices.length, 0);
  assert.ok(Groups.html([], groups, {table:()=>''}).includes('В этой группе пока нет клиентов.'));
  assert.ok(Groups.html(devices, groups, {query:'нет совпадений'}).includes('Ничего не найдено'));
});
test('missing metadata cannot silently hide a visible client', () => {
  const result = Groups.model([{id:'x',group_id:9,group_name:'Временная',owner_name:'Анна',name:'X'}], []);
  assert.equal(result[0].id, 9); assert.equal(result[0].devices[0].id, 'x');
});
test('empty result has a useful invitation message', () => {
  assert.ok(Groups.html([], []).includes('Пока нет групп'));
});
test('escapes group and owner text, keeps row action renderer', () => {
  let rows;
  const html = Groups.html(devices, [{...groups[0],name:'<img onerror="x">',owner_name:'<script>x</script>'}], {
    showOwners:true, table:(ds, grouped) => { rows=ds; assert.equal(grouped,true); return '<table></table>'; }
  });
  assert.ok(html.includes('&lt;img onerror=&quot;x&quot;&gt;'));
  assert.ok(html.includes('&lt;script&gt;x&lt;/script&gt;'));
  assert.ok(!html.includes('<img')); assert.ok(rows.length);
});
test('administrator sections use ID, with groups and clients nested below them', () => {
  const tree = Groups.administrators(Groups.model(devices, groups));
  assert.deepEqual(tree.map(a=>[a.id,a.name,a.groups.map(g=>g.id),a.count]),
    [['1','Анна',[1,2],3],['2','Борис',[3,4],1]]);
  const distinct = Groups.administrators(Groups.model([], [groups[0],{...groups[2],owner_name:'Анна'}]));
  assert.equal(distinct.length, 2);
});
test('partial search counts and native accessible disclosures are rendered', () => {
  const html = Groups.html(devices, groups, {query:'ноутбук',table:()=>'<table></table>'});
  assert.ok(html.includes('Найдено: 1 из 2'));
  assert.ok(html.includes('data-device-disclosure="admin:1"'));
  assert.ok(html.includes('<summary class="device-group-head">'));
  assert.equal((html.match(/<details class="device-group"/g)||[]).length, 1);
});
test('collapsed administrator and group state survives render and search', () => {
  const render = query => Groups.html([], [groups[0]], {query});
  Groups.remember({dataset:{deviceDisclosure:'admin:1'},open:false});
  Groups.remember({dataset:{deviceDisclosure:'group:1'},open:false});
  assert.ok(render().includes('data-device-disclosure="admin:1">'));
  assert.ok(render().includes('data-device-disclosure="group:1">'));
  assert.ok(render('Анна').includes('data-device-disclosure="admin:1" data-device-search="true" open'));
  Groups.remember({dataset:{deviceDisclosure:'admin:1',deviceSearch:'true'},open:true});
  assert.ok(render().includes('data-device-disclosure="admin:1">'));
  Groups.remember({dataset:{deviceDisclosure:'admin:1'},open:true});
  Groups.remember({dataset:{deviceDisclosure:'group:1'},open:true});
  assert.ok(render().includes('data-device-disclosure="group:1" open'));
});
test('grouping is integrated in initial render and live search, before admin script', () => {
  const admin = fs.readFileSync(path.join(__dirname,'static/admin.js'),'utf8');
  const html = fs.readFileSync(path.join(__dirname,'static/admin.html'),'utf8');
  assert.ok(html.indexOf('/static/device-groups.js') < html.indexOf('/static/admin.js'));
  assert.equal((admin.match(/groupedDevices\(\)/g)||[]).length, 3);
  for (const action of ['data-download','data-move','data-revoke']) assert.ok(admin.includes(action));
});

test('authoritative lifetime group totals include history without double counting visible clients', () => {
  const result = Groups.model([{...devices[0],rx:5,tx:7},{...devices[1],rx:3,tx:4}],
    [{...groups[0],rx:100,tx:200}]);
  assert.deepEqual([result[0].rx,result[0].tx], [100,200]);
  const zero = Groups.model([{...devices[0],rx:5,tx:7}], [{...groups[0],rx:0,tx:0}]);
  assert.deepEqual([zero[0].rx,zero[0].tx], [0,0]);
});

test('fallback totals use every supplied row including revoked history, not just search matches', () => {
  const result = Groups.model([{...devices[0],rx:5,tx:7},{...devices[1],rx:'3',tx:'4'},
    {id:'old',group_id:1,state:'revoked',rx:10,tx:20}], [groups[0]], 'Телефон');
  assert.deepEqual([result[0].rx,result[0].tx,result[0].devices.length], [18,31,1]);
  const missing = Groups.model([{...devices[0],rx:12,tx:34}], []);
  assert.deepEqual([missing[0].rx,missing[0].tx], [12,34]);
});

test('empty groups keep historical traffic while revoked clients remain hidden', () => {
  const html = Groups.html([], [{...groups[0],rx:40,tx:60}], {table:()=>{throw Error('No visible clients');}});
  assert.ok(html.includes('Клиентов: 0'));
  assert.ok(html.includes('За всё время: <strong>100 Б</strong>'));
  assert.ok(html.includes('В этой группе пока нет клиентов.'));
});

test('administrator totals sum group histories by owner ID without mixing administrators', () => {
  const source = [{...groups[0],rx:10,tx:20},{...groups[1],rx:30,tx:40},
    {...groups[2],rx:100,tx:200},{...groups[3],rx:3,tx:4}];
  const tree = Groups.administrators(Groups.model([], source));
  assert.deepEqual(tree.map(a=>[a.id,a.rx,a.tx]), [['1',40,60],['2',103,204]]);
  const scoped = Groups.administrators(Groups.model([], source.filter(g=>g.owner_id===2)));
  assert.deepEqual(scoped.map(a=>[a.id,a.rx,a.tx]), [['2',103,204]]);
});

test('search leaves full group and administrator traffic unchanged including hidden sibling groups', () => {
  const source = [{...groups[0],rx:10,tx:20},{...groups[1],rx:30,tx:40},{...groups[2],rx:100,tx:200}];
  const html = Groups.html(devices, source, {query:'Ноутбук',table:()=>'<table></table>',bytes:n=>n+' bytes'});
  assert.ok(html.includes('Найдено: 1 из 2'));
  assert.ok(html.includes('За всё время: <strong>100 bytes</strong>'));
  assert.ok(html.includes('За всё время: <strong>30 bytes</strong>'));
  assert.ok(html.includes('↓ 60 bytes'));
  assert.ok(html.includes('↑ 40 bytes'));
  assert.ok(!html.includes('data-device-disclosure="group:2"'));
  assert.ok(!html.includes('300 bytes'));
});

test('directions match client perspective: TX is downloaded and RX is uploaded', () => {
  const html = Groups.html([], [{...groups[0],rx:12,tx:34}], {bytes:n=>String(n)});
  assert.ok(html.includes('title="Скачано клиентами">↓ 34'));
  assert.ok(html.includes('title="Отправлено клиентами">↑ 12'));
  assert.ok(html.includes('За всё время: <strong>46</strong>'));
  assert.ok(html.includes('с начала наблюдения панелью'));
});

test('invalid counters cannot poison totals and formatter output is escaped', () => {
  const result = Groups.model([{...devices[0],rx:10,tx:15},{...devices[1],rx:-5,tx:NaN}],
    [{...groups[0],rx:Infinity,tx:null}]);
  assert.deepEqual([result[0].rx,result[0].tx], [10,15]);
  const html = Groups.html([], [{...groups[0],rx:1,tx:2}], {bytes:()=>'<img src=x onerror=bad>'});
  assert.ok(!html.includes('<img'));
  assert.ok(html.includes('&lt;img src=x onerror=bad&gt;'));
});

test('shared byte formatter and responsive compact traffic headers are integrated', () => {
  const admin = fs.readFileSync(path.join(__dirname,'static/admin.js'),'utf8');
  const css = fs.readFileSync(path.join(__dirname,'static/style.css'),'utf8');
  assert.ok(admin.includes('DeviceGroups.html(data.devices,data.groups,{query,table,bytes})'));
  for (const selector of ['.device-head-stats','.device-traffic-directions','.device-admin-head>.device-head-stats','.device-group-head>.device-head-stats'])
    assert.ok(css.includes(selector));
  assert.ok(css.includes('grid-column:2;justify-content:space-between'));
});
console.log(passed + ' client-group tests passed');
