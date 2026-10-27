'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),zlib=require('node:zlib'),fs=require('node:fs');
const QR=require('./static/profile-qr.js'),Import=require('./static/profile-import.js');
function native(config){const raw=Buffer.from(JSON.stringify(config)),length=Buffer.alloc(4);length.writeUInt32BE(raw.length);return 'vpn://'+Buffer.concat([length,zlib.deflateSync(raw)]).toString('base64url');}
test('native QR matches Amnezia 5.0.3 QDataStream framing and reconstructs the unchanged guest JSON',()=>{
  const config={description:'Synthetic phone · телефон',hostName:'203.0.113.10',containers:[{container:'amnezia-awg'}]};
  const original=native(config),value=QR.payload(original,'vpn'),frame=Buffer.from(value,'base64url');
  assert.ok(!value.startsWith('vpn://'));assert.equal(frame.readInt16BE(0),1984);assert.equal(frame[2],1);assert.equal(frame[3],0);
  assert.equal(frame.readUInt32BE(4),frame.length-8);const compressed=frame.subarray(8),raw=zlib.inflateSync(compressed.subarray(4));
  assert.equal(raw.length,compressed.readUInt32BE(0));assert.deepEqual(JSON.parse(raw),config);
  assert.equal(compressed.toString('base64url'),original.slice(6));
});
test('native QR rejects malformed Base64URL and invalid qCompress headers rather than showing scan 0/0 data',()=>{
  for(const value of ['a','AAAA','DEMO_PROFILE_NOT_FOR_CONNECTION','aaaaa','AAAAAAAAeAAB'])assert.throws(()=>QR.payload('vpn://'+value,'vpn'));
  const good=native({description:'Synthetic'});assert.throws(()=>QR.payload(good+'=','vpn'));
});
test('WG QR remains the exact wg-quick text; no unsupported name field or comment is inserted',()=>{
  const conf='[Interface]\nPrivateKey = '+('A'.repeat(43))+'=\n\n[Peer]\nPublicKey = '+('B'.repeat(43))+'=\nEndpoint = 203.0.113.10:39265\n';
  assert.equal(QR.payload(conf,'conf'),conf);assert.ok(!QR.payload(conf,'conf').includes('Name ='));
});
test('WG filenames preserve Unicode client names and neutralize path/control/reserved names',()=>{
  assert.equal(Import.fileName('Телефон Ирины'),'Телефон Ирины.conf');assert.equal(Import.fileName('Phone'),'Phone.conf');
  assert.equal(Import.fileName('../../a\\b\r\n'),'_.._a_b__.conf');
  for(const name of ['CON','nul.txt','COM1','LPT9'])assert.ok(Import.fileName(name).startsWith('AmneziaWG-'));
  for(const name of ['',null,'...','   '])assert.equal(Import.fileName(name),'AmneziaWG.conf');
  assert.equal(Array.from(Import.fileName('я'.repeat(100)).slice(0,-5)).length,64);
});
test('iPhone share uses the client-named file, preserves bytes and never shares during preparation',async()=>{
  const conf='[Interface]\nPrivateKey = synthetic\n\n[Peer]\nPublicKey = synthetic\n',name='Телефон Ирины';let shares=0;
  const nav={userAgent:'iPhone',canShare:()=>true,share:()=>{shares++;return Promise.resolve();}};
  const plan=Import.prepareConf(conf,nav,File,name);assert.equal(shares,0);assert.equal(plan.file.name,name+'.conf');assert.equal(await plan.file.text(),conf);
  await Import.launch(plan,nav,()=>assert.fail(),()=>assert.fail());assert.equal(shares,1);
});
test('both administrator and invitation download/share paths use current client names',()=>{
  const join=fs.readFileSync(__dirname+'/static/join.js','utf8'),admin=fs.readFileSync(__dirname+'/static/admin.js','utf8'),html=fs.readFileSync(__dirname+'/static/admin.html','utf8');
  assert.ok(join.includes('ProfileImport.fileName(device?.name)'));assert.ok(join.includes('globalThis.File,device?.name)'));
  assert.ok(admin.includes('ProfileImport.fileName(name)'));assert.ok(admin.includes('data.devices.find(d=>d.id===b.dataset.downloadConf)?.name'));
  assert.ok(html.indexOf('/static/profile-import.js')<html.indexOf('/static/admin.js'));
});
