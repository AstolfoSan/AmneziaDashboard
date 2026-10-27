"""Synthetic native-export and scoped endpoint regressions; no live peer access."""
import base64
import copy
import json
import struct
import time
import unittest
import uuid
import zlib
from unittest.mock import patch

from awg_export import conf_from_vpn
import test_panel as fixtures


def key(number):
    return base64.b64encode(bytes([number]) * 32).decode()


def document():
    native = ('[Interface]\nPrivateKey = '+key(1)+'\nAddress = 10.8.1.13/32\n'
              'DNS = $PRIMARY_DNS, $SECONDARY_DNS\nMTU = 1280\n'
              'HeaderProtectionKey = '+key(4)+'\nJc = 4\nJmin = 40\nJmax = 70\n'
              'S1 = 11\nS2 = 12\nS3 = 13\nS4 = 14\nH1 = 100-200\nH2 = 300\nH3 = 400\nH4 = 500\n'
              'I1 = <r 32>\nRandomTrailers = off\nDisableCookies = on\nContentPaddingAddition = 10-100\n'
              '\n[Peer]\nPublicKey = '+key(2)+'\nPresharedKey = '+key(3)+'\n'
              'AllowedIPs = 0.0.0.0/0, ::/0\nEndpoint = 203.0.113.10:39265\nPersistentKeepalive = 25-35\n')
    last = {'config': native, 'client_priv_key': key(1), 'server_pub_key': key(2),
            'psk_key': key(3), 'client_ip': '10.8.1.13'}
    return {'containers': [{'container': 'amnezia-awg2', 'awg': {'protocol_version': '3.1', 'last_config': json.dumps(last)}}],
            'defaultContainer': 'amnezia-awg2', 'description': 'Synthetic guest',
            'hostName': '203.0.113.10', 'dns1': '1.1.1.1', 'dns2': '8.8.8.8'}


def encode(doc):
    raw = json.dumps(doc).encode()
    return 'vpn://' + base64.urlsafe_b64encode(struct.pack('>I', len(raw)) + zlib.compress(raw)).decode().rstrip('=')


def changed_native(old, new):
    doc = document()
    last = json.loads(doc['containers'][0]['awg']['last_config'])
    last['config'] = last['config'].replace(old, new)
    doc['containers'][0]['awg']['last_config'] = json.dumps(last)
    return doc


