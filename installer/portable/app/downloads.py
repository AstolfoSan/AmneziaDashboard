"""Resolve public installers from the official latest stable GitHub release."""
import json
import re
import threading
import time
import urllib.parse
import urllib.request

API='https://api.github.com/repos/amnezia-vpn/amnezia-client/releases/latest'
REPOSITORY_PATH='/amnezia-vpn/amnezia-client/releases/download/'
APP_STORE='https://apps.apple.com/us/app/amneziavpn/id1600529900'
PLATFORMS=('android','ios','windows','macos','linux')
ANDROID=re.compile(r'_android(?:(\d+)(\+|-(\d+))?)?_(arm64-v8a|armeabi-v7a|x86_64|x86|universal)\.apk$',re.I)

class DownloadUnavailable(Exception):pass

def fetch_release():
    req=urllib.request.Request(API,headers={'User-Agent':'Kontur-Amnezia-downloads','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
    with urllib.request.urlopen(req,timeout=4) as response:raw=response.read(1048577)
    if len(raw)>1048576:raise DownloadUnavailable('Oversized release response')
    return json.loads(raw)

class ReleaseDownloads:
    def __init__(self,fetch=fetch_release,clock=time.monotonic,ttl=900):
        self.fetch=fetch;self.clock=clock;self.ttl=ttl;self.lock=threading.Lock()
        self.cached=None;self.checked_at=0;self.retry_at=0
    def latest(self):
        with self.lock:
            now=self.clock()
            if self.cached and now-self.checked_at<self.ttl:return self.cached
            if now<self.retry_at:raise DownloadUnavailable('GitHub temporarily unavailable')
            try:
                data=self.fetch()
                if not isinstance(data,dict) or data.get('draft') or data.get('prerelease') or not re.fullmatch(r'[A-Za-z0-9_.+-]{1,80}',str(data.get('tag_name',''))):raise DownloadUnavailable('Not a stable release')
                if not isinstance(data.get('assets'),list) or len(data['assets'])>200:raise DownloadUnavailable('Invalid asset list')
                self.cached=data;self.checked_at=now;self.retry_at=0
                return data
            except Exception as e:
                self.retry_at=now+60
                raise DownloadUnavailable('Cannot check current official release') from e
    @staticmethod
    def safe_asset(asset,tag):
        if not isinstance(asset,dict):return False
        name=asset.get('name','');url=asset.get('browser_download_url','')
        if not isinstance(name,str) or not isinstance(url,str) or not name.startswith('AmneziaVPN_') or not re.fullmatch(r'[A-Za-z0-9_.+-]+',name):return False
        p=urllib.parse.urlsplit(url);prefix=REPOSITORY_PATH+urllib.parse.quote(tag,safe='')+'/'
        return p.scheme=='https' and p.netloc=='github.com' and not p.query and not p.fragment and p.path.startswith(prefix) and urllib.parse.unquote(p.path[len(prefix):])==name
    def resolve(self,platform,arch=None,android_os=None):
        if platform not in PLATFORMS:raise ValueError('Unsupported platform')
        if platform=='ios':return {'platform':platform,'url':APP_STORE,'name':'AmneziaVPN · App Store','hint':'App Store · iPhone / iPad'}
        data=self.latest();assets=[a for a in data['assets'] if self.safe_asset(a,data['tag_name'])]
        if platform=='android':
            arch=arch or 'arm64-v8a'
            if arch not in {'arm64-v8a','armeabi-v7a','x86','x86_64','universal'}:raise ValueError('Unsupported Android architecture')
            candidates=[]
            for a in assets:
                m=ANDROID.search(a['name'])
                if not m:continue
                low=int(m[1] or 0);high=int(m[3]) if m[3] else None;abi=m[4].lower()
                if abi not in {arch,'universal'}:continue
                if android_os is not None and (android_os<low or (high is not None and android_os>high)):continue
                if android_os is None and high is not None:continue
                candidates.append(((int(abi=='universal'),low),a,low,high))
            if not candidates:raise DownloadUnavailable('No matching Android installer')
            _,asset,low,high=max(candidates,key=lambda a:a[0])
            suffix=('Android '+str(low)+('–'+str(high) if high else '+')) if low else 'Android'
            hint='APK · '+suffix+(' · 32 бит' if arch in {'armeabi-v7a','x86'} else '')
        else:
            arch=arch or 'x64'
            if arch not in {'x64','arm64'}:raise ValueError('Unsupported architecture')
            formats={'windows':('exe','msi'),'macos':('pkg','dmg','zip'),'linux':('run','AppImage','deb','rpm')};candidates=[]
            for a in assets:
                m=re.search('_'+platform+r'_(x64|x86_64|amd64|arm64|aarch64|universal)\.(exe|msi|pkg|dmg|zip|run|AppImage|deb|rpm)$',a['name'],re.I)
                if not m:continue
                abi=m[1].lower();ext=m[2].lower();order=[x.lower() for x in formats[platform]]
                desired={'x64','x86_64','amd64'} if arch=='x64' else {'arm64','aarch64'}
                if abi not in desired|{'universal'} or ext not in order:continue
                candidates.append(((int(abi=='universal'),-order.index(ext)),a,ext,abi))
            if not candidates:raise DownloadUnavailable('No matching installer')
            _,asset,ext,abi=max(candidates,key=lambda a:a[0])
            hint=ext.upper()+' · '+('универсальный' if abi=='universal' else arch)
        return {'platform':platform,'url':asset['browser_download_url'],'name':asset['name'],'hint':hint,'version':data['tag_name']}
    def metadata(self):
        data=self.latest();available={}
        for platform in PLATFORMS:
            try:available[platform]=self.resolve(platform)
            except DownloadUnavailable:continue
        return {'version':data['tag_name'],'platforms':available,'refresh_interval_seconds':self.ttl}
