"""Privileged fresh-Ubuntu worker. Only executed on explicitly approved new VPSs."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request

VPN=Path('/opt/amnezia-dashboard-vpn');PANEL=Path('/opt/amnezia-dashboard');AGENT=Path('/opt/amnezia-dashboard-agent')
WORK=None;SPEC=None

def execute(args,timeout=1200,capture=False,allowed=(0,)):
    env={**os.environ,'DEBIAN_FRONTEND':'noninteractive','DOCKER_HOST':'unix:///var/run/docker.sock',
         'PATH':'/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'}
    env.pop('DOCKER_CONTEXT',None)
    with (WORK/'install.log').open('ab') as log:
        p=subprocess.run(args,stdout=subprocess.PIPE if capture else log,stderr=log,env=env,timeout=timeout)
    if p.returncode not in allowed:raise RuntimeError('Provisioning step failed; see private install.log')
    return p.stdout if capture else p.returncode

def save(path,data,mode=0o600):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.new')
    temporary.write_bytes(data.encode() if isinstance(data,str) else data);temporary.chmod(mode);os.replace(temporary,path)

def own(path):
    path=Path(path);marker=path/'installer-owner.json'
    if path.exists():
        if not marker.is_file() or json.loads(marker.read_text()).get('run_id')!=SPEC['run_id']:
            raise RuntimeError('Existing installation directory is not owned by this installation')
    else:
        path.mkdir(parents=True,mode=0o700);save(marker,json.dumps({'run_id':SPEC['run_id']}))

def outside_ip():
    for url in ('https://api.ipify.org','https://checkip.amazonaws.com'):
        try:
            output=execute(['curl','-4','--noproxy','*','--fail','--silent','--max-time','12',url],capture=True,timeout=20).decode().strip()
            return str(ipaddress.IPv4Address(output))
        except Exception:pass
    raise RuntimeError('External HTTPS IP checks failed')

def backup():
    paths=[p for p in ('/root/.ssh/authorized_keys','/etc/ufw','/etc/docker','/etc/sysctl.conf','/etc/sysctl.d') if Path(p).exists()]
    save(WORK/'packages-before.txt',execute(['dpkg-query','-W'],capture=True))
    save(WORK/'routes-before.json',execute(['ip','-j','route'],capture=True))
    if shutil.which('iptables-save'):save(WORK/'iptables-before.txt',execute(['iptables-save'],capture=True))
    archive=WORK/'before-install.tar.gz'
    if archive.exists():raise RuntimeError('Original recovery archive must not be overwritten')
    execute(['tar','-czpf',str(archive),*paths,str(WORK/'packages-before.txt'),str(WORK/'routes-before.json')])
    archive.chmod(0o600)
    return {'archive':str(archive),'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}

def prepare():
    own(VPN)
    execute(['apt-get','update','-qq'])
    execute(['apt-get','install','-y','--no-install-recommends','ca-certificates','curl','openssl','python3','python3-venv','git','iptables'])
    if not shutil.which('docker'):
        key=Path('/etc/apt/keyrings/amnezia-dashboard-docker.asc');source=Path('/etc/apt/sources.list.d/amnezia-dashboard-docker.sources')
        if key.exists() or source.exists():raise RuntimeError('Existing Docker repository settings require manual review')
        with urllib.request.urlopen('https://download.docker.com/linux/ubuntu/gpg',timeout=30) as response:save(key,response.read(),0o644)
        arch=execute(['dpkg','--print-architecture'],capture=True).decode().strip()
        if arch not in {'amd64','arm64'}:raise RuntimeError('Unsupported CPU architecture')
        save(source,'Types: deb\nURIs: https://download.docker.com/linux/ubuntu\nSuites: noble\nComponents: stable\nArchitectures: '+arch+'\nSigned-By: '+str(key)+'\n',0o644)
        execute(['apt-get','update','-qq'])
        execute(['apt-get','install','-y','docker-ce','docker-ce-cli','containerd.io','docker-buildx-plugin','docker-compose-plugin'])
    execute(['systemctl','enable','--now','docker'])
    execute(['docker','compose','version'])
    return {'prepared':True,'outside_ip':outside_ip()}

def build():
    own(VPN)
    execute(['docker','build','-t',SPEC['vpn_image'],str(WORK/'vpn-image')],timeout=1800)
    version=execute(['docker','run','--rm','--network','none','--entrypoint','awg',SPEC['vpn_image'],'--version'],capture=True).decode().strip()
    match=re.search(r'\bv?(\d+)\.(\d+)\.\d+',version)
    if not match or tuple(map(int,match.groups()))<(3,1):raise RuntimeError('Current official image does not advertise compatible AWG 3.1 tools; no VPN started')
    save(WORK/'awg-version.txt',version+'\n')
    return {'vpn_image_built':True,'awg_tools_version':version}

def vpn_up():
    own(VPN);execute(['docker','compose','-f',str(VPN/'compose.json'),'up','-d'])
    for _ in range(50):
        if execute(['docker','exec','amnezia-dashboard-vpn','python3','/usr/local/share/amnezia-dashboard/vpn_runtime.py','--health'],allowed=(0,1))==0:
            return {'vpn_interfaces_started':True}
        time.sleep(1)
    raise RuntimeError('VPN userspace interfaces did not start')

def firewall():
    # Never enable/disable UFW, flush a global table or touch unrelated listeners.
    if shutil.which('ufw') and b'Status: active' in execute(['ufw','status'],capture=True):
        ports=[(SPEC['vpn_port'],'udp')] if SPEC['role'] in {'direct','cascade-entry'} else [(SPEC['relay_port'],'tcp')]
        if SPEC['host_is_panel']:ports.extend([(80,'tcp'),(SPEC['panel_port'],'tcp')])
        for number,proto in ports:execute(['ufw','allow',str(number)+'/'+proto,'comment','AmneziaDashboard installer'])
        if SPEC['agent_source']:
            execute(['ufw','allow','from',SPEC['agent_source'],'to','any','port',str(SPEC['ssh_port']),'proto','tcp','comment','AmneziaDashboard restricted agent'])
    if SPEC['role']=='cascade-exit':
        # Docker DNAT precedes DOCKER-USER. Match only this new container/port.
        script=WORK/'cascade-source-filter.py'
        save(script,'''import subprocess,sys
args=['iptables','-w','-s','''+repr(SPEC['entry_public_ip'])+''','-d','''+repr(SPEC['vpn_ip'])+''','-p','tcp','--dport','24443','-j','ACCEPT']
drop=['iptables','-w','-d','''+repr(SPEC['vpn_ip'])+''','-p','tcp','--dport','24443','-j','DROP']
for rule in (drop,args):
    p=subprocess.run(rule[:2]+['-C','DOCKER-USER']+rule[2:],capture_output=True)
    if '--remove' in sys.argv:
        if not p.returncode:subprocess.run(rule[:2]+['-D','DOCKER-USER']+rule[2:],check=True)
    elif p.returncode:subprocess.run(rule[:2]+['-I','DOCKER-USER','1']+rule[2:],check=True)
''')
        unit='''[Unit]
Description=Restrict only the installer-owned cascade TLS listener
After=docker.service
Requires=docker.service
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 '''+str(script)+'''
ExecStop=/usr/bin/python3 '''+str(script)+''' --remove
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
'''
        save('/etc/systemd/system/amnezia-dashboard-cascade-filter.service',unit,0o644)
        execute(['systemctl','daemon-reload']);execute(['systemctl','enable','--now','amnezia-dashboard-cascade-filter.service'])
    return {'scoped_firewall_ready':True}

def install_agent():
    own(AGENT)
    config_dir=Path('/etc/amnezia-dashboard')
    if config_dir.exists() and not (config_dir/'installer-owner.json').exists():raise RuntimeError('Existing agent config must not be overwritten')
    own(config_dir)
    for name in ('agent.py','portable_settings.py','requirements.txt'):save(AGENT/name,(WORK/'agent'/name).read_bytes(),0o644)
    if not (AGENT/'venv').exists():execute(['python3','-m','venv',str(AGENT/'venv')])
    execute([str(AGENT/'venv/bin/pip'),'install','--disable-pip-version-check','--no-cache-dir','-r',str(AGENT/'requirements.txt')])
    save(config_dir/'agent.json',(WORK/'agent.json').read_bytes())
    state=Path('/var/lib/amnezia-dashboard-agent');state.mkdir(mode=0o700,exist_ok=False)
    for name in ('amnezia-dashboard-expiry.service','amnezia-dashboard-expiry.timer'):
        save(Path('/etc/systemd/system')/name,(WORK/name).read_bytes(),0o644)
    execute(['systemd-analyze','verify','/etc/systemd/system/amnezia-dashboard-expiry.service','/etc/systemd/system/amnezia-dashboard-expiry.timer'])
    ssh=Path('/root/.ssh');ssh.mkdir(mode=0o700,exist_ok=True)
    line=(WORK/'authorized-key.txt').read_text().strip()
    if not line.startswith('from="'+SPEC['agent_source']+'",restrict,command="/usr/bin/env -i ') or '\n' in line or 'ssh-ed25519 ' not in line:raise RuntimeError('Invalid restricted SSH key line')
    keys=ssh/'authorized_keys';existing=keys.read_text() if keys.exists() else ''
    if line in existing:raise RuntimeError('Unexpected duplicate installer key')
    with keys.open('a') as stream:stream.write(('\n' if existing and not existing.endswith('\n') else '')+line+'\n')
    keys.chmod(0o600);execute(['/usr/sbin/sshd','-t'])
    execute(['systemctl','daemon-reload']);execute(['systemctl','enable','--now','amnezia-dashboard-expiry.timer'])
    execute(['systemctl','start','amnezia-dashboard-expiry.service'])
    return {'agent_ready':True}

def panel():
    own(PANEL)
    (PANEL/'certs').mkdir(mode=0o750,exist_ok=True)
    for name in ('data','secrets'):
        root=PANEL/name;root.mkdir(exist_ok=True);os.chown(root,10001,10001);root.chmod(0o700)
    for name in ('agent_key','agent_known_hosts'):
        path=PANEL/'secrets'/name;os.chown(path,10001,10001);path.chmod(0o400)
    (PANEL/'acme-webroot').mkdir(exist_ok=True);(PANEL/'acme-webroot').chmod(0o755)
    full=(PANEL/'nginx.conf').read_bytes();save(PANEL/'nginx.full.conf',full,0o644)
    bootstrap='worker_processes 1; pid /tmp/nginx.pid; error_log /dev/stderr warn; events {worker_connections 64;} http {access_log off; server_tokens off; server {listen 8080; location /.well-known/acme-challenge/ {root /acme;} location / {return 404;}}}\n'
    # Bind the directory, not a file inode: atomic replacements remain visible.
    (PANEL/'nginx').mkdir(mode=0o755,exist_ok=True)
    save(PANEL/'nginx/nginx.conf',bootstrap,0o644)
    execute(['docker','compose','-f',str(PANEL/'compose.yaml'),'up','-d','web'])
    acme_source=PANEL/'acme-source';home=PANEL/'acme'
    meta=SPEC['versions']['acme']
    execute(['git','clone','--quiet','--depth','1','--branch',meta['tag'],'https://github.com/acmesh-official/acme.sh.git',str(acme_source)])
    if execute(['git','-C',str(acme_source),'rev-parse','HEAD'],capture=True).decode().strip()!=meta['commit']:raise RuntimeError('ACME source changed after release discovery')
    execute(['git','-C',str(acme_source),'-c','gpg.ssh.allowedSignersFile='+str(acme_source/'allowed_signers'),'verify-tag',meta['tag']])
    home.mkdir(mode=0o700)
    execute(['sh',str(acme_source/'acme.sh'),'--install','--home',str(home),'--nocron','--noprofile'])
    command=[str(home/'acme.sh'),'--home',str(home),'--server','letsencrypt']
    register=command+['--register-account']
    if SPEC.get('email'):register+=['--accountemail',SPEC['email']]
    execute(register)
    old=os.umask(0o022)
    try:execute(command+['--issue','-d',SPEC['public_ip'],'-w',str(PANEL/'acme-webroot'),'--cert-profile','shortlived','--days','3','--keylength','ec-256'])
    finally:os.umask(old)
    execute(command+['--install-cert','-d',SPEC['public_ip'],'--ecc','--key-file',str(PANEL/'certs/key.pem'),
                    '--fullchain-file',str(PANEL/'certs/fullchain.pem'),'--reloadcmd','/usr/bin/python3 '+str(PANEL/'cert_deploy.py')])
    save(PANEL/'nginx/nginx.conf',full,0o644)
    execute(['docker','compose','-f',str(PANEL/'compose.yaml'),'build','app'],timeout=1800)
    execute(['docker','compose','-f',str(PANEL/'compose.yaml'),'up','-d','app'])
    for _ in range(50):
        result=execute(['docker','exec','amnezia-dashboard-app','python','-c',"import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=3)"],allowed=(0,1))
        if result==0:break
        time.sleep(1)
    else:raise RuntimeError('Panel app readiness failed')
    execute(['python3',str(PANEL/'cert_deploy.py')])
    renewal='''[Unit]
Description=Renew AmneziaDashboard short-lived IP certificate
After=network-online.target docker.service
[Service]
Type=oneshot
ExecStart='''+str(home/'acme.sh')+' --cron --home '+str(home)+'''
UMask=0077
Nice=10
CPUQuota=15%
MemoryMax=128M
TimeoutStartSec=300
'''
    save('/etc/systemd/system/amnezia-dashboard-cert-renew.service',renewal,0o644)
    save('/etc/systemd/system/amnezia-dashboard-cert-renew.timer','[Unit]\nDescription=Hourly IP certificate renewal check\n[Timer]\nOnCalendar=hourly\nRandomizedDelaySec=300\nPersistent=true\n[Install]\nWantedBy=timers.target\n',0o644)
    execute(['systemctl','daemon-reload']);execute(['systemctl','enable','--now','amnezia-dashboard-cert-renew.timer'])
    execute(['systemctl','start','amnezia-dashboard-cert-renew.service'])
    return {'panel_ready':True,'certificate_renewal_timer_enabled':True}

def probe_start():
    name='amnezia-dashboard-probe';data=WORK/'probe'
    execute(['docker','run','-d','--name',name,'--label','amnezia-dashboard.install='+SPEC['run_id'],
             '--cap-drop','ALL','--cap-add','NET_ADMIN','--device','/dev/net/tun','--memory','128m','--cpus','.5',
             '--pids-limit','64','--read-only','--tmpfs','/run:rw,size=16m','--tmpfs','/tmp:rw,size=8m',
             '-e','AMDASH_PRIVATE_NETNS=1','--network','amnezia-dashboard-vpn-net','-v',str(data)+':/opt/amnezia:ro',SPEC['vpn_image']])
    for _ in range(30):
        if execute(['docker','exec',name,'python3','/usr/local/share/amnezia-dashboard/vpn_runtime.py','--health'],allowed=(0,1))==0:return {'probe_started':True}
        time.sleep(1)
    raise RuntimeError('Disposable probe did not start')

def probe_ip(allow_failure=False):
    for url in ('https://api.ipify.org','https://checkip.amazonaws.com'):
        try:
            raw=execute(['docker','exec','amnezia-dashboard-probe','curl','-4','--noproxy','*','--fail','--silent','--max-time','12',url],capture=True,timeout=20)
            return {'ip':str(ipaddress.IPv4Address(raw.decode().strip()))}
        except Exception:pass
    if allow_failure:return {'blocked':True}
    raise RuntimeError('Actual HTTPS through the disposable VPN client failed')

def probe_stop():
    label=execute(['docker','inspect','--format','{{index .Config.Labels "amnezia-dashboard.install"}}','amnezia-dashboard-probe'],capture=True).decode().strip()
    if label!=SPEC['run_id']:raise RuntimeError('Refusing to remove an unowned probe')
    execute(['docker','rm','-f','amnezia-dashboard-probe'])
    for name in ('node.json','probe.conf'):(WORK/'probe'/name).unlink(missing_ok=True)
    return {'probe_removed':True}

def probe_reconnect():
    label=execute(['docker','inspect','--format','{{index .Config.Labels "amnezia-dashboard.install"}}','amnezia-dashboard-probe'],capture=True).decode().strip()
    if label!=SPEC['run_id']:raise RuntimeError('Unowned probe')
    peers=execute(['docker','exec','amnezia-dashboard-probe','awg','show','awgtest','peers'],capture=True).decode().split()
    if len(peers)!=1:raise RuntimeError('Unexpected probe peer count')
    execute(['docker','exec','amnezia-dashboard-probe','awg','set','awgtest','peer',peers[0],'remove'])
    execute(['docker','exec','amnezia-dashboard-probe','awg','setconf','awgtest','/run/amnezia-dashboard/awgtest.conf'])
    return {'probe_reconnected':True}

def check_timers():
    names=[]
    if SPEC['role'] in {'direct','cascade-entry'}:names.append('amnezia-dashboard-expiry')
    if SPEC['host_is_panel']:names.append('amnezia-dashboard-cert-renew')
    for name in names:
        execute(['systemctl','is-enabled','--quiet',name+'.timer'])
        execute(['systemctl','is-active','--quiet',name+'.timer'])
        if execute(['systemctl','show','-p','Result','--value',name+'.service'],capture=True).strip()!=b'success':raise RuntimeError('An enforcement/renewal service failed')
    return {'timers_verified':names}

def stop_owned():
    # Preserve data. Disable autostart only for objects bearing this run's marker.
    owned_vpn=VPN.exists() and (VPN/'installer-owner.json').exists() and json.loads((VPN/'installer-owner.json').read_text()).get('run_id')==SPEC['run_id']
    owned_panel=(PANEL/'installer-owner.json').exists() and json.loads((PANEL/'installer-owner.json').read_text()).get('run_id')==SPEC['run_id']
    if owned_vpn and (VPN/'compose.json').exists():execute(['docker','compose','-f',str(VPN/'compose.json'),'stop'])
    if owned_panel and (PANEL/'compose.yaml').exists():execute(['docker','compose','-f',str(PANEL/'compose.yaml'),'stop'])
    if owned_vpn:
        try:probe_stop()
        except Exception:pass
        # Docker restart policy must not restart a failed/incomplete new deployment.
        names=['amnezia-dashboard-vpn']+(['amnezia-dashboard-app','amnezia-dashboard-web'] if owned_panel else [])
        for name in names:
            try:
                label=execute(['docker','inspect','--format','{{index .Config.Labels "amnezia-dashboard.install"}}',name],capture=True).decode().strip()
                if label==SPEC['run_id']:execute(['docker','update','--restart=no',name])
            except Exception:pass
        units=[]
        if SPEC['role'] in {'direct','cascade-entry'}:units+=['amnezia-dashboard-expiry.timer']
        if owned_panel:units+=['amnezia-dashboard-cert-renew.timer']
        if SPEC['role']=='cascade-exit':units+=['amnezia-dashboard-cascade-filter.service']
        for unit in units:
            if Path('/etc/systemd/system',unit).exists():execute(['systemctl','disable','--now',unit])
        # Revoke only this new exact forced-command line, preserving every old key.
        authorized=Path('/root/.ssh/authorized_keys');new_line=WORK/'authorized-key.txt'
        if SPEC['role'] in {'direct','cascade-entry'} and new_line.exists() and authorized.exists():
            wanted=new_line.read_text().strip();lines=authorized.read_text().splitlines()
            if wanted in lines:save(authorized,'\n'.join(line for line in lines if line!=wanted)+'\n')
    return {'owned_deployment_stopped':True,'private_data_retained':True}

def stage_panel():
    own(PANEL);return {'panel_directory_reserved':True}

def after_backup():
    import sqlite3
    paths=[str(VPN)]
    if SPEC['host_is_panel']:
        source=sqlite3.connect('file:'+str(PANEL/'data/panel.sqlite3')+'?mode=ro',uri=True)
        target=sqlite3.connect(str(WORK/'panel-consistent.sqlite3'));source.backup(target)
        if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Panel DB integrity check failed')
        source.close();target.close()
        snapshot=WORK/'panel-data-snapshot';snapshot.mkdir(mode=0o700)
        for name in ('master.key','bootstrap-password.txt'):shutil.copyfile(PANEL/'data'/name,snapshot/name)
        paths.extend([str(PANEL),str(WORK/'panel-consistent.sqlite3'),str(snapshot)])
    if SPEC['role'] in {'direct','cascade-entry'}:paths.extend([str(AGENT),'/etc/amnezia-dashboard','/var/lib/amnezia-dashboard-agent'])
    archive=WORK/'after-install-private.tar.gz'
    paths.extend([str(WORK/'node-spec.json'),str(WORK/'vpn-image')])
    for path in (WORK/'node_install.py',WORK/'authorized-key.txt',WORK/'cascade-source-filter.py',
                 Path('/root/.ssh/authorized_keys'),Path('/etc/apt/keyrings/amnezia-dashboard-docker.asc'),
                 Path('/etc/apt/sources.list.d/amnezia-dashboard-docker.sources')):
        if path.exists():paths.append(str(path))
    units=['amnezia-dashboard-expiry.service','amnezia-dashboard-expiry.timer',
           'amnezia-dashboard-cert-renew.service','amnezia-dashboard-cert-renew.timer','amnezia-dashboard-cascade-filter.service']
    paths.extend(str(Path('/etc/systemd/system')/name) for name in units if Path('/etc/systemd/system',name).exists())
    execute(['tar','--exclude='+str(PANEL/'data').lstrip('/'),'--exclude='+str(PANEL/'acme-source').lstrip('/'),
             '--exclude='+str(AGENT/'venv').lstrip('/'),'-czpf',str(archive),'-C','/',*[p.lstrip('/') for p in paths]],timeout=300)
    archive.chmod(0o600)
    return {'archive':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'bytes':archive.stat().st_size}

def main():
    global WORK,SPEC
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('work');parser.add_argument('action');args=parser.parse_args()
    if os.geteuid()!=0 or not re.fullmatch(r'/root/amnezia-dashboard-installer-[a-f0-9]{12}',args.work):raise RuntimeError('Invalid worker invocation')
    WORK=Path(args.work);SPEC=json.loads((WORK/'node-spec.json').read_text())
    if WORK.name!='amnezia-dashboard-installer-'+SPEC['run_id']:raise RuntimeError('Ownership mismatch')
    actions={'backup':backup,'prepare':prepare,'build':build,'vpn-up':vpn_up,'firewall':firewall,'agent':install_agent,
             'panel':panel,'stage-panel':stage_panel,'after-backup':after_backup,'probe-start':probe_start,'probe-ip':probe_ip,'probe-blocked':lambda:probe_ip(True),'probe-stop':probe_stop,
             'probe-reconnect':probe_reconnect,'check-timers':check_timers,'stop-owned':stop_owned}
    if args.action=='link-down' or args.action=='link-up':
        if SPEC['role']!='cascade-entry':raise RuntimeError('Wrong node role')
        execute(['docker','exec','amnezia-dashboard-vpn','ip','link','set','awgout','down' if args.action=='link-down' else 'up'])
        result={'outer_link':args.action}
    else:result=actions[args.action]()
    save(WORK/('stage-'+args.action+'.json'),json.dumps(result));print(json.dumps(result))
if __name__=='__main__':
    try:main()
    except Exception:
        if WORK:
            import traceback
            with (WORK/'install.log').open('a') as stream:traceback.print_exc(file=stream)
        print(json.dumps({'error':'Installation stage failed; private log retained'}));raise SystemExit(1)
