"""Language preference never modifies stored identities, meters or VPN profiles."""
import tempfile
from pathlib import Path
import unittest
from api_i18n import current_language,error_text
from panel import create_app
import test_panel


class ApiLanguageTests(unittest.TestCase):
    def test_request_preference_and_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            app=create_app({'DATA_DIR':temp,'COLLECTOR':False})
            for headers,expected in [({},'ru'),({'Accept-Language':'en-US,en;q=0.9'},'en'),
                ({'Accept-Language':'en','Cookie':'dashboard_lang=ru'},'ru'),
                ({'Cookie':'dashboard_lang=ru','X-Dashboard-Language':'en'},'en')]:
                with app.test_request_context('/',headers=headers):self.assertEqual(current_language(),expected)
            with app.test_request_context('/',headers={'X-Dashboard-Language':'en'}):
                self.assertEqual(error_text('Войдите в кабинет'),'Sign in to continue')
                self.assertEqual(error_text('Unknown English error'),'Unknown English error')
                self.assertNotIn('Неизвестная',error_text('Неизвестная ошибка'))

    def test_unauthorized_error_and_headers(self):
        with tempfile.TemporaryDirectory() as temp:
            app=create_app({'DATA_DIR':temp,'COLLECTOR':False});client=app.test_client()
            for lang,message in [('en','Sign in to continue'),('ru','Войдите в кабинет')]:
                response=client.get('/api/dashboard',headers={'Accept-Language':lang})
                self.assertEqual(response.status_code,401);self.assertEqual(response.json['error'],message)
                self.assertEqual(response.headers['Content-Language'],lang)


class DataLanguageTests(unittest.TestCase):
    setUp=test_panel.PanelTests.setUp
    tearDown=test_panel.PanelTests.tearDown

    def test_names_profiles_and_counters_unchanged(self):
        group=self.client.post('/api/groups',json={'name':'Семья — Groups','limit':2},headers=self.headers).json['id']
        device=self.client.post('/api/devices',json={'name':'Тест — Save','group_id':group},headers=self.headers).json
        before=self.client.get('/api/devices/'+device['id']+'/download').data
        ru=self.client.get('/api/dashboard',headers={'X-Dashboard-Language':'ru'}).json
        en=self.client.get('/api/dashboard',headers={'X-Dashboard-Language':'en'}).json
        self.assertEqual(ru,en)
        self.assertEqual(self.client.get('/api/devices/'+device['id']+'/download',headers={'X-Dashboard-Language':'en'}).data,before)


if __name__=='__main__':unittest.main()
