import tempfile
from pathlib import Path
import unittest
import zipfile
from privacy_check import inspect,scan,ROOT


class PrivacyTests(unittest.TestCase):
    def test_private_paths_and_parent_traversal_are_rejected(self):
        for name in ('data/state.json','sessions/plan.json','backup.sqlite3','client.vpn','secret.key','.env','../escape.py'):
            self.assertTrue(inspect(name,b'{}'),name)

    def test_actual_key_and_token_shapes_are_rejected_without_echoing_them(self):
        values=[b'-----BEGIN '+b'OPENSSH PRIVATE KEY-----',b'ghp_'+b'a'*36,b'vpn://'+b'a'*100]
        for payload in values:self.assertIn('credential or private identity pattern',inspect('example.py',payload))

    def test_examples_and_public_dns_are_allowed_but_other_hosts_are_not(self):
        self.assertEqual(inspect('example.json',b'{"host":"203.0.113.10","dns":"1.1.1.1"}'),[])
        payload='.'.join(('8','8','7','7')).encode()
        self.assertIn('non-example public IPv4',inspect('example.json',payload))

    def test_unreviewed_png_is_rejected(self):
        self.assertIn('unreviewed image',inspect('screenshot.png',b'not-a-reviewed-image'))

    def test_reviewed_synthetic_image_is_path_and_hash_bound(self):
        path='docs/images/dashboard-en.png';payload=(ROOT/path).read_bytes()
        self.assertEqual(inspect(path,payload),[])
        self.assertIn('unreviewed image',inspect('other/dashboard-en.png',payload))
        self.assertIn('unreviewed image',inspect(path,payload+b'changed'))

    def test_zip_members_are_scanned_not_just_the_container_name(self):
        with tempfile.TemporaryDirectory() as temp:
            archive=Path(temp)/'test.zip'
            with zipfile.ZipFile(archive,'w') as zipped:zipped.writestr('AmneziaDashboard/secrets/key.txt','private')
            report=scan(archive=archive)
            self.assertFalse(report['passed']);self.assertIn('AmneziaDashboard/secrets/key.txt',report['findings'])


if __name__=='__main__':unittest.main()
