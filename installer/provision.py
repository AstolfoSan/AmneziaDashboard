"""Two-node installation state machine; every READY result requires live checks."""
import base64
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import secrets
import stat
import shutil
import sys
import tempfile
import time
import urllib.request
import urllib.error
import http.cookiejar
import uuid
import zlib
from model import InstallError
from transport import Remote
from crypto_config import vpn_configs,mutual_tls,ssh_key
import versions

ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
VPNROOT='/opt/amnezia-dashboard-vpn';PANELROOT='/opt/amnezia-dashboard'

def exists(remote,path):
    try:return remote.sftp.stat(path)
    except FileNotFoundError:return None

def read_inventory(remote):
    release=dict(line.split('=',1) for line in remote.read('/etc/os-release').decode().splitlines() if '=' in line)
    mem=dict(line.replace(':','').split()[:2] for line in remote.read('/proc/meminfo').decode().splitlines())
    paths=['/opt/amnezia','/etc/amnezia','/opt/amnezia-panel','/opt/amnezia-dashboard','/opt/amnezia-dashboard-vpn',
           '/opt/amnezia-dashboard-agent','/etc/amnezia-dashboard','/var/lib/amnezia-dashboard-agent',
           '/etc/systemd/system/amnezia-dashboard-expiry.service','/etc/systemd/system/amnezia-dashboard-expiry.timer',
           '/etc/systemd/system/amnezia-dashboard-cert-renew.service','/etc/systemd/system/amnezia-dashboard-cert-renew.timer',
           '/etc/systemd/system/amnezia-dashboard-cascade-filter.service',
           '/etc/apt/keyrings/amnezia-dashboard-docker.asc','/etc/apt/sources.list.d/amnezia-dashboard-docker.sources']
    architecture=remote.run(['uname','-m']).decode().strip()
    tun=exists(remote,'/dev/net/tun')
    docker=exists(remote,'/var/lib/docker/containers')
    free=int(remote.run(['df','-Pk','/']).decode().splitlines()[-1].split()[3])*1024
    return {'uid':int(remote.run(['id','-u'])),'os':release.get('ID','').strip('"'),'version':release.get('VERSION_ID','').strip('"'),
            'architecture':{'x86_64':'amd64','aarch64':'arm64'}.get(architecture,architecture),
            'cpus':int(remote.run(['getconf','_NPROCESSORS_ONLN'])),'ram_mib':int(mem['MemTotal'])//1024,
            'available_mib':int(mem['MemAvailable'])//1024,'free_disk_gib':free/1024**3,
            'tun':bool(tun and stat.S_ISCHR(tun.st_mode)),'existing_paths':[p for p in paths if exists(remote,p)],
            'existing_containers':len(remote.sftp.listdir('/var/lib/docker/containers')) if docker else 0,
            'links':json.loads(remote.run(['ip','-j','link'])),'routes':json.loads(remote.run(['ip','-j','route'])),
            'rules':json.loads(remote.run(['ip','-j','rule'])),'listeners':remote.run(['ss','-H','-lntu']).decode(),
            'python_present':bool(exists(remote,'/usr/bin/python3'))}

def validate_inventory(info,settings,node):
    if info['uid']!=0 or info['os']!='ubuntu' or info['version']!='24.04':raise InstallError('Поддерживаются новые VPS Ubuntu 24.04 с доступом root')
    if info['architecture'] not in {'amd64','arm64'}:raise InstallError('Поддерживаются amd64 и arm64')
    if info['available_mib']<480 or info['free_disk_gib']<3:raise InstallError('Нужно минимум около 1 ГБ RAM и 3 ГБ свободного диска')
    if not info['tun']:raise InstallError('На VPS нет /dev/net/tun. Включите TUN в панели хостинга')
    if info['existing_paths'] or info['existing_containers']:raise InstallError('Найдена существующая VPN/Docker-установка. Автоматическая перезапись запрещена')
    if any(r.get('priority') not in {0,32766,32767} for r in info['rules']):raise InstallError('На VPS уже есть policy-routing. Нужна ручная проверка')
    if any(link.get('linkinfo',{}).get('info_kind') in {'tun','wireguard','amneziawg'} for link in info['links']):raise InstallError('На VPS уже есть VPN-интерфейсы')
    needed={(settings.vpn_port,'udp')} if node=='entry' or settings.mode=='direct' else {(settings.relay_port,'tcp')}
    if node=='foreign':needed|={(80,'tcp'),(settings.panel_port,'tcp')}
    for line in info['listeners'].splitlines():
        fields=line.split()
        if len(fields)>4:
            try:number=int(fields[4].rsplit(':',1)[1])
            except ValueError:continue
            if (number,fields[0]) in needed:raise InstallError('Нужный порт уже занят: '+str(number)+'/'+fields[0])

