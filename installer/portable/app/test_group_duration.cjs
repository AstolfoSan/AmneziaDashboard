'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const A=require('./static/client-access.js');let count=0;
function test(name,fn){fn();count++;console.log('ok - '+name);}
test('blank group duration means unlimited',()=>{for(const value of ['',null,undefined,'  '])assert.equal(A.parseDays(value),null)});
test('valid whole days are parsed and bounded',()=>{assert.equal(A.parseDays('30'),30);assert.equal(A.parseDays('3650'),3650);assert.equal(A.parseDays(' 1 '),1)});
test('invalid duration cannot reach the API',()=>{for(const value of ['0','-1','3651','1.5','1e2','bad','<img>',true])assert.throws(()=>A.parseDays(value))});
test('group field is optional and existing clients are explicitly unaffected',()=>{const html=A.groupForm(30);assert.ok(html.includes('value="30"'));assert.ok(html.includes('max="3650"'));assert.ok(!html.includes('required'));assert.ok(html.includes('Уже выданные клиенты'))});
test('group description distinguishes unlimited and limited issuance',()=>{assert.ok(A.groupText(null).includes('без срока'));assert.ok(A.groupText(30).includes('30 дн.'))});
test('group create/edit and public invitation use the shared policy UI',()=>{
  const read=f=>fs.readFileSync(path.join(__dirname,'static',f),'utf8');const admin=read('admin.js'),join=read('join.js'),html=read('join.html');
  assert.equal((admin.match(/ClientAccess.groupForm/g)||[]).length,2);
  assert.equal((admin.match(/ClientAccess.parseDays/g)||[]).length,2);
  assert.ok(admin.includes('ClientAccess.groupText(g.default_access_days)'));
  assert.ok(join.includes('ClientAccess.groupText(d.default_access_days)'));
  assert.ok(join.includes('device.expires_at=issued.expires_at'));
  assert.ok(html.indexOf('/static/client-access.js')<html.indexOf('/static/join.js'));
});
console.log(count+' group duration tests passed');