class NativeExportTests(unittest.TestCase):
    def test_same_identity_parameters_routes_endpoint_and_dns(self):
        doc = document(); original = copy.deepcopy(doc)
        value = conf_from_vpn(encode(doc))
        self.assertEqual(doc, original)
        for field in ('PrivateKey = '+key(1), 'PublicKey = '+key(2), 'PresharedKey = '+key(3),
                      'HeaderProtectionKey = '+key(4), 'Address = 10.8.1.13/32', 'MTU = 1280',
                      'DNS = 1.1.1.1, 8.8.8.8', 'Endpoint = 203.0.113.10:39265',
                      'H1 = 100-200', 'PersistentKeepalive = 25-35', 'I1 = <r 32>',
                      'ContentPaddingAddition = 10-100', 'AllowedIPs = 0.0.0.0/0, ::/0'):
            self.assertIn(field, value)
        self.assertNotIn('$', value); self.assertNotIn('protocol_version', value)
        self.assertEqual(conf_from_vpn(encode(doc)), value)

    def test_crlf_normalized_without_changing_values(self):
        doc = document(); last = json.loads(doc['containers'][0]['awg']['last_config'])
        last['config'] = last['config'].replace('\n', '\r\n')
        doc['containers'][0]['awg']['last_config'] = json.dumps(last)
        self.assertEqual(conf_from_vpn(encode(doc)), conf_from_vpn(encode(document())))

    def test_refuses_management_unknown_and_multiple_container_exports(self):
        for field in ('password', 'userName', 'privateKey', 'ssh_key'):
            doc = document(); doc[field] = 'synthetic-management-value'
            with self.subTest(field=field), self.assertRaises(ValueError): conf_from_vpn(encode(doc))
        doc = document(); doc['containers'] *= 2
        with self.assertRaises(ValueError): conf_from_vpn(encode(doc))
        doc = document(); doc['containers'][0]['container'] = 'other'
        with self.assertRaises(ValueError): conf_from_vpn(encode(doc))

    def test_refuses_shell_hooks_unknown_sections_and_duplicates(self):
        for addition in ('PostUp = echo unsafe', 'PreDown = echo unsafe', 'SaveConfig = true',
                         'UnknownField = value', 'PrivateKey = '+key(1), '[Interface]', '[Other]'):
            with self.subTest(addition=addition), self.assertRaises(ValueError):
                conf_from_vpn(encode(changed_native('MTU = 1280', 'MTU = 1280\n'+addition)))

    def test_refuses_invalid_keys_addresses_endpoint_dns_and_ranges(self):
        for old, new in [('PrivateKey = '+key(1), 'PrivateKey = bad'),
                         ('Address = 10.8.1.13/32', 'Address = invalid'),
                         ('Endpoint = 203.0.113.10:39265', 'Endpoint = https://evil.example'),
                         ('MTU = 1280', 'MTU = nope'),
                         ('PersistentKeepalive = 25-35', 'PersistentKeepalive = 35-25')]:
            with self.subTest(field=old), self.assertRaises(ValueError):
                conf_from_vpn(encode(changed_native(old, new)))
        doc = document(); doc['dns1'] = '1.1.1.1\nPostUp = echo unsafe'
        with self.assertRaises(ValueError): conf_from_vpn(encode(doc))

    def test_inconsistent_identity_is_not_silently_reissued(self):
        for field in ('client_priv_key', 'server_pub_key', 'psk_key', 'client_ip'):
            doc = document(); last = json.loads(doc['containers'][0]['awg']['last_config'])
            last[field] = '10.8.1.99' if field == 'client_ip' else key(8)
            doc['containers'][0]['awg']['last_config'] = json.dumps(last)
            with self.subTest(field=field), self.assertRaises(ValueError): conf_from_vpn(encode(doc))

    def test_bounded_decompression_length_trailing_bytes_and_uri_validation(self):
        for value in ('https://example.test', 'vpn://abc#bad', 'vpn://'+'a'*65536, None):
            with self.subTest(value_type=type(value).__name__), self.assertRaises((ValueError, TypeError)): conf_from_vpn(value)
        for length, compressed in [(300000, zlib.compress(b'{}')), (2, zlib.compress(b'a'*100000)),
                                   (2, zlib.compress(b'{}')+b'trailing')]:
            value = 'vpn://'+base64.urlsafe_b64encode(struct.pack('>I', length)+compressed).decode().rstrip('=')
            with self.assertRaises(ValueError): conf_from_vpn(value)

    def test_duplicate_json_keys_are_rejected(self):
        raw = b'{"containers":[],"containers":[]}'
        value = 'vpn://'+base64.urlsafe_b64encode(struct.pack('>I', len(raw))+zlib.compress(raw)).decode().rstrip('=')
        with self.assertRaises(ValueError): conf_from_vpn(value)