def networks(inventories):
    occupied=[]
    for info in inventories:
        for route in info['routes']:
            dst=route.get('dst','default')
            if dst=='default':continue
            try:occupied.append(ipaddress.IPv4Network(dst,strict=False))
            except ValueError:pass
    selected=[]
    for prefix,candidates in [(28,['172.30.'+str(n)+'.0/28' for n in range(220,250)]),
                              (28,['172.31.'+str(n)+'.0/28' for n in range(220,250)]),
                              (24,['10.241.'+str(n)+'.0/24' for n in range(32)] + ['192.168.'+str(n)+'.0/24' for n in range(200,240)]),
                              (30,['10.242.'+str(n)+'.0/30' for n in range(32)] + ['192.168.'+str(n)+'.0/30' for n in range(150,190)])]:
        choice=next((ipaddress.IPv4Network(value) for value in candidates if not any(ipaddress.IPv4Network(value).overlaps(n) for n in occupied+selected)),None)
        if choice is None:raise InstallError('Не удалось подобрать свободные подсети без изменения существующих маршрутов')
        selected.append(choice)
    return dict(zip(('panel','vpn','clients','outer'),map(str,selected)))

def dockerfile(lock):
    return ('FROM '+lock['awg']['image']+' AS official_awg\nFROM '+lock['alpine']['image']+'''\nRUN apk add --no-cache python3 iproute2 iptables curl ca-certificates
COPY --from=official_awg /usr/bin/amneziawg-go /usr/bin/amneziawg-go
COPY --from=official_awg /usr/bin/awg /usr/bin/awg
COPY vpn_runtime.py relay.py /usr/local/share/amnezia-dashboard/
ENV AMDASH_PRIVATE_NETNS=1 PYTHONUNBUFFERED=1
CMD ["python3","/usr/local/share/amnezia-dashboard/vpn_runtime.py"]
''')

def vpn_compose(spec,net):
    role=spec['role'];ports=[str(spec['vpn_port'])+':'+str(spec['vpn_port'])+'/udp'] if role in {'direct','cascade-entry'} else [str(spec['relay_port'])+':24443/tcp']
    return {'name':'amnezia-dashboard-vpn','services':{'vpn':{'image':spec['vpn_image'],'container_name':'amnezia-dashboard-vpn',
            'restart':'unless-stopped','labels':{'amnezia-dashboard.install':spec['run_id']},'read_only':True,
            'cap_drop':['ALL'],'cap_add':['NET_ADMIN'],'devices':['/dev/net/tun:/dev/net/tun'],
            'security_opt':['no-new-privileges:true'],'volumes':['./data:/opt/amnezia'],
            'tmpfs':['/run:rw,size=16m,mode=755','/tmp:rw,size=8m,mode=1777'],
            'sysctls':{'net.ipv4.ip_forward':'1','net.ipv4.conf.all.rp_filter':'0','net.ipv4.conf.default.rp_filter':'0'},
            'mem_limit':str(spec['vpn_ram_mib'])+'m','cpus':spec['vpn_cpu'],'pids_limit':128,'ports':ports,
            'networks':{'vpn':{'ipv4_address':spec['vpn_ip']}},'logging':{'driver':'json-file','options':{'max-size':'3m','max-file':'2'}},
            'healthcheck':{'test':['CMD','python3','/usr/local/share/amnezia-dashboard/vpn_runtime.py','--health'],'interval':'15s','timeout':'4s','retries':3}}},
            'networks':{'vpn':{'name':'amnezia-dashboard-vpn-net','ipam':{'config':[{'subnet':net}]}}}}

