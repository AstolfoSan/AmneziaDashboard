import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch
import uuid
import zlib
if os.name=='nt': sys.modules['fcntl']=types.SimpleNamespace(LOCK_EX=2,flock=lambda *a:None)
from agent import Agent,fields,split_config
from panel import create_app

class Engine:
    def __init__(self):
        self.cfg='[Interface]\nAddress = 10.8.1.0/24\nPrivateKey = SERVER_PRIVATE\nListenPort = 39265\nHeaderProtectionKey = HEADER\nJc = 4\nH1 = 1\nRandomTrailers = on\n\n[Peer]\nPublicKey = LEGACY\nPresharedKey = ORIGINAL\nAllowedIPs = 10.8.1.1/32\n'
        self.rows=[{'clientId':'LEGACY','userData':{'clientName':'Old phone'}}];self.counter=0;self.fail=False;self.resets=0
    def read(self):return self.cfg,self.rows,json.dumps(self.rows).encode()
    def key(self,public=False,private=None):
        self.counter+=1;return base64.b64encode(bytes([self.counter])*32).decode()
    def wg(self,field):return {'SERVER_PUBLIC':[]} if field=='public-key' else {}
    def commit(self,old,raw,new,rows,pub,psk=None,ip=None,reset=False):
        assert self.cfg==old
        self.resets+=int(reset)
        self.cfg=new;self.rows=rows
        if self.fail:self.fail=False;raise RuntimeError('Interrupted after commit')

