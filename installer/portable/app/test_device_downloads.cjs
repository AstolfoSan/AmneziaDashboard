'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const downloads=require('./static/device-downloads.js');
const ua=userAgent=>({userAgent});

test('Android is not misidentified as Linux',()=>{
  assert.equal(downloads.detect(ua('Mozilla/5.0 (Linux; Android 14; Example Phone) AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36')),'android');
  assert.equal(downloads.detect({userAgentData:{platform:'Android'}}),'android');
});
test('iPhone and iPad, including desktop-style iPadOS, use App Store',()=>{
  for(const userAgent of ['Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)','Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X)'])assert.equal(downloads.detect(ua(userAgent)),'ios');
  assert.equal(downloads.detect({userAgent:'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) Version/18.0 Safari/605.1.15',platform:'MacIntel',maxTouchPoints:5}),'ios');
  assert.equal(downloads.detect({platform:'MacIntel',maxTouchPoints:2}),'ios');
});
test('Windows, macOS and Linux are distinct, with Client Hints fallback',()=>{
  for(const [userAgent,result] of [['Mozilla/5.0 (Windows NT 10.0; Win64; x64)','windows'],['Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)','macos'],['Mozilla/5.0 (X11; Linux x86_64)','linux']])assert.equal(downloads.detect(ua(userAgent)),result);
  for(const [platform,result] of [['Windows','windows'],['macOS','macos'],['Linux','linux']])assert.equal(downloads.detect({userAgentData:{platform}}),result);
});
test('Unavailable hints and unknown/unsupported systems keep manual choice',()=>{
  const nav={userAgent:'Windows NT 10.0',get userAgentData(){throw Error('Blocked')}};
  assert.equal(downloads.detect(nav),'windows');
  for(const nav of [{},ua('unknown'),ua('Mozilla/5.0 (X11; CrOS x86_64)'),ua('Windows Phone 10.0; Android 4.2; IEMobile')])assert.equal(downloads.detect(nav),null);
});

function fixture(){
  class Node{
    constructor(dataset={}){this.dataset=dataset;this.children=[];this.hidden=true;this.open=true;this.classList={toggle:(key,value)=>{this.matched=value;}};}
    append(node){if(node.parent)node.parent.children=node.parent.children.filter(child=>child!==node);this.children.push(node);node.parent=this;}
  }
  const nodes=Object.fromEntries(['device-downloads','other-device-downloads','other-device-options','other-device-notes','device-download-caption','device-download-notes'].map(id=>[id,new Node()]));
  const links=['android','android','ios','windows','macos','linux'].map(os=>{const link=new Node({deviceOs:os});link.href='/download/'+os;nodes['device-downloads'].append(link);return link;});
  links[1].href='https://play.google.com/store/apps/details?id=org.amnezia.vpn';
  const extras=['android','ios'].map(os=>{const node=new Node({deviceExtra:os});nodes['device-download-notes'].append(node);return node;});
  const doc={querySelector:s=>nodes[s.slice(1)],querySelectorAll:s=>s==='[data-device-os]'?links:extras};
  return {doc,nodes,links,extras,primary:()=>nodes['device-downloads'].children.map(l=>l.dataset.deviceOs)};
}
test('Windows displays its single original link, with other systems collapsed',()=>{
  const f=fixture(),before=f.links.map(l=>l.href);assert.equal(downloads.mount(f.doc,ua('Windows NT 10.0')),'windows');
  assert.deepEqual(f.primary(),['windows']);assert.equal(f.nodes['other-device-downloads'].hidden,false);assert.equal(f.nodes['other-device-downloads'].open,false);
  assert.equal(f.nodes['other-device-options'].children.length,5);assert.deepEqual(f.links.map(l=>l.href),before);
});
test('Android retains both APK and Google Play, with Android-only help',()=>{
  const f=fixture();downloads.mount(f.doc,ua('Linux; Android 14'));
  assert.deepEqual(f.primary(),['android','android']);assert.deepEqual(f.nodes['device-download-notes'].children.map(n=>n.dataset.deviceExtra),['android']);
  assert.deepEqual(f.nodes['other-device-notes'].children.map(n=>n.dataset.deviceExtra),['ios']);
});
test('iPhone shows only its App Store link and relevant help',()=>{
  const f=fixture();downloads.mount(f.doc,ua('iPhone; CPU iPhone OS 18'));
  assert.deepEqual(f.primary(),['ios']);assert.deepEqual(f.nodes['device-download-notes'].children.map(n=>n.dataset.deviceExtra),['ios']);
});
test('Repeated mounting never clones links; unknown OS restores manual options',()=>{
  const f=fixture();for(let i=0;i<2;i++)downloads.mount(f.doc,ua('Windows NT 10.0'));
  downloads.mount(f.doc,{});assert.equal(f.primary().length,6);assert.equal(f.nodes['other-device-options'].children.length,0);
  assert.equal(new Set(f.nodes['device-downloads'].children).size,6);assert.equal(f.nodes['other-device-downloads'].hidden,true);
});
test('Static fallback keeps every download; detection does not touch profile issuance',()=>{
  const html=fs.readFileSync(path.join(__dirname,'static/join.html'),'utf8');
  assert.ok(html.indexOf('device-downloads.js')<html.indexOf('join.js'));
  for(const os of ['android','ios','windows','macos','linux'])assert.ok(html.includes('href="/download/'+os+'"'));
  assert.match(html,/<details id="other-device-downloads"[^>]* hidden>/);
  const source=fs.readFileSync(path.join(__dirname,'static/device-downloads.js'),'utf8');
  assert.doesNotMatch(source,/\b(?:fetch|getHighEntropyValues)\s*\(|\blocation\.(?:href|assign|replace)|download_token|\/api\/join/);
});
