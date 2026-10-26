'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const Access=require('./static/client-access.js');
const source=fs.readFileSync(__dirname+'/static/admin.js','utf8').replace(/start\(\)\.catch\(\(\)=>\{\}\);\s*$/,'');
const fakeLink='vpn://c3ludGhldGljX3Byb2ZpbGVfb25seQ';
let count=0;
function fixture(options={}){
  const nodes=new Map(),events={},requests=[],writes=[];
  function node(selector){if(!nodes.has(selector))nodes.set(selector,{textContent:'',innerHTML:'',value:'',open:false,
    classList:{add(){},remove(){},toggle(){}},showModal(){this.open=true},close(){this.open=false},
    focus(){this.focused=true},select(){this.selected=true},remove(){nodes.delete(selector)}});return nodes.get(selector);}
  const device={id:'synthetic-id',name:'Synthetic client',group_name:'Family',owner_name:'owner',group_id:2,ip:'10.8.1.13',legacy:0,state:'active',
    tx:0,rx:0,handshake:0,up_bps:0,down_bps:0,manual_paused:0,expires_at:null,traffic_limit_bytes:null,...options.device};
  const state={devices:[device],groups:[],chart_info:{window_end:1793030400}};
  const nav=options.noClipboard?{}:{clipboard:{writeText:async text=>{if(options.clipboardDenied)throw Error('Permission denied');writes.push(text)}}};
  const context=vm.createContext({document:{querySelector:node,querySelectorAll:()=>[],addEventListener:(type,fn)=>events[type]=fn},navigator:nav,
    ClientAccess:Access,Date,setTimeout:()=>0,clearTimeout(){},encodeURIComponent,
    fetch:async(url,opts)=>{requests.push({url,opts});if(options.wait)await options.wait;
      return {ok:!options.httpError,json:async()=>({error:'Профиль недоступен'}),text:async()=>options.body??fakeLink+'\n'};}});
  vm.runInContext(source,context);context.testState=state;vm.runInContext("me={role:'super'};data=testState",context);
  const button={dataset:{copyConfig:device.id},disabled:false,textContent:'Копировать ссылку',id:''};
  return {node,nodes,device,state,requests,writes,context,button,events,
    click:()=>events.click({target:{closest:()=>button}}),table:()=>vm.runInContext('table(data.devices,true)',context)};
}
async function test(name,fn){await fn();count++;console.log('PASS '+name)}
(async()=>{
  await test('ready portal profiles have a copy button beside .vpn, never the secret in table markup',()=>{
    for(const state of ['active','paused','expired','limited']){
      const f=fixture({device:{state}}),html=f.table();assert.ok(html.includes('data-copy-config="synthetic-id"'));
      assert.ok(html.indexOf('data-download=')<html.indexOf('data-copy-config='));assert.ok(html.includes('Копировать ссылку'));assert.ok(!html.includes(fakeLink));
    }
    for(const device of [{legacy:1},{state:'pending'},{state:'error'},{state:'revoked'}])assert.ok(!fixture({device}).table().includes('data-copy-config='));
  });
  await test('copy reads the existing authenticated download once and copies the exact native link',async()=>{
    const f=fixture();await f.click();assert.deepEqual(f.writes,[fakeLink]);assert.equal(f.requests.length,1);
    const {url,opts}=f.requests[0];assert.equal(url,'/api/devices/synthetic-id/download');assert.equal(opts.method,undefined);
    assert.equal(opts.credentials,'same-origin');assert.equal(opts.cache,'no-store');assert.equal(opts.body,undefined);
    assert.ok(f.node('#toast').textContent.includes('скопирована'));assert.equal(f.button.disabled,false);assert.equal(f.button.textContent,'Копировать ссылку');
  });
  await test('copy of suspended or expired profiles never resumes, extends, replaces or reissues them',async()=>{
    for(const state of ['paused','expired','limited']){
      const f=fixture({device:{state,manual_paused:1,expires_at:1793000000,traffic_limit_bytes:1024}}),before=JSON.stringify(f.state);
      await f.click();assert.equal(JSON.stringify(f.state),before);assert.deepEqual(f.writes,[fakeLink]);
      assert.ok(f.requests.every(r=>r.url.endsWith('/download')&&r.opts.body===undefined));
    }
  });
  await test('forged, legacy and incomplete clicks never fetch or expose a profile',async()=>{
    for(const device of [{legacy:1},{state:'pending'},{state:'error'},{state:'revoked'}]){
      const f=fixture({device});await f.click();assert.equal(f.requests.length,0);assert.equal(f.writes.length,0);
    }
    const f=fixture();f.button.dataset.copyConfig='not-in-visible-scope';await f.click();assert.equal(f.requests.length,0);
  });
  await test('double click is bounded to one request and the original button is restored',async()=>{
    let release;const wait=new Promise(resolve=>release=resolve),f=fixture({wait});const first=f.click();
    assert.equal(f.button.disabled,true);await f.click();assert.equal(f.requests.length,1);release();await first;
    assert.equal(f.writes.length,1);assert.equal(f.button.disabled,false);assert.equal(f.button.textContent,'Копировать ссылку');
  });
  await test('HTTP failure does not copy a URL/error document and releases the button',async()=>{
    const f=fixture({httpError:true});await f.click();assert.equal(f.writes.length,0);assert.equal(f.button.disabled,false);
    assert.equal(f.node('#toast').textContent,'Профиль недоступен');assert.equal(f.node('#modal').open,false);
  });
  await test('invalid schemes, injected markup, whitespace and oversized payloads are rejected',async()=>{
    for(const body of ['https://example.invalid/config','<html>login</html>','vpn://abc?bad=1','vpn://bad payload','vpn://'+'a'.repeat(65536),'']){
      const f=fixture({body});await f.click();assert.equal(f.writes.length,0);assert.ok(f.node('#toast').textContent.includes('корректную ссылку'));
      assert.equal(f.button.disabled,false);assert.ok(!f.node('#modal-body').innerHTML.includes(body)||body==='');
    }
  });
  await test('clipboard denial or absence falls back to a selected readonly native link without new API calls',async()=>{
    for(const options of [{clipboardDenied:true},{noClipboard:true}]){
      const f=fixture(options);await f.click();assert.equal(f.requests.length,1);assert.equal(f.writes.length,0);assert.equal(f.node('#modal').open,true);
      const html=f.node('#modal-body').innerHTML;assert.ok(html.includes('readonly'));assert.ok(html.includes(fakeLink));assert.ok(html.includes('ключ доступа'));
      assert.equal(f.node('#profile-copy-value').selected,true);assert.equal(f.node('#profile-copy-value').focused,true);
      f.events.close({target:{id:'modal'}});assert.ok(!f.nodes.has('#profile-copy-value'));
    }
  });
  console.log(count+' configuration-copy tests passed');
})().catch(error=>{console.error(error);process.exit(1)});
