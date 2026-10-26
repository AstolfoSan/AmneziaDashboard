'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const Import=require('./static/profile-import.js');
const key='vpn://'+('AbC_def-0123456789'.repeat(20));
let count=0;const tests=[];function test(name,fn){tests.push([name,fn]);}
test('platform detects iPhone, Android and iPad desktop mode',()=>{
  assert.equal(Import.platform({userAgent:'iPhone OS 18'}),'ios');
  assert.equal(Import.platform({userAgent:'Macintosh',maxTouchPoints:5}),'ios');
  assert.equal(Import.platform({userAgent:'Macintosh',maxTouchPoints:0}),'desktop');
  assert.equal(Import.platform({userAgent:'Android 14 Chrome/130'}),'android');
});
test('rejects injected URLs, fragments, wrong protocol and excessive payloads',()=>{
  for(const value of ['https://example.test','javascript:alert(1)','vpn://','vpn://abc#Intent;end','vpn://abc?key=x','vpn://a\nb','vpn://'+'a'.repeat(65536)])assert.throws(()=>Import.key(value));
});
test('Android Chrome targets the official package and preserves payload case',()=>{
  const p=Import.prepare(key,{userAgent:'Android Chrome/130'});
  assert.equal(p.mode,'android');assert.equal(p.uri,'intent://'+key.slice(6)+'#Intent;scheme=vpn;package=org.amnezia.vpn;end');
  assert.ok(!p.uri.includes('https://'));assert.ok(!p.uri.includes('browser_fallback_url'));
});
test('Android non-Chromium uses the registered vpn scheme',()=>{
  assert.equal(Import.prepare(key,{userAgent:'Android Firefox/130'}).uri,key);
});
test('iOS file is byte-identical, .vpn named, and text/plain typed',async()=>{
  const p=Import.prepare(key,{userAgent:'iPhone',canShare:()=>true,share:()=>Promise.resolve()});
  assert.equal(p.mode,'share');assert.equal(p.file.name,'AmneziaVPN.vpn');assert.equal(p.file.type,'text/plain');assert.equal(await p.file.text(),key+'\n');assert.equal(p.uri,undefined);
});
test('share runs synchronously from click, never during prefetch, with files only',async()=>{
  let calls=0,payload;const nav={userAgent:'iPhone',canShare:()=>true,share:p=>{calls++;payload=p;return Promise.resolve()}};
  const p=Import.prepare(key,nav);assert.equal(calls,0);
  const promise=Import.launch(p,nav,()=>assert.fail('No iOS URL navigation'),()=>assert.fail('No download'));
  assert.equal(calls,1);assert.deepEqual(Object.keys(payload),['files']);assert.equal(await promise,'shared');
});
test('iOS unsupported file sharing falls back to download without fake deep link',async()=>{
  let downloaded=0;const nav={userAgent:'iPhone',canShare:()=>false,share:()=>assert.fail()};const p=Import.prepare(key,nav);
  assert.equal(p.mode,'download');await Import.launch(p,nav,()=>assert.fail(),()=>downloaded++);assert.equal(downloaded,1);
  const throwing=Import.prepare(key,{userAgent:'iPhone',share:()=>{},canShare:()=>{throw Error('Unsupported')}});assert.equal(throwing.mode,'download');
});
test('Android launch forwards only to its intended handler',async()=>{
  let destination;const p=Import.prepare(key,{userAgent:'Android Chrome/130'});
  assert.equal(await Import.launch(p,{},value=>destination=value,()=>assert.fail()),'opened');assert.equal(destination,p.uri);
});
test('cancellation is distinguishable from failure',async()=>{
  const error=Object.assign(Error('cancelled'),{name:'AbortError'}),nav={userAgent:'iPhone',canShare:()=>true,share:()=>Promise.reject(error)};
  const p=Import.prepare(key,nav);await assert.rejects(Import.launch(p,nav,()=>{},()=>{}),e=>e.name==='AbortError');
});
test('existing ready profile is prefetched once; import/copy/download never issue another peer',async()=>{
  const elements=new Map();class Element{constructor(){this.classList={add(){},remove(){}};this.textContent='';this.disabled=false;this.click=()=>{}}}
  const $=s=>{if(!elements.has(s))elements.set(s,new Element());return elements.get(s)};
  const device={id:'synthetic-client',download_token:'synthetic-download-secret',ready:true,at:Date.now(),expires_at:null};
  const storage=new Map([['join:preview-only',JSON.stringify(device)]]),calls=[],shares=[],copies=[],blobs=[];
  const navigator={userAgent:'iPhone',canShare:()=>true,share:p=>{shares.push(p);return Promise.resolve()},clipboard:{writeText:async text=>copies.push(text)}};
  const sandbox={document:{querySelector:$,createElement:()=>new Element()},location:{pathname:'/j/preview-only',href:'https://local.test'},navigator,
    sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
    fetch:async(url,opts)=>{calls.push({url,opts});assert.ok(!url.includes(key));if(url==='/api/downloads')return{ok:true,json:async()=>({version:'test',platforms:{}})};
      if(url.startsWith('/api/join/'))return{ok:true,json:async()=>({name:'Preview',default_access_days:30})};
      assert.equal(url,'/api/receive/synthetic-client');assert.equal(opts.headers.Authorization,'Bearer synthetic-download-secret');return{ok:true,text:async()=>key};},
    ProfileImport:Import,ClientAccess:require('./static/client-access.js'),File,Blob,URL:{createObjectURL:b=>{blobs.push(b);return 'blob:synthetic'},revokeObjectURL(){}},setTimeout:()=>0,crypto:globalThis.crypto};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'static/join.js'),'utf8'),sandbox);
  await new Promise(setImmediate);await new Promise(setImmediate);
  assert.equal($('#import-app').disabled,false);$('#import-app').onclick();await new Promise(setImmediate);
  assert.equal(shares.length,1);assert.equal(await shares[0].files[0].text(),key+'\n');
  await $('#copy').onclick();await $('#download').onclick();assert.equal(copies[0],key);assert.equal(await blobs[0].text(),key+'\n');
  assert.equal(calls.filter(c=>c.url.startsWith('/api/receive/')).length,1);assert.ok(calls.every(c=>!c.opts?.method));
  assert.ok(![...storage.values()].some(value=>value.includes(key)));
});
test('public page wires the import module and retains manual alternatives',()=>{
  const html=fs.readFileSync(path.join(__dirname,'static/join.html'),'utf8');
  assert.ok(html.indexOf('/static/profile-import.js')<html.indexOf('/static/join.js'));
  for(const id of ['import-app','import-hint','download','copy'])assert.ok(html.includes('id="'+id+'"'));
});
(async()=>{for(const [name,fn] of tests){await fn();count++;console.log('PASS '+name)}console.log(count+' profile import tests passed')})().catch(e=>{console.error(e);process.exitCode=1});
