'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/static/admin.js','utf8').replace(/start\(\)\.catch\(\(\)=>\{\}\);\s*$/,'');
let passed=0;
function fixture(overrides={}){
  const nodes=new Map(),events={},requests=[];
  const liveUsers=[{id:1,username:'owner',enabled:1,role:'super',max_devices:150},
    {id:2,username:'closed-admin',enabled:0,role:'admin',max_devices:25},
    {id:3,username:'open-admin',enabled:1,role:'admin',max_devices:25}];
  const node=s=>{if(!nodes.has(s))nodes.set(s,{innerHTML:'',textContent:'',className:'',disabled:false,open:false,
    classList:{add(){},remove(){},toggle(){}},showModal(){this.open=true},close(){this.open=false}});return nodes.get(s)};
  const sandbox={document:{querySelector:node,querySelectorAll:()=>[],addEventListener:(type,fn)=>events[type]=fn},
    TrafficChart:{destroy(){}},Date,console,setTimeout:()=>0,clearTimeout(){},
    FormData:class{*[Symbol.iterator](){}},fixtureUsers:liveUsers,
    fetch:async(url,opts={})=>{requests.push({url,opts});
      if(opts.method==='DELETE'){
        if(overrides.conflict)return {ok:false,json:async()=>({error:'У администратора ещё есть группы'})};
        const at=liveUsers.findIndex(u=>u.id===Number(url.split('/').pop()));liveUsers.splice(at,1);return {ok:true,json:async()=>({ok:true,deleted:true})};
      }
      if(url==='/api/users')return {ok:true,json:async()=>({users:liveUsers})};
      assert.equal(url,'/api/dashboard');return {ok:true,json:async()=>({devices:[],groups:[],meta:{last_sync:Math.floor(Date.now()/1000)}})};
    }};
  const context=vm.createContext(sandbox);vm.runInContext(source,context);
  vm.runInContext("me={id:1,role:'super',csrf:'synthetic-csrf'};users=fixtureUsers;page='users'",context);
  return {node,requests,context,liveUsers,
    click:dataset=>events.click({target:{closest:()=>({dataset})}}),
    submit:()=>node('#modal-form').onsubmit({preventDefault(){},target:{}})};
}
async function test(name,fn){await fn();passed++;console.log('PASS '+name)}
(async()=>{
  await test('delete appears only for closed non-protected accounts',()=>{
    const f=fixture();
    assert.ok(vm.runInContext('userActions(users[1])',f.context).includes('data-user-delete="2"'));
    assert.ok(!vm.runInContext('userActions(users[2])',f.context).includes('data-user-delete'));
    for(const expr of ['userActions(users[0])',"(me.id=2,userActions(users[1]))"]){
      const html=vm.runInContext(expr,f.context);assert.ok(html.includes('Защищённая учётная запись'));
      assert.ok(html.includes('data-user-password'));assert.ok(!/data-user-(toggle|delete)/.test(html));
    }
  });
  await test('opening and cancelling confirmation performs no mutation',async()=>{
    const f=fixture();await f.click({userDelete:'2'});assert.ok(f.node('#modal').open);assert.equal(f.requests.length,0);
    f.node('#modal-cancel').onclick();assert.equal(f.node('#modal').open,false);assert.equal(f.requests.length,0);
    assert.ok(f.node('#modal-body').innerHTML.includes('Клиенты и VPN-конфиги автоматически не удаляются'));
  });
  await test('confirmed deletion sends only CSRF-protected DELETE and refreshes the list',async()=>{
    const f=fixture();await f.click({userDelete:'2'});await f.submit();await new Promise(setImmediate);
    const mutations=f.requests.filter(r=>r.opts.method);assert.equal(mutations.length,1);
    assert.equal(mutations[0].url,'/api/users/2');assert.equal(mutations[0].opts.method,'DELETE');
    assert.deepEqual(JSON.parse(mutations[0].opts.body),{});assert.equal(mutations[0].opts.headers['X-CSRF-Token'],'synthetic-csrf');
    assert.ok(!f.node('#content').innerHTML.includes('closed-admin'));assert.equal(f.node('#modal').open,false);
    assert.ok(!f.requests.some(r=>/revoke|devices|groups/.test(r.url)));
  });
  await test('stale, protected or non-super delegated clicks are ignored',async()=>{
    for(const id of ['1','3','99']){const f=fixture();await f.click({userDelete:id});assert.equal(f.node('#modal').open,false);assert.equal(f.requests.length,0)}
    for(const change of ["me.id=2","me.role='admin'"]){const f=fixture();vm.runInContext(change,f.context);await f.click({userDelete:'2'});assert.equal(f.requests.length,0);assert.equal(f.node('#modal').open,false)}
  });
  await test('administrator name is escaped in the confirmation',async()=>{
    const f=fixture();f.liveUsers[1].username='<img onerror=bad>';await f.click({userDelete:'2'});
    assert.ok(f.node('#modal-body').innerHTML.includes('&lt;img onerror=bad&gt;'));assert.ok(!f.node('#modal-body').innerHTML.includes('<img'));
  });
  await test('group conflict keeps the account and displays the server reason in the open dialog',async()=>{
    const f=fixture({conflict:true});await f.click({userDelete:'2'});await f.submit();
    assert.equal(f.node('#modal-error').textContent,'У администратора ещё есть группы');assert.ok(f.node('#modal').open);
    assert.ok(f.liveUsers.some(u=>u.id===2));assert.equal(f.node('#modal-submit').disabled,false);
  });
  await test('administrator table renders the new action beside reopen',async()=>{
    const f=fixture();await vm.runInContext('renderUsers()',f.context);
    const html=f.node('#content').innerHTML;assert.ok(html.includes('data-user-toggle="2">Открыть кабинет'));
    assert.ok(html.includes('data-user-delete="2">Удалить'));assert.ok(!html.includes('data-user-delete="3"'));
    assert.ok(html.includes('журнал и статистика сохранятся'));
  });
  console.log(passed+' administrator deletion UI tests passed');
})().catch(error=>{console.error(error);process.exit(1)});
