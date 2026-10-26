"""Offline translation and verified-download regression tests."""
import ast
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parent))
import i18n,cli,windows_client
from model import Login,InstallError


class LocalizationTests(unittest.TestCase):
    def tearDown(self):i18n.set_language('ru')

    def test_all_operator_literals_are_covered(self):
        import re
        for name in ('cli.py','model.py','provision.py','transport.py','versions.py'):
            tree=ast.parse((Path(__file__).parent/name).read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='tr':
                    value=ast.literal_eval(node.args[0])
                    self.assertIsNone(re.search('[А-Яа-яЁё]',i18n.english(value)),(name,value))

    def test_english_validation_and_russian_fallback(self):
        for lang,message in [('en','Enter a valid server IPv4'),('ru','Введите корректный IPv4 сервера')]:
            i18n.set_language(lang)
            with self.assertRaises(InstallError) as caught:Login('invalid',password='SYNTHETIC_SECRET').validate()
            self.assertNotIn('SYNTHETIC_SECRET',str(caught.exception));self.assertTrue(str(caught.exception))
            self.assertEqual(str(caught.exception),i18n.tr('Введите корректный IPv4 сервера'))

    def test_english_plan_confirmation_is_explicit(self):
        i18n.set_language('en')
        with patch('builtins.input',return_value=''):self.assertFalse(cli.yes('Confirm'))
        from test_installer import settings,version_lock
        plan={**settings().public_plan(),'versions':version_lock(),'networks':{'clients':'10.241.0.0/24'}}
        with patch('builtins.print'),patch('builtins.input',return_value='yes'):self.assertFalse(cli.confirm_plan(plan))
        with patch('builtins.print'),patch('builtins.input',return_value='INSTALL'):self.assertTrue(cli.confirm_plan(plan))

    def test_language_does_not_rewrite_plans_or_secrets(self):
        from test_installer import settings
        value=settings();before=value.public_plan();password=value.foreign.password
        for lang in ('en','ru'):i18n.set_language(lang);self.assertEqual(value.public_plan(),before);self.assertEqual(value.foreign.password,password)


class WindowsClientTests(unittest.TestCase):
    def metadata(self,payload=b'official-test-bytes'):
        name='AmneziaVPN_5.0.3.0_windows_x64.exe'
        return {'tag_name':'5.0.3.0','assets':[{'name':name,'browser_download_url':windows_client.PREFIX+'5.0.3.0/'+name,'digest':'sha256:'+hashlib.sha256(payload).hexdigest(),'size':len(payload)}]}

    def response(self,value):return io.BytesIO(json.dumps(value).encode())

    def test_official_stable_asset_only(self):
        data=self.metadata()
        with patch.object(windows_client,'open_url',return_value=self.response(data)):self.assertEqual(windows_client.resolve()['size'],19)

    def test_missing_digest_and_prerelease_fail_closed(self):
        for change in ('digest','prerelease','url'):
            data=self.metadata()
            if change=='digest':data['assets'][0].pop('digest')
            elif change=='prerelease':data['prerelease']=True
            else:data['assets'][0]['browser_download_url']='https://example.com/client.exe'
            with patch.object(windows_client,'open_url',return_value=self.response(data)),self.assertRaises(ValueError):windows_client.resolve()

    def test_hash_checked_before_any_launch(self):
        data=self.metadata();asset=data['assets'][0]
        resolved={'url':asset['browser_download_url'],'size':asset['size'],'sha256':asset['digest'][7:],'name':asset['name']}
        for content,valid in [(b'official-test-bytes',True),(b'incorrect-test-byte',False)]:
            with tempfile.TemporaryDirectory() as temp,patch.object(windows_client,'resolve',return_value=resolved),patch.object(windows_client,'open_url',return_value=io.BytesIO(content)),patch.object(windows_client,'launch') as launch:
                if valid:self.assertEqual(windows_client.download(temp).read_bytes(),content)
                else:
                    with self.assertRaises(ValueError):windows_client.download(temp)
                    self.assertEqual(list(Path(temp).iterdir()),[])
                launch.assert_not_called()

    def test_redirect_rejected(self):
        response=io.BytesIO();response.url='http://example.com/client.exe'
        with patch('urllib.request.urlopen',return_value=response),self.assertRaises(ValueError):windows_client.open_url(windows_client.PREFIX+'test.exe')


if __name__=='__main__':unittest.main()
