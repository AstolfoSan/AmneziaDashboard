"""Render a NEW deployment folder. Does not SSH, install, start or edit a server."""
import argparse
import html
import ipaddress
import json
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'app'))
from portable_settings import hostname,label,port,validate_agent


def validate(raw):
    allowed={'mode','public_origin','panel_bind_ip','publish_http_challenge','panel_network_cidr','route_label','route_path','agent','vpn','images'}
    if not isinstance(raw,dict) or set(raw)-allowed:raise ValueError('Unknown deployment fields')
    if raw.get('mode') not in {'direct','cascade'}:raise ValueError('Mode must be direct or cascade')
    url=urlsplit(raw['public_origin']);host=hostname(url.hostname)
    if url.scheme!='https' or url.username or url.password or url.query or url.fragment or url.path not in {'','/'}:raise ValueError('Use a root HTTPS origin without credentials')
    tls_port=port(url.port or 443)
    bind=str(ipaddress.IPv4Address(raw.get('panel_bind_ip','0.0.0.0')))
    network=ipaddress.IPv4Network(raw.get('panel_network_cidr','172.30.240.0/28'))
    private=any(network.subnet_of(ipaddress.IPv4Network(n)) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))
    if not private or not 24<=network.prefixlen<=28:raise ValueError('Use an unused private /24 to /28 Docker subnet')
    connection=dict(raw['agent'])
    if set(connection)-{'ssh_host','ssh_port','ssh_user','same_host','source_cidr'}:raise ValueError('Unknown SSH fields')
    if type(connection.get('same_host')) is not bool:raise ValueError('same_host must be boolean')
    connection['ssh_host']=hostname(connection['ssh_host']);connection['ssh_port']=port(connection.get('ssh_port',22))
    if connection.get('ssh_user','root')!='root':raise ValueError('This worker requires root; no unrestricted sudo fallback')
    connection['ssh_user']='root'
    app_ip=str(network.network_address+2)
    if connection['same_host']:
        if connection['ssh_host']!='host.docker.internal':raise ValueError('Same-host deployment uses host.docker.internal')
        source=app_ip+'/32'
    else:
        source=str(ipaddress.IPv4Network(connection['source_cidr']))
        if ipaddress.IPv4Network(source).prefixlen!=32:raise ValueError('Restrict the agent key to the panel server source IPv4 /32')
    connection['source_cidr']=source
    name=label(raw.get('route_label','Прямой VPN' if raw['mode']=='direct' else 'Каскадный VPN'))
    route=label(raw.get('route_path','Ваше устройство → VPN-сервер → Интернет' if raw['mode']=='direct' else 'Ваше устройство → Входной сервер → Зарубежный сервер → Интернет'))
    vpn=validate_agent({**raw['vpn'],'route_label':name})
    images=raw['images']
    for image in ('python','nginx'):
        if not re.fullmatch(r'(?:docker.io/library/)?'+image+r'@sha256:[a-f0-9]{64}',images[image]):raise ValueError('Pin the official '+image+' image by digest')
    http=raw.get('publish_http_challenge',False)
    if type(http) is not bool:raise ValueError('publish_http_challenge must be boolean')
    return {**raw,'public_origin':'https://'+host+(':'+str(tls_port) if tls_port!=443 else ''),
            'panel_bind_ip':bind,'host':host,'tls_port':tls_port,'panel_network_cidr':str(network),
            'app_ip':app_ip,'web_ip':str(network.network_address+3),'agent':connection,'vpn':vpn,
            'route_label':name,'route_path':route,'publish_http_challenge':http}


def nginx(host):
    return '''worker_processes 1;
pid /tmp/nginx.pid;
error_log /dev/stderr warn;
events { worker_connections 256; }
http {
  include /etc/nginx/mime.types;
  default_type application/octet-stream;
  access_log off;
  server_tokens off;
  client_body_temp_path /tmp/body;
  proxy_temp_path /tmp/proxy;
  client_max_body_size 16k;
  keepalive_timeout 30;
  limit_req_zone $binary_remote_addr zone=api:1m rate=3r/s;
  server { listen 8080; server_name '''+host+''';
    location /.well-known/acme-challenge/ { root /acme; }
    location / { return 404; }
  }
  server { listen 10443 ssl; server_name '''+host+''';
    ssl_certificate /certs/fullchain.pem;
    ssl_certificate_key /certs/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:SSL:1m;
    ssl_session_tickets off;
    add_header Strict-Transport-Security 'max-age=86400' always;
    location / {
      limit_req zone=api burst=30 nodelay;
      limit_req_status 429;
      proxy_pass http://app:8000;
      proxy_set_header Host $http_host;
      proxy_set_header X-Forwarded-For $remote_addr;
      proxy_set_header X-Forwarded-Proto https;
      proxy_connect_timeout 3s;
      proxy_read_timeout 40s;
    }
  }
}
'''