class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.engine=Engine();self.agent=Agent(Path(self.tmp.name),self.engine);self.uid=str(uuid.uuid4());self.original=self.engine.cfg
    def tearDown(self):self.tmp.cleanup()
    def test_create_export_revoke_preserves_legacy(self):
        result=self.agent.create(self.uid,'Анна');self.assertEqual(result['ip'],'10.8.1.2')
        cfg=self.engine.cfg;self.assertEqual(split_config(cfg)[0],split_config(self.original)[0]);self.assertEqual(fields(split_config(cfg)[1][0]),fields(split_config(self.original)[1][0]))
        key=self.agent.export(self.uid)['vpn'][6:];raw=base64.urlsafe_b64decode(key+'='*(-len(key)%4));doc=json.loads(zlib.decompress(raw[4:]));last=json.loads(doc['containers'][0]['awg']['last_config'])
        self.assertNotIn('password',doc);self.assertNotIn('userName',doc);self.assertIn('HeaderProtectionKey = HEADER',last['config']);self.assertEqual(doc['hostName'],'203.0.113.10');self.assertEqual(last['mtu'],'1280')
        self.agent.create(self.uid,'Duplicate');self.assertEqual(len(self.engine.rows),2)
        self.agent.revoke(self.uid);self.assertEqual(fields(split_config(self.engine.cfg)[1][0]),fields(split_config(self.original)[1][0]));self.assertEqual(self.engine.rows,[{'clientId':'LEGACY','userData':{'clientName':'Old phone'}}])
        with self.assertRaises(ValueError):self.agent.export(self.uid)
        with self.assertRaises(ValueError):self.agent.create(self.uid,'No resurrection')
    def test_interruption_is_idempotent(self):
        self.engine.fail=True
        with self.assertRaises(RuntimeError):self.agent.create(self.uid,'Retry')
        self.agent.create(self.uid,'Retry');self.assertEqual(len(self.engine.rows),2);self.assertEqual(len(split_config(self.engine.cfg)[1]),2)
    def test_cannot_mutate_legacy(self):
        with self.assertRaises(ValueError):self.agent.revoke('legacy_aaa')
        with self.assertRaises(ValueError):self.agent.revoke(str(uuid.uuid4()))
        self.assertEqual(self.original,self.engine.cfg)
    def test_large_allowed_range_is_bounded(self):
        self.engine.cfg=self.engine.cfg.replace('10.8.1.1/32','0.0.0.0/0')
        with self.assertRaises(ValueError):self.agent.create(self.uid,'No allocation')
    def test_rejects_commands_and_paths(self):
        with self.assertRaises(ValueError):self.agent.dispatch({'action':'shell','command':'true'})
        with self.assertRaises(ValueError):self.agent.create('../../etc/passwd','X')
    def test_pause_resume_preserves_keys_export_and_reserved_address(self):
        self.agent.create(self.uid,'Pause');original=self.agent.load(self.uid);cfg=self.engine.cfg;rows=json.dumps(self.engine.rows)
        result=self.agent.access({'id':self.uid,'paused':True});self.assertEqual(result['state'],'paused')
        paused=self.agent.load(self.uid)
        for field in ('ip','private','public','psk','vpn'):self.assertEqual(paused[field],original[field])
        self.assertNotEqual(paused['pause_psk'],original['psk']);self.assertIn('AllowedIPs = '+original['ip']+'/32',self.engine.cfg)
        self.assertEqual(self.agent.export(self.uid)['vpn'],original['vpn']);self.assertEqual(json.dumps(self.engine.rows),rows)
        self.assertEqual(self.agent.stats()['peers'][1]['state'],'paused')
        with self.assertRaises(ValueError):self.agent.create(self.uid,'Cannot bypass pause')
        self.agent.access({'id':self.uid,'paused':False});self.assertEqual(self.engine.cfg,cfg);self.assertEqual(self.engine.resets,2)
    def test_expiry_enforced_without_panel_and_extension_restores_same_config(self):
        self.agent.create(self.uid,'Expiry');cfg=self.engine.cfg;vpn=self.agent.export(self.uid)['vpn'];deadline=int(time.time())+60
        self.agent.access({'id':self.uid,'expires_at':deadline});self.assertEqual(self.engine.resets,0)
        with patch('agent.time.time',return_value=deadline+1):
            self.assertEqual(self.agent.enforce()['changed'],1);self.assertEqual(self.agent.load(self.uid)['status'],'expired')
            self.assertEqual(self.agent.enforce()['changed'],0)
            self.agent.access({'id':self.uid,'expires_at':deadline+3600});self.assertEqual(self.agent.load(self.uid)['status'],'active')
        self.assertEqual(self.engine.cfg,cfg);self.assertEqual(self.agent.export(self.uid)['vpn'],vpn)
    def test_manual_pause_is_not_undone_by_extension_or_clearing_deadline(self):
        self.agent.create(self.uid,'Manual');self.agent.access({'id':self.uid,'paused':True,'expires_at':int(time.time())-1})
        self.agent.access({'id':self.uid,'expires_at':None});self.assertEqual(self.agent.load(self.uid)['status'],'paused');self.assertEqual(self.engine.resets,1)
    def test_partial_pause_and_resume_are_repaired_idempotently(self):
        self.agent.create(self.uid,'Retry');cfg=self.engine.cfg
        self.engine.fail=True
        with self.assertRaises(RuntimeError):self.agent.access({'id':self.uid,'paused':True})
        self.assertTrue(self.agent.load(self.uid)['access_dirty']);self.agent.enforce();self.assertEqual(self.agent.load(self.uid)['status'],'paused')
        self.engine.fail=True
        with self.assertRaises(RuntimeError):self.agent.access({'id':self.uid,'paused':False})
        self.agent.enforce();self.assertEqual(self.engine.cfg,cfg);self.assertEqual(self.agent.load(self.uid)['status'],'active')
    def test_invalid_policy_and_legacy_protection(self):
        self.agent.create(self.uid,'Validate');cfg=self.engine.cfg
        for payload in ({'paused':1},{'expires_at':True},{'expires_at':'tomorrow'},{'expires_at':0},{'paused':False,'shell':'true'},{}):
            with self.assertRaises(ValueError):self.agent.access({'id':self.uid,**payload})
        with self.assertRaises(ValueError):self.agent.access({'id':str(uuid.uuid4()),'paused':True})
        self.assertEqual(self.engine.cfg,cfg)
    def test_revoked_profile_cannot_be_resumed_or_exported(self):
        self.agent.create(self.uid,'Revoked');self.agent.access({'id':self.uid,'paused':True});self.agent.revoke(self.uid)
        with self.assertRaises(ValueError):self.agent.access({'id':self.uid,'paused':False})
        with self.assertRaises(ValueError):self.agent.export(self.uid)
        self.assertEqual(self.agent.enforce()['changed'],0)
    def test_existing_unlimited_records_unchanged_by_enforcement(self):
        self.agent.create(self.uid,'Unlimited');path=Path(self.tmp.name)/(self.uid+'.enc');before=path.read_bytes();cfg=self.engine.cfg
        for _ in range(3):self.agent.dispatch({'action':'stats'})
        self.assertEqual(path.read_bytes(),before);self.assertEqual(self.engine.cfg,cfg);self.assertEqual(self.engine.resets,0)
    def test_outside_peer_changes_are_not_overwritten(self):
        self.agent.create(self.uid,'Outside');self.engine.cfg=self.engine.cfg.replace('AllowedIPs = 10.8.1.2/32','AllowedIPs = 10.8.1.99/32');cfg=self.engine.cfg
        with self.assertRaises(ValueError):self.agent.access({'id':self.uid,'paused':True})
        self.assertEqual(self.engine.cfg,cfg)
    def test_indented_psk_is_disabled_persistently_not_just_in_memory(self):
        self.agent.create(self.uid,'Whitespace');record=self.agent.load(self.uid)
        self.engine.cfg=self.engine.cfg.replace('PresharedKey = '+record['psk'],'  PresharedKey = '+record['psk'])
        self.agent.access({'id':self.uid,'paused':True})
        block=next(p for p in split_config(self.engine.cfg)[1] if fields(p).get('PublicKey')==record['public'])
        self.assertEqual(fields(block)['PresharedKey'],self.agent.load(self.uid)['pause_psk'])
    def test_limited_creation_persists_deadline_before_enabling_peer(self):
        deadline=int(time.time())+86400;commit=self.engine.commit
        def guarded(*args,**kw):
            self.assertEqual(self.agent.load(self.uid)['expires_at'],deadline);return commit(*args,**kw)
        self.engine.commit=guarded
        result=self.agent.dispatch({'action':'create_limited','id':self.uid,'name':'Limited','expires_at':deadline})
        self.assertEqual(result['expires_at'],deadline);self.assertEqual(result['state'],'active')
        vpn=self.agent.export(self.uid)['vpn'];self.agent.create(self.uid,'Retry',deadline+86400)
        self.assertEqual(self.agent.load(self.uid)['expires_at'],deadline);self.assertEqual(self.agent.export(self.uid)['vpn'],vpn)
    def test_limited_creation_retry_never_extends_deadline(self):
        deadline=int(time.time())+60;self.engine.fail=True
        with self.assertRaises(RuntimeError):self.agent.create(self.uid,'Retry limited',deadline)
        result=self.agent.create(self.uid,'Retry limited',deadline+3600)
        self.assertEqual(result['expires_at'],deadline);self.assertEqual(len(self.engine.rows),2)
    def test_already_expired_limited_creation_never_installs_original_psk(self):
        result=self.agent.create(self.uid,'Already expired',int(time.time())-60);record=self.agent.load(self.uid)
        self.assertEqual(result['state'],'expired');self.assertFalse(record['active'])
        block=next(p for p in split_config(self.engine.cfg)[1] if fields(p)['PublicKey']==record['public'])
        self.assertEqual(fields(block)['PresharedKey'],record['pause_psk']);self.assertNotEqual(record['pause_psk'],record['psk'])
        self.assertEqual(self.agent.export(self.uid)['vpn'],record['vpn'])
    def test_pending_limited_retry_after_deadline_is_disabled(self):
        deadline=int(time.time())+60;self.engine.fail=True
        with self.assertRaises(RuntimeError):self.agent.create(self.uid,'Late retry',deadline)
        with patch('agent.time.time',return_value=deadline+1):result=self.agent.create(self.uid,'Late retry',deadline+3600)
        self.assertEqual(result['state'],'expired');self.assertEqual(result['expires_at'],deadline);self.assertEqual(self.engine.resets,1)
    def test_limited_creation_requires_a_valid_deadline(self):
        for value in (None,True,'30',0,4133970000):
            with self.assertRaises(ValueError):self.agent.dispatch({'action':'create_limited','id':self.uid,'name':'Invalid','expires_at':value})
        self.assertIsNone(self.agent.load(self.uid));self.assertEqual(self.original,self.engine.cfg)
    def test_partial_limited_creation_expires_even_without_retry(self):
        deadline=int(time.time())+60;self.engine.fail=True
        with self.assertRaises(RuntimeError):self.agent.create(self.uid,'No retry',deadline)
        with patch('agent.time.time',return_value=deadline+1):self.assertEqual(self.agent.enforce()['changed'],1)
        record=self.agent.load(self.uid);self.assertEqual(record['status'],'expired');self.assertEqual(self.engine.resets,1)
        block=next(p for p in split_config(self.engine.cfg)[1] if fields(p)['PublicKey']==record['public'])
        self.assertEqual(fields(block)['PresharedKey'],record['pause_psk'])

