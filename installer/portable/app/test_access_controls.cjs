'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const A=require('./static/client-access.js');
const source=fs.readFileSync(__dirname+'/static/admin.js','utf8').replace(/start\(\)\.catch\(\(\)=>\{\}\);\s*$/,'');
let count=0;
function fixture(device){
  const nodes=new Map(),events={},requests=[];
  function element(){return {innerHTML:'',textContent:'',className:'',value:'',attrs:{},setAttribute(k,v){this.attrs[k]=String(v)},disabled:false,open:false,classList:{add(){},remove(){},toggle(){}},showModal(){this.open=true},close(){this.open=false}};}
  const node=s=>{if(!nodes.has(s))nodes.set(s,element());return nodes.get(s)};
  const state={devices:[{name:'Тест',group_name:'Группа',owner_name:'owner',group_id:2,ip:'10.8.1.250',tx:0,rx:0,handshake:0,up_bps:0,down_bps:0,...device}],groups:[],chart:[],meta:{last_sync:Math.floor(Date.now()/1000)}};
  const sandbox={document:{querySelector:node,querySelectorAll:()=>[],addEventListener:(type,fn)=>events[type]=fn},
    ClientAccess:A,TrafficChart:{destroy(){}},DeviceGroups:{html:()=>''},Date,console,setTimeout:()=>0,clearTimeout(){},
    FormData:class{constructor(target){this.target=target}*[Symbol.iterator](){yield* Object.entries(this.target.values||{})}},
    fetch:async(url,opts)=>{requests.push({url,opts});if(opts?.method==='PATCH'){
      const body=JSON.parse(opts.body),d=state.devices[0];
      if(Object.hasOwn(body,'paused'))d.manual_paused=Number(body.paused);
      if(Object.hasOwn(body,'expires_at'))d.expires_at=body.expires_at;
      if(Object.hasOwn(body,'limit_bytes'))d.traffic_limit_bytes=body.limit_bytes;
      d.state=d.manual_paused?'paused':A.expired(d)?'expired':d.traffic_limit_bytes!=null&&d.rx+d.tx>=d.traffic_limit_bytes?'limited':'active';return {ok:true,json:async()=>d};
    }assert.equal(url,'/api/dashboard');return {ok:true,json:async()=>state};}};
  const context=vm.createContext(sandbox);vm.runInContext(source,context);
  sandbox.fixtureData=state;vm.runInContext("me={role:'super',csrf:'synthetic-csrf'};data=fixtureData;page='devices'",context);
  return {node,requests,state,context,
    click:(dataset,id='')=>events.click({target:{closest:()=>({dataset,id})}}),
    input:target=>events.input({target}),change:target=>events.change({target}),
    submit:values=>node('#modal-form').onsubmit({preventDefault(){},target:{values}})};
}
async function test(name,fn){await fn();count++;console.log('PASS '+name)}
(async()=>{
  await test('pause sends only paused and leaves the exact deadline untouched',async()=>{
    const expiry=A.parse('2026-12-01T12:30'),f=fixture({id:'test',state:'active',manual_paused:0,expires_at:expiry});
    await f.click({pause:'test'});assert.equal(f.requests.length,0);assert.ok(f.node('#modal').open);
    await f.submit({});assert.deepEqual(JSON.parse(f.requests[0].opts.body),{paused:true});
    assert.equal(f.state.devices[0].expires_at,expiry);assert.equal(f.state.devices[0].state,'paused');
  });
  await test('resume sends only paused false and never clears an expired deadline',async()=>{
    const f=fixture({id:'test',state:'paused',manual_paused:1,expires_at:100});
    await f.click({pause:'test'});assert.ok(f.node('#modal-body').innerHTML.includes('Срок доступа уже истёк'));
    await f.submit({});assert.deepEqual(JSON.parse(f.requests[0].opts.body),{paused:false});
    assert.equal(f.state.devices[0].state,'expired');assert.equal(f.state.devices[0].expires_at,100);
    assert.ok(f.node('#toast').textContent.includes('срок истёк'));
  });
  await test('expiry-only save retains manual pause and omits paused from the request',async()=>{
    const f=fixture({id:'test',state:'paused',manual_paused:1,expires_at:null});
    await f.click({expiry:'test'});assert.ok(!f.node('#modal-body').innerHTML.includes('name="paused"'));
    await f.submit({expires_local:'2026-12-01T12:30'});
    assert.deepEqual(JSON.parse(f.requests[0].opts.body),{expires_at:A.parse('2026-12-01T12:30')});
    assert.equal(f.state.devices[0].state,'paused');assert.equal(f.state.devices[0].manual_paused,1);
  });
  await test('clearing expiry sends null, not a guessed future date or an access toggle',async()=>{
    const f=fixture({id:'test',state:'expired',manual_paused:0,expires_at:100});await f.click({expiry:'test'});await f.submit({expires_local:''});
    assert.deepEqual(JSON.parse(f.requests[0].opts.body),{expires_at:null});assert.equal(f.state.devices[0].state,'active');
  });
  await test('invalid expiry is rejected before any HTTP mutation',async()=>{
    const f=fixture({id:'test',state:'active'});await f.click({expiry:'test'});await f.submit({expires_local:'bad'});
    assert.equal(f.requests.length,0);assert.ok(f.node('#modal-error').textContent);assert.ok(f.node('#modal').open);
  });
  await test('legacy and incomplete peers cannot open access controls even through delegated clicks',async()=>{
    for(const d of [{legacy:1,state:'active'},{state:'pending'},{state:'error'}]){
      const f=fixture({id:'test',...d});await f.click({pause:'test'});await f.click({expiry:'test'});
      assert.equal(f.requests.length,0);assert.equal(f.node('#modal').open,false);
    }
  });
  await test('the actual table has seven matching cells and separate control buttons',async()=>{
    const f=fixture({id:'test',state:'active',manual_paused:0,expires_at:null});
    const html=vm.runInContext('table(data.devices,true)',f.context);
    assert.equal((html.match(/<th(?:\s[^>]*)?>/g)||[]).length,7);assert.equal((html.match(/<td>/g)||[]).length,7);
    for(const marker of ['<th>Доступ</th>','<th>Срок доступа</th>','<th>Текущая скорость</th>','Разрешён','Без срока','data-pause="test"','data-expiry="test"'])assert.ok(html.includes(marker));
    assert.ok(!html.includes('Текущий обмен'));
    assert.ok(!html.includes('Доступ / срок'));assert.equal((html.match(/Без срока/g)||[]).length,1);
  });
  await test('last activity uses handshake age at server time, with a strict three-minute boundary',async()=>{
    const now=1792919820,f=fixture({id:'test',state:'active'});f.state.chart_info={window_end:now};
    for(const [age,green] of [[0,true],[179,true],[180,false],[3600,false],[-1,false]]){
      f.state.devices[0].handshake=now-age;
      const html=vm.runInContext('activity(data.devices[0])',f.context);
      assert.equal(html.includes('activity-dot is-recent'),green);
      assert.ok(html.includes('<time '));
    }
  });
  await test('absent and invalid handshakes are gray without a fabricated timestamp',async()=>{
    const f=fixture({id:'test',state:'active'});
    for(const handshake of [0,null,undefined,'bad',-1,Infinity,1e99]){
      f.state.devices[0].handshake=handshake;const html=vm.runInContext('activity(data.devices[0])',f.context);
      assert.ok(!html.includes('is-recent'));assert.ok(html.includes('Не было'));assert.ok(!html.includes('<time '));
    }
  });
  await test('activity is separate from permission and no word-based connection status remains',async()=>{
    const now=1792919820,f=fixture({id:'test',state:'paused',manual_paused:1,handshake:now-20,online:false});f.state.chart_info={window_end:now};
    const html=vm.runInContext('table(data.devices,true)',f.context);
    assert.ok(html.includes('Последняя активность'));assert.ok(html.includes('activity-dot is-recent'));
    assert.ok(html.includes('Ручная пауза'));
    for(const word of ['Ожидание','Недавний обмен','Нет обмена','<th>Активность</th>'])assert.ok(!html.includes(word));
    assert.ok(html.includes('role="img"'));assert.ok(html.includes('aria-label="Handshake за последние 3 минуты"'));
  });
  await test('visible handshake timestamps explicitly use Moscow time regardless of browser timezone',async()=>{
    const at=A.parse('2026-11-01T12:30'),f=fixture({id:'test',state:'active',handshake:at});
    for(const zone of ['UTC','America/New_York','Asia/Tokyo']){
      process.env.TZ=zone;const html=vm.runInContext('activity(data.devices[0])',f.context);
      assert.ok(html.includes('01.11.2026, 12:30 МСК'));assert.ok(html.includes('2026-11-01T09:30:00.000Z'));
    }
  });
  await test('unlimited is an explicit non-submit button with the correct initial selection',async()=>{
    const finite=A.expiryForm({expires_at:A.parse('2026-12-01T12:30')}),unlimited=A.expiryForm({expires_at:null});
    assert.ok(finite.includes('type="button" id="expiry-unlimited"'));
    assert.ok(finite.includes('aria-pressed="false">∞ Бесконечно'));
    assert.ok(unlimited.includes('aria-pressed="true">∞ Бесконечно'));
  });
  await test('unlimited clears only the form; cancel never changes client policy or calls HTTP',async()=>{
    const expiry=A.parse('2026-12-01T12:30'),f=fixture({id:'test',state:'active',expires_at:expiry});
    await f.click({expiry:'test'});const input=f.node('#modal input[name="expires_local"]');input.value=A.input(expiry);
    await f.click({},'expiry-unlimited');assert.equal(input.value,'');assert.equal(f.requests.length,0);
    assert.equal(f.node('#expiry-unlimited').attrs['aria-pressed'],'true');assert.ok(f.node('#expiry-mode').textContent.includes('Без срока'));
    assert.equal(f.state.devices[0].expires_at,expiry);f.node('#modal-cancel').onclick();
    assert.equal(f.node('#modal').open,false);assert.equal(f.state.devices[0].expires_at,expiry);
  });
  await test('saving unlimited sends only null expiry and retains manual pause',async()=>{
    const f=fixture({id:'test',state:'paused',manual_paused:1,expires_at:100});await f.click({expiry:'test'});
    await f.click({},'expiry-unlimited');await f.submit({expires_local:f.node('#modal input[name="expires_local"]').value});
    assert.deepEqual(JSON.parse(f.requests[0].opts.body),{expires_at:null});
    assert.equal(f.state.devices[0].state,'paused');assert.equal(f.state.devices[0].manual_paused,1);
  });
  await test('manual date input and calendar change deselect unlimited without saving',async()=>{
    const f=fixture({id:'test',state:'active',expires_at:null});await f.click({expiry:'test'});
    const input=f.node('#modal input[name="expires_local"]');input.name='expires_local';
    for(const event of [f.input,f.change]){
      input.value='2026-12-01T12:30';event(input);assert.equal(f.node('#expiry-unlimited').attrs['aria-pressed'],'false');
      assert.ok(f.node('#expiry-mode').textContent.includes('До указанной даты'));
      input.value='';event(input);assert.equal(f.node('#expiry-unlimited').attrs['aria-pressed'],'true');
    }
    assert.equal(f.requests.length,0);assert.equal(f.state.devices[0].expires_at,null);
  });
  await test('traffic save sends only a byte limit and preserves date/manual pause',async()=>{
    const expiry=A.parse('2026-12-01T12:30'),f=fixture({id:'test',state:'paused',manual_paused:1,expires_at:expiry});
    await f.click({traffic:'test'});assert.equal(f.requests.length,0);assert.ok(f.node('#modal-body').innerHTML.includes('Уже использовано'));
    await f.submit({traffic_amount:'10',traffic_unit:'gb'});
    assert.equal(f.requests[0].url,'/api/devices/test/traffic');assert.deepEqual(JSON.parse(f.requests[0].opts.body),{limit_bytes:10*1024**3});
    assert.equal(f.state.devices[0].manual_paused,1);assert.equal(f.state.devices[0].expires_at,expiry);
  });
  await test('traffic unlimited is local until save and never resets accumulated bytes',async()=>{
    const f=fixture({id:'test',state:'limited',rx:100,tx:200,traffic_limit_bytes:300});await f.click({traffic:'test'});
    f.node('#modal input[name="traffic_amount"]').value='300';await f.click({},'traffic-unlimited');
    assert.equal(f.requests.length,0);assert.equal(f.node('#modal input[name="traffic_amount"]').value,'');
    await f.submit({traffic_amount:'',traffic_unit:'gb'});
    assert.deepEqual(JSON.parse(f.requests[0].opts.body),{limit_bytes:null});assert.equal(f.state.devices[0].rx+f.state.devices[0].tx,300);
    assert.equal(f.state.devices[0].state,'active');
  });
  await test('a traffic limit below usage is shown as suspended and invalid input is not sent',async()=>{
    const f=fixture({id:'test',state:'active',rx:100,tx:200});await f.click({traffic:'test'});
    await f.submit({traffic_amount:'-1',traffic_unit:'gb'});assert.equal(f.requests.length,0);
    await f.submit({traffic_amount:'299',traffic_unit:'b'});assert.equal(f.state.devices[0].state,'limited');
    assert.ok(f.node('#toast').textContent.includes('Лимит исчерпан'));
    const html=vm.runInContext('table(data.devices,true)',f.context);assert.ok(html.includes('Лимит трафика'));assert.ok(html.includes('data-download="test"'));
  });
  await test('legacy clients cannot open a traffic-limit form',async()=>{
    const f=fixture({id:'test',state:'active',legacy:1});await f.click({traffic:'test'});
    assert.equal(f.requests.length,0);assert.equal(f.node('#modal').open,false);
  });
  console.log(count+' separate access-control tests passed');
})().catch(e=>{console.error(e);process.exitCode=1});
