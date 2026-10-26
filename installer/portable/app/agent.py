#!/usr/bin/python3
"""Restricted SSH worker: only portal-owned peers are mutable; no VPN restarts."""
import base64
import datetime as dt
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import time
import uuid
import zlib
from cryptography.fernet import Fernet

from portable_settings import load_agent, bind_deployment
SETTINGS = load_agent()
ROOT = Path(SETTINGS['state_dir'])
CONTAINER = SETTINGS['container']
CONFIG = SETTINGS['config_path']
TABLE = SETTINGS['clients_table']
HOST = SETTINGS['public_host']
IFACE = SETTINGS['interface']
AWG = SETTINGS['awg_binary']
MAX_TRAFFIC = 2**53-1

def sha(data): return hashlib.sha256(data).hexdigest()
def fields(text):
    return {k.strip(): v.strip() for line in text.splitlines() if '=' in line and not line.lstrip().startswith(('#', ';')) for k, v in [line.split('=', 1)]}
def split_config(text):
    pieces = re.split(r'(?m)^\[Peer\][ \t]*\r?\n', text)
    return pieces[0], ['[Peer]\n'+p for p in pieces[1:]]
def identifier(value):
    value = str(value)
    if str(uuid.UUID(value)) != value: raise ValueError('Invalid device identifier')
    return value
def label(value):
    value = str(value).strip()
    if not 1 <= len(value) <= 64 or any(ord(c) < 32 for c in value): raise ValueError('Invalid device name')
    return value
def atomic(path, data):
    tmp = path.with_name(path.name+'.new')
    with tmp.open('wb') as h: h.write(data); h.flush(); os.fsync(h.fileno())
    tmp.chmod(0o600); os.replace(tmp, path)

class Docker:
    def run(self, args, data=None):
        return subprocess.run(args, input=data, capture_output=True, check=True, timeout=12).stdout
    def read(self):
        cfg = self.run(['docker','exec',CONTAINER,'cat',CONFIG]).decode()
        raw = self.run(['docker','exec',CONTAINER,'cat',TABLE])
        rows = json.loads(raw); assert isinstance(rows, list)
        return cfg, rows, raw
    def wg(self, field):
        text = self.run(['docker','exec',CONTAINER,AWG,'show',IFACE,field]).decode()
        return {line.split()[0]: line.split()[1:] for line in text.splitlines() if line.split()}
    def key(self, public=False, private=None):
        return self.run(['docker','exec','-i',CONTAINER,AWG,'pubkey' if public else 'genkey'], (private+'\n').encode() if public else None).decode().strip()
    def counter_epoch(self):
        container=self.run(['docker','inspect','--format','{{.Id}} {{.State.StartedAt}}',CONTAINER]).decode().strip()
        interface=self.run(['docker','exec',CONTAINER,'cat','/sys/class/net/'+IFACE+'/ifindex']).decode().strip()
        return container+'/'+interface
    def commit(self, old_cfg, old_raw, new_cfg, rows, pub, psk=None, ip=None, reset=False):
        # Compare-and-swap avoids overwriting changes made by the official app.
        new_raw = json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()
        with tempfile.TemporaryDirectory(prefix='amnezia-portal-') as temp:
            tmp = Path(temp); (tmp/'config').write_text(new_cfg); (tmp/'table').write_bytes(new_raw)
            for p in tmp.iterdir(): p.chmod(0o600)
            tag = uuid.uuid4().hex
            cp = CONFIG+'.portal-'+tag; tp = TABLE+'.portal-'+tag; kp = CONFIG+'.psk-'+tag
            self.run(['docker','cp',str(tmp/'config'),CONTAINER+':'+cp])
            self.run(['docker','cp',str(tmp/'table'),CONTAINER+':'+tp])
            try:
                script = 'test "$(sha256sum '+CONFIG+' | cut -d\" \" -f1)" = '+sha(old_cfg.encode())+' && test "$(sha256sum '+TABLE+' | cut -d\" \" -f1)" = '+sha(old_raw)+' && mv '+cp+' '+CONFIG+' && mv '+tp+' '+TABLE
                self.run(['docker','exec',CONTAINER,'sh','-c',script])
                if psk:
                    (tmp/'psk').write_text(psk+'\n'); (tmp/'psk').chmod(0o600)
                    self.run(['docker','cp',str(tmp/'psk'),CONTAINER+':'+kp])
                    if reset:
                        # Forget established session keys, not just the next handshake.
                        self.run(['docker','exec',CONTAINER,AWG,'set',IFACE,'peer',pub,'remove'])
                    self.run(['docker','exec',CONTAINER,AWG,'set',IFACE,'peer',pub,'preshared-key',kp,'allowed-ips',ip+'/32'])
                else:
                    self.run(['docker','exec',CONTAINER,AWG,'set',IFACE,'peer',pub,'remove'])
            except Exception:
                # Roll back only if the files still contain our exact replacement.
                # Restore each file independently, and never overwrite a later
                # edit from the official app. Rename makes each restore atomic.
                current, _, raw = self.read()
                if current == new_cfg:
                    (tmp/'config').write_text(old_cfg)
                    self.run(['docker','cp',str(tmp/'config'),CONTAINER+':'+cp])
                    self.run(['docker','exec',CONTAINER,'sh','-c','test "$(sha256sum '+CONFIG+' | cut -d\" \" -f1)" = '+sha(new_cfg.encode())+' && mv '+cp+' '+CONFIG])
                if raw == new_raw:
                    (tmp/'table').write_bytes(old_raw)
                    self.run(['docker','cp',str(tmp/'table'),CONTAINER+':'+tp])
                    self.run(['docker','exec',CONTAINER,'sh','-c','test "$(sha256sum '+TABLE+' | cut -d\" \" -f1)" = '+sha(new_raw)+' && mv '+tp+' '+TABLE])
                raise
            finally:
                try: self.run(['docker','exec',CONTAINER,'rm','-f',cp,tp,kp])
                except Exception: pass

