'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const Import=require('./static/profile-import.js'),Choice=require('./static/client-choice.js');
globalThis.DeviceDownloads=require('./static/device-downloads.js');
const config='[Interface]\nPrivateKey = synthetic-key\nAddress = 10.8.1.13/32\n\n[Peer]\nPublicKey = synthetic-public\nEndpoint = 203.0.113.10:39265\n';
const native='vpn://'+('AbC_def-0123456789'.repeat(20));

test('native AWG sharing uses the exact .conf file and never an invented URL scheme',async()=>{
  let shares=0,payload;const nav={userAgent:'iPhone',canShare:()=>true,share:p=>{shares++;payload=p;return Promise.resolve()}};
  const plan=Import.prepareConf(config,nav);assert.equal(shares,0);assert.equal(plan.mode,'share');
  assert.equal(plan.file.name,'AmneziaWG.conf');assert.equal(await plan.file.text(),config);assert.equal(plan.uri,undefined);
  const pending=Import.launch(plan,nav,()=>assert.fail('No fake scheme'),()=>assert.fail('No download'));
  assert.equal(shares,1);assert.deepEqual(Object.keys(payload),['files']);assert.equal(await pending,'shared');
});
test('unsupported sharing downloads .conf on desktop and Android without targeting AmneziaVPN',async()=>{
  for(const userAgent of ['Windows NT 10.0','Android Chrome/130','iPhone']){
    const plan=Import.prepareConf(config,{userAgent,canShare:()=>false});assert.equal(plan.mode,'download');let count=0;
    await Import.launch(plan,{},()=>assert.fail('No Android vpn intent for AWG'),()=>count++);assert.equal(count,1);
  }
  for(const text of ['<html>error</html>','vpn://abc','[Interface]\nPrivateKey = test','[Interface]\n\u0000\n[Peer]\nKey = x','a'.repeat(65537)])
    assert.throws(()=>Import.conf(text));
});
function fixture(){
  class Node{
    constructor(dataset={}){this.dataset=dataset;this.hidden=true;this.open=true;this.children=[];}
    append(node){if(node.parent)node.parent.children=node.parent.children.filter(n=>n!==node);this.children.push(node);node.parent=this;}
    addEventListener(kind,fn){this[kind]=fn;}
    querySelectorAll(){return inputs;}
  }
  const nodes=Object.fromEntries(['client-choice','client-choice-primary','other-client','other-client-options'].map(id=>[id,new Node()]));
  const inputs=['vpn','awg'].map(value=>Object.assign(new Node(),{name:'client',value,checked:false}));
  const content=['vpn','awg'].map(client=>new Node({client}));
  const doc={querySelector:s=>nodes[s.slice(1)],querySelectorAll:()=>content};
  return {nodes,inputs,content,doc};
}
test('iPhone and desktop-style iPad get explicit app choice; other systems keep it collapsed',()=>{
  for(const nav of [{userAgent:'iPhone'},{userAgent:'Macintosh',platform:'MacIntel',maxTouchPoints:5},{userAgent:'Android 14'},{userAgent:'Windows NT 10.0'}]){
    const f=fixture(),values=[],controller=Choice.mount(f.doc,nav,value=>values.push(value)),ios=DeviceDownloads.detect(nav)==='ios';
    assert.equal(f.nodes['other-client'].hidden,ios);assert.equal(f.nodes['other-client'].open,false);
    assert.equal(f.nodes['client-choice'].parent,ios?f.nodes['client-choice-primary']:f.nodes['other-client-options']);
    assert.equal(f.inputs[0].checked,true);assert.equal(f.content[0].hidden,false);assert.equal(f.content[1].hidden,true);
    controller.select('awg');assert.equal(f.inputs[1].checked,true);assert.equal(f.content[0].hidden,true);assert.equal(f.content[1].hidden,false);
    controller.select('bad');assert.deepEqual(values,['vpn','awg']);
  }
});
test('changing ready-client app fetches each authorized format once, without enrolling or persisting keys',async()=>{
  class Element{constructor(){this.classList={add(){},remove(){}};this.disabled=false;this.click=()=>{};}}
  const nodes=new Map(),$=s=>{if(!nodes.has(s))nodes.set(s,new Element());return nodes.get(s);};
  const device={id:'synthetic-client',download_token:'synthetic-download-secret',ready:true,at:Date.now(),expires_at:null},
    storage=new Map([['join:demo',JSON.stringify(device)]]),calls=[],blobs=[],shares=[];let choose;
  const navigator={userAgent:'iPhone',canShare:()=>true,share:p=>{shares.push(p);return Promise.resolve()},clipboard:{writeText:async()=>{}}};
  const context={document:{querySelector:$,createElement:()=>new Element()},location:{pathname:'/j/demo',href:'https://local.test'},navigator,
    sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
    ClientChoice:{mount:(doc,nav,fn)=>{choose=fn;fn('vpn');}},ProfileImport:Import,ClientAccess:require('./static/client-access.js'),
    fetch:async(url,opts)=>{calls.push({url,opts});assert.ok(!url.includes(native)&&!url.includes('synthetic-download-secret'));
      if(url==='/api/downloads')return{ok:true,json:async()=>({version:'test',platforms:{}})};
      if(url==='/api/join/demo')return{ok:true,json:async()=>({name:'Synthetic group'})};
      assert.ok(url.startsWith('/api/receive/synthetic-client'));assert.equal(opts.headers.Authorization,'Bearer synthetic-download-secret');
      assert.equal(opts.cache,'no-store');return{ok:true,text:async()=>url.includes('format=conf')?config:native};},
    File,Blob,URL:{createObjectURL:b=>{blobs.push(b);return'blob:synthetic';},revokeObjectURL(){}},setTimeout:()=>0,crypto:globalThis.crypto};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'static/join.js'),'utf8'),context);
  const tick=()=>new Promise(setImmediate);await tick();await tick();
  choose('awg');await tick();await tick();assert.equal($('#import-awg').disabled,false);
  $('#import-awg').onclick();assert.equal(shares.length,1);assert.equal(shares[0].files[0].name,'AmneziaWG.conf');
  await $('#download-conf').onclick();assert.equal(await blobs[0].text(),config);
  choose('vpn');await tick();choose('awg');await tick();
  assert.equal(calls.filter(c=>c.url.startsWith('/api/receive/')).length,2);
  assert.ok(calls.every(c=>!c.opts?.method));assert.ok(![...storage.values()].some(v=>v.includes(native)||v.includes('[Interface]')));
});
test('official Apple RU option is visible to iPhone and non-Apple alternatives are details only',()=>{
  const html=fs.readFileSync(path.join(__dirname,'static/join.html'),'utf8');
  assert.match(html,/<a[^>]*data-device-os="ios"[^>]*href="https:\/\/apps.apple.com\/ru\/app\/amneziawg\/id6478942365"/);
  assert.ok(html.includes('Рекомендуется'));assert.ok(html.includes('value="vpn" checked'));
  for(const os of ['android','windows','macos','linux'])assert.match(html,new RegExp('<details class="download-more" data-device-extra="'+os+'">[\\s\\S]*?AmneziaWG'));
  assert.ok(html.indexOf('client-choice.js')<html.indexOf('join.js'));assert.ok(html.includes('id="download-conf"'));
  const admin=fs.readFileSync(path.join(__dirname,'static/admin.js'),'utf8');
  assert.ok(admin.includes('data-download-conf='));assert.ok(admin.includes('/download?format=conf'));
  assert.ok(admin.includes("format==='conf'?'AmneziaWG.conf'"));
});
