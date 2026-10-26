'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.join(__dirname,'static');
function context(lang='en'){
  const state=new Map([['dashboard-language',lang]]),ctx=vm.createContext({Intl,Date,console,localStorage:{getItem:k=>state.get(k),setItem:(k,v)=>state.set(k,v)}});
  for(const name of ['i18n-en.js','i18n.js','client-access.js','device-groups.js'])vm.runInContext(fs.readFileSync(path.join(root,name),'utf8'),ctx);
  return ctx;
}
test('English covers every translated source literal, including markup',()=>{
  const ctx=context();let count=0;
  for(const name of fs.readdirSync(root).filter(n=>n.endsWith('.js')&&!n.startsWith('i18n'))){
    const source=fs.readFileSync(path.join(root,name),'utf8');
    for(const match of source.matchAll(/\btr\(("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')\)/g)){
      const value=vm.runInNewContext(match[1]);const result=ctx.DashboardI18n.english(value);count++;
      assert.doesNotMatch(result,/[А-Яа-яЁё]/,name+': '+value);
    }
  }
  assert.ok(count>300);
});
test('Russian remains original; language preference persists and rejects unknowns',()=>{
  const ctx=context('ru');assert.equal(ctx.DashboardI18n.text('Сохранить'),'Сохранить');
  ctx.DashboardI18n.setLanguage('en',false);assert.equal(ctx.DashboardI18n.text('Сохранить'),'Save');assert.equal(ctx.DashboardI18n.locale(),'en-GB');
  assert.equal(ctx.localStorage.getItem('dashboard-language'),'en');assert.throws(()=>ctx.DashboardI18n.setLanguage('xx',false));
});
test('User names and escaping are not translated inside English rendering',()=>{
  const ctx=context();
  const html=ctx.DeviceGroups.html([{id:'synthetic',name:'Сохранить <b>',group_id:2,group_name:'Группа',owner_id:1,owner_name:'Администратор',state:'active',rx:2,tx:3}],
    [{id:2,name:'Группа',owner_id:1,owner_name:'Администратор',rx:2,tx:3}],{table:rows=>rows.map(d=>d.name.replace('<','&lt;')).join(''),bytes:n=>n+' B'});
  assert.ok(html.includes('Группа'));assert.ok(html.includes('Администратор'));assert.ok(html.includes('Сохранить &lt;b>'));assert.ok(html.includes('Administrator'));
});
test('English expiry keeps Moscow timezone and unlimited semantics',()=>{
  const ctx=context();assert.match(ctx.ClientAccess.format(1792922400),/MSK/);assert.equal(ctx.ClientAccess.parse(''),null);
  assert.match(ctx.ClientAccess.termCell({legacy:false,expires_at:null}),/No expiry/);
});
