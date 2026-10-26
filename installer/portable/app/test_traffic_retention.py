import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from panel import create_app, digest, moscow_day, retain_traffic


class TrafficRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.now = 1792919820  # A fixed instant; all boundaries below use explicit MSK math.
        self.day = moscow_day(self.now)
        self.sample = self.now
        self.peers = []
        self.calls = []
        with patch('panel.time.time', return_value=self.now):
            self.app = create_app({'DATA_DIR': self.temp.name, 'COLLECTOR': False, 'COOKIE_SECURE': False}, self.rpc)
        self.db = self.app.extensions['panel_db']
        with self.db() as conn:
            conn.execute("INSERT INTO devices(id,group_id,name,legacy,state,created) VALUES('one',1,'Synthetic',1,'active',?)", (self.now-45*86400,))
            conn.execute('INSERT INTO sessions VALUES(?,?,?,?)', (digest('test-session'), 1, 'test-csrf', self.now+86400))
        self.client = self.app.test_client()
        self.client.set_cookie('panel_session', 'test-session')

    def tearDown(self):
        self.temp.cleanup()

    def rpc(self, payload):
        self.calls.append(payload['action'])
        self.assertEqual(payload['action'], 'stats')
        return {'sampled_at': self.sample, 'peers': self.peers}

    def sync(self, rx=0, tx=0):
        self.peers = [{'id': 'one', 'legacy': True, 'active': True, 'state': 'active',
                       'ip': '10.8.1.250', 'rx': rx, 'tx': tx, 'handshake': self.sample}]
        self.app.extensions['panel_sync']()
        with self.db() as conn:
            self.assertEqual(conn.execute("SELECT value FROM meta WHERE key='sync_error'").fetchone()[0], '')

    def dashboard(self, client=None):
        with patch('panel.time.time', return_value=self.now):
            response = (client or self.client).get('/api/dashboard')
        self.assertEqual(response.status_code, 200)
        return response.json

    def test_moscow_midnight_is_2100_utc_not_server_local_midnight(self):
        self.assertEqual(moscow_day(self.day-1), self.day-86400)
        self.assertEqual(moscow_day(self.day), self.day)
        self.assertEqual(self.day % 86400, 21*3600)

    def test_old_history_migrates_before_pruning_and_restart_does_not_double_it(self):
        samples = [(self.day-32*86400, 1, 2), (self.day-31*86400, 3, 4),
                   (self.day-2*86400+60, 5, 6), (self.now-120, 7, 8), (self.now-60, 9, 10)]
        with self.db() as conn:
            conn.execute("DELETE FROM meta WHERE key='traffic_daily_v1'")
            conn.executemany("INSERT INTO traffic VALUES('one',?,?,?)", samples)
            before = tuple(conn.execute("SELECT * FROM devices WHERE id='one'").fetchone())
        for _ in range(2):
            with patch('panel.time.time', return_value=self.now):
                create_app({'DATA_DIR': self.temp.name, 'COLLECTOR': False}, self.rpc)
        with self.db() as conn:
            self.assertEqual([tuple(r) for r in conn.execute('SELECT day,rx,tx FROM traffic_daily ORDER BY day')],
                             [(self.day-31*86400, 3, 4), (self.day-2*86400, 5, 6), (self.day, 16, 18)])
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM traffic').fetchone()[0], 2)
            self.assertEqual(tuple(conn.execute("SELECT * FROM devices WHERE id='one'").fetchone()), before)
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_rollup_and_pruning_are_rolled_back_together_on_failure(self):
        with self.db() as conn:
            conn.execute("DELETE FROM meta WHERE key='traffic_daily_v1'")
            conn.execute("INSERT INTO traffic VALUES('one',?,10,20)", (self.now-2*86400,))
        with self.assertRaises(RuntimeError):
            with self.db() as conn:
                retain_traffic(conn, self.now)
                raise RuntimeError('Simulated interrupted startup')
        with self.db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM traffic').fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM traffic_daily').fetchone()[0], 0)
            self.assertIsNone(conn.execute("SELECT value FROM meta WHERE key='traffic_daily_v1'").fetchone())

    def test_each_counter_delta_updates_both_series_once_including_repeated_samples(self):
        self.sync(10, 20)
        self.sync(10, 20)
        self.sample += 15
        self.sync(14, 27)
        with self.db() as conn:
            self.assertEqual(tuple(conn.execute('SELECT SUM(rx),SUM(tx) FROM traffic').fetchone()), (14, 27))
            self.assertEqual(tuple(conn.execute('SELECT SUM(rx),SUM(tx) FROM traffic_daily').fetchone()), (14, 27))
            self.assertEqual(tuple(conn.execute("SELECT rx,tx FROM devices WHERE id='one'").fetchone()), (14, 27))

    def test_samples_around_moscow_midnight_belong_to_different_days(self):
        self.sample = self.day+86400-1
        self.sync(10, 20)
        self.sample += 2
        self.sync(13, 25)
        with self.db() as conn:
            self.assertEqual([tuple(r) for r in conn.execute('SELECT day,rx,tx FROM traffic_daily ORDER BY day')],
                             [(self.day, 10, 20), (self.day+86400, 3, 5)])

    def test_cleanup_is_bounded_and_does_not_trim_cumulative_counters(self):
        with self.db() as conn:
            conn.executemany("INSERT INTO traffic_daily VALUES('one',?,1,2)", [(self.day-i*86400,) for i in range(40)])
            conn.execute("INSERT INTO traffic VALUES('one',?,7,8)", (self.now-86460,))
            conn.execute("INSERT INTO traffic VALUES('one',?,9,10)", ((self.now-86400)//60*60,))
            conn.execute("UPDATE devices SET rx=10000,tx=20000 WHERE id='one'")
        self.sync()
        with self.db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM traffic_daily').fetchone()[0], 32)
            self.assertEqual(conn.execute('SELECT MIN(day) FROM traffic_daily').fetchone()[0], self.day-31*86400)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM traffic').fetchone()[0], 1)
            self.assertEqual(tuple(conn.execute("SELECT rx,tx FROM devices WHERE id='one'").fetchone()), (10000, 20000))

    def test_24h_api_includes_yesterday_and_excludes_older_than_rolling_window(self):
        with self.db() as conn:
            conn.executemany("INSERT INTO traffic VALUES('one',?,?,?)", [(self.now-25*3600, 999, 999),
                             (self.now-23*3600, 11, 22), (self.now-60, 33, 44)])
        data = self.dashboard()
        self.assertEqual(sum(r['rx'] for r in data['chart_samples']), 44)
        self.assertTrue(any(r['at'] < self.day for r in data['chart_samples']))
        self.assertEqual(data['chart_info']['window_end'], self.now)

    def test_daily_api_returns_31_completed_days_excluding_today_and_older_rows(self):
        with self.db() as conn:
            conn.executemany("INSERT INTO traffic_daily VALUES('one',?,1,2)", [(self.day-i*86400,) for i in range(33)])
        data = self.dashboard()
        self.assertEqual(len(data['chart_daily']), 31)
        self.assertEqual(data['chart_daily'][0]['at'], self.day-31*86400)
        self.assertEqual(data['chart_daily'][-1]['at'], self.day-86400)
        self.assertEqual(data['chart_info']['daily_end'], self.day)
        self.assertEqual(data['chart_info']['detail_retention_seconds'], 86400)

    def test_daily_history_retains_archived_clients_and_is_scoped_to_admin(self):
        with self.db() as conn:
            conn.execute("UPDATE devices SET state='revoked' WHERE id='one'")
            conn.execute("INSERT INTO traffic_daily VALUES('one',?,10,20)", (self.day-86400,))
            conn.execute("INSERT INTO users(id,username,password,role) VALUES(2,'synthetic-admin','invalid','admin')")
            conn.execute("INSERT INTO groups_(id,owner_id,name,created) VALUES(2,2,'Other',?)", (self.now,))
            conn.execute("INSERT INTO devices(id,group_id,name,state,created) VALUES('other',2,'Other','active',?)", (self.now-86400,))
            conn.execute("INSERT INTO traffic_daily VALUES('other',?,30,40)", (self.day-86400,))
            conn.execute("INSERT INTO sessions VALUES(?,2,'csrf',?)", (digest('other-session'), self.now+86400))
        other = self.app.test_client()
        other.set_cookie('panel_session', 'other-session')
        self.assertEqual(self.dashboard()['chart_daily'][0]['rx'], 40)
        self.assertEqual(self.dashboard(other)['chart_daily'][0]['rx'], 30)

    def test_expired_detail_is_not_required_to_preserve_the_daily_total_on_restart(self):
        with self.db() as conn:
            conn.execute("INSERT INTO traffic_daily VALUES('one',?,100,200)", (self.day-10*86400,))
        for _ in range(2):
            with patch('panel.time.time', return_value=self.now):
                create_app({'DATA_DIR': self.temp.name, 'COLLECTOR': False}, self.rpc)
        self.assertEqual(self.dashboard()['chart_daily'][0]['rx'], 100)


if __name__ == '__main__':
    unittest.main()