def compose(c):
    common={'restart':'unless-stopped','read_only':True,'cap_drop':['ALL'],
            'security_opt':['no-new-privileges:true'],
            'logging':{'driver':'json-file','options':{'max-size':'5m','max-file':'2'}}}
    app={**common,'build':{'context':'./app','args':{'PYTHON_IMAGE':c['images']['python']}},
         'image':'local/amnezia-dashboard:portable-1.0.0','container_name':'amnezia-dashboard-app',
         'environment':{'PUBLIC_ORIGIN':c['public_origin'],'PANEL_DATA':'/data','AGENT_HOST':c['agent']['ssh_host'],
                        'AGENT_PORT':str(c['agent']['ssh_port']),'AGENT_USER':c['agent']['ssh_user']},
         'volumes':['./data:/data','./secrets:/run/secrets:ro'],'tmpfs':['/tmp:size=16m,mode=1777'],
         'mem_limit':'128m','cpus':.20,'pids_limit':48,
         'networks':{'panel':{'ipv4_address':c['app_ip']}},
         'healthcheck':{'test':['CMD','python','-c',"import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=3)"],
                        'interval':'60s','timeout':'5s','retries':3}}
    if c['agent']['same_host']:app['extra_hosts']=['host.docker.internal:host-gateway']
    ports=[c['panel_bind_ip']+':'+str(c['tls_port'])+':10443/tcp']
    if c['publish_http_challenge']:ports.append(c['panel_bind_ip']+':80:8080/tcp')
    web={**common,'image':c['images']['nginx'],'container_name':'amnezia-dashboard-web','entrypoint':['nginx','-g','daemon off;'],
         'user':'101:101','ports':ports,'volumes':['./nginx.conf:/etc/nginx/nginx.conf:ro','./certs:/certs:ro','./acme-webroot:/acme:ro'],
         'tmpfs':['/tmp:size=8m,mode=1777','/var/cache/nginx:size=8m,mode=0777'],'mem_limit':'48m','cpus':.05,'pids_limit':24,
         'networks':{'panel':{'ipv4_address':c['web_ip']}}}
    return {'name':'amnezia-dashboard','services':{'app':app,'web':web},
            'networks':{'panel':{'ipam':{'config':[{'subnet':c['panel_network_cidr']}]}}}}


def write(path,text):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text,encoding='utf-8',newline='\n')


def render(config,output):
    c=validate(config);output=Path(output).resolve()
    if output.is_relative_to((ROOT/'app').resolve()):raise ValueError('Output cannot be inside the app source tree')
    if output.exists():raise ValueError('Output must be a NEW directory; existing deployments are never overwritten')
    output.mkdir(parents=True)
    shutil.copytree(ROOT/'app',output/'app',ignore=shutil.ignore_patterns('test_*','__pycache__','*.pyc'))
    for path in (output/'app'/'static').iterdir():
        if path.suffix in {'.html','.js'}:
            text=path.read_text(encoding='utf-8')
            name=html.escape(c['route_label'],quote=True);route=html.escape(c['route_path'],quote=True)
            if path.suffix=='.js':
                name=name.replace('\\','\\\\').replace("'","\\'").replace('\u2028','\\u2028').replace('\u2029','\\u2029')
            text=text.replace('__DASHBOARD_ROUTE_LABEL__',name).replace('__DASHBOARD_ROUTE_PATH__',route)
            if '__DASHBOARD_' in text:raise ValueError('Unrendered UI setting')
            write(path,text)
    write(output/'compose.yaml',json.dumps(compose(c),ensure_ascii=False,indent=2)+'\n')
    write(output/'nginx.conf',nginx(c['host']))
    write(output/'agent.json',json.dumps(c['vpn'],ensure_ascii=False,indent=2)+'\n')
    (output/'agent').mkdir()
    for name in ('agent.py','portable_settings.py'):shutil.copyfile(output/'app'/name,output/'agent'/name)
    write(output/'agent'/'requirements.txt','cryptography==50.0.2\ncffi==2.1.1\npycparser==3.12\n')
    state=c['vpn']['state_dir']
    write(output/'amnezia-dashboard-expiry.service','''[Unit]
Description=Enforce AmneziaDashboard access and traffic limits
After=docker.service
Requires=docker.service
[Service]
Type=oneshot
Environment=AMNEZIA_AGENT_CONFIG=/etc/amnezia-dashboard/agent.json
Environment=DOCKER_HOST=unix:///var/run/docker.sock
ExecStart=/opt/amnezia-dashboard-agent/venv/bin/python -E -s /opt/amnezia-dashboard-agent/agent.py --enforce
Nice=10
CPUQuota=10%
MemoryMax=96M
TasksMax=32
TimeoutStartSec=45
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths='''+state+'''
RestrictAddressFamilies=AF_UNIX
''')
    write(output/'amnezia-dashboard-expiry.timer','''[Unit]
Description=Check AmneziaDashboard policies every 15 seconds
[Timer]
OnBootSec=30s
OnUnitActiveSec=15s
AccuracySec=1s
Unit=amnezia-dashboard-expiry.service
[Install]
WantedBy=timers.target
''')
    command='/usr/bin/env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin DOCKER_HOST=unix:///var/run/docker.sock AMNEZIA_AGENT_CONFIG=/etc/amnezia-dashboard/agent.json /usr/bin/nice -n 10 /opt/amnezia-dashboard-agent/venv/bin/python -E -s /opt/amnezia-dashboard-agent/agent.py'
    write(output/'authorized-key.example','from="'+c['agent']['source_cidr']+'",restrict,command="'+command+'" <NEW-PUBLIC-KEY> amnezia-dashboard-only\n')
    for name in ('data','secrets','certs','acme-webroot'):(output/name).mkdir()
    write(output/'.gitignore','data/\nsecrets/\ncerts/\n*.sqlite3*\n*.key\n')
    write(output/'DEPLOYMENT.json',json.dumps({k:c[k] for k in ('mode','public_origin','agent','vpn','panel_network_cidr','route_label','route_path')},ensure_ascii=False,indent=2)+'\n')
    shutil.copyfile(ROOT/'INSTALL_FOR_CODEX.md',output/'INSTALL_FOR_CODEX.md')
    return {'output':str(output),'mode':c['mode'],'origin':c['public_origin'],'server_changes':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();print(json.dumps(render(json.loads(Path(args.config).read_text(encoding='utf-8')),args.output),ensure_ascii=False))
