'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const QR=require('./static/profile-qr.js'),Import=require('./static/profile-import.js');
const vendor=fs.readFileSync(path.join(__dirname,'static/qrcodegen.js'),'utf8'),scope={};vm.runInNewContext(vendor,scope);
const encoder=scope.qrcodegen,native='vpn://'+('AbC_def-0123456789'.repeat(20)),conf='[Interface]\nPrivateKey = '+('A'.repeat(43))+'=\nAddress = 10.8.1.13/32\n\n[Peer]\nPublicKey = '+('B'.repeat(43))+'=\nEndpoint = 203.0.113.10:39265\nAllowedIPs = 0.0.0.0/0\n';
test('the local encoder is the exact MIT upstream asset, without networking or storage',()=>{
  assert.equal(crypto.createHash('sha256').update(vendor).digest('hex'),'6a1116192ed1dd67fa1bf31e77f5817103d71c23bbac24c382e698b7668bdd01');
  assert.ok(vendor.includes('Copyright (c) Project Nayuki. (MIT License)'));
  const source=fs.readFileSync(path.join(__dirname,'static/profile-qr.js'),'utf8');
  assert.doesNotMatch(source,/fetch\s*\(|XMLHttpRequest|localStorage|sessionStorage|sendBeacon|https:\/\//);
});
test('both native and conf generate deterministic square QR matrices',()=>{
  for(const [value,format] of [[native,'vpn'],[conf,'conf']]){
    const qr=QR.encode(value,format,encoder);assert.ok(qr.size>=21&&qr.size<=177);assert.equal((qr.size-21)%4,0);
    assert.ok(qr.modules.every(row=>row.length===qr.size&&row.every(v=>typeof v==='boolean')));
    assert.deepEqual(qr,QR.encode(value,format,encoder));
  }
});
test('medium byte capacity is bounded, never truncated, split or replaced with an invitation',()=>{
  const full='vpn://'+('a'.repeat(2325));assert.equal(QR.encode(full,'vpn',encoder).size,177);
  for(const value of [full+'a',conf+'# '+('я'.repeat(1200))])assert.throws(()=>QR.encode(value,value.startsWith('vpn:')?'vpn':'conf',encoder),/QR_TOO_LARGE/);
  for(const [value,format] of [['https://example.test/j/demo','vpn'],['vpn://a<svg>','vpn'],[native,'bad'],['<html>error</html>','conf'],[conf+'\0','conf'],[null,'vpn']])assert.throws(()=>QR.encode(value,format,encoder));
  assert.throws(()=>QR.encode(native,'vpn',{}),/QR_UNAVAILABLE/);
});
class Element{
  constructor(doc){this.ownerDocument=doc;this.children=[];this.attributes={};this.hidden=false;this.classList={add(){},remove(){}};}
  setAttribute(k,v){this.attributes[k]=String(v);}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=[...items];}
}
test('SVG has a four-module quiet zone, neutral high contrast and no raw key in markup',()=>{
  const doc={createElementNS:(ns,tag)=>Object.assign(new Element(doc),{ns,tag})},target=new Element(doc);
  const size=QR.render(target,native,'vpn','QR code for AmneziaVPN',encoder),svg=target.children[0];
  assert.equal(svg.attributes.viewBox,'0 0 '+(size+8)+' '+(size+8));assert.equal(svg.attributes.role,'img');
  assert.equal(svg.children[0].attributes.fill,'#ffffff');assert.equal(svg.children[1].attributes.fill,'#000000');
  for(const match of svg.children[1].attributes.d.matchAll(/M(\d+),(\d+)h1v1h-1z/g))assert.ok(+match[1]>=4&&+match[2]>=4&&+match[1]<size+4&&+match[2]<size+4);
  assert.ok(!JSON.stringify(svg.attributes).includes(native));assert.ok(!JSON.stringify(svg.children.map(n=>n.attributes)).includes(native));
  assert.throws(()=>QR.render(target,'vpn://'+('a'.repeat(2400)),'vpn','QR',encoder),/QR_TOO_LARGE/);assert.deepEqual(target.children,[]);
});
function fixture(options={}){
  const nodes=new Map(),get=s=>{if(!nodes.has(s))nodes.set(s,new Element());return nodes.get(s);};get('#profile-qr').hidden=true;
  const device={id:'synthetic-client',ready:true,at:Date.now(),download_token:'DEMO_NOT_A_CREDENTIAL'},storage=new Map([['join:demo',JSON.stringify(device)]]),calls=[],renders=[],events={};let choose,resolveConf;
  const context={document:{querySelector:get,createElement:()=>new Element()},location:{pathname:'/j/demo'},navigator:{userAgent:'Windows'},
    ClientChoice:{mount:(doc,nav,cb)=>{choose=cb;cb('vpn');}},ClientAccess:require('./static/client-access.js'),ProfileImport:Import,
    ProfileQR:{render:(target,text,format,label)=>{if(options.failure)throw Error(options.failure);renders.push({text,format,label});target.replaceChildren('synthetic-svg');}},
    addEventListener:(name,fn)=>events[name]=fn,sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},setTimeout:()=>0,
    fetch:async(url,opts)=>{calls.push({url,opts});assert.ok(!url.includes(native)&&!url.includes('DEMO_NOT_A_CREDENTIAL'));
      if(url==='/api/downloads')return{ok:true,json:async()=>({version:'test',platforms:{}})};
      if(url==='/api/join/demo')return{ok:true,json:async()=>({name:'Synthetic group'})};
      assert.ok(url.startsWith('/api/receive/synthetic-client'));assert.equal(opts.headers.Authorization,'Bearer DEMO_NOT_A_CREDENTIAL');assert.equal(opts.cache,'no-store');
      return{ok:true,text:()=>url.includes('format=conf')?(options.delayConf?new Promise(resolve=>{resolveConf=resolve;}):Promise.resolve(conf)):Promise.resolve(native)};},File,Blob};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'static/join.js'),'utf8'),context);
  return {get,calls,renders,storage,choose:v=>choose(v),resolve:()=>resolveConf(conf),events};
}
const tick=()=>new Promise(setImmediate);
test('QR is opt-in after ready and reuses existing authorized exports without another client',async()=>{
  const f=fixture();await tick();await tick();assert.equal(f.renders.length,0);assert.equal(f.get('#profile-qr').hidden,true);
  await f.get('#show-qr').onclick();assert.equal(f.renders[0].text,native);assert.equal(f.renders[0].format,'vpn');assert.equal(f.get('#show-qr').attributes['aria-expanded'],'true');
  f.choose('awg');await tick();assert.equal(f.renders.at(-1).text,conf);assert.equal(f.renders.at(-1).format,'conf');
  assert.equal(f.calls.filter(c=>c.url.startsWith('/api/receive/')).length,2);assert.ok(f.calls.every(c=>!c.opts?.method));
  assert.ok(![...f.storage.values()].some(v=>v.includes(native)||v.includes('[Interface]')));
});
test('closing QR and pagehide remove its SVG and collapse the controls',async()=>{
  const f=fixture();await tick();await f.get('#show-qr').onclick();f.get('#show-qr').onclick();
  assert.equal(f.get('#profile-qr').hidden,true);assert.deepEqual(f.get('#qr-image').children,[]);assert.equal(f.get('#show-qr').attributes['aria-expanded'],'false');
  await f.get('#show-qr').onclick();f.events.pagehide();assert.deepEqual(f.get('#qr-image').children,[]);assert.equal(f.get('#profile-qr').hidden,true);
});
test('a slow alternate export cannot reveal the wrong QR after app change or closing',async()=>{
  const f=fixture({delayConf:true});await tick();await f.get('#show-qr').onclick();f.choose('awg');await tick();
  assert.deepEqual(f.get('#qr-image').children,[]);f.choose('vpn');await tick();const count=f.renders.length;f.resolve();await tick();assert.equal(f.renders.length,count);assert.equal(f.renders.at(-1).format,'vpn');
  f.get('#show-qr').onclick();assert.deepEqual(f.get('#qr-image').children,[]);
});
test('QR failures never echo raw errors or block the original import and download buttons',async()=>{
  for(const failure of ['QR_TOO_LARGE','Secret profile '+native]){
    const f=fixture({failure});await tick();await f.get('#show-qr').onclick();assert.deepEqual(f.get('#qr-image').children,[]);
    assert.ok(!f.get('#qr-status').textContent.includes(native));assert.ok(f.get('#qr-status').textContent.includes(failure==='QR_TOO_LARGE'?'слишком большой':'Не удалось'));
    assert.equal(typeof f.get('#download').onclick,'function');assert.equal(typeof f.get('#import-app').onclick,'function');
  }
});
test('QR controls are inside the ready section and load only local scripts in dependency order',()=>{
  const html=fs.readFileSync(path.join(__dirname,'static/join.html'),'utf8');
  assert.ok(html.indexOf('id="show-qr"')>html.indexOf('id="ready-view"'));assert.ok(html.includes('id="profile-qr" class="profile-qr" hidden'));
  assert.ok(html.indexOf('/static/qrcodegen.js')<html.indexOf('/static/profile-qr.js'));assert.ok(html.indexOf('/static/profile-qr.js')<html.indexOf('/static/join.js'));
  assert.ok(html.includes('QR-код содержит ваш приватный ключ.'));assert.ok(!/https?:\/\/[^" ]*(?:qrserver|quickchart|chart.googleapis)/i.test(html));
});
