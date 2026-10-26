"""Existing super-only password reset contract, using disposable accounts only."""
from pathlib import Path
import tempfile
import unittest

from panel import create_app, HASHER
from test_panel import RPC


class AdminPasswordTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.rpc=RPC()
        self.app=create_app({'DATA_DIR':self.tmp.name,'COLLECTOR':False,'COOKIE_SECURE':False,
                            'PUBLIC_ORIGIN':'http://localhost','TESTING':True},self.rpc)
        self.owner_password=(Path(self.tmp.name)/'bootstrap-password.txt').read_text().strip()
        self.client,self.headers=self.login('owner',self.owner_password)

    def tearDown(self):
        self.tmp.cleanup()

    def login(self,name,password):
        client=self.app.test_client();headers={'Origin':'http://localhost'}
        self.assertEqual(client.post('/api/login',json={'username':name,'password':password},headers=headers).status_code,200)
        headers['X-CSRF-Token']=client.get('/api/session').json['csrf']
        return client,headers

    def add(self,name='helper',role='admin'):
        result=self.client.post('/api/users',json={'username':name,'password':'synthetic-original-password',
                               'role':role,'limit':17},headers=self.headers)
        self.assertEqual(result.status_code,200)
        return result.json['id']

    def snapshot(self):
        with self.app.extensions['panel_db']() as c:
            return {table:[tuple(row) for row in c.execute('SELECT * FROM '+table+' ORDER BY rowid')]
                    for table in ('users','sessions','groups_','devices','audit')}

    def test_reset_without_old_invalidates_only_target_sessions(self):
        uid=self.add();target,_=self.login('helper','synthetic-original-password')
        target2,_=self.login('helper','synthetic-original-password')
        other_id=self.add('unaffected');other,_=self.login('unaffected','synthetic-original-password')
        calls=list(self.rpc.calls)
        result=self.client.patch('/api/users/'+str(uid),json={'password':'synthetic-new-password'},headers=self.headers)
        self.assertEqual(result.status_code,200)
        for client in (target,target2):self.assertEqual(client.get('/api/session').status_code,401)
        for client in (self.client,other):self.assertEqual(client.get('/api/session').status_code,200)
        self.assertEqual(self.app.test_client().post('/api/login',json={'username':'helper','password':'synthetic-original-password'},headers={'Origin':'http://localhost'}).status_code,401)
        self.login('helper','synthetic-new-password')
        with self.app.extensions['panel_db']() as c:
            row=c.execute('SELECT password FROM users WHERE id=?',(uid,)).fetchone()
            self.assertNotEqual(row['password'],'synthetic-new-password');self.assertTrue(HASHER.verify(row['password'],'synthetic-new-password'))
            self.assertNotIn('synthetic-new-password',str([tuple(r) for r in c.execute('SELECT * FROM audit')]))
        self.assertEqual(self.rpc.calls,calls)

    def test_closed_account_and_all_profiles_statistics_and_roles_stay_unchanged(self):
        uid=self.add()
        gid=self.client.post('/api/groups',json={'name':'Preserved group','owner_id':uid},headers=self.headers).json['id']
        device=self.client.post('/api/devices',json={'group_id':gid,'name':'Preserved VPN'},headers=self.headers).json
        self.rpc.rows[device['id']].update(rx=12345,tx=67890);self.app.extensions['panel_sync']()
        self.client.patch('/api/users/'+str(uid),json={'enabled':False},headers=self.headers)
        before=self.snapshot();calls=list(self.rpc.calls)
        self.assertEqual(self.client.patch('/api/users/'+str(uid),json={'password':'synthetic-new-password'},headers=self.headers).status_code,200)
        after=self.snapshot()
        self.assertEqual(before['groups_'],after['groups_']);self.assertEqual(before['devices'],after['devices'])
        with self.app.extensions['panel_db']() as c:
            self.assertEqual(tuple(c.execute('SELECT role,enabled,max_devices FROM users WHERE id=?',(uid,)).fetchone()),('admin',0,17))
        self.assertEqual(self.app.test_client().post('/api/login',json={'username':'helper','password':'synthetic-new-password'},headers={'Origin':'http://localhost'}).status_code,401)
        self.assertEqual(self.rpc.calls,calls)

    def test_owner_can_reset_self_without_old_password(self):
        other,_=self.login('owner',self.owner_password)
        self.assertEqual(self.client.patch('/api/users/1',json={'password':'synthetic-new-password'},headers=self.headers).status_code,200)
        for client in (self.client,other):self.assertEqual(client.get('/api/session').status_code,401)
        self.login('owner','synthetic-new-password')
        self.assertEqual(self.rpc.calls,[])

    def test_other_super_can_reset_protected_owner_without_unprotecting_it(self):
        self.add('second-super','super');second,h=self.login('second-super','synthetic-original-password')
        self.assertEqual(second.patch('/api/users/1',json={'password':'synthetic-new-password'},headers=h).status_code,200)
        self.assertEqual(second.get('/api/session').status_code,200);self.assertEqual(self.client.get('/api/session').status_code,401)
        self.assertEqual(second.patch('/api/users/1',json={'enabled':False},headers=h).status_code,403)
        self.assertEqual(second.delete('/api/users/1',json={},headers=h).status_code,403)

    def test_ordinary_admin_cannot_reset_any_account_or_bypass_own_old_password(self):
        uid=self.add();other,h=self.login('helper','synthetic-original-password');before=self.snapshot()
        for target in (1,uid,999):
            self.assertEqual(other.patch('/api/users/'+str(target),json={'password':'synthetic-new-password'},headers=h).status_code,403)
        for payload in ({'new':'synthetic-new-password'},{'old':'wrong-old-password','new':'synthetic-new-password'}):
            self.assertEqual(other.post('/api/password',json=payload,headers=h).status_code,400)
        self.assertEqual(before,self.snapshot())
        self.assertEqual(other.post('/api/password',json={'old':'synthetic-original-password','new':'synthetic-new-password'},headers=h).status_code,200)
        self.login('helper','synthetic-new-password')

    def test_csrf_origin_and_auth_are_enforced_without_mutations(self):
        uid=self.add();url='/api/users/'+str(uid);before=self.snapshot()
        for headers in ({'Origin':'http://localhost'},{**self.headers,'X-CSRF-Token':'incorrect'},
                        {**self.headers,'Origin':'https://evil.test'},{'X-CSRF-Token':self.headers['X-CSRF-Token']}):
            self.assertEqual(self.client.patch(url,json={'password':'synthetic-new-password'},headers=headers).status_code,403)
        self.assertEqual(self.app.test_client().patch(url,json={'password':'synthetic-new-password'},headers=self.headers).status_code,401)
        self.assertEqual(before,self.snapshot())

    def test_invalid_password_missing_or_deleted_user_leave_database_unchanged(self):
        uid=self.add();self.client.patch('/api/users/'+str(uid),json={'enabled':False},headers=self.headers)
        self.client.delete('/api/users/'+str(uid),json={},headers=self.headers)
        before=self.snapshot()
        for password in ('','x'*11,'x'*129):
            self.assertEqual(self.client.patch('/api/users/1',json={'password':password},headers=self.headers).status_code,400)
        for target in (uid,999):
            self.assertEqual(self.client.patch('/api/users/'+str(target),json={'password':'synthetic-new-password'},headers=self.headers).status_code,404)
        self.assertEqual(before,self.snapshot())


if __name__=='__main__':unittest.main()
