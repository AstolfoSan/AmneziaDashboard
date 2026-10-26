"""Userspace-only VPN supervisor inside an installer-owned network namespace."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

DATA=Path('/opt/amnezia');RUN=Path('/run/amnezia-dashboard');children=[]
def run(*args):return subprocess.run(args,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def rule(*args):
    # Containers can retain their private namespace on restart. Never duplicate rules.
    position=args.index('-A')
    check=(*args[:position],'-C',*args[position+1:])
    if subprocess.run(check,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:run(*args)
def spawn(args):
    process=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);children.append(process);return process
def interface(name,config,mtu=1280):
    text=(DATA/config).read_text();address=None;lines=[]
    for line in text.splitlines():
        if line.strip().startswith('Address ='):address=line.split('=',1)[1].strip()
        elif not line.strip().startswith(('MTU =','DNS =')):lines.append(line)
    if not address:raise RuntimeError('Missing interface address')
    RUN.mkdir(parents=True,exist_ok=True);stripped=RUN/(name+'.conf');stripped.write_text('\n'.join(lines)+'\n');stripped.chmod(0o600)
    Path('/run/amneziawg').mkdir(parents=True,exist_ok=True)
    process=spawn(['/usr/bin/amneziawg-go','-f',name])
    for _ in range(100):
        if process.poll() is not None:raise RuntimeError('Userspace VPN exited')
        if Path('/run/amneziawg/'+name+'.sock').exists():break
        time.sleep(.1)
    else:raise RuntimeError('Userspace VPN did not create its control socket')
    run('awg','setconf',name,str(stripped));run('ip','address','replace',address,'dev',name)
    run('ip','link','set','dev',name,'mtu',str(mtu),'up')
    return address
def forwarding(config):
    subnet=config['client_subnet'];role=config['role']
    run('iptables','-P','FORWARD','DROP')
    if role=='cascade-entry':
        run('ip','route','replace','blackhole','default','metric','32760','table','101')
        run('ip','route','replace','default','dev','awgout','metric','10','table','101')
        current=json.loads(subprocess.check_output(['ip','-j','rule']))
        if not any(r.get('priority')==10100 and r.get('src')==subnet and str(r.get('table'))=='101' for r in current):
            if any(r.get('priority')==10100 for r in current):raise RuntimeError('Unexpected private policy rule')
            run('ip','rule','add','priority','10100','from',subnet,'lookup','101')
        rule('iptables','-A','FORWARD','-i','awg0','-o','awgout','-s',subnet,'-j','ACCEPT')
        rule('iptables','-A','FORWARD','-i','awgout','-o','awg0','-d',subnet,'-m','conntrack','--ctstate','ESTABLISHED,RELATED','-j','ACCEPT')
    else:
        iface='awg0' if role=='direct' else 'awgout'
        if role=='cascade-exit':run('ip','route','replace',subnet,'dev',iface)
        rule('iptables','-A','FORWARD','-i',iface,'-o','eth0','-s',subnet,'-j','ACCEPT')
        rule('iptables','-A','FORWARD','-i','eth0','-o',iface,'-d',subnet,'-m','conntrack','--ctstate','ESTABLISHED,RELATED','-j','ACCEPT')
        rule('iptables','-t','nat','-A','POSTROUTING','-s',subnet,'-o','eth0','-j','MASQUERADE')
    rule('iptables','-t','mangle','-A','FORWARD','-p','tcp','--tcp-flags','SYN,RST','SYN','-j','TCPMSS','--clamp-mss-to-pmtu')
def start(config):
    role=config['role']
    if os.getenv('AMDASH_PRIVATE_NETNS')!='1' or not Path('/.dockerenv').exists():
        raise RuntimeError('VPN runtime may only run inside its installer-owned container')
    if role not in {'direct','cascade-entry','cascade-exit','probe'}:raise RuntimeError('Invalid VPN role')
    # Fail closed before bringing up interfaces, including failed startup paths.
    run('iptables','-P','FORWARD','DROP')
    if role=='probe':
        routes=json.loads(subprocess.check_output(['ip','-j','route','show','default']))
        route=routes[0];run('ip','route','replace',config['endpoint']+'/32','via',route['gateway'],'dev',route['dev'])
        interface('awgtest','probe.conf');run('ip','route','replace','default','dev','awgtest')
    else:
        if role in {'direct','cascade-entry'}:interface('awg0','awg/awg0.conf')
        if role in {'cascade-entry','cascade-exit'}:
            interface('awgout','awg/awgout.conf')
            spawn([sys.executable,'/usr/local/share/amnezia-dashboard/relay.py',str(DATA/'relay.json')])
        forwarding(config)
    RUN.mkdir(parents=True,exist_ok=True);(RUN/'ready').write_text('ready')
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--health',action='store_true');args=parser.parse_args()
    if args.health:
        if not (RUN/'ready').exists():raise SystemExit(1)
        return
    def stop(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:
        start(json.loads((DATA/'node.json').read_text()))
        while True:
            if any(p.poll() is not None for p in children):raise RuntimeError('Required VPN process exited')
            time.sleep(1)
    finally:
        (RUN/'ready').unlink(missing_ok=True)
        for p in children:
            if p.poll() is None:p.terminate()
        for p in children:
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill();p.wait()
if __name__=='__main__':main()
