'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/static/admin.js','utf8').replace(/start\(\)\.catch\(\(\)=>\{\}\);\s*$/,'');
let passed=0;
const expected={
  login:'Вход в кабинет','password.changed':'Пароль изменён',
  'admin.created':'Администратор создан','admin.updated':'Настройки администратора изменены','admin.deleted':'Администратор удалён',
  'group.created':'Группа создана','group.updated':'Настройки группы изменены','group.deleted':'Группа удалена',
  'device.requested':'Запрошен VPN-конфиг','device.created':'VPN-конфиг создан',
  'device.revoked':'Клиент удалён, доступ отозван','device.group_changed':'Клиент перенесён в другую группу',
  'device.access_updated':'Доступ или срок действия изменён','device.traffic_limit_updated':'Лимит трафика изменён',
  'device.paused':'Доступ клиента приостановлен','device.expired':'Срок доступа истёк','device.limited':'Лимит трафика исчерпан'
};
function fixture(events=[]){
  const nodes=new Map(),requests=[];
  const node=selector=>{if(!nodes.has(selector))nodes.set(selector,{innerHTML:'',textContent:''});return nodes.get(selector)};
  const context=vm.createContext({document:{querySelector:node,addEventListener(){}},setTimeout:()=>0,clearTimeout(){},Date,
    fetch:async(url,opts)=>{requests.push({url,opts});return {ok:true,json:async()=>({events})}}});
  vm.runInContext(source,context);return {node,requests,context,label:event=>{context.event=event;return vm.runInContext('auditAction(event)',context)}};
}
async function test(name,fn){await fn();passed++;console.log('PASS '+name)}
(async()=>{
  await test('all 17 supported actions have precise Russian descriptions',()=>{
    const f=fixture();for(const [event,label] of Object.entries(expected))assert.equal(f.label(event),label);
  });
  await test('mapping covers every literal and automatic state event emitted by the backend',()=>{
    const python=fs.readFileSync(__dirname+'/panel.py','utf8');const f=fixture();
    const emitted=[...python.matchAll(/log\(c,'([^']+)'/g)].map(m=>m[1]).filter(event=>!event.endsWith('.'));
    emitted.push('device.paused','device.expired','device.limited');
    for(const event of emitted)assert.notEqual(f.label(event),'Другое действие',event);
  });
  await test('unknown, empty and inherited-object names use an honest safe fallback',()=>{
    const f=fixture();for(const event of ['future.event','constructor','toString','__proto__','',null,undefined])assert.equal(f.label(event),'Другое действие');
  });
  await test('actual audit table renders translated actions and retains raw code only in the tooltip',async()=>{
    const f=fixture(Object.keys(expected).map(event=>({at:1792885000,event,username:'owner',detail:'Existing object'})));
    await vm.runInContext('renderAudit()',f.context);const html=f.node('#content').innerHTML;
    for(const [event,label] of Object.entries(expected)){
      assert.ok(html.includes('title="Технический код: '+event+'">'+label+'</td>'));
      assert.ok(!html.includes('>'+event+'</td>'));
    }
  });
  await test('unknown event codes, actor names and historical details remain HTML escaped',async()=>{
    const f=fixture([{at:1792885000,event:'<img onerror="bad">',username:'<script>actor</script>',detail:'<b>unchanged</b>'}]);
    await vm.runInContext('renderAudit()',f.context);const html=f.node('#content').innerHTML;
    assert.ok(html.includes('Другое действие'));assert.ok(html.includes('&lt;img onerror=&quot;bad&quot;&gt;'));
    assert.ok(!/<img|<script|<b>/.test(html));assert.ok(html.includes('&lt;b&gt;unchanged&lt;/b&gt;'));
  });
  await test('labels are presentation-only and neither mutate events nor send write requests',async()=>{
    const events=[{at:1792885000,event:'device.traffic_limit_updated',username:null,detail:'existing record'}],before=JSON.stringify(events),f=fixture(events);
    await vm.runInContext('renderAudit()',f.context);assert.equal(JSON.stringify(events),before);
    assert.equal(f.requests.length,1);assert.equal(f.requests[0].url,'/api/audit');assert.equal(f.requests[0].opts.method,undefined);
    assert.ok(f.node('#content').innerHTML.includes('Приглашение'));
  });
  console.log(passed+' audit action label tests passed');
})().catch(error=>{console.error(error);process.exit(1)});