class ExportEndpointTests(unittest.TestCase):
    setUpBase = fixtures.PanelTests.setUp
    tearDownBase = fixtures.PanelTests.tearDown
    post = fixtures.PanelTests.post
    group = fixtures.PanelTests.group

    def setUp(self):
        self.setUpBase(); self.export_value = encode(document())
        original = fixtures.RPC.__call__
        def rpc(instance, payload):
            if payload['action'] == 'export':
                instance.calls.append('export'); instance.requests.append(dict(payload))
                return {'vpn': self.export_value}
            return original(instance, payload)
        self.patcher = patch.object(fixtures.RPC, '__call__', rpc); self.patcher.start()
        self.gid, self.invitation = self.group()
        self.device = self.post('/api/devices', {'group_id': self.gid, 'name': 'Synthetic device'}).json
        self.url = '/api/devices/'+self.device['id']+'/download'

    def tearDown(self):
        self.patcher.stop(); self.tearDownBase()

    def test_admin_conf_and_original_vpn_are_same_profile_without_mutations(self):
        before = len(self.rpc.rows); calls = len(self.rpc.calls)
        for _ in range(2):
            response = self.client.get(self.url+'?format=conf')
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data.startswith(b'[Interface]\n'))
            self.assertIn('.conf', response.headers['Content-Disposition'])
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
            self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
        self.assertEqual(self.client.get(self.url).data, (self.export_value+'\n').encode())
        self.assertEqual(len(self.rpc.rows), before)
        self.assertEqual(self.rpc.calls[calls:], ['export', 'export', 'export'])

    def test_public_conf_requires_same_bearer_and_download_window(self):
        public = self.app.test_client(); uid = str(uuid.uuid4())
        payload = {'id': uid, 'name': 'Other device', 'download_token': 'x'*32}
        self.assertEqual(public.post('/api/join/'+self.invitation, json=payload, headers={'Origin':'http://localhost'}).status_code,200)
        url = '/api/receive/'+uid+'?format=conf'; headers = {'Authorization': 'Bearer '+'x'*32}
        self.assertEqual(public.get(url).status_code,404)
        self.assertEqual(public.get(url,headers={'Authorization':'Bearer wrong'}).status_code,404)
        self.assertEqual(public.get(url,headers=headers).status_code,200)
        with self.app.extensions['panel_db']() as connection:
            connection.execute('UPDATE devices SET download_expires=? WHERE id=?',(int(time.time())-5, uid))
        self.assertEqual(public.get(url,headers=headers).status_code,404)

    def test_access_states_and_lifetime_counters_unchanged_by_both_exports(self):
        for state in ('active','paused','expired','limited'):
            with self.app.extensions['panel_db']() as connection:
                connection.execute('UPDATE devices SET state=?,manual_paused=1,expires_at=1,traffic_limit_bytes=1,rx=17,tx=29 WHERE id=?',(state,self.device['id']))
            for suffix in ('','?format=conf'):
                self.assertEqual(self.client.get(self.url+suffix).status_code,200)
            with self.app.extensions['panel_db']() as connection:
                row=connection.execute('SELECT state,manual_paused,expires_at,traffic_limit_bytes,rx,tx FROM devices WHERE id=?',(self.device['id'],)).fetchone()
            self.assertEqual(tuple(row),(state,1,1,1,17,29))

    def test_unknown_format_and_malformed_export_fail_without_leaking_or_creating(self):
        count = len(self.rpc.rows)
        self.assertEqual(self.client.get(self.url+'?format=unknown').status_code,400)
        self.export_value = 'vpn://THIS_IS_NOT_A_VALID_EXPORT'
        response = self.client.get(self.url+'?format=conf')
        self.assertEqual(response.status_code,503)
        self.assertNotIn(self.export_value.encode(),response.data)
        self.assertEqual(len(self.rpc.rows),count)

    def test_conf_download_is_scoped_to_owner_and_closed_cabinets_are_denied(self):
        uid=self.post('/api/users',{'username':'synthetic-helper','password':'ordinary-test-password'}).json['id']
        other=self.app.test_client()
        self.assertEqual(other.post('/api/login',json={'username':'synthetic-helper','password':'ordinary-test-password'},headers={'Origin':'http://localhost'}).status_code,200)
        self.assertEqual(other.get(self.url+'?format=conf').status_code,404)
        self.assertEqual(self.client.patch('/api/users/'+str(uid),json={'enabled':False},headers=self.headers).status_code,200)
        self.assertEqual(other.get(self.url+'?format=conf').status_code,401)

    def test_revoked_legacy_and_pending_downloads_remain_denied(self):
        self.assertEqual(self.app.test_client().get(self.url+'?format=conf').status_code,401)
        for state in ('pending','error','revoked'):
            with self.app.extensions['panel_db']() as connection:
                connection.execute('UPDATE devices SET state=? WHERE id=?',(state,self.device['id']))
            self.assertNotEqual(self.client.get(self.url+'?format=conf').status_code,200)
        with self.app.extensions['panel_db']() as connection:
            connection.execute("UPDATE devices SET state='active',legacy=1 WHERE id=?",(self.device['id'],))
        self.assertEqual(self.client.get(self.url+'?format=conf').status_code,409)