class RPC:
    def __init__(self):self.rows={};self.legacy={'id':'legacy_original','name':'Original','ip':'10.8.1.1','legacy':True,'rx':10000,'tx':20000,'handshake':0,'active':True};self.now=int(time.time());self.calls=[];self.requests=[];self.on_create=None;self.fail_revoke=False;self.fail_access=False;self.reject_limited=False
    def __call__(self,p):
        uid=p.get('id');action=p['action']
        self.calls.append(action)
        self.requests.append(dict(p))
        if action=='stats':
            for row in self.rows.values():
                if row.get('state')=='revoked':continue
                row['state']='paused' if row.get('manual_paused') else 'expired' if row.get('expires_at') is not None and row['expires_at']<=self.now else 'active'
                row['active']=row['state']=='active'
            return {'peers':[self.legacy]+list(self.rows.values()),'sampled_at':self.now}
        if action in {'create','create_limited'}:
            if action=='create_limited' and self.reject_limited:raise ValueError('Unsupported operation')
            self.rows.setdefault(uid,{'id':uid,'name':p['name'],'ip':'10.8.1.2','legacy':False,'rx':0,'tx':0,'handshake':0,'active':True,'state':'active','expires_at':p.get('expires_at')})
            if self.on_create:self.on_create(uid)
            return self.rows[uid]
        if action=='export':return {'vpn':'vpn://TEST_NOT_A_REAL_KEY'}
        if action=='access':
            if self.fail_access:raise RuntimeError('Worker unavailable')
            row=self.rows[uid];row['manual_paused']=p.get('paused',row.get('manual_paused',False));row['expires_at']=p.get('expires_at',row.get('expires_at'))
            row['state']='paused' if row['manual_paused'] else 'expired' if row['expires_at'] is not None and row['expires_at']<=self.now else 'active'
            row['active']=row['state']=='active';return {k:row[k] for k in ('id','state','manual_paused','expires_at')}
        if action=='revoke':
            if self.fail_revoke:raise RuntimeError('Worker unavailable')
            self.rows[uid]['active']=False;self.rows[uid]['state']='revoked';return {'ok':True}

class PanelTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.rpc=RPC();self.app=create_app({'DATA_DIR':self.tmp.name,'COLLECTOR':False,'COOKIE_SECURE':False,'PUBLIC_ORIGIN':'http://localhost','TESTING':True},self.rpc);self.client=self.app.test_client();self.headers={'Origin':'http://localhost'}
        password=(Path(self.tmp.name)/'bootstrap-password.txt').read_text().strip();self.assertEqual(self.client.post('/api/login',json={'username':'owner','password':password},headers=self.headers).status_code,200);self.csrf=self.client.get('/api/session').json['csrf'];self.headers['X-CSRF-Token']=self.csrf
    def tearDown(self):self.tmp.cleanup()
    def post(self,url,body):return self.client.post(url,json=body,headers=self.headers)
    def group(self):
        gid=self.post('/api/groups',{'name':'Friends','limit':2}).json['id'];row=next(g for g in self.client.get('/api/dashboard').json['groups'] if g['id']==gid);return gid,row['link'].split('/j/')[1]
    def delete_group(self,gid):return self.client.delete('/api/groups/'+str(gid),json={},headers=self.headers)
    def test_pages_headers_and_auth(self):
        for path in ['/','/admin','/static/admin.js','/static/style.css']:
            r=self.client.get(path);self.assertEqual(r.status_code,200);self.assertIn("script-src 'self'",r.headers['Content-Security-Policy']);r.close()
        self.assertEqual(self.app.test_client().get('/api/dashboard').status_code,401)
        self.assertEqual(self.client.post('/api/groups',json={'name':'x'},headers={'Origin':'https://evil.test','X-CSRF-Token':self.csrf}).status_code,403)
        self.assertEqual(self.client.post('/api/groups',json={'name':'x'},headers={'Origin':'http://localhost'}).status_code,403)
    def test_legacy_read_only_and_counter_reset(self):
        self.app.extensions['panel_sync']();d=self.client.get('/api/dashboard').json['devices'][0];self.assertEqual(d['rx'],0)
        self.rpc.now+=15;self.rpc.legacy['rx']+=150;self.rpc.legacy['tx']+=300;self.app.extensions['panel_sync']();d=self.client.get('/api/dashboard').json['devices'][0];self.assertEqual(d['rx'],150);self.assertEqual(d['up_bps'],10)
        self.rpc.now+=15;self.rpc.legacy['rx']=30;self.app.extensions['panel_sync']();d=self.client.get('/api/dashboard').json['devices'][0];self.assertEqual(d['rx'],180)
        self.assertEqual(self.post('/api/devices/legacy_original/revoke',{}).status_code,403);self.assertEqual(self.client.get('/api/devices/legacy_original/download').status_code,409)
        self.client.patch('/api/groups/1',json={'name':'Renamed'},headers=self.headers);self.app.extensions['panel_sync']();self.assertEqual(self.client.get('/api/dashboard').json['meta']['sync_error'],'')
    def test_invite_idempotency_and_quota(self):
        gid,token=self.group();guest=self.app.test_client();payload={'id':str(uuid.uuid4()),'name':'Phone','download_token':'x'*32};h={'Origin':'http://localhost'}
        for _ in range(2):self.assertEqual(guest.post('/api/join/'+token,json=payload,headers=h).status_code,200)
        self.assertEqual(len(self.rpc.rows),1);self.assertEqual(guest.get('/api/receive/'+payload['id']).status_code,404)
        self.assertEqual(guest.get('/api/receive/'+payload['id'],headers={'Authorization':'Bearer '+'x'*32}).status_code,200)
        self.assertEqual(guest.get('/api/receive/'+payload['id'],headers={'Authorization':'Bearer bad'}).status_code,404)
        payload2=dict(payload,id=str(uuid.uuid4()));self.assertEqual(guest.post('/api/join/'+token,json=payload2,headers=h).status_code,200)
        payload3=dict(payload,id=str(uuid.uuid4()));self.assertEqual(guest.post('/api/join/'+token,json=payload3,headers=h).status_code,409)
        self.assertEqual(self.post('/api/devices/'+payload['id']+'/revoke',{}).status_code,200)
    def test_admin_isolation(self):
        gid,token=self.group();pw='ordinary-admin-password';user=self.post('/api/users',{'username':'helper','password':pw}).json
        guest=self.app.test_client();h={'Origin':'http://localhost'};self.assertEqual(guest.post('/api/login',json={'username':'helper','password':pw},headers=h).status_code,200);h['X-CSRF-Token']=guest.get('/api/session').json['csrf']
        self.assertEqual(guest.get('/api/dashboard').json['groups'],[]);self.assertEqual(guest.get('/api/users').status_code,403)
        self.assertEqual(guest.post('/api/devices',json={'name':'Spy','group_id':gid},headers=h).status_code,404)
        self.assertEqual(guest.patch('/api/groups/'+str(gid),json={'enabled':False},headers=h).status_code,404)
        self.assertEqual(guest.post('/api/groups',json={'name':'Escalate','owner_id':1},headers=h).status_code,403)
    def test_disable_admin_does_not_revoke_profiles(self):
        u=self.post('/api/users',{'username':'helper','password':'ordinary-admin-password'}).json['id'];self.assertEqual(self.client.patch('/api/users/'+str(u),json={'enabled':False},headers=self.headers).status_code,200);self.assertEqual(self.rpc.rows,{})
        self.assertEqual(self.client.patch('/api/users/1',json={'enabled':False},headers=self.headers).status_code,400)
    def test_paused_group_blocks_new_only(self):
        gid,token=self.group();d=self.post('/api/devices',{'group_id':gid,'name':'One'}).json;self.client.patch('/api/groups/'+str(gid),json={'enabled':False},headers=self.headers)
        self.assertEqual(self.post('/api/devices',{'group_id':gid,'name':'Two'}).status_code,403);self.assertEqual(self.client.get('/api/devices/'+d['id']+'/download').status_code,200)
    def test_delete_admin_requires_closed_account_and_is_idempotent(self):
        uid=self.post('/api/users',{'username':'helper','password':'ordinary-admin-password'}).json['id'];url='/api/users/'+str(uid)
        other=self.app.test_client();other.post('/api/login',json={'username':'helper','password':'ordinary-admin-password'},headers={'Origin':'http://localhost'})
        self.assertEqual(self.client.delete(url,json={},headers=self.headers).status_code,409)
        self.client.patch(url,json={'enabled':False},headers=self.headers)
        calls=list(self.rpc.calls)
        for _ in range(2):self.assertEqual(self.client.delete(url,json={},headers=self.headers).json,{'ok':True,'deleted':True})
        self.assertNotIn(uid,[u['id'] for u in self.client.get('/api/users').json['users']])
        self.assertEqual(other.get('/api/session').status_code,401)
        self.assertEqual(other.post('/api/login',json={'username':'helper','password':'ordinary-admin-password'},headers={'Origin':'http://localhost'}).status_code,401)
        self.assertEqual(self.client.patch(url,json={'enabled':True},headers=self.headers).status_code,404)
        self.assertEqual(self.post('/api/users',{'username':'helper','password':'another-test-password'}).status_code,409)
        self.assertEqual(self.rpc.calls,calls)
        events=self.client.get('/api/audit').json['events'];self.assertEqual(sum(e['event']=='admin.deleted' for e in events),1)
        with self.app.extensions['panel_db']() as c:
            row=c.execute('SELECT enabled,deleted_at FROM users WHERE id=?',(uid,)).fetchone();self.assertEqual(row['enabled'],0);self.assertIsNotNone(row['deleted_at'])
    def test_delete_owner_self_and_missing_admin_are_protected(self):
        self.assertEqual(self.client.delete('/api/users/1',json={},headers=self.headers).status_code,403)
        self.assertEqual(self.client.delete('/api/users/999',json={},headers=self.headers).status_code,404)
        uid=self.post('/api/users',{'username':'second-super','password':'ordinary-admin-password','role':'super'}).json['id']
        other=self.app.test_client();h={'Origin':'http://localhost'};other.post('/api/login',json={'username':'second-super','password':'ordinary-admin-password'},headers=h);h['X-CSRF-Token']=other.get('/api/session').json['csrf']
        self.assertEqual(other.delete('/api/users/'+str(uid),json={},headers=h).status_code,403)
    def test_delete_admin_is_super_only_and_csrf_origin_checked(self):
        uid=self.post('/api/users',{'username':'target','password':'ordinary-admin-password'}).json['id'];url='/api/users/'+str(uid)
        self.client.patch(url,json={'enabled':False},headers=self.headers)
        self.post('/api/users',{'username':'ordinary','password':'ordinary-admin-password'})
        other=self.app.test_client();h={'Origin':'http://localhost'};other.post('/api/login',json={'username':'ordinary','password':'ordinary-admin-password'},headers=h);h['X-CSRF-Token']=other.get('/api/session').json['csrf']
        self.assertEqual(other.delete(url,json={},headers=h).status_code,403)
        self.assertEqual(self.client.delete(url,json={},headers={'Origin':'http://localhost'}).status_code,403)
        self.assertEqual(self.client.delete(url,json={},headers={**self.headers,'Origin':'https://evil.test'}).status_code,403)
        self.assertEqual(self.app.test_client().delete(url,json={},headers=self.headers).status_code,401)
        self.assertIn(uid,[u['id'] for u in self.client.get('/api/users').json['users']])
    def test_delete_admin_never_cascades_groups_or_clients(self):
        uid=self.post('/api/users',{'username':'helper','password':'ordinary-admin-password'}).json['id'];url='/api/users/'+str(uid)
        gid=self.post('/api/groups',{'name':'Helper group','owner_id':uid}).json['id']
        device=self.post('/api/devices',{'name':'Keep VPN','group_id':gid}).json
        self.client.patch(url,json={'enabled':False},headers=self.headers);calls=list(self.rpc.calls)
        self.assertEqual(self.client.delete(url,json={},headers=self.headers).status_code,409)
        self.assertTrue(self.rpc.rows[device['id']]['active']);self.assertEqual(self.rpc.calls,calls)
        self.assertEqual(self.client.get('/api/devices/'+device['id']+'/download').status_code,200)
    def test_empty_groups_must_be_removed_and_archived_history_is_preserved(self):
        uid=self.post('/api/users',{'username':'helper','password':'ordinary-admin-password'}).json['id'];url='/api/users/'+str(uid)
        gid=self.post('/api/groups',{'name':'History','owner_id':uid}).json['id'];device=self.post('/api/devices',{'name':'Old VPN','group_id':gid}).json
        self.rpc.rows[device['id']].update(rx=123,tx=456);self.app.extensions['panel_sync']();self.post('/api/devices/'+device['id']+'/revoke',{})
        self.client.patch(url,json={'enabled':False},headers=self.headers)
        self.assertEqual(self.client.delete(url,json={},headers=self.headers).status_code,409)
        self.assertEqual(self.delete_group(gid).status_code,200);before=self.client.get('/api/dashboard').json
        with self.app.extensions['panel_db']() as c:c.execute('INSERT INTO audit(at,user_id,event,detail) VALUES(?,?,?,?)',(int(time.time()),uid,'test.history','Historical actor'))
        self.assertEqual(self.client.delete(url,json={},headers=self.headers).status_code,200)
        after=self.client.get('/api/dashboard').json
        self.assertEqual(after['summary'],before['summary']);self.assertEqual(after['chart'],before['chart'])
        self.assertTrue(any(e['event']=='test.history' and e['username']=='helper' for e in self.client.get('/api/audit').json['events']))
        with self.app.extensions['panel_db']() as c:
            self.assertEqual(tuple(c.execute('SELECT rx,tx FROM devices WHERE id=?',(device['id'],)).fetchone()),(123,456))
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
    def test_admin_delete_defensively_blocks_clients_in_already_archived_group(self):
        uid=self.post('/api/users',{'username':'helper','password':'ordinary-admin-password'}).json['id'];gid=self.post('/api/groups',{'name':'Inconsistent import','owner_id':uid}).json['id']
        with self.app.extensions['panel_db']() as c:
            c.execute('UPDATE users SET enabled=0 WHERE id=?',(uid,));c.execute('UPDATE groups_ SET deleted_at=? WHERE id=?',(int(time.time()),gid))
            c.execute('INSERT INTO devices(id,group_id,name,state,created) VALUES(?,?,?,?,?)',(str(uuid.uuid4()),gid,'Pending imported peer','pending',int(time.time())))
        self.assertEqual(self.client.delete('/api/users/'+str(uid),json={},headers=self.headers).status_code,409)
    def test_user_archive_schema_upgrade_is_idempotent_and_does_not_hide_existing_users(self):
        self.post('/api/users',{'username':'helper','password':'ordinary-admin-password'})
        with self.app.extensions['panel_db']() as c:
            c.execute('ALTER TABLE users DROP COLUMN deleted_at')
            before=[tuple(r) for r in c.execute('SELECT * FROM users ORDER BY id')]
        for _ in range(2):create_app({'DATA_DIR':self.tmp.name,'COLLECTOR':False},self.rpc)
        with self.app.extensions['panel_db']() as c:
            self.assertEqual(before,[tuple(r) for r in c.execute('SELECT id,username,password,role,enabled,max_devices FROM users ORDER BY id')])
            self.assertEqual(c.execute('SELECT count(*) FROM users WHERE deleted_at IS NOT NULL').fetchone()[0],0)
        self.assertEqual(len(self.client.get('/api/users').json['users']),2)
    def test_invalid_body_is_rejected(self):
        self.assertEqual(self.client.post('/api/groups',json=[],headers=self.headers).status_code,400)
        self.assertEqual(self.post('/api/groups',{'name':'X','limit':'not a number'}).status_code,400)
    def test_rate_limit_survives_collection(self):
        gid,token=self.group();h={'Origin':'http://localhost'};guest=self.app.test_client();payload={'id':str(uuid.uuid4()),'name':'Phone','download_token':'x'*32}
        for _ in range(6):self.assertEqual(guest.post('/api/join/'+token,json=payload,headers=h).status_code,200)
        self.app.extensions['panel_sync']();self.assertEqual(guest.post('/api/join/'+token,json=payload,headers=h).status_code,429)
    def test_revoke_removes_row_preserves_history_and_is_idempotent(self):
        gid,token=self.group();d=self.post('/api/devices',{'group_id':gid,'name':'Delete me'}).json;uid=d['id']
        self.rpc.rows[uid].update(rx=100,tx=250);self.app.extensions['panel_sync']()
        self.assertEqual(self.post('/api/devices/'+uid+'/revoke',{}).json,{'ok':True,'deleted':True})
        dash=self.client.get('/api/dashboard').json
        self.assertNotIn(uid,[d['id'] for d in dash['devices']]);self.assertEqual(dash['summary'],{'rx':100,'tx':250})
        gr=next(g for g in dash['groups'] if g['id']==gid);self.assertEqual((gr['rx'],gr['tx']),(100,250));self.assertTrue(dash['chart'])
        self.assertEqual(self.client.get('/api/devices/'+uid+'/download').status_code,404)
        self.assertEqual(self.client.patch('/api/devices/'+uid,json={'group_id':1},headers=self.headers).status_code,404)
        self.assertEqual(self.post('/api/devices/'+uid+'/revoke',{}).status_code,200);self.assertEqual(self.rpc.calls.count('revoke'),1)
        self.assertTrue(any(e['event']=='device.revoked' and 'Delete me' in e['detail'] for e in self.client.get('/api/audit').json['events']))
        self.rpc.rows[uid].update(active=True,rx=9999,tx=9999);self.rpc.now+=15;self.app.extensions['panel_sync']()
        dash=self.client.get('/api/dashboard').json;self.assertNotIn(uid,[d['id'] for d in dash['devices']]);self.assertEqual(dash['summary'],{'rx':100,'tx':250})
    def test_revoked_public_download_and_recreate_are_denied(self):
        gid,token=self.group();payload={'id':str(uuid.uuid4()),'name':'Phone','download_token':'x'*32};guest=self.app.test_client();h={'Origin':'http://localhost'}
        self.assertEqual(guest.post('/api/join/'+token,json=payload,headers=h).status_code,200);self.post('/api/devices/'+payload['id']+'/revoke',{})
        self.assertEqual(guest.get('/api/receive/'+payload['id'],headers={'Authorization':'Bearer '+'x'*32}).status_code,404)
        self.assertEqual(guest.post('/api/join/'+token,json=payload,headers=h).status_code,409)
    def test_failed_revoke_keeps_client_visible(self):
        gid,token=self.group();d=self.post('/api/devices',{'group_id':gid,'name':'Keep me'}).json;self.rpc.fail_revoke=True
        self.assertEqual(self.post('/api/devices/'+d['id']+'/revoke',{}).status_code,503)
        self.assertIn(d['id'],[d['id'] for d in self.client.get('/api/dashboard').json['devices']])
    def test_deleted_creation_cannot_be_resurrected(self):
        gid,token=self.group()
        def mark(uid):
            with self.app.extensions['panel_db']() as c:c.execute("UPDATE devices SET state='revoked' WHERE id=?",(uid,))
        self.rpc.on_create=mark
        self.assertEqual(self.post('/api/devices',{'group_id':gid,'name':'Cancelled'}).status_code,409)
        self.app.extensions['panel_sync']();self.assertEqual(self.client.get('/api/dashboard').json['devices'][0]['legacy'],1)
    def test_archived_totals_are_scoped_to_admin(self):
        gid,token=self.group();d=self.post('/api/devices',{'group_id':gid,'name':'Root private'}).json;self.rpc.rows[d['id']].update(rx=10,tx=20);self.app.extensions['panel_sync']();self.post('/api/devices/'+d['id']+'/revoke',{})
        self.post('/api/users',{'username':'helper','password':'ordinary-admin-password'});other=self.app.test_client();h={'Origin':'http://localhost'};other.post('/api/login',json={'username':'helper','password':'ordinary-admin-password'},headers=h)
        dash=other.get('/api/dashboard').json;self.assertEqual(dash['summary'],{'rx':0,'tx':0});self.assertEqual(dash['chart'],[])
    def test_delete_empty_group_invalidates_invite_and_is_idempotent(self):
        gid,token=self.group();self.assertEqual(self.client.get('/api/join/'+token).status_code,200)
        self.assertEqual(self.delete_group(gid).json,{'ok':True,'deleted':True})
        self.assertNotIn(gid,[g['id'] for g in self.client.get('/api/dashboard').json['groups']])
        self.assertEqual(self.client.get('/api/join/'+token).status_code,404)
        payload={'id':str(uuid.uuid4()),'name':'No access','download_token':'x'*32}
        self.assertEqual(self.post('/api/join/'+token,payload).status_code,404)
        self.assertEqual(self.post('/api/devices',{'group_id':gid,'name':'No access'}).status_code,404)
        self.assertEqual(self.client.patch('/api/groups/'+str(gid),json={'enabled':True},headers=self.headers).status_code,404)
        self.assertEqual(self.delete_group(gid).status_code,200)
        self.assertEqual(sum(e['event']=='group.deleted' for e in self.client.get('/api/audit').json['events']),1)
        self.assertNotIn('revoke',self.rpc.calls)
    def test_delete_populated_group_blocked_until_client_moved(self):
        gid,token=self.group();d=self.post('/api/devices',{'group_id':gid,'name':'Keep connected'}).json
        self.assertEqual(self.delete_group(gid).status_code,409)
        self.assertEqual(self.client.get('/api/join/'+token).status_code,200);self.assertTrue(self.rpc.rows[d['id']]['active'])
        target=self.post('/api/groups',{'name':'Destination'}).json['id']
        self.assertEqual(self.client.patch('/api/devices/'+d['id'],json={'group_id':target},headers=self.headers).status_code,200)
        self.assertEqual(self.delete_group(gid).status_code,200)
        self.assertEqual(self.client.get('/api/devices/'+d['id']+'/download').status_code,200);self.assertNotIn('revoke',self.rpc.calls)
        self.assertEqual(self.client.patch('/api/devices/'+d['id'],json={'group_id':gid},headers=self.headers).status_code,404)
    def test_pending_or_failed_clients_also_block_group_deletion(self):
        for state in ('pending','error'):
            gid,token=self.group()
            with self.app.extensions['panel_db']() as c:c.execute('INSERT INTO devices(id,group_id,name,state,created) VALUES(?,?,?,?,?)',(str(uuid.uuid4()),gid,'Unfinished client',state,int(time.time())))
            self.assertEqual(self.delete_group(gid).status_code,409)
    def test_service_group_is_protected_even_when_empty(self):
        self.assertEqual(self.delete_group(1).status_code,403)
    def test_group_delete_preserves_revoked_accounting_and_audit(self):
        gid,token=self.group();d=self.post('/api/devices',{'group_id':gid,'name':'History'}).json
        self.rpc.rows[d['id']].update(rx=100,tx=250);self.app.extensions['panel_sync']();self.post('/api/devices/'+d['id']+'/revoke',{})
        before=self.client.get('/api/dashboard').json;self.assertEqual(self.delete_group(gid).status_code,200)
        after=self.client.get('/api/dashboard').json;self.assertEqual(after['summary'],before['summary']);self.assertEqual(after['chart'],before['chart'])
        self.assertNotIn(gid,[g['id'] for g in after['groups']])
        self.assertTrue(any(e['event']=='group.deleted' and 'Friends' in e['detail'] for e in self.client.get('/api/audit').json['events']))
    def test_group_delete_is_owner_scoped(self):
        gid,token=self.group();uid=self.post('/api/users',{'username':'helper','password':'ordinary-admin-password'}).json['id']
        other=self.app.test_client();h={'Origin':'http://localhost'};other.post('/api/login',json={'username':'helper','password':'ordinary-admin-password'},headers=h);h['X-CSRF-Token']=other.get('/api/session').json['csrf']
        self.assertEqual(other.delete('/api/groups/'+str(gid),json={},headers=h).status_code,404)
        own=other.post('/api/groups',json={'name':'Helper own'},headers=h).json['id'];self.assertEqual(other.delete('/api/groups/'+str(own),json={},headers=h).status_code,200)
        another=self.post('/api/groups',{'owner_id':uid,'name':'Root managed'}).json['id'];self.assertEqual(self.delete_group(another).status_code,200)
    def test_existing_group_schema_upgrade_is_idempotent(self):
        gid,token=self.group()
        with self.app.extensions['panel_db']() as c:
            c.execute('ALTER TABLE groups_ DROP COLUMN deleted_at')
            before=[tuple(r) for r in c.execute('SELECT id,owner_id,name,token_hash,token_enc,device_limit,enabled,created FROM groups_ ORDER BY id')]
        for _ in range(2):create_app({'DATA_DIR':self.tmp.name,'COLLECTOR':False},self.rpc)
        with self.app.extensions['panel_db']() as c:
            self.assertIn('deleted_at',[r[1] for r in c.execute('PRAGMA table_info(groups_)')])
            self.assertEqual(before,[tuple(r) for r in c.execute('SELECT id,owner_id,name,token_hash,token_enc,device_limit,enabled,created FROM groups_ ORDER BY id')])
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
    def test_chart_metadata_uses_scoped_history_including_archived_devices(self):
        gid,token=self.group();d=self.post('/api/devices',{'group_id':gid,'name':'History'}).json
        with self.app.extensions['panel_db']() as c:c.execute('UPDATE devices SET created=? WHERE id=?',(int(time.time())-7200,d['id']))
        before=self.client.get('/api/dashboard').json['chart_info'];self.assertEqual(before['timezone'],'Europe/Moscow');self.assertLess(before['started_at'],before['window_end'])
        self.post('/api/devices/'+d['id']+'/revoke',{});self.delete_group(gid)
        self.assertEqual(self.client.get('/api/dashboard').json['chart_info']['started_at'],before['started_at'])
        self.post('/api/users',{'username':'helper','password':'ordinary-admin-password'});other=self.app.test_client();other.post('/api/login',json={'username':'helper','password':'ordinary-admin-password'},headers={'Origin':'http://localhost'})
        self.assertIsNone(other.get('/api/dashboard').json['chart_info']['started_at'])
    def access(self,uid,payload):return self.client.patch('/api/devices/'+uid+'/access',json=payload,headers=self.headers)
    def test_pause_visible_downloadable_moveable_and_counted_towards_quota(self):
        gid,token=self.group();d=self.post('/api/devices',{'group_id':gid,'name':'Pause me'}).json;uid=d['id']
        self.rpc.rows[uid].update(rx=100,tx=250);self.app.extensions['panel_sync']();before=self.client.get('/api/dashboard').json['summary']
        self.assertEqual(self.access(uid,{'paused':True}).json['state'],'paused')
        self.app.extensions['panel_sync']();dash=self.client.get('/api/dashboard').json;row=next(d for d in dash['devices'] if d['id']==uid)
        self.assertEqual(row['state'],'paused');self.assertFalse(row['online']);self.assertEqual(dash['summary'],before)
        self.assertEqual(self.client.get('/api/devices/'+uid+'/download').status_code,200)
        self.assertEqual(self.delete_group(gid).status_code,409)
        self.assertEqual(self.post('/api/devices',{'group_id':gid,'name':'Second'}).status_code,200)
        self.assertEqual(self.post('/api/devices',{'group_id':gid,'name':'Third'}).status_code,409)
        self.assertEqual(self.client.patch('/api/devices/'+uid,json={'group_id':1},headers=self.headers).status_code,200)
        self.assertEqual(self.access(uid,{'paused':False}).json['state'],'active')
    def test_expired_client_is_retained_and_can_be_extended(self):
        gid,token=self.group();d=self.post('/api/devices',{'group_id':gid,'name':'Expires'}).json;uid=d['id'];end=self.rpc.now+60
        self.assertEqual(self.access(uid,{'expires_at':end}).json['state'],'active');self.rpc.now=end+1;self.app.extensions['panel_sync']()
        row=next(d for d in self.client.get('/api/dashboard').json['devices'] if d['id']==uid);self.assertEqual(row['state'],'expired');self.assertEqual(row['expires_at'],end)
        self.assertEqual(self.access(uid,{'expires_at':None}).json['state'],'active')
        self.assertTrue(any(e['event']=='device.expired' for e in self.client.get('/api/audit').json['events']))
    def test_invitation_retry_cannot_bypass_pause(self):
        gid,token=self.group();payload={'id':str(uuid.uuid4()),'name':'Phone','download_token':'x'*32}
        self.assertEqual(self.post('/api/join/'+token,payload).status_code,200);self.access(payload['id'],{'paused':True})
        self.assertEqual(self.post('/api/join/'+token,payload).status_code,409);self.assertEqual(self.rpc.calls.count('create'),1)
    def test_access_mutation_is_owner_scoped_csrf_checked_and_legacy_protected(self):
        gid,token=self.group();d=self.post('/api/devices',{'group_id':gid,'name':'Private'}).json
        self.app.extensions['panel_sync']();self.assertEqual(self.access('legacy_original',{'paused':True}).status_code,403)
        self.post('/api/users',{'username':'helper','password':'ordinary-admin-password'});other=self.app.test_client();h={'Origin':'http://localhost'}
        other.post('/api/login',json={'username':'helper','password':'ordinary-admin-password'},headers=h);h['X-CSRF-Token']=other.get('/api/session').json['csrf']
        self.assertEqual(other.patch('/api/devices/'+d['id']+'/access',json={'paused':True},headers=h).status_code,404)
        self.assertEqual(self.client.patch('/api/devices/'+d['id']+'/access',json={'paused':True},headers={'Origin':'http://localhost'}).status_code,403)
        self.assertNotIn('access',self.rpc.calls)
    def test_invalid_policy_or_failed_rpc_does_not_claim_paused(self):
        gid,token=self.group();d=self.post('/api/devices',{'group_id':gid,'name':'Validate'}).json
        for payload in ({'paused':1},{'expires_at':True},{'expires_at':0},{'expires_at':'bad'},{'other':1},{}):self.assertEqual(self.access(d['id'],payload).status_code,400)
        self.rpc.fail_access=True;self.assertEqual(self.access(d['id'],{'paused':True}).status_code,503)
        row=next(x for x in self.client.get('/api/dashboard').json['devices'] if x['id']==d['id']);self.assertEqual(row['state'],'active')
    def test_revocation_is_terminal_even_for_paused_or_expired_clients(self):
        gid,token=self.group();d=self.post('/api/devices',{'group_id':gid,'name':'Terminal'}).json;uid=d['id'];self.access(uid,{'paused':True});self.post('/api/devices/'+uid+'/revoke',{})
        self.assertEqual(self.access(uid,{'paused':False}).status_code,404);self.app.extensions['panel_sync']();self.assertNotIn(uid,[d['id'] for d in self.client.get('/api/dashboard').json['devices']])
    def test_expiry_schema_upgrade_preserves_existing_profiles(self):
        gid,token=self.group();self.post('/api/devices',{'group_id':gid,'name':'Old unlimited'})
        with self.app.extensions['panel_db']() as c:
            c.execute('ALTER TABLE devices DROP COLUMN expires_at');c.execute('ALTER TABLE devices DROP COLUMN manual_paused');before=[tuple(r) for r in c.execute('SELECT * FROM devices')]
        for _ in range(2):create_app({'DATA_DIR':self.tmp.name,'COLLECTOR':False},self.rpc)
        with self.app.extensions['panel_db']() as c:
            after=[tuple(r) for r in c.execute('SELECT * FROM devices')];self.assertEqual(after,[r+(0,None) for r in before]);self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
    def test_group_duration_applies_to_admin_and_invitation_issuance(self):
        gid,token=self.group();self.assertEqual(self.client.patch('/api/groups/'+str(gid),json={'default_access_days':30},headers=self.headers).status_code,200)
        self.assertEqual(self.client.get('/api/join/'+token).json['default_access_days'],30)
        now=int(time.time());first=self.post('/api/devices',{'group_id':gid,'name':'Admin issued'}).json
        second=self.post('/api/join/'+token,{'id':str(uuid.uuid4()),'name':'Invite issued','download_token':'x'*32,'expires_at':None}).json
        for row in (first,second):self.assertTrue(now+30*86400<=row['expires_at']<=int(time.time())+30*86400)
        self.assertEqual(self.rpc.calls.count('create_limited'),2);self.assertNotIn('access',self.rpc.calls)
    def test_group_change_and_move_do_not_retroactively_change_clients(self):
        gid,token=self.group();old=self.post('/api/devices',{'group_id':gid,'name':'Existing unlimited'}).json
        self.client.patch('/api/groups/'+str(gid),json={'default_access_days':30},headers=self.headers)
        new=self.post('/api/devices',{'group_id':gid,'name':'New limited'}).json
        self.client.patch('/api/groups/'+str(gid),json={'default_access_days':7},headers=self.headers)
        target=self.post('/api/groups',{'name':'Another','default_access_days':90}).json['id']
        self.client.patch('/api/devices/'+new['id'],json={'group_id':target},headers=self.headers)
        rows={d['id']:d for d in self.client.get('/api/dashboard').json['devices']}
        self.assertIsNone(rows[old['id']]['expires_at']);self.assertEqual(rows[new['id']]['expires_at'],new['expires_at'])
    def test_clearing_group_default_affects_only_future_clients(self):
        gid,token=self.group();self.client.patch('/api/groups/'+str(gid),json={'default_access_days':1},headers=self.headers)
        old=self.post('/api/devices',{'group_id':gid,'name':'Limited'}).json
        self.client.patch('/api/groups/'+str(gid),json={'default_access_days':None},headers=self.headers)
        new=self.post('/api/devices',{'group_id':gid,'name':'Unlimited'}).json
        self.assertIsNone(new['expires_at']);self.assertEqual(self.rpc.rows[old['id']]['expires_at'],old['expires_at'])
    def test_group_duration_retry_is_frozen_even_after_interruption(self):
        gid,token=self.group();self.client.patch('/api/groups/'+str(gid),json={'default_access_days':30},headers=self.headers)
        payload={'id':str(uuid.uuid4()),'name':'Retry','download_token':'x'*32}
        def interrupted(uid):raise RuntimeError('Response lost')
        self.rpc.on_create=interrupted;self.assertEqual(self.post('/api/join/'+token,payload).status_code,503)
        deadline=self.rpc.rows[payload['id']]['expires_at'];self.rpc.on_create=None
        self.client.patch('/api/groups/'+str(gid),json={'default_access_days':90},headers=self.headers)
        result=self.post('/api/join/'+token,payload);self.assertEqual(result.status_code,200);self.assertEqual(result.json['expires_at'],deadline)
        self.assertEqual(self.post('/api/join/'+token,payload).json['expires_at'],deadline);self.assertEqual(len(self.rpc.rows),1)
        self.assertTrue(all(p['expires_at']==deadline for p in self.rpc.requests if p['action']=='create_limited'))
    def test_old_worker_cannot_silently_issue_unlimited_for_limited_group(self):
        gid,token=self.group();self.client.patch('/api/groups/'+str(gid),json={'default_access_days':30},headers=self.headers)
        self.rpc.reject_limited=True;result=self.post('/api/devices',{'group_id':gid,'name':'Must fail closed'})
        self.assertEqual(result.status_code,503);self.assertEqual(self.rpc.rows,{});self.assertNotIn('create',self.rpc.calls)
    def test_group_default_validation_and_legacy_service_group_protection(self):
        gid,token=self.group()
        for value in (0,3651,True,'30',1.5,-1):
            self.assertEqual(self.client.patch('/api/groups/'+str(gid),json={'default_access_days':value},headers=self.headers).status_code,400)
            self.assertEqual(self.post('/api/groups',{'name':'Bad','default_access_days':value}).status_code,400)
        self.assertEqual(self.client.patch('/api/groups/1',json={'default_access_days':30},headers=self.headers).status_code,403)
    def test_group_duration_schema_upgrade_is_idempotent(self):
        gid,token=self.group()
        with self.app.extensions['panel_db']() as c:
            c.execute('ALTER TABLE groups_ DROP COLUMN default_access_days');before=[tuple(r) for r in c.execute('SELECT * FROM groups_')]
        for _ in range(2):create_app({'DATA_DIR':self.tmp.name,'COLLECTOR':False},self.rpc)
        with self.app.extensions['panel_db']() as c:self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM groups_')],[r+(None,) for r in before])
    def test_minute_chart_samples_preserve_resolution_and_hourly_totals(self):
        gid,token=self.group();d=self.post('/api/devices',{'group_id':gid,'name':'Chart samples'}).json;minute=int(time.time())//60*60
        with self.app.extensions['panel_db']() as c:
            c.execute('UPDATE devices SET created=? WHERE id=?',(minute-3600,d['id']))
            c.execute('INSERT INTO traffic VALUES(?,?,?,?)',(d['id'],minute-120,10,20));c.execute('INSERT INTO traffic VALUES(?,?,?,?)',(d['id'],minute-60,30,40))
        dashboard=self.client.get('/api/dashboard').json
        self.assertEqual(dashboard['chart_info']['sample_interval'],60)
        self.assertEqual(dashboard['chart_samples'],[{'at':minute-120,'rx':10,'tx':20},{'at':minute-60,'rx':30,'tx':40}])
        self.assertEqual(sum(r['rx'] for r in dashboard['chart']),40);self.assertEqual(sum(r['tx'] for r in dashboard['chart']),60)
    def test_minute_chart_samples_do_not_leak_other_administrators(self):
        gid,token=self.group();d=self.post('/api/devices',{'group_id':gid,'name':'Private chart'}).json
        with self.app.extensions['panel_db']() as c:c.execute('INSERT INTO traffic VALUES(?,?,?,?)',(d['id'],int(time.time())//60*60,123,456))
        self.post('/api/users',{'username':'helper','password':'ordinary-admin-password'});other=self.app.test_client();h={'Origin':'http://localhost'}
        other.post('/api/login',json={'username':'helper','password':'ordinary-admin-password'},headers=h)
        self.assertEqual(other.get('/api/dashboard').json['chart_samples'],[])

if __name__=='__main__':unittest.main(verbosity=2)
