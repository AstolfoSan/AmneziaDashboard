"""Validated settings for the portable edition. Never embeds deployment secrets."""
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess


def hostname(value):
    if not isinstance(value,str) or len(value)>253 or value.startswith('-'):
        raise ValueError('Invalid hostname')
    try:
        address=ipaddress.ip_address(value)
        if address.version!=4:raise ValueError('Use IPv4 or a DNS name for this release')
        return str(address)
    except ValueError:
        if ':' in value or not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',part) for part in value.split('.')):
            raise ValueError('Use an IPv4 address or ASCII DNS hostname')
        return value


def absolute_path(value):
    if not isinstance(value,str) or not re.fullmatch(r'/[A-Za-z0-9_./-]+',value) or '..' in PurePosixPath(value).parts or value=='/':
        raise ValueError('Use a non-root absolute path without spaces or shell characters')
    return value


def port(value):
    if type(value) is not int or not 1<=value<=65535:raise ValueError('Invalid port')
    return value


def label(value):
    if not isinstance(value,str) or not 1<=len(value)<=100 or any(ord(c)<32 for c in value):
        raise ValueError('Label must be 1-100 printable characters')
    return value


def validate_agent(raw):
    allowed={'public_host','container','interface','config_path','clients_table','state_dir','route_label',
             'endpoint_port','mtu','dns1','dns2','awg_binary','protocol_version'}
    if not isinstance(raw,dict) or set(raw)-allowed:raise ValueError('Unknown agent settings')
    settings={'container':'amnezia-awg2','interface':'awg0','config_path':'/opt/amnezia/awg/awg0.conf',
              'clients_table':'/opt/amnezia/awg/clientsTable','state_dir':'/var/lib/amnezia-dashboard-agent',
              'route_label':'Прямой VPN','endpoint_port':None,'mtu':1280,'dns1':'1.1.1.1','dns2':'8.8.8.8',
              'awg_binary':'awg','protocol_version':'3.1',**raw}
    settings['public_host']=hostname(settings.get('public_host'))
    for key in ('config_path','clients_table','state_dir'):absolute_path(settings[key])
    if settings['config_path']==settings['clients_table']:raise ValueError('Config and client table must differ')
    for key,pattern in [('container',r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}'),('interface',r'[A-Za-z0-9][A-Za-z0-9_-]{0,14}')]:
        if not isinstance(settings[key],str) or not re.fullmatch(pattern,settings[key]):raise ValueError('Invalid '+key)
    if settings['awg_binary']!='awg':absolute_path(settings['awg_binary'])
    if settings['protocol_version']!='3.1':raise ValueError('Only compatible AmneziaWG 3.1 installations are supported')
    if type(settings['mtu']) is not int or not 1280<=settings['mtu']<=1500:raise ValueError('MTU must be 1280-1500')
    if settings['endpoint_port'] is not None:port(settings['endpoint_port'])
    for key in ('dns1','dns2'):ipaddress.ip_address(settings[key])
    label(settings['route_label'])
    return settings


def load_agent():
    path=Path(os.getenv('AMNEZIA_AGENT_CONFIG','/etc/amnezia-dashboard/agent.json'))
    if os.name=='posix' and (path.stat().st_mode & 0o022 or path.stat().st_uid!=os.geteuid()):
        raise ValueError('Agent settings must belong to the worker user and not be group/world writable')
    return validate_agent(json.loads(path.read_text(encoding='utf-8')))


def bind_deployment(root,settings):
    """Prevent silently repointing existing issued identities to another VPN."""
    if os.name=='posix' and (Path(root).stat().st_mode & 0o077 or Path(root).stat().st_uid!=os.geteuid()):
        raise ValueError('Worker state must be private and belong to the worker user')
    value={key:settings[key] for key in ('public_host','endpoint_port','container','interface','config_path','clients_table','protocol_version')}
    path=Path(root)/'deployment-binding.json'
    if not path.exists() and ((Path(root)/'master.key').exists() or any(Path(root).glob('*.enc'))):
        raise ValueError('Existing unbound worker state found; a separate migration plan is required')
    try:
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError:
        if json.loads(path.read_text(encoding='utf-8'))!=value:raise ValueError('Agent deployment identity changed; do not reuse state for another VPN server')
    else:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(value,stream,sort_keys=True);stream.flush();os.fsync(stream.fileno())


class PortableSSHAgent:
    def __call__(self,payload):
        host=hostname(os.environ['AGENT_HOST'])
        ssh_port=port(int(os.getenv('AGENT_PORT','22')))
        user=os.getenv('AGENT_USER','root')
        if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}',user):raise ValueError('Invalid SSH user')
        args=['ssh','-F','/dev/null','-p',str(ssh_port),'-o','BatchMode=yes','-o','ConnectTimeout=5',
              '-o','ConnectionAttempts=1','-o','StrictHostKeyChecking=yes',
              '-o','UserKnownHostsFile=/run/secrets/agent_known_hosts','-o','UpdateHostKeys=no',
              '-o','IdentitiesOnly=yes','-o','ClearAllForwardings=yes','-o','RequestTTY=no',
              '-o','PasswordAuthentication=no','-o','KbdInteractiveAuthentication=no',
              '-i','/run/secrets/agent_key',user+'@'+host]
        result=subprocess.run(args,input=json.dumps(payload)+'\n',capture_output=True,text=True,timeout=20)
        if result.returncode:raise RuntimeError('VPN-сервер временно недоступен')
        reply=json.loads(result.stdout)
        if not reply.get('ok'):raise RuntimeError(reply.get('error','Ошибка VPN-сервера'))
        return reply['result']
