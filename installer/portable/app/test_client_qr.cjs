'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const Access=require('./static/client-access.js'),QR=require('./static/profile-qr.js');
const vendor={};vm.runInNewContext(fs.readFileSync(__dirname+'/static/qrcodegen.js','utf8'),vendor);
const raw=Buffer.from(JSON.stringify({description:'Synthetic phone',containers:[]})),header=Buffer.alloc(4);header.writeUInt32BE(raw.length);
const native='vpn://'+Buffer.concat([header,require('node:zlib').deflateSync(raw)]).toString('base64url'),conf='[Interface]\nPrivateKey = '+('A'.repeat(43))+'=\nAddress = 10.8.1.13/32\n\n[Peer]\nPublicKey = '+('B'.repeat(43))+'=\nEndpoint = 203.0.113.10:39265\n';
const admin=fs.readFileSync(__dirname+'/static/admin.js','utf8').replace(/start\(\)\.catch\(\(\)=>\{\}\);\s*$/,'');
function fixture(options={}){
  const nodes=new Map(),events={},requests=[],renders=[],timers=new Set(),pageEvents={},copies=[];let releaseConf;
  function node(selector){if(!nodes.has(selector))nodes.set(selector,{textContent:'',innerHTML:'',value:'',open:false,children:[],
    classList:{add(){},remove(){},toggle(){}},showModal(){this.open=true},close(){this.open=false;events.close?.({target:{id:'modal'}})},
    replaceChildren(...items){this.children=items},remove(){nodes.delete(selector)}});return nodes.get(selector);}
  const device={id:'synthetic-id',name:'Synthetic phone',group_id:2,group_name:'Family',owner_name:'owner',ip:'10.8.1.13',legacy:0,state:'active',
    tx:500,rx:250,handshake:0,up_bps:0,down_bps:0,manual_paused:0,expires_at:1795000000,traffic_limit_bytes:4096,...options.device};
  const state={devices:[device],groups:[],chart_info:{window_end:1793030400}};
  const context=vm.createContext({document:{querySelector:node,querySelectorAll:()=>[],addEventListener:(type,fn)=>events[type]=fn},
    ClientAccess:Access,AbortController,Date,encodeURIComponent,navigator:{clipboard:{writeText:async value=>copies.push(value)}},addEventListener:(type,fn)=>pageEvents[type]=fn,
    setTimeout:(fn,delay)=>{const t={fn,delay};timers.add(t);return t},clearTimeout:t=>timers.delete(t),
    ProfileQR:{render:(image,value,format,label)=>{QR.encode(value,format,vendor.qrcodegen);renders.push({value,format,label});image.replaceChildren('synthetic-qr-geometry')}},
    fetch:async(url,opts)=>{
      requests.push({url,opts});assert.ok(!url.includes(native));
      if(options.hang)return new Promise((resolve,reject)=>opts.signal.addEventListener('abort',()=>reject(Error('AbortError'))));
      if(options.delayConf&&url.endsWith('?format=conf'))await new Promise(resolve=>releaseConf=resolve);
      return {ok:!options.httpError,text:async()=>options.body??(url.includes('format=conf')?conf:native+'\n'),json:async()=>({error:'Do not show '+native})};
    }});
  vm.runInContext(fs.readFileSync(__dirname+'/static/client-qr.js','utf8'),context);vm.runInContext(admin,context);
  context.state=state;context.role=options.role||'super';vm.runInContext('me={role};data=state',context);
  const button={id:'',dataset:{qr:device.id},disabled:false};
  return {context,node,nodes,device,state,button,events,pageEvents,requests,renders,timers,copies,
    click:()=>events.click({target:{closest:()=>button}}),table:()=>vm.runInContext('table(data.devices,true)',context),
    select:value=>{node('#client-qr-format').value=value;return node('#client-qr-format').onchange()},resolve:()=>releaseConf()};
}
const tick=()=>new Promise(setImmediate);
test('QR appears beside existing downloads for every exportable state, never legacy or incomplete clients',()=>{
  for(const state of ['active','paused','expired','limited'])assert.ok(fixture({device:{state}}).table().includes('data-qr="synthetic-id"'));
  for(const device of [{legacy:1},{state:'pending'},{state:'error'},{state:'revoked'}])assert.ok(!fixture({device}).table().includes('data-qr='));
});
test('QR reads both existing formats once per dialog using authenticated no-store GET, without changing policy or counters',async()=>{
  for(const role of ['super','admin']){
    const f=fixture({role,device:{state:'paused',manual_paused:1}}),before=JSON.stringify(f.state);await f.click();
    assert.equal(f.renders[0].value,native);assert.equal(f.node('#modal').open,true);assert.equal(f.node('#modal-cancel').hidden,true);
    await f.select('conf');assert.equal(f.renders.at(-1).value,conf);await f.select('vpn');await f.select('conf');
    assert.equal(f.requests.length,2);assert.equal(JSON.stringify(f.state),before);assert.ok(!f.table().includes(native));
    for(const request of f.requests){assert.ok(request.url.startsWith('/api/devices/synthetic-id/download'));assert.equal(request.opts.credentials,'same-origin');assert.equal(request.opts.cache,'no-store');assert.equal(request.opts.method,undefined);assert.equal(request.opts.body,undefined);}
    f.node('#modal').close();
  }
});
test('forged, out-of-scope, disabled, non-admin and protected legacy clicks perform no exports',async()=>{
  for(const options of [{device:{legacy:1}},{device:{state:'pending'}},{device:{state:'revoked'}},{device:{state:'error'}},{role:'guest'}]){
    const f=fixture(options);await f.click();assert.equal(f.requests.length,0);assert.equal(f.node('#modal').open,false);
  }
  for(const mode of ['out-of-scope','disabled']){const f=fixture();if(mode==='out-of-scope')f.button.dataset.qr='not-visible';else f.button.disabled=true;await f.click();assert.equal(f.requests.length,0);}
});
test('double click is bounded and close/Escape/pagehide clear the secret SVG and dialog cache',async()=>{
  const f=fixture();await f.click();await f.click();assert.equal(f.requests.length,1);
  f.node('#modal').close();assert.deepEqual(f.node('#client-qr-image').children,[]);assert.equal(f.node('#client-qr-format').onchange,null);
  await f.click();assert.equal(f.requests.length,2);f.pageEvents.pagehide();assert.deepEqual(f.node('#client-qr-image').children,[]);
});
test('a slow alternate export cannot redraw after app switch, close or another dialog',async()=>{
  const f=fixture({delayConf:true});await f.click();const pending=f.select('conf');await tick();assert.deepEqual(f.node('#client-qr-image').children,[]);
  await f.select('vpn');const count=f.renders.length;f.resolve();await pending;assert.equal(f.renders.length,count);assert.equal(f.renders.at(-1).format,'vpn');
  f.node('#modal').close();
  const g=fixture({delayConf:true});await g.click();const late=g.select('conf');await tick();vm.runInContext("dialog('Other dialog','',async()=>{})",g.context);
  assert.equal(g.node('#modal-cancel').hidden,false);g.resolve();await late;assert.deepEqual(g.node('#client-qr-image').children,[]);
});
test('denied or expired sessions display a safe message and never render a backend error as QR',async()=>{
  const f=fixture({httpError:true});await f.click();assert.equal(f.renders.length,0);assert.deepEqual(f.node('#client-qr-image').children,[]);
  assert.ok(f.node('#client-qr-status').textContent.includes('Проверьте доступ'));assert.ok(!f.node('#client-qr-status').textContent.includes(native));
  assert.ok(!f.node('#modal-body').innerHTML.includes(native));f.node('#modal').close();
});
test('invalid, injected and oversized profiles fail safely without truncation or secret disclosure',async()=>{
  for(const body of ['<html>login</html>','vpn://bad payload','vpn://'+('a'.repeat(2400)),'x'.repeat(65537)]){
    const f=fixture({body});await f.click();assert.equal(f.renders.length,0);assert.deepEqual(f.node('#client-qr-image').children,[]);
    assert.ok(!f.node('#client-qr-status').textContent.includes(body));f.node('#modal').close();
  }
  const f=fixture();await f.click();await f.select('invalid');assert.equal(f.requests.length,1);assert.deepEqual(f.node('#client-qr-image').children,[]);
});
test('stalled exports time out once, closing aborts pending requests, reopening can retry',async()=>{
  const f=fixture({hang:true}),first=f.click();await tick();assert.equal(f.requests.length,1);
  [...f.timers].find(t=>t.delay===15000).fn();await first;assert.ok(f.node('#client-qr-status').textContent.includes('Не удалось'));assert.equal(f.requests.length,1);
  f.node('#modal').close();const second=f.click();await tick();const signal=f.requests.at(-1).opts.signal;f.node('#modal').close();await second;
  assert.equal(signal.aborted,true);assert.equal(f.timers.size,0);assert.deepEqual(f.node('#client-qr-image').children,[]);
});
test('client names are text-only and the dialog makes unchanged access and private-key warnings explicit',async()=>{
  const name='<img src=x onerror=bad()>',f=fixture({device:{name,state:'expired'}});await f.click();
  assert.equal(f.node('#modal-title').textContent,'QR-код · '+name);assert.ok(!f.node('#modal-body').innerHTML.includes(name));
  assert.ok(f.node('#modal-body').innerHTML.includes('Срок, пауза, лимит трафика и ключи не изменяются'));
  assert.ok(f.node('#modal-body').innerHTML.includes('приватный ключ'));assert.equal(f.renders[0].label,'QR-код для AmneziaVPN');f.node('#modal').close();
});
test('admin loads the local encoder and renderer before its controller, with no QR network service',()=>{
  const html=fs.readFileSync(__dirname+'/static/admin.html','utf8');
  for(const file of ['qrcodegen.js','profile-qr.js','client-qr.js'])assert.ok(html.indexOf('/static/'+file)<html.indexOf('/static/admin.js'));
  const source=fs.readFileSync(__dirname+'/static/client-qr.js','utf8');
  assert.doesNotMatch(source,/localStorage|sessionStorage|sendBeacon|https:\/\//);assert.ok(source.includes('credentials:\'same-origin\''));
});
test('WG displays and copies the exact client name without inventing a config Name field',async()=>{
  const name='Телефон <iPhone>',f=fixture({device:{name}});await f.click();assert.equal(f.node('#client-qr-naming').hidden,true);
  await f.select('conf');assert.equal(f.node('#client-qr-naming').hidden,false);assert.equal(f.node('#client-qr-name').textContent,name);
  await f.node('#client-qr-copy-name').onclick();assert.deepEqual(f.copies,[name]);assert.equal(f.renders.at(-1).value,conf);
  assert.ok(!f.node('#modal-body').innerHTML.includes(name));f.node('#modal').close();assert.equal(f.node('#client-qr-name').textContent,'');assert.equal(f.node('#client-qr-copy-name').onclick,null);
});