class Agent:
    def __init__(self, root=ROOT, engine=None):
        self.root = root; root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.engine = engine or Docker()
        key = root/'master.key'
        if not key.exists(): atomic(key, Fernet.generate_key())
        self.crypt = Fernet(key.read_bytes())
    def load(self, uid):
        p = self.root/(identifier(uid)+'.enc')
        return json.loads(self.crypt.decrypt(p.read_bytes())) if p.exists() else None
    def save(self, record):
        atomic(self.root/(record['id']+'.enc'), self.crypt.encrypt(json.dumps(record).encode()))
    def records(self):
        return [json.loads(self.crypt.decrypt(p.read_bytes())) for p in self.root.glob('*.enc')]
    def transfer_snapshot(self):
        if getattr(self,'_transfer_snapshot',None) is None:
            epoch=getattr(self.engine,'counter_epoch',None)
            self._transfer_snapshot=(self.engine.wg('transfer'),epoch() if epoch else 'unknown')
        return self._transfer_snapshot
    def meter_update(self, record):
        if not record.get('traffic_meter') or record.get('access_reset_pending'):return
        transfer,epoch=self.transfer_snapshot()
        if record['public'] not in transfer:return
        rx,tx=map(int,transfer[record['public']]);assert rx>=0 and tx>=0
        reset=record.get('meter_epoch')!=epoch
        old_rx=record.get('meter_last_rx',0);old_tx=record.get('meter_last_tx',0)
        drx=rx if reset or rx<old_rx else rx-old_rx
        dtx=tx if reset or tx<old_tx else tx-old_tx
        if drx or dtx or reset or (rx,tx)!=(old_rx,old_tx):
            record.update(meter_rx=record.get('meter_rx',0)+drx,meter_tx=record.get('meter_tx',0)+dtx,
                          meter_last_rx=rx,meter_last_tx=tx,meter_epoch=epoch)
            self.save(record)
    @staticmethod
    def access_result(record):
        result={'id':record['id'],'state':record['status'],'manual_paused':bool(record.get('manual_paused',False)),
                'expires_at':record.get('expires_at'),'traffic_limit_bytes':record.get('traffic_limit_bytes')}
        if record.get('traffic_meter'):
            result.update(traffic_meter=True,total_rx=record.get('meter_rx',0),total_tx=record.get('meter_tx',0))
        return result
    def stats(self):
        cfg, rows, _ = self.engine.read(); _, blocks = split_config(cfg)
        managed = {r['public']: r for r in self.records()}
        names = {r.get('clientId'): r.get('userData',{}).get('clientName','') for r in rows}
        transfer = self.engine.wg('transfer'); handshakes = self.engine.wg('latest-handshakes')
        output = []
        for block in blocks:
            f = fields(block); pub = f.get('PublicKey'); rec = managed.get(pub)
            if not pub: continue
            rx, tx = map(int, transfer.get(pub, ['0','0']))
            state=rec.get('status','active') if rec else 'active'
            item={'id': rec['id'] if rec else 'legacy_'+sha(pub.encode())[:24], 'name': names.get(pub) or 'Существующий профиль', 'ip': f.get('AllowedIPs','').split('/')[0], 'legacy': rec is None, 'rx': rx, 'tx': tx, 'handshake': int(handshakes.get(pub,['0'])[0]), 'active': state=='active', 'state':state, 'manual_paused':bool(rec.get('manual_paused',False)) if rec else False, 'expires_at':rec.get('expires_at') if rec else None}
            if rec:item.update(self.access_result(rec))
            output.append(item)
        present = {x['id'] for x in output}
        for rec in managed.values():
            if rec['id'] not in present: output.append({'id':rec['id'],'name':rec['name'],'ip':rec['ip'],'legacy':False,'rx':0,'tx':0,'handshake':0,'active':False,'state':'revoked','manual_paused':bool(rec.get('manual_paused',False)),'expires_at':rec.get('expires_at')})
        return {'peers':output,'sampled_at':int(time.time())}
    def guest(self, header, record):
        f = fields(header); server = self.engine.wg('public-key'); port = str(SETTINGS['endpoint_port'] or int(f['ListenPort']))
        # public-key has no row values; its only dictionary key is the public key.
        server_pub = next(iter(server)); private = record['private']; ip = record['ip']
        parameters = {k:v for k,v in f.items() if k not in {'PrivateKey','Address','ListenPort','PostUp','PostDown','PreUp','PreDown','SaveConfig','MTU','DNS'}}
        parameters.update({'protocol_version':SETTINGS['protocol_version'],'port':port,'subnet_address':f['Address'].split('/')[0],'transport_proto':'udp'})
        native = '[Interface]\nAddress = '+ip+'/32\nMTU = '+str(SETTINGS['mtu'])+'\nDNS = $PRIMARY_DNS, $SECONDARY_DNS\nPrivateKey = '+private+'\n'
        native += '\n'.join(k+' = '+v for k,v in f.items() if k in parameters)+'\n'
        native += '\n[Peer]\nPublicKey = '+server_pub+'\nPresharedKey = '+record['psk']+'\nAllowedIPs = 0.0.0.0/0, ::/0\nEndpoint = '+HOST+':'+port+'\nPersistentKeepalive = 25-35\n'
        last = dict(parameters,clientId=record['public'],client_ip=ip,client_priv_key=private,client_pub_key=record['public'],server_pub_key=server_pub,psk_key=record['psk'],config=native,hostName=HOST,port=int(port),mtu=str(SETTINGS['mtu']),persistent_keep_alive='25-35',allowed_ips=['0.0.0.0/0','::/0'])
        parameters['last_config'] = json.dumps(last,ensure_ascii=False)
        doc = {'containers':[{'awg':parameters,'container':'amnezia-awg2'}],'defaultContainer':'amnezia-awg2','description':SETTINGS['route_label']+' · '+record['name'],'dns1':SETTINGS['dns1'],'dns2':SETTINGS['dns2'],'hostName':HOST}
        raw=json.dumps(doc,ensure_ascii=False).encode()
        return 'vpn://'+base64.urlsafe_b64encode(struct.pack('>I',len(raw))+zlib.compress(raw,8)).decode().rstrip('=')
    def create(self, uid, name, expires_at=None):
        if expires_at is not None and (type(expires_at) is not int or not 946684800<=expires_at<=4133969999):raise ValueError('Invalid expiry date')
        uid=identifier(uid); name=label(name); record=self.load(uid)
        if record:
            if record.get('status')=='revoked': raise ValueError('Profile was revoked')
            if record.get('status') in {'paused','expired','limited'} or record.get('access_dirty'):raise ValueError('Profile access is suspended')
            if record.get('active'):
                if self.access_state(record)!='active':self.apply_access(record)
                return {'id':uid,'ip':record['ip'],'state':record['status'],'expires_at':record.get('expires_at')}
        cfg, rows, raw=self.engine.read(); header, blocks=split_config(cfg)
        if len(blocks)>=250 or (not record and len(self.records())>=1024): raise ValueError('Peer capacity reached')
        networks=[]
        for block in blocks:
            for item in fields(block).get('AllowedIPs','').split(','):
                try: networks.append(ipaddress.ip_network(item.strip(),strict=False))
                except ValueError: raise ValueError('Unexpected server address range')
        if not record:
            server_address=ipaddress.IPv4Interface(fields(header)['Address'])
            pool=server_address.network
            if pool.prefixlen!=24:raise ValueError('This release requires an IPv4 /24 client pool')
            reserved={r['ip'] for r in self.records() if r.get('status')=='pending'} | {str(server_address.ip)}
            ip=next((str(a) for a in pool.hosts() if str(a) not in reserved and not any(a in n for n in networks if n.version==4)),None)
            if not ip: raise ValueError('Address pool is full')
            private=self.engine.key()
            record={'id':uid,'name':name,'ip':ip,'private':private,'public':self.engine.key(public=True,private=private),'psk':self.engine.key(),'active':False,'status':'pending','created':int(time.time()),'expires_at':expires_at,'manual_paused':False}
            record.update(traffic_meter=1,meter_rx=0,meter_tx=0,meter_last_rx=0,meter_last_tx=0)
            record['vpn']=self.guest(header,record)
            self.save(record)
        state=self.access_state(record)
        if state!='active' and not record.get('pause_psk'):record['pause_psk']=self.engine.key();self.save(record)
        public=record['public']; ip=record['ip']; psk=record['psk'] if state=='active' else record['pause_psk']
        own=[p for p in blocks if fields(p).get('PublicKey')==public]
        if len(own)>1 or (own and (fields(own[0]).get('AllowedIPs')!=ip+'/32' or fields(own[0]).get('PresharedKey') not in {record['psk'],record.get('pause_psk')})):
            raise ValueError('Profile changed outside the portal')
        if not own and any(ipaddress.ip_address(ip) in n for n in networks if n.version==4):
            raise ValueError('Reserved address changed outside the portal')
        new_cfg=cfg if own else cfg.rstrip()+'\n\n[Peer]\nPublicKey = '+public+'\nPresharedKey = '+psk+'\nAllowedIPs = '+ip+'/32\n'
        reset=bool(own and fields(own[0]).get('PresharedKey')!=psk)
        if reset:
            replacement,count=re.subn(r'(?m)^[ \t]*PresharedKey[ \t]*=[^\r\n]*','PresharedKey = '+psk,own[0])
            if count!=1:raise ValueError('Unexpected profile key format')
            new_cfg=cfg.replace(own[0],replacement,1)
        metadata={'clientId':public,'userData':{'allowed_ips':ip+'/32','clientName':record['name'],'creationDate':dt.datetime.now().strftime('%a %b %d %H:%M:%S %Y'),'dataReceived':'0','dataSent':'0','latestHandshake':''}}
        new_rows=rows if any(r.get('clientId')==public for r in rows) else rows+[metadata]
        self.engine.commit(cfg,raw,new_cfg,new_rows,public,psk,ip,reset=reset)
        record['active']=state=='active'; record['status']=state; self.save(record)
        return {'id':uid,'ip':ip,'state':state,'expires_at':record.get('expires_at')}
    def revoke(self, uid):
        record=self.load(uid)
        if not record: raise ValueError('Only portal-created peers can be revoked')
        cfg, rows, raw=self.engine.read(); head, blocks=split_config(cfg)
        new=head+''.join(p for p in blocks if fields(p).get('PublicKey')!=record['public'])
        self.engine.commit(cfg,raw,new,[r for r in rows if r.get('clientId')!=record['public']],record['public'])
        record['active']=False; record['status']='revoked'
        for key in ('private','psk','vpn','pause_psk','access_dirty','access_reset_pending'): record.pop(key,None)
        self.save(record); return {'id':uid,'active':False}
    def export(self, uid):
        record=self.load(uid)
        if not record or record.get('status') not in {'active','paused','expired','limited'} or not record.get('vpn'): raise ValueError('Existing portal profile required')
        return {'vpn':record['vpn']}
    @staticmethod
    def access_state(record, now=None):
        if record.get('manual_paused',False):return 'paused'
        if record.get('expires_at') is not None and record['expires_at'] <= (time.time() if now is None else now):return 'expired'
        if record.get('traffic_limit_bytes') is not None and record.get('meter_rx',0)+record.get('meter_tx',0)>=record['traffic_limit_bytes']:return 'limited'
        return 'active'
    def apply_access(self, record):
        self.meter_update(record)
        state=self.access_state(record)
        cfg,rows,raw=self.engine.read();_,blocks=split_config(cfg)
        own=[p for p in blocks if fields(p).get('PublicKey')==record['public']]
        if len(own)!=1:raise ValueError('Profile removed or changed outside the portal')
        current=fields(own[0])
        if current.get('AllowedIPs')!=record['ip']+'/32' or current.get('PresharedKey') not in {record['psk'],record.get('pause_psk')}:
            raise ValueError('Profile changed outside the portal')
        if state!='active' and not record.get('pause_psk'):
            record['pause_psk']=self.engine.key();self.save(record)
        target=record['psk'] if state=='active' else record['pause_psk']
        if current['PresharedKey']!=target or record.get('access_reset_pending'):
            record['access_reset_pending']=True;self.save(record)
            replacement,count=re.subn(r'(?m)^[ \t]*PresharedKey[ \t]*=[^\r\n]*', 'PresharedKey = '+target,own[0])
            if count!=1:raise ValueError('Unexpected profile key format')
            new=cfg.replace(own[0],replacement,1)
            if new==cfg and current['PresharedKey']!=target:raise ValueError('Profile configuration changed')
            # Keep IP reservation/clientsTable and original keys/export unchanged.
            # A separate disabled PSK persists across VPN/container restarts.
            self.engine.commit(cfg,raw,new,rows,record['public'],target,record['ip'],reset=True)
            if record.get('traffic_meter'):record.update(meter_last_rx=0,meter_last_tx=0)
            self._transfer_snapshot=None
        record['status']=state;record['active']=state=='active';record.pop('access_dirty',None);record.pop('access_reset_pending',None);self.save(record)
        return self.access_result(record)
    def access(self, request):
        self._transfer_snapshot=None
        if not set(request)<= {'action','id','paused','expires_at'} or not {'paused','expires_at'} & set(request):raise ValueError('Invalid access request')
        record=self.load(request.get('id'))
        if not record or record.get('status') not in {'active','paused','expired','limited'}:raise ValueError('Only existing portal-created peers can be suspended')
        if 'paused' in request and type(request['paused']) is not bool:raise ValueError('Invalid pause flag')
        expires=request.get('expires_at',record.get('expires_at'))
        if expires is not None and (type(expires) is not int or not 946684800<=expires<=4133969999):raise ValueError('Invalid expiry date')
        record['manual_paused']=request.get('paused',bool(record.get('manual_paused',False)))
        record['expires_at']=expires;record['access_dirty']=True
        # Persist intent first. A partial RPC/commit is repaired by the local timer.
        self.save(record)
        return self.apply_access(record)
    def traffic_limit(self, request):
        if set(request)!= {'action','id','limit_bytes','seed'}:raise ValueError('Invalid traffic limit request')
        limit=request['limit_bytes'];seed=request['seed']
        if limit is not None and (type(limit) is not int or not 1<=limit<=MAX_TRAFFIC):raise ValueError('Invalid traffic limit')
        if not isinstance(seed,dict) or set(seed)!={'rx','tx','last_rx','last_tx'} or any(type(v) is not int or not 0<=v<=MAX_TRAFFIC for v in seed.values()):raise ValueError('Invalid traffic baseline')
        record=self.load(request.get('id'))
        if not record or record.get('status') not in {'active','paused','expired','limited'}:raise ValueError('Existing portal-created profile required')
        self._transfer_snapshot=None
        if not record.get('traffic_meter'):
            _,epoch=self.transfer_snapshot()
            record.update(traffic_meter=1,meter_rx=seed['rx'],meter_tx=seed['tx'],meter_last_rx=seed['last_rx'],meter_last_tx=seed['last_tx'],meter_epoch=epoch)
        self.meter_update(record)
        record['traffic_limit_bytes']=limit;record['access_dirty']=True;self.save(record)
        return self.apply_access(record)
    def enforce(self):
        self._transfer_snapshot=None
        changed=failed=0
        for record in self.records():
            # A crash after installing a peer may leave its enrollment pending.
            # A finite deadline must still be enforced without a client retry.
            if record.get('status')=='pending' and record.get('expires_at') is not None and record['expires_at']<=time.time():
                try:self.create(record['id'],record['name']);changed+=1
                except Exception:failed+=1
                continue
            if record.get('status') not in {'active','paused','expired','limited'}:continue
            try:
                self.meter_update(record)
                if record.get('access_dirty') or self.access_state(record)!=record['status']:
                    self.apply_access(record);changed+=1
            except Exception:failed+=1
        if failed:raise RuntimeError('Some access policies could not be confirmed')
        return {'changed':changed,'checked_at':int(time.time())}
    def dispatch(self, request):
        action=request.get('action')
        if action=='stats':self.enforce();return self.stats()
        if action=='create': return self.create(request.get('id'),request.get('name'))
        if action=='create_limited':
            if request.get('expires_at') is None:raise ValueError('Expiry is required for limited issuance')
            return self.create(request.get('id'),request.get('name'),request['expires_at'])
        if action=='revoke': return self.revoke(request.get('id'))
        if action=='export': return self.export(request.get('id'))
        if action=='access':return self.access(request)
        if action=='traffic_limit':return self.traffic_limit(request)
        raise ValueError('Unsupported operation')

def main():
    os.umask(0o077); ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
    with (ROOT/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        try:
            bind_deployment(ROOT, SETTINGS)
            if sys.argv[1:]==['--enforce']:
                print(json.dumps({'ok':True,'result':Agent().enforce()}));return
            if sys.argv[1:]:raise ValueError('Unsupported arguments')
            data=sys.stdin.buffer.readline(4097)
            if len(data)>4096: raise ValueError('Request too large')
            request=json.loads(data); assert isinstance(request,dict)
            result=Agent().dispatch(request)
            print(json.dumps({'ok':True,'result':result},ensure_ascii=False))
        except ValueError as e:
            print(json.dumps({'ok':False,'error':str(e)}))
            if sys.argv[1:]==['--enforce']:sys.exit(1)
        except Exception:
            print(json.dumps({'ok':False,'error':'Worker operation failed; no secret details exposed'}))
            if sys.argv[1:]==['--enforce']:sys.exit(1)
if __name__=='__main__': main()
