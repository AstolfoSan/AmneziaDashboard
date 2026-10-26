'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const read = file => fs.readFileSync(path.join(__dirname,'static',file),'utf8');
let passed = 0;
function test(name, fn) { fn(); passed++; console.log('ok - ' + name); }
const pages = ['admin.html','join.html','download-unavailable.html'];
test('all pages have the exact name, local logo and favicon', () => {
  for (const page of pages) {
    const html=read(page);
    assert.match(html, /<title>AmneziaDashboard —/);
    assert.ok(html.includes('AmneziaDashboard'));
    assert.ok(!/контур|Контур|class="logo">к/.test(html));
    assert.ok(html.includes('rel="icon" type="image/svg+xml" href="/static/dashboard-icon.svg"'));
    assert.ok(html.includes('<img class="logo" src="/static/dashboard-icon.svg" alt=""'));
  }
});
test('original SVG uses the sampled multicolour palette without scripts or external assets', () => {
  const svg=read('dashboard-icon.svg');
  for (const colour of ['#7EBAD2','#9B8BC1','#F6A453']) assert.ok(svg.includes(colour));
  assert.ok(!/#66BCB2|#FAD67F|#F18928|linearGradient/i.test(svg));
  assert.ok(!/<script|<image|<foreignObject|\bon\w+=|\bhref=/.test(svg));
  assert.ok(svg.includes('viewBox="0 0 48 48"'));
});
test('orange primary and blue chart replace the old lime palette', () => {
  const css=read('style.css');
  assert.ok(css.includes('--accent:#F6A453'));
  assert.ok(css.includes('.traffic-line-rx{stroke:#7EBAD2}'));
  assert.ok(!/#b7f36b|#c3ef9e|#c6e5ba|#23342b/i.test(css));
});
test('main button, accent and muted text meet WCAG AA contrast', () => {
  const light = hex => {
    const rgb=hex.match(/[0-9a-f]{2}/gi).map(x=>parseInt(x,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);
    return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;
  };
  const contrast=(a,b)=>(Math.max(light(a),light(b))+.05)/(Math.min(light(a),light(b))+.05);
  const css=read('style.css'),tokens=Object.fromEntries([...css.matchAll(/--([\w-]+):\s*([^;}]+)/g)].map(m=>[m[1],m[2].trim()]));
  const hex=name=>tokens[name].slice(1);
  assert.ok(contrast(hex('accent'),hex('bg'))>=4.5);
  assert.ok(contrast(hex('text'),hex('surface'))>=4.5);
  assert.ok(contrast(hex('muted'),hex('card'))>=4.5);
  const mix=(a,b,t)=>a.match(/../g).map((v,i)=>Math.round(parseInt(v,16)*t+parseInt(b.slice(i*2,i*2+2),16)*(1-t)).toString(16).padStart(2,'0')).join('');
  assert.ok(contrast(hex('purple'),mix(hex('purple'),hex('surface'),.1))>=4.5);
  assert.ok(contrast(hex('blue'),mix(hex('blue'),hex('surface'),.12))>=4.5);
});
test('existing hierarchy and application scripts stay wired', () => {
  const html=read('admin.html'),css=read('style.css');
  for(const file of ['traffic-chart.js','device-groups.js','admin.js']) assert.ok(html.includes('/static/'+file));
  assert.ok(css.includes('.device-admin-head{padding:11px 16px;'));
  assert.ok(css.includes('.device-group-head{padding:10px 14px;'));
  assert.ok(read('join.html').includes('/static/join.js'));
});
test('official installer routes remain unchanged', () => {
  const html=read('join.html');
  for(const platform of ['android','ios','windows','macos','linux']) assert.ok(html.includes('href="/download/'+platform+'"'));
});
test('all literal colours are the three exact brand accents, neutral grayscale, or semantic indicators',()=>{
  const brand=new Set(['F6A453','7EBAD2','9B8BC1']);
  function base(colour){let v=colour.slice(1).toUpperCase();if(v.length===3||v.length===4)v=[...v].map(c=>c+c).join('');return v.slice(0,6)}
  function neutral(v){return v.slice(0,2)===v.slice(2,4)&&v.slice(2,4)===v.slice(4,6)}
  for(const file of ['style.css','dashboard-icon.svg']){
    for(const match of read(file).matchAll(/#[0-9a-f]{3,8}\b/gi)){
      const v=base(match[0]),semantic=file==='style.css'&&['FF9B96','55C58A'].includes(v);
      assert.ok(neutral(v)||brand.has(v)||semantic,'Unexpected decorative colour '+match[0]+' in '+file);
    }
  }
  const css=read('style.css').replace(/\/\*[\s\S]*?\*\//g,'');
  assert.ok(!/(?:rgba?|hsla?|hwb|oklch|lab)\s*\(/i.test(css),'Use approved tokens instead of new raw colour functions');
  assert.ok(!/(?<![\w-])(?:red|green|blue|purple|orange|yellow|teal|olive|lime|pink|cyan|magenta)(?![\w-])/i.test(css),'Use exact brand tokens instead of named colours');
});
test('green is confined to the recent-handshake indicator and inactive dots are neutral gray',()=>{
  const css=read('style.css');
  assert.equal((css.match(/#55c58a/gi)||[]).length,1);
  assert.ok(css.includes('.activity-dot.is-recent{background:#55c58a}'));
  assert.ok(/\.activity-dot\{[^}]*background:#888888/.test(css));
  assert.ok(css.includes('.badge.access-allowed{background:var(--blue-soft);color:var(--blue)}'));
});
console.log(passed+' branding tests passed');