def cert_hook(ip):
    ipaddress.IPv4Address(ip)
    return '''import os,subprocess
from pathlib import Path
os.environ['DOCKER_HOST']='unix:///var/run/docker.sock';os.environ.pop('DOCKER_CONTEXT',None)
os.environ['PATH']='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
root=Path('/opt/amnezia-dashboard/certs');os.chown(root,0,101);root.chmod(0o750)
for name in ('fullchain.pem','key.pem'):
 p=root/name;os.chown(p,0,101);p.chmod(0o640)
def run(args):return subprocess.check_output(args,stderr=subprocess.DEVNULL)
run(['openssl','x509','-in',str(root/'fullchain.pem'),'-noout','-checkip','''+repr(ip)+'''])
run(['openssl','x509','-in',str(root/'fullchain.pem'),'-noout','-checkend','86400'])
if run(['openssl','x509','-in',str(root/'fullchain.pem'),'-pubkey','-noout'])!=run(['openssl','pkey','-in',str(root/'key.pem'),'-pubout']):raise RuntimeError('Certificate/key mismatch')
run(['docker','exec','amnezia-dashboard-web','nginx','-c','/config/nginx.conf','-t']);run(['docker','exec','amnezia-dashboard-web','nginx','-c','/config/nginx.conf','-s','reload'])
'''

