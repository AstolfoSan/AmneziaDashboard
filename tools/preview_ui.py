"""Read-only synthetic UI for documentation. No SSH, credentials or profile issuing."""
import argparse
import base64
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import time
import zlib
from urllib.parse import urlsplit

STATIC=Path(__file__).resolve().parents[1]/'installer/portable/app/static'
DEMO_DEVICE=None
DEMO_READY=False
DEMO_LANGUAGE='ru'


def demo_native():
    raw=json.dumps({'description':'DEMO synthetic phone','hostName':'203.0.113.10',
                    'defaultContainer':'amnezia-awg','containers':[{'container':'amnezia-awg',
                    'awg':{'last_config':json.dumps({'config':'[Interface]\nPrivateKey = SYNTHETIC_NOT_A_KEY\n\n[Peer]\nPublicKey = SYNTHETIC_NOT_A_KEY\n'})}}]},ensure_ascii=False).encode()
    return 'vpn://'+base64.urlsafe_b64encode(len(raw).to_bytes(4,'big')+zlib.compress(raw)).decode().rstrip('=')


def dashboard():
    now=int(time.time());minute=now//60*60
    groups=[{'id':1,'name':'Existing profiles','owner_id':1,'owner_name':'owner','device_limit':0,'enabled':False,'rx':0,'tx':0,'link':None},
            {'id':2,'name':'Family','owner_id':1,'owner_name':'owner','device_limit':10,'default_access_days':30,'enabled':True,'rx':125829120,'tx':1572864000,'link':'/j/demo'},
            {'id':3,'name':'Office','owner_id':2,'owner_name':'demo-admin','device_limit':25,'default_access_days':None,'enabled':True,'rx':52428800,'tx':734003200,'link':'/j/demo'}]
    devices=[]
    for i,(name,gid,state,rx,tx) in enumerate([('Phone',2,'active',104857600,1363148800),('Laptop',2,'paused',20971520,209715200),('Tablet',3,'active',52428800,734003200)]):
        group=next(g for g in groups if g['id']==gid)
        devices.append({'id':'demo-device-'+str(i),'name':name,'group_id':gid,'group_name':group['name'],'owner_id':group['owner_id'],'owner_name':group['owner_name'],
                        'ip':'10.8.1.'+str(10+i),'state':state,'legacy':False,'handshake':now-35 if state=='active' else now-7200,
                        'rx':rx,'tx':tx,'online':state=='active','down_bps':65536 if i==0 else 0,'up_bps':8192 if i==0 else 0,'manual_paused':state=='paused',
                        'expires_at':now+30*86400 if gid==2 else None,'traffic_limit_bytes':None,'traffic_used_bytes':rx+tx})
    samples=[{'at':minute-i*60,'rx':(i%5+1)*81920,'tx':((i*7)%17+1)*1048576} for i in range(1440)]
    return {'devices':devices,'groups':groups,'meta':{'last_sync':now,'sync_error':None},'chart_samples':samples,
            'chart_daily':[{'at':minute//86400*86400-i*86400,'rx':(i+1)*10485760,'tx':(i+1)*104857600} for i in range(31)],
            'chart_info':{'sampled_at':now,'window_end':now,'started_at':now-31*86400,'sample_interval':60,'timezone':'Europe/Moscow'}}


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,payload,mime='application/json'):
        if isinstance(payload,(dict,list)):payload=json.dumps(payload).encode()
        self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(payload)
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/preview/mobile':
            return self.send(b'<!doctype html><html><head><meta charset="utf-8"><title>Mobile invitation preview</title></head><body style="margin:0;background:#141414"><iframe title="Mobile invitation, 390 pixels" src="/j/demo" width="390" height="2300" style="display:block;border:0;max-width:100%"></iframe></body></html>','text/html; charset=utf-8')
        if path=='/api/session':return self.send({'id':1,'username':'owner','role':'super','csrf':'DEMO_NOT_A_CREDENTIAL'})
        if path=='/api/dashboard':return self.send(dashboard())
        if path=='/api/users':return self.send({'users':[{'id':1,'username':'owner','role':'super','enabled':True,'max_devices':150},{'id':2,'username':'demo-admin','role':'admin','enabled':True,'max_devices':25}]})
        if path=='/api/audit':return self.send({'events':[{'at':int(time.time()),'username':'owner','event':'group.created','detail':'DEMO'}]})
        if path=='/api/downloads':return self.send({'version':'5.0.3.0','platforms':{}})
        if path=='/api/join/demo':return self.send({'name':'Family','default_access_days':30})
        if path in {'/api/devices/demo-device-'+str(i)+'/download' for i in range(3)} and DEMO_READY:
            value='[Interface]\nPrivateKey = '+('A'*43)+'=\nAddress = 10.8.1.13/32\nDNS = 1.1.1.1\n\n[Peer]\nPublicKey = '+('B'*43)+'=\nEndpoint = 203.0.113.10:39265\nAllowedIPs = 0.0.0.0/0\n'
            return self.send((value if 'format=conf' in self.path else demo_native()).encode(),'application/octet-stream')
        if path=='/api/receive/demo-device-0' and DEMO_READY:
            if self.headers.get('Authorization')!='Bearer DEMO_NOT_A_CREDENTIAL':return self.send_error(404)
            value='[Interface]\nPrivateKey = '+('A'*43)+'=\nAddress = 10.8.1.13/32\nDNS = 1.1.1.1\n\n[Peer]\nPublicKey = '+('B'*43)+'=\nEndpoint = 203.0.113.10:39265\nAllowedIPs = 0.0.0.0/0\n'
            return self.send((value if 'format=conf' in self.path else demo_native()).encode(),'application/octet-stream')
        if path.startswith('/api/'):return self.send_error(404)
        file='admin.html' if path=='/admin' else 'join.html' if path in {'/','/j/demo'} else path.removeprefix('/static/') if path.startswith('/static/') else ''
        target=(STATIC/file).resolve()
        if not file or not target.is_relative_to(STATIC) or not target.is_file():return self.send_error(404)
        payload=target.read_bytes()
        if target.suffix in {'.js','.html'}:
            payload=payload.replace(b'__DASHBOARD_ROUTE_LABEL__',b'Direct VPN').replace(b'__DASHBOARD_ROUTE_PATH__',b'Device -> foreign VPS -> Internet')
        if target.suffix=='.html':
            setup='localStorage.setItem("dashboard-language",'+json.dumps(DEMO_LANGUAGE)+');'
            if DEMO_DEVICE:
                ua={'ios':'iPhone; CPU iPhone OS 18_0','android':'Linux; Android 14; Chrome/130','windows':'Windows NT 10.0','macos':'Macintosh','linux':'X11; Linux x86_64'}[DEMO_DEVICE]
                setup+='Object.defineProperty(navigator,"userAgent",{value:'+json.dumps(ua)+'});'
            if DEMO_READY:
                device={'id':'demo-device-0','name':'Synthetic phone','download_token':'DEMO_NOT_A_CREDENTIAL','ready':True,'at':int(time.time()*1000),'expires_at':None}
                setup+='sessionStorage.setItem("join:demo",JSON.stringify('+json.dumps(device)+'));'
            payload=payload.replace(b'<body>',('<body><script>'+setup+'</script><div style="text-align:center;padding:6px;color:#F6A453;background:#141414">DEMO &middot; SYNTHETIC DATA &middot; READ ONLY</div>').encode())
        self.send(payload,mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
    def do_POST(self):self.send_error(405,'Read-only documentation preview')
    do_PATCH=do_POST
    do_DELETE=do_POST


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=18910)
    parser.add_argument('--device',choices=['ios','android','windows','macos','linux']);parser.add_argument('--ready',action='store_true');parser.add_argument('--lang',choices=['ru','en'],default='ru');args=parser.parse_args()
    DEMO_DEVICE=args.device;DEMO_READY=args.ready;DEMO_LANGUAGE=args.lang
    print('Synthetic preview: http://127.0.0.1:'+str(args.port)+'/admin',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
