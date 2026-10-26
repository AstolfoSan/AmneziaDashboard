import json
from pathlib import Path
import tempfile
import time
import unittest
import uuid

import test_panel
from agent import Agent, fields, split_config
from panel import create_app


class MeterEngine(test_panel.Engine):
    def __init__(self):
        super().__init__()
        self.transfer = {}
        self.epoch = 'first-generation'
    def counter_epoch(self): return self.epoch
    def wg(self, field):
        if field == 'transfer': return {k: list(map(str, v)) for k, v in self.transfer.items()}
        return super().wg(field)
    def commit(self, old, raw, new, rows, pub, psk=None, ip=None, reset=False):
        super().commit(old, raw, new, rows, pub, psk, ip, reset)
        if psk is None: self.transfer.pop(pub, None)
        elif reset or pub not in self.transfer: self.transfer[pub] = [0, 0]


class QuotaAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = MeterEngine()
        self.agent = Agent(Path(self.temp.name), self.engine)
        self.uid = str(uuid.uuid4())
        self.agent.create(self.uid, 'Synthetic quota test')
        self.original = self.agent.load(self.uid)
        self.pub = self.original['public']
        self.agent.enforce()
    def tearDown(self): self.temp.cleanup()
    def quota(self, value, seed=None):
        return self.agent.dispatch({'action': 'traffic_limit', 'id': self.uid, 'limit_bytes': value,
                                   'seed': seed or dict(rx=0, tx=0, last_rx=0, last_tx=0)})
    def test_reaches_sum_of_upload_and_download_and_keeps_original_config(self):
        self.quota(300)
        self.engine.transfer[self.pub] = [100, 200]
        self.agent.enforce()
        record = self.agent.load(self.uid)
        self.assertEqual(record['status'], 'limited')
        self.assertEqual((record['meter_rx'], record['meter_tx']), (100, 200))
        for key in ('private', 'public', 'psk', 'vpn', 'ip'):
            self.assertEqual(record[key], self.original[key])
        block = next(p for p in split_config(self.engine.cfg)[1] if fields(p)['PublicKey'] == self.pub)
        self.assertEqual(fields(block)['PresharedKey'], record['pause_psk'])
        self.assertEqual(self.agent.export(self.uid)['vpn'], self.original['vpn'])
        with self.assertRaises(ValueError): self.agent.create(self.uid, 'Cannot bypass quota')
    def test_usage_survives_repeated_checks_restart_and_quota_extension(self):
        self.quota(300)
        self.engine.transfer[self.pub] = [100, 200]
        self.agent.enforce(); self.agent.enforce()
        self.agent = Agent(Path(self.temp.name), self.engine)
        result = self.quota(1000)
        self.assertEqual(result['state'], 'active')
        self.engine.transfer[self.pub] = [300, 400]
        self.agent.enforce()
        record = self.agent.load(self.uid)
        self.assertEqual((record['meter_rx'], record['meter_tx']), (400, 600))
        self.assertEqual(record['status'], 'limited')
        self.assertEqual(self.quota(None)['state'], 'active')
        self.assertEqual(self.agent.load(self.uid)['meter_rx'], 400)
    def test_generation_change_counts_the_whole_new_counter_even_when_it_exceeds_old(self):
        self.engine.transfer[self.pub] = [100, 200]; self.agent.enforce()
        self.engine.epoch = 'after-container-or-interface-restart'
        self.engine.transfer[self.pub] = [500, 600]; self.agent.enforce(); self.agent.enforce()
        record = self.agent.load(self.uid)
        self.assertEqual((record['meter_rx'], record['meter_tx']), (600, 800))
    def test_initial_seed_includes_old_panel_totals_and_only_unsampled_delta(self):
        record = self.agent.load(self.uid)
        for key in list(record):
            if key.startswith('meter_') or key == 'traffic_meter': record.pop(key)
        self.agent.save(record)
        self.engine.transfer[self.pub] = [1100, 2200]
        seed = dict(rx=200, tx=100, last_rx=1000, last_tx=2000)
        result = self.quota(10000, seed)
        self.assertEqual((result['total_rx'], result['total_tx']), (300, 300))
        result = self.quota(10000, dict(rx=0, tx=0, last_rx=0, last_tx=0))
        self.assertEqual((result['total_rx'], result['total_tx']), (300, 300))
    def test_quota_changes_cannot_override_manual_pause_or_expiry(self):
        self.agent.access({'id': self.uid, 'paused': True})
        self.assertEqual(self.quota(None)['state'], 'paused')
        self.agent.access({'id': self.uid, 'paused': False, 'expires_at': int(time.time())-1})
        self.assertEqual(self.quota(10000)['state'], 'expired')
        self.agent.access({'id': self.uid, 'expires_at': None})
        self.engine.transfer[self.pub] = [10000, 0]; self.agent.enforce()
        self.assertEqual(self.agent.access({'id': self.uid, 'paused': False, 'expires_at': None})['state'], 'limited')
    def test_failed_peer_reset_is_repaired_without_double_counting_known_usage(self):
        self.quota(300); self.engine.transfer[self.pub] = [100, 200]; self.engine.fail = True
        with self.assertRaises(RuntimeError): self.agent.enforce()
        self.agent.enforce(); self.agent.enforce()
        record = self.agent.load(self.uid)
        self.assertEqual(record['status'], 'limited')
        self.assertEqual((record['meter_rx'], record['meter_tx']), (100, 200))
    def test_unmetered_existing_records_stay_byte_identical_during_enforcement(self):
        record = self.agent.load(self.uid)
        for key in list(record):
            if key.startswith('meter_') or key == 'traffic_meter': record.pop(key)
        self.agent.save(record)
        path = Path(self.temp.name)/(self.uid+'.enc'); before = path.read_bytes()
        self.agent.enforce()
        self.assertEqual(before, path.read_bytes())
    def test_invalid_limits_and_unknown_or_legacy_profiles_are_rejected(self):
        for limit in [True, 0, -1, 1.5, '5', 2**53]:
            with self.assertRaises(ValueError): self.quota(limit)
        for uid in ['legacy_original', str(uuid.uuid4())]:
            with self.assertRaises(ValueError): self.agent.dispatch({'action':'traffic_limit','id':uid,'limit_bytes':100,'seed':dict(rx=0,tx=0,last_rx=0,last_tx=0)})
        self.assertEqual(self.agent.load(self.uid).get('traffic_limit_bytes'), None)


class QuotaPanelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.engine = MeterEngine(); self.agent = Agent(root/'worker', self.engine)
        self.fail = False
        def rpc(payload):
            if self.fail and payload['action'] == 'traffic_limit': raise ValueError('Unsupported old worker')
            return self.agent.dispatch(payload)
        self.app = create_app({'DATA_DIR':str(root/'panel'),'COLLECTOR':False,'COOKIE_SECURE':False,'PUBLIC_ORIGIN':'http://localhost'}, rpc)
        self.client = self.app.test_client(); self.headers = {'Origin':'http://localhost'}
        password = (root/'panel/bootstrap-password.txt').read_text().strip()
        self.client.post('/api/login',json={'username':'owner','password':password},headers=self.headers)
        self.headers['X-CSRF-Token'] = self.client.get('/api/session').json['csrf']
        gid = self.client.post('/api/groups',json={'name':'Quota','limit':5},headers=self.headers).json['id']
        self.uid = self.client.post('/api/devices',json={'group_id':gid,'name':'Synthetic'},headers=self.headers).json['id']
        self.pub = self.agent.load(self.uid)['public']
    def tearDown(self): self.temp.cleanup()
    def quota(self, value, headers=None):
        return self.client.patch('/api/devices/'+self.uid+'/traffic',json={'limit_bytes':value},headers=headers or self.headers)
    def row(self): return next(d for d in self.client.get('/api/dashboard').json['devices'] if d['id']==self.uid)
    def test_limit_is_enforced_locally_without_panel_then_final_bytes_are_collected(self):
        self.assertEqual(self.quota(300).status_code, 200)
        self.engine.transfer[self.pub] = [100, 200]; self.agent.enforce()
        self.app.extensions['panel_sync']()
        row = self.row()
        self.assertEqual((row['rx'], row['tx'], row['state']), (100, 200, 'limited'))
        self.assertEqual(row['traffic_limit_bytes'], 300)
        self.assertEqual(self.client.get('/api/devices/'+self.uid+'/download').status_code, 200)
        self.assertEqual(self.quota(1000).json['state'], 'active')
        self.engine.transfer[self.pub] = [50, 60]; self.app.extensions['panel_sync']()
        self.assertEqual((self.row()['rx'], self.row()['tx']), (150, 260))
    def test_unlimited_preserves_totals_and_manual_pause(self):
        self.engine.transfer[self.pub] = [100, 200]; self.app.extensions['panel_sync']()
        self.client.patch('/api/devices/'+self.uid+'/access',json={'paused':True},headers=self.headers)
        self.assertEqual(self.quota(None).json['state'], 'paused')
        self.app.extensions['panel_sync']()
        self.assertEqual((self.row()['rx'], self.row()['tx']), (100, 200))
    def test_invalid_limit_missing_csrf_legacy_and_old_worker_fail_without_saving(self):
        for limit in [False, 0, -1, 1.5, '100', 2**53]: self.assertEqual(self.quota(limit).status_code, 400)
        self.assertEqual(self.quota(100, {'Origin':'http://localhost'}).status_code, 403)
        self.app.extensions['panel_sync']()
        legacy = next(d for d in self.client.get('/api/dashboard').json['devices'] if d['legacy'])
        self.assertEqual(self.client.patch('/api/devices/'+legacy['id']+'/traffic',json={'limit_bytes':100},headers=self.headers).status_code,403)
        self.fail = True
        self.assertEqual(self.quota(100).status_code,503)
        self.assertIsNone(self.row()['traffic_limit_bytes'])
    def test_other_admin_cannot_change_another_clients_quota(self):
        self.client.post('/api/users',json={'username':'helper','password':'ordinary-admin-password'},headers=self.headers)
        other = self.app.test_client(); headers = {'Origin':'http://localhost'}
        other.post('/api/login',json={'username':'helper','password':'ordinary-admin-password'},headers=headers)
        headers['X-CSRF-Token'] = other.get('/api/session').json['csrf']
        self.assertEqual(other.patch('/api/devices/'+self.uid+'/traffic',json={'limit_bytes':100},headers=headers).status_code,404)


if __name__ == '__main__': unittest.main()