class Runner:
    def __init__(self,settings,home,status,approve_host,approve_plan,cancel,remote_class=Remote,resolver=versions.discover):
        self.settings=settings.validate();self.home=Path(home);self.status=status;self.approve_host=approve_host
        self.approve_plan=approve_plan;self.cancel=cancel;self.remote_class=remote_class;self.resolver=resolver
        self.run_id=secrets.token_hex(6);self.work='/root/amnezia-dashboard-installer-'+self.run_id
        self.session=self.home/'sessions'/self.run_id;self.remotes={};self.created=False;self.probe_started=False;self.test_id=None
    def log(self,message):self.status(message)
    def checkpoint(self):
        if self.cancel.is_set():raise InstallError('Остановлено между этапами. Созданные данные сохранены, чужие службы не затронуты')
    def mkdir(self,remote,path,mode=0o700):
        remote.run(['mkdir','-p',path]);remote.sftp.chmod(path,mode)
    def put(self,remote,path,value,public=False):
        self.mkdir(remote,str(Path(path).parent).replace('\\','/'))
        remote.put(path,value.encode() if isinstance(value,str) else value,0o644 if public else 0o600)
    def tree(self,remote,local,destination):
        self.mkdir(remote,destination,0o755)
        for path in Path(local).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                target=destination+'/'+path.relative_to(local).as_posix();self.mkdir(remote,target.rsplit('/',1)[0],0o755)
                remote.put(target,path.read_bytes(),0o644)
    def action(self,node,action,timeout=2400,cleanup=False):
        if not cleanup:self.checkpoint()
        try:raw=self.remotes[node].run(['python3',self.work+'/node_install.py',self.work,action],timeout=timeout)
        except Exception as error:raise InstallError('Не завершён этап '+action+' ('+node+'). Приватный журнал на VPS: '+self.work+'/install.log') from error
        result=json.loads(raw)
        if result.get('error'):raise InstallError('Этап '+action+' не завершён; приватный журнал: '+self.work+'/install.log')
        journal=self.session/'stages.jsonl'
        with journal.open('a',encoding='utf-8') as stream:stream.write(json.dumps({'node':node,'stage':action,'ok':True})+'\n')
        journal.chmod(0o600)
        return result
    def backup(self,node,after=False):
        if after:result=self.action(node,'after-backup')
        else:
            remote=self.remotes[node];archive=self.work+'/before-install.tar.gz'
            paths=[p for p in ('/root/.ssh/authorized_keys','/etc/ssh','/etc/ufw','/etc/docker','/etc/sysctl.conf','/etc/sysctl.d','/etc/systemd/system','/etc/apt/sources.list.d') if exists(remote,p)]
            self.put(remote,self.work+'/packages-before.txt',remote.run(['dpkg-query','-W']))
            self.put(remote,self.work+'/routes-before.json',remote.run(['ip','-j','route']))
            self.put(remote,self.work+'/rules-before.json',remote.run(['ip','-j','rule']))
            extra=[self.work+'/'+n for n in ('packages-before.txt','routes-before.json','rules-before.json')]
            for binary in ('/usr/sbin/iptables-save','/sbin/iptables-save'):
                if exists(remote,binary):
                    self.put(remote,self.work+'/iptables-before.txt',remote.run([binary]));extra.append(self.work+'/iptables-before.txt');break
            remote.run(['tar','-czpf',archive,'-C','/',*[p.lstrip('/') for p in paths+extra]])
            remote.sftp.chmod(archive,0o600)
            result={'archive':archive,'bytes':remote.sftp.stat(archive).st_size,'sha256':remote.run(['sha256sum',archive]).decode().split()[0]}
        path=self.session/(node+('-after-private.tar.gz' if after else '-before-private.tar.gz'))
        expected=self.work+('/after-install-private.tar.gz' if after else '/before-install.tar.gz')
        if result['archive']!=expected or not 0<result['bytes']<=256*1024**2:raise InstallError('Непредвиденный путь или размер резервной копии')
        self.remotes[node].get(result['archive'],path)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=result['sha256']:raise InstallError('Контрольная сумма резервной копии не совпала')
    def agent(self,payload):
        target='entry' if self.settings.mode=='cascade' else 'foreign'
        raw=self.remotes[target].run(['/usr/bin/env','-i','PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
            'DOCKER_HOST=unix:///var/run/docker.sock','AMNEZIA_AGENT_CONFIG=/etc/amnezia-dashboard/agent.json',
            '/opt/amnezia-dashboard-agent/venv/bin/python','-E','-s','/opt/amnezia-dashboard-agent/agent.py'],input_data=(json.dumps(payload)+'\n').encode())
        reply=json.loads(raw)
        if not reply.get('ok'):raise InstallError('VPN-агент не подтвердил операцию')
        return reply['result']
    def tests(self,expected,net):
        self.log('Проверка нового тестового VPN-клиента и реального HTTPS-трафика…')
        self.test_id=str(uuid.uuid4());self.agent({'action':'create','id':self.test_id,'name':'Installer disposable self-test'})
        value=self.agent({'action':'export','id':self.test_id})['vpn'];encoded=value[6:]
        raw=base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4))
        doc=json.loads(zlib.decompress(raw[4:]))
        native=json.loads(doc['containers'][0]['awg']['last_config'])['config']
        endpoint=self.settings.entrance.host
        if self.settings.mode=='direct':
            endpoint=str(ipaddress.IPv4Network(net['vpn']).network_address+2)
            native=native.replace('Endpoint = '+self.settings.foreign.host+':','Endpoint = '+endpoint+':')
        remote=self.remotes['foreign'];self.put(remote,self.work+'/probe/probe.conf',native)
        self.put(remote,self.work+'/probe/node.json',json.dumps({'role':'probe','endpoint':endpoint}))
        self.probe_started=True;self.action('foreign','probe-start')
        for attempt in range(3):
            try:
                if self.action('foreign','probe-ip')['ip']==expected:break
                raise InstallError('Получен неожиданный выходной IP')
            except Exception:
                if attempt==2:raise
                time.sleep(3)
        if self.settings.mode=='cascade':
            self.log('Проверка fail-closed: без зарубежного туннеля RU не должен выпускать трафик…')
            self.action('entry','link-down')
            try:
                if not self.action('foreign','probe-blocked').get('blocked'):raise InstallError('Fail-closed проверка не пройдена')
            finally:self.action('entry','link-up',cleanup=True)
            time.sleep(3)
            if self.action('foreign','probe-ip')['ip']!=expected:raise InstallError('Каскад не восстановился после fail-closed теста')
        self.agent({'action':'access','id':self.test_id,'paused':True})
        if not self.action('foreign','probe-blocked').get('blocked'):raise InstallError('Приостановка тестового клиента не сработала')
        self.agent({'action':'access','id':self.test_id,'paused':False})
        if self.agent({'action':'export','id':self.test_id})['vpn']!=value:raise InstallError('Тестовый профиль изменился при снятии паузы')
        self.action('foreign','probe-reconnect')
        if self.action('foreign','probe-ip')['ip']!=expected:raise InstallError('Клиент не восстановился после паузы')
        self.log('Проверка автоматического окончания доступа локальным таймером…')
        self.agent({'action':'access','id':self.test_id,'expires_at':int(time.time())+3})
        time.sleep(22)
        if not self.action('foreign','probe-blocked').get('blocked'):raise InstallError('Таймер окончания доступа не сработал')
        self.agent({'action':'access','id':self.test_id,'expires_at':None})
        self.action('foreign','probe-reconnect')
        if self.agent({'action':'export','id':self.test_id})['vpn']!=value:raise InstallError('Профиль изменился при продлении')
        if self.action('foreign','probe-ip')['ip']!=expected:raise InstallError('Не восстановлен доступ после продления')
        self.agent({'action':'revoke','id':self.test_id});self.test_id=None
        self.action('foreign','probe-stop');self.probe_started=False
    def run(self):
        self.session.mkdir(parents=True,mode=0o700)
        try:
            self.log('Проверка последних стабильных релизов официальных источников…');lock=self.resolver()
            self.log('AmneziaVPN '+lock['amnezia_client']['tag']+'; серверный образ закреплён по digest')
            inventory={}
            for name,login in [('foreign',self.settings.foreign)]+([('entry',self.settings.entry)] if self.settings.mode=='cascade' else []):
                self.checkpoint();self.log('Проверка SSH и чистоты '+('зарубежного' if name=='foreign' else 'RU')+' VPS…')
                remote=self.remote_class(login,self.home/'known_hosts',self.approve_host).connect();self.remotes[name]=remote
                info=read_inventory(remote);validate_inventory(info,self.settings,name);inventory[name]=info
                required=('awg','alpine','python','nginx') if name=='foreign' else ('awg','alpine')
                if any(info['architecture'] not in lock[key]['platforms'] for key in required):raise InstallError('Официальные образы недоступны для архитектуры VPS')
            net=networks(inventory.values());plan={**self.settings.public_plan(),'versions':lock,'networks':net}
            if not self.approve_plan(plan):raise InstallError('Установка не подтверждена')
            (self.session/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
            self.plan=plan;self.specs={}
            vpn_ip=str(ipaddress.IPv4Network(net['vpn']).network_address+2)
            for name,remote in self.remotes.items():
                role='direct' if self.settings.mode=='direct' else 'cascade-exit' if name=='foreign' else 'cascade-entry'
                info=inventory[name]
                spec={'run_id':self.run_id,'role':role,'host_is_panel':name=='foreign','versions':lock,
                      'public_ip':remote.login.host,'entry_public_ip':self.settings.entrance.host,
                      'vpn_port':self.settings.vpn_port,'panel_port':self.settings.panel_port,'relay_port':self.settings.relay_port,
                      'vpn_image':'local/amnezia-dashboard-vpn:'+self.run_id,'vpn_ip':vpn_ip,
                      'vpn_ram_mib':min(512,max(128,int(info['ram_mib']*.30))),'vpn_cpu':max(.5,info['cpus']-.35),
                      'ssh_port':remote.login.port,'agent_source':'','email':self.settings.email}
                self.specs[name]=spec;self.mkdir(remote,self.work)
                self.put(remote,self.work+'/node_install.py',(ROOT/'node_install.py').read_bytes(),True)
                self.put(remote,self.work+'/node-spec.json',json.dumps(spec))
            self.log('Создание и проверка резервных копий до установки…')
            for name in self.remotes:self.backup(name)
            self.created=True;outside={}
            for name in self.remotes:
                if not inventory[name]['python_present']:
                    self.log('Установка Python после резервного копирования: '+name+'…')
                    self.remotes[name].run(['env','DEBIAN_FRONTEND=noninteractive','apt-get','update','-qq'],timeout=1200)
                    self.remotes[name].run(['env','DEBIAN_FRONTEND=noninteractive','apt-get','install','-y','--no-install-recommends','python3'],timeout=1200)
                self.log('Установка Docker и необходимых пакетов: '+name+'…');outside[name]=self.action(name,'prepare')['outside_ip']
            for name,remote in self.remotes.items():
                self.put(remote,self.work+'/vpn-image/Dockerfile',dockerfile(lock),True)
                for filename in ('vpn_runtime.py','relay.py'):self.put(remote,self.work+'/vpn-image/'+filename,(ROOT/filename).read_bytes(),True)
                self.log('Сборка актуального AmneziaWG на '+name+'…');self.action(name,'build')
            self.configure_nodes(net,outside)
            if self.settings.mode=='cascade':self.action('foreign','firewall');self.action('foreign','vpn-up')
            entry='entry' if self.settings.mode=='cascade' else 'foreign'
            self.action(entry,'firewall');self.action(entry,'vpn-up');self.action(entry,'agent')
            self.tests(outside['foreign'],net)
            self.log('Автоматический HTTPS по IP и запуск панели на зарубежном VPS…')
            self.action('foreign','panel')
            result=self.finish_panel(plan['panel_url'])
            self.log('Итоговые приватные резервные копии и проверки таймеров…')
            for name in self.remotes:self.action(name,'check-timers');self.backup(name,True)
            private={'url':plan['panel_url'],'username':'owner','password':result,'run_id':self.run_id,'mode':self.settings.mode,'backup_directory':str(self.session)}
            target=self.session/'result-private.json';target.write_text(json.dumps(private,ensure_ascii=False,indent=2),encoding='utf-8');target.chmod(0o600)
            self.log('Установка завершена. Тестовый клиент удалён; панель готова к выдаче профилей.')
            return private
        except Exception:
            if self.test_id:
                try:self.agent({'action':'revoke','id':self.test_id})
                except Exception:pass
            if self.probe_started:
                try:self.action('foreign','probe-stop',cleanup=True)
                except Exception:pass
            if self.created:
                for name in self.remotes:
                    try:self.action(name,'stop-owned',cleanup=True)
                    except Exception:pass
            raise
        finally:
            for remote in self.remotes.values():remote.close()

    def configure_nodes(self,net,outside):
        source=ROOT/'portable';spec=importlib.util.spec_from_file_location('dashboard_portable_configure',source/'configure.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        same=self.settings.mode=='direct';entry='foreign' if same else 'entry';entry_remote=self.remotes[entry]
        config={'mode':self.settings.mode,'public_origin':self.plan['panel_url'],'panel_bind_ip':'0.0.0.0','publish_http_challenge':True,
                'panel_network_cidr':net['panel'],'route_label':'Зарубежный VPS' if same else 'RU → Зарубежный VPS',
                'agent':{'same_host':same,'ssh_host':'host.docker.internal' if same else self.settings.entry.host,
                         'ssh_port':self.settings.entrance.port,'ssh_user':'root',**({} if same else {'source_cidr':outside['foreign']+'/32'})},
                'vpn':{'public_host':self.settings.entrance.host,'container':'amnezia-dashboard-vpn','interface':'awg0','state_dir':'/var/lib/amnezia-dashboard-agent'},
                'images':{'python':self.plan['versions']['python']['image'],'nginx':self.plan['versions']['nginx']['image']}}
        with tempfile.TemporaryDirectory(prefix='amnezia-installer-render-') as temp:
            directory=Path(temp)/'deployment';module.render(config,directory)
            compose=json.loads((directory/'compose.yaml').read_text())
            for service in compose['services'].values():service.setdefault('labels',{})['amnezia-dashboard.install']=self.run_id
            web=compose['services']['web']
            web['volumes']=['./nginx:/config:ro' if item=='./nginx.conf:/etc/nginx/nginx.conf:ro' else item for item in web['volumes']]
            web['entrypoint']=['nginx','-c','/config/nginx.conf','-g','daemon off;']
            (directory/'compose.yaml').write_text(json.dumps(compose),encoding='utf-8')
            self.action('foreign','stage-panel');self.tree(self.remotes['foreign'],directory,PANELROOT)
            self.put(self.remotes['foreign'],PANELROOT+'/cert_deploy.py',cert_hook(self.settings.foreign.host),True)
            self.tree(entry_remote,directory/'agent',self.work+'/agent')
            for filename in ('agent.json','amnezia-dashboard-expiry.service','amnezia-dashboard-expiry.timer'):
                self.put(entry_remote,self.work+'/'+filename,(directory/filename).read_bytes())
            key=ssh_key();key_line=(directory/'authorized-key.example').read_text().replace('<NEW-PUBLIC-KEY>',key['public'])
            self.put(entry_remote,self.work+'/authorized-key.txt',key_line)
            self.put(self.remotes['foreign'],PANELROOT+'/secrets/agent_key',key['private'])
            alias='host.docker.internal' if same else self.settings.entry.host
            self.put(self.remotes['foreign'],PANELROOT+'/secrets/agent_known_hosts',entry_remote.host_key_line(alias,self.settings.entrance.port))
            agent_source=str(ipaddress.IPv4Network(net['panel']).network_address+2)+'/32' if same else outside['foreign']+'/32'
            self.specs[entry]['agent_source']=agent_source
        files=vpn_configs(self.settings,net['clients'],net['outer'])
        tls=mutual_tls(self.settings.foreign.host) if not same else None
        for name,remote in self.remotes.items():
            if self.settings.mode=='cascade':self.specs[name]['entry_public_ip']=outside['entry']
            spec=self.specs[name];self.put(remote,self.work+'/node-spec.json',json.dumps(spec))
            role=spec['role'];contents=files['entry' if name==entry else 'foreign']
            for filename,text in contents.items():self.put(remote,VPNROOT+'/data/'+filename,text)
            self.put(remote,VPNROOT+'/data/node.json',json.dumps({'role':role,'client_subnet':net['clients']}))
            self.put(remote,VPNROOT+'/compose.json',json.dumps(vpn_compose(spec,net['vpn'])))
            if tls:
                kind='client' if name=='entry' else 'server'
                for filename in ('ca.pem',kind+'.pem',kind+'.key'):self.put(remote,VPNROOT+'/data/tls/'+filename,tls[filename])
                relay={'role':kind,'cert_dir':'/opt/amnezia/tls','awg_port':51821}
                relay.update({'host':self.settings.foreign.host,'port':self.settings.relay_port,'local_port':15543} if kind=='client' else {'port':24443})
                self.put(remote,VPNROOT+'/data/relay.json',json.dumps(relay))

    def finish_panel(self,url):
        password=self.remotes['foreign'].read(PANELROOT+'/data/bootstrap-password.txt').decode().strip()
        jar=http.cookiejar.CookieJar();opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        def api(path,body=None,csrf=None):
            headers={'Origin':url,'Content-Type':'application/json'}
            if csrf:headers['X-CSRF-Token']=csrf
            request=urllib.request.Request(url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
            with opener.open(request,timeout=30) as response:return json.load(response)
        try:api('/api/dashboard')
        except urllib.error.HTTPError as error:
            if error.code!=401:raise InstallError('Неожиданный ответ проверки авторизации панели')
        else:raise InstallError('Панель открыла данные без авторизации')
        api('/api/login',{'username':'owner','password':password});csrf=api('/api/session')['csrf']
        api('/api/groups',{'name':'Мои устройства','limit':100},csrf)
        for _ in range(25):
            data=api('/api/dashboard');meta=data['meta']
            if not meta.get('sync_error') and time.time()-int(meta.get('last_sync',0))<60:break
            time.sleep(2)
        else:raise InstallError('Панель не видит VPN-агент')
        return password
