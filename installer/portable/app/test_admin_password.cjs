'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/static/admin.js','utf8').replace(/start\(\)\.catch\(\(\)=>\{\}\);\s*$/,'');
let passed=0;
function fixture({role='super',error=false}={}){
  const nodes=new Map(),events={},requests=[],passwordInputs=[{value:'synthetic-input'},{value:'synthetic-confirm'}];
  let fields={},reloads=0;
  const liveUsers=[{id:1,username:'owner',enabled:1,role:'super',max_devices:150},
    {id:2,username:'closed-admin',enabled:0,role:'admin',max_devices:25},
    {id:3,username:'open-admin',enabled:1,role:'admin',max_devices:25}];
  const node=s=>{
    if(s==='#profile-copy-value')return null;
    if(!nodes.has(s))nodes.set(s,{innerHTML:'',textContent:'',className:'',disabled:false,open:false,
      classList:{add(){},remove(){},toggle(){}},showModal(){this.open=true},close(){this.open=false;events.close({target:{id:'modal'}})}});
    return nodes.get(s);
  };
  const sandbox={document:{querySelector:node,querySelectorAll:selector=>selector.includes('password')?passwordInputs:[],addEventListener:(type,fn)=>events[type]=fn},
    TrafficChart:{destroy(){}},Date,console,setTimeout:()=>0,clearTimeout(){},location:{reload(){reloads++}},
    FormData:class{*[Symbol.iterator](){yield*Object.entries(fields)}},fixtureUsers:liveUsers,
    fetch:async(url,opts={})=>{requests.push({url,opts});
      if(opts.method)return error?{ok:false,status:403,json:async()=>({error:'Нет прав'})}:{ok:true,json:async()=>({ok:true})};
      if(url==='/api/users')return{ok:true,json:async()=>({users:liveUsers})};
      assert.equal(url,'/api/dashboard');return{ok:true,json:async()=>({devices:[],groups:[],meta:{last_sync:Math.floor(Date.now()/1000)}})};
    }};
  const context=vm.createContext(sandbox);vm.runInContext(source,context);
  vm.runInContext(`me={id:1,username:'owner',role:'${role}',csrf:'synthetic-csrf'};users=fixtureUsers;page='users'`,context);
  return{node,requests,context,liveUsers,passwordInputs,reloads:()=>reloads,
    click:(dataset={},id='')=>events.click({target:{closest:()=>({dataset,id})}}),
    submit:async values=>{fields=values;await node('#modal-form').onsubmit({preventDefault(){},target:{}});await new Promise(setImmediate)}};
}
async function test(name,fn){await fn();passed++;console.log('PASS '+name)}
(async()=>{
  await test('super sees password action for open, closed and protected owner accounts',()=>{
    const f=fixture();for(let i=0;i<3;i++)assert.ok(vm.runInContext(`userActions(users[${i}])`,f.context).includes(`data-user-password="${i+1}"`));
    const html=vm.runInContext('userActions(users[0])',f.context);assert.ok(!/data-user-(toggle|delete)/.test(html));assert.ok(html.includes('Защищённая'));
  });
  await test('non-super cannot see or open reset; missing target is ignored',async()=>{
    const f=fixture({role:'admin'});assert.equal(vm.runInContext('userActions(users[1])',f.context),'');
    await f.click({userPassword:'2'});assert.equal(f.node('#modal').open,false);assert.equal(f.requests.length,0);
    const s=fixture();await s.click({userPassword:'999'});assert.equal(s.node('#modal').open,false);
  });
  await test('masked new and confirmation fields, no old password, escaped name and closed-account warning',async()=>{
    const f=fixture();f.liveUsers[1].username='<img onerror=bad>';await f.click({userPassword:'2'});
    assert.equal(f.node('#modal-title').textContent,'Сменить пароль · <img onerror=bad>');
    const html=f.node('#modal-body').innerHTML;assert.ok(!html.includes('<img'));assert.equal((html.match(/type="password"/g)||[]).length,2);
    assert.ok(html.includes('name="confirm"'));assert.ok(!html.includes('name="old"'));assert.ok(html.includes('Закрытый кабинет останется закрытым'));
    assert.ok(html.includes('VPN-конфиги, клиенты и их доступ не изменятся'));assert.equal(f.requests.length,0);
  });
  await test('cancel clears both secret fields and does not call the API',async()=>{
    const f=fixture();await f.click({userPassword:'2'});f.node('#modal-cancel').onclick();
    assert.equal(f.node('#modal').open,false);assert.ok(f.passwordInputs.every(input=>input.value===''));assert.equal(f.requests.length,0);
    assert.equal(vm.runInContext('modalAction',f.context),null);
  });
  await test('mismatch and invalid lengths are rejected before HTTP',async()=>{
    for(const values of [{new:'synthetic-password',confirm:'different-password'},{new:'short',confirm:'short'},{new:'a'.repeat(129),confirm:'a'.repeat(129)}]){
      const f=fixture();await f.click({userPassword:'2'});await f.submit(values);
      assert.equal(f.requests.length,0);assert.ok(f.node('#modal-error').textContent);assert.ok(f.node('#modal').open);assert.equal(f.node('#modal-submit').disabled,false);
    }
  });
  await test('reset sends only the new password by scoped CSRF PATCH; no access or VPN mutation',async()=>{
    const f=fixture();await f.click({userPassword:'2'});await f.submit({new:'synthetic-password',confirm:'synthetic-password',enabled:true,role:'super'});
    const mutations=f.requests.filter(r=>r.opts.method);assert.equal(mutations.length,1);
    const request=mutations[0];assert.equal(request.url,'/api/users/2');assert.equal(request.opts.method,'PATCH');
    assert.deepEqual(JSON.parse(request.opts.body),{password:'synthetic-password'});assert.equal(request.opts.headers['X-CSRF-Token'],'synthetic-csrf');
    assert.equal(f.node('#modal').open,false);assert.equal(f.reloads(),0);assert.ok(!f.requests.some(r=>/devices|groups|password$/.test(r.url)));
    assert.ok(!f.node('#toast').textContent.includes('synthetic-password'));assert.equal(f.liveUsers[1].enabled,0);
  });
  await test('own reset reloads for sign-in without querying the expired session',async()=>{
    const f=fixture();await f.click({userPassword:'1'});assert.ok(f.node('#modal-body').innerHTML.includes('войдите с новым паролем'));
    await f.submit({new:'synthetic-password',confirm:'synthetic-password'});assert.equal(f.reloads(),1);
    assert.equal(f.requests.length,1);assert.equal(f.requests[0].url,'/api/users/1');assert.ok(f.passwordInputs.every(input=>input.value===''));
  });
  await test('My account uses no-old-password reset for super only',async()=>{
    const f=fixture();await f.click({},'change-password');assert.ok(!f.node('#modal-body').innerHTML.includes('name="old"'));
    await f.submit({new:'synthetic-password',confirm:'synthetic-password'});assert.equal(f.requests[0].url,'/api/users/1');
    const a=fixture({role:'admin'});await a.click({},'change-password');assert.ok(a.node('#modal-body').innerHTML.includes('name="old"'));
    await a.submit({old:'synthetic-old-password',new:'synthetic-password'});assert.equal(a.requests[0].url,'/api/password');assert.equal(a.reloads(),1);assert.equal(a.requests.length,1);
  });
  await test('server denial preserves the open form without success toast or reload',async()=>{
    const f=fixture({error:true});await f.click({userPassword:'2'});await f.submit({new:'synthetic-password',confirm:'synthetic-password'});
    assert.equal(f.node('#modal-error').textContent,'Нет прав');assert.ok(f.node('#modal').open);assert.equal(f.node('#modal-submit').disabled,false);assert.equal(f.reloads(),0);
    assert.equal(f.node('#toast').textContent,'');
  });
  console.log(passed+' administrator password UI tests passed');
})().catch(error=>{console.error(error);process.exit(1)});
