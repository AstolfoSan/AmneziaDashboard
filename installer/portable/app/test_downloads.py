import copy
from html.parser import HTMLParser
import tempfile
from pathlib import Path
import unittest
from downloads import ReleaseDownloads,DownloadUnavailable,APP_STORE
from panel import create_app

def release(version='5.0.3.0'):
    names=['android11+_arm64-v8a.apk','android11+_armeabi-v7a.apk','android9-10_arm64-v8a.apk','android9-10_armeabi-v7a.apk','windows_x64.exe','macos_x64.pkg','linux_x64.run']
    return {'tag_name':version,'prerelease':False,'draft':False,'assets':[{'name':'AmneziaVPN_'+version+'_'+n,'browser_download_url':'https://github.com/amnezia-vpn/amnezia-client/releases/download/'+version+'/AmneziaVPN_'+version+'_'+n.replace('+','%2B')} for n in names]}

class DownloadTests(unittest.TestCase):
    def test_google_play_is_additional_static_official_link(self):
        class Links(HTMLParser):
            def __init__(self):super().__init__();self.links=[]
            def handle_starttag(self,tag,attrs):
                if tag=='a':self.links.append(dict(attrs))
        html=(Path(__file__).parent/'static/join.html').read_text(encoding='utf-8')
        links=Links();links.feed(html)
        play=[a for a in links.links if a.get('href','').startswith('https://play.google.com/')]
        self.assertEqual(len(play),1)
        self.assertEqual(play[0]['href'],'https://play.google.com/store/apps/details?id=org.amnezia.vpn')
        self.assertEqual(play[0]['target'],'_blank')
        self.assertTrue({'noopener','noreferrer'}<=set(play[0]['rel'].split()))
        self.assertNotIn('data-platform',play[0])
        for platform in ('android','ios','windows','macos','linux'):
            self.assertTrue(any(a.get('href')=='/download/'+platform for a in links.links))
        self.assertIn('/download/android?os=9',html)

    def test_all_platforms_and_android_variants(self):
        d=ReleaseDownloads(fetch=release)
        self.assertEqual(d.resolve('ios')['url'],APP_STORE)
        self.assertTrue(d.resolve('android')['url'].endswith('android11%2B_arm64-v8a.apk'))
        self.assertTrue(d.resolve('android',android_os=9)['url'].endswith('android9-10_arm64-v8a.apk'))
        self.assertTrue(d.resolve('android',arch='armeabi-v7a',android_os=10)['url'].endswith('android9-10_armeabi-v7a.apk'))
        for p,ext in [('windows','exe'),('macos','pkg'),('linux','run')]:self.assertTrue(d.resolve(p)['url'].endswith('.'+ext))
        self.assertEqual(len(d.metadata()['platforms']),5)
    def test_future_release_is_selected_after_cache_expiry(self):
        clock=[1];calls=[]
        def fetch():calls.append(1);return release('5.0.3.0' if len(calls)==1 else '6.0.0.0')
        d=ReleaseDownloads(fetch=fetch,clock=lambda:clock[0]);self.assertEqual(d.resolve('windows')['version'],'5.0.3.0');d.metadata();self.assertEqual(len(calls),1)
        clock[0]=902;self.assertEqual(d.resolve('windows')['version'],'6.0.0.0');self.assertEqual(len(calls),2)
    def test_no_arbitrary_redirect_and_no_prerelease(self):
        for badurl in ['http://github.com/amnezia-vpn/amnezia-client/releases/download/5.0.3.0/AmneziaVPN_5.0.3.0_windows_x64.exe','https://evil.example/AmneziaVPN_5.0.3.0_windows_x64.exe','https://github.com/evil/repo/releases/download/x/AmneziaVPN_5.0.3.0_windows_x64.exe']:
            r=release();r['assets']=[{'name':'AmneziaVPN_5.0.3.0_windows_x64.exe','browser_download_url':badurl}]
            with self.assertRaises(DownloadUnavailable):ReleaseDownloads(fetch=lambda:r).resolve('windows')
        r=release();r['prerelease']=True
        with self.assertRaises(DownloadUnavailable):ReleaseDownloads(fetch=lambda:r).metadata()
    def test_failure_cooldown_and_ios_without_github(self):
        calls=[];clock=[1]
        def fail():calls.append(1);raise OSError('offline')
        d=ReleaseDownloads(fetch=fail,clock=lambda:clock[0])
        for _ in range(2):
            with self.assertRaises(DownloadUnavailable):d.resolve('windows')
        self.assertEqual(len(calls),1);self.assertEqual(d.resolve('ios')['url'],APP_STORE)
        clock[0]=62
        with self.assertRaises(DownloadUnavailable):d.resolve('windows')
        self.assertEqual(len(calls),2)
    def test_unsupported_arch_or_missing_asset(self):
        d=ReleaseDownloads(fetch=release)
        with self.assertRaises(ValueError):d.resolve('unknown')
        with self.assertRaises(ValueError):d.resolve('android',arch='../../x')
        with self.assertRaises(DownloadUnavailable):d.resolve('linux',arch='arm64')
        with self.assertRaises(DownloadUnavailable):d.resolve('android',android_os=8)
    def test_routes_and_friendly_failure_without_auth(self):
        with tempfile.TemporaryDirectory() as temp:
            d=ReleaseDownloads(fetch=release);app=create_app({'DATA_DIR':temp,'COLLECTOR':False,'DOWNLOADS':d});c=app.test_client()
            self.assertEqual(c.get('/api/downloads').status_code,200)
            for p in ('android','ios','windows','macos','linux'):
                r=c.get('/download/'+p);self.assertEqual(r.status_code,302);self.assertEqual(r.headers['Referrer-Policy'],'no-referrer')
            self.assertEqual(c.get('/download/unknown').status_code,404)
            self.assertEqual(c.get('/download/android?os=oops').status_code,400)
            r=c.get('/download/linux?arch=arm64');self.assertEqual(r.status_code,503);self.assertIn('Официальный релиз'.encode(),r.data);r.close()
            html=c.get('/');self.assertIn(b'/download/windows',html.data);self.assertIn(b'/download/ios',html.data);html.close()

if __name__=='__main__':unittest.main(verbosity=2)
