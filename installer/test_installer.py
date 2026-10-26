"""Offline safety/contract tests; no SSH or server installation is performed."""
import asyncio
import base64
import copy
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
import struct
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from model import Login,Settings,InstallError
import versions,provision,crypto_config,relay,vpn_runtime,node_install
import cli
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

def settings(mode='cascade'):
    return Settings(mode,Login('203.0.113.2',password='FOREIGN_TEST_PASSWORD'),
                    Login('203.0.113.1',password='ENTRY_TEST_PASSWORD') if mode=='cascade' else None,ca_terms_accepted=True)

def inventory():
    return {'uid':0,'os':'ubuntu','version':'24.04','architecture':'amd64','cpus':2,'ram_mib':2048,
            'available_mib':1500,'free_disk_gib':10,'tun':True,'existing_paths':[],'existing_containers':0,
            'links':[],'routes':[{'dst':'default','gateway':'203.0.113.254'}],
            'rules':[{'priority':0},{'priority':32766},{'priority':32767}],'listeners':'tcp LISTEN 0 128 0.0.0.0:22 0.0.0.0:*','python_present':True}

def version_lock():
    return {'amnezia_client':{'tag':'5.0.3.0','commit':'a'*40},'acme':{'tag':'3.1.6','commit':'b'*40},
            **{n:{'image':({'awg':'amneziavpn/amneziawg-go'}.get(n,n))+'@sha256:'+'a'*64,'platforms':['amd64']}
               for n in ('awg','alpine','python','nginx')}}

class InputTests(unittest.TestCase):
    def test_both_modes(self):
        for mode in ('direct','cascade'):self.assertEqual(settings(mode).validate().mode,mode)
    def test_credentials_never_in_repr_or_plan(self):
        value=settings();out=repr(value)+json.dumps(value.public_plan())
        self.assertNotIn('FOREIGN_TEST_PASSWORD',out);self.assertNotIn('ENTRY_TEST_PASSWORD',out)
    def test_no_credentials_rejected(self):
        with self.assertRaises(InstallError):Login('203.0.113.1').validate()
    def test_public_key_not_private(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'key.pub';path.touch()
            with self.assertRaises(InstallError):Login('203.0.113.1',key_file=str(path)).validate()
    def test_same_node_rejected(self):
        value=settings();value.entry.host=value.foreign.host
        with self.assertRaises(InstallError):value.validate()
    def test_bad_ips(self):
        for host in ('not-ip','127.0.0.1','0.0.0.0','224.0.0.1','::1','1.2.3.999'):
            with self.subTest(host=host),self.assertRaises(InstallError):Login(host,password='test').validate()
    def test_ca_consent_required(self):
        value=settings();value.ca_terms_accepted=False
        with self.assertRaises(InstallError):value.validate()
    def test_tcp_conflicts_rejected(self):
        value=settings();value.panel_port=443
        with self.assertRaises(InstallError):value.validate()
    def test_ssh_tls_conflict_rejected(self):
        value=settings();value.foreign.port=443
        with self.assertRaises(InstallError):value.validate()

class ConsoleTests(unittest.TestCase):
    def test_no_secret_input_from_pipe(self):
        with patch.object(cli.sys.stdin,'isatty',return_value=False),patch.object(cli.getpass,'getpass') as password:
            with self.assertRaises(InstallError):cli.collect()
            password.assert_not_called()
    def test_default_confirmations_are_no(self):
        with patch('builtins.input',return_value=''):self.assertFalse(cli.yes('confirm'))
    def test_plan_requires_exact_confirmation(self):
        plan={**settings().public_plan(),'versions':version_lock(),'networks':{'clients':'10.241.0.0/24'}}
        with patch('builtins.input',return_value='yes'),patch('builtins.print'):self.assertFalse(cli.confirm_plan(plan))
        with patch('builtins.input',return_value='УСТАНОВИТЬ'),patch('builtins.print'):self.assertTrue(cli.confirm_plan(plan))
    def test_direct_wizard_asks_one_node_only(self):
        # mode, change ports, optional email, explicit CA approval
        with patch.object(cli.sys.stdin,'isatty',return_value=True),patch('builtins.input',side_effect=['2','','','да']),patch('builtins.print'),patch.object(cli,'node',return_value=Login('203.0.113.2',password='test')) as prompt:
            value=cli.collect();self.assertEqual(value.mode,'direct');self.assertIsNone(value.entry);prompt.assert_called_once()
    def test_terminal_failure_is_not_success(self):
        class Fail:
            def __init__(self,*args):pass
            def run(self):raise InstallError('failure')
        with tempfile.TemporaryDirectory() as temp,patch.object(cli,'Runner',Fail),patch('builtins.print'):
            self.assertEqual(cli.run_wizard(settings(),Path(temp)),1)

class InventoryTests(unittest.TestCase):
    def test_clean(self):provision.validate_inventory(inventory(),settings(),'foreign')
    def test_existing_install_refused(self):
        for key,value in [('existing_paths',['/opt/amnezia']),('existing_containers',1),('tun',False),
                          ('available_mib',100),('free_disk_gib',.2),('version','22.04'),('uid',1000),
                          ('rules',[{'priority':10100}]),('links',[{'linkinfo':{'info_kind':'wireguard'}}])]:
            info=inventory();info[key]=value
            with self.subTest(key=key),self.assertRaises(InstallError):provision.validate_inventory(info,settings(),'foreign')
    def test_busy_ports(self):
        for port,proto,node in [(80,'tcp','foreign'),(10443,'tcp','foreign'),(443,'tcp','foreign'),(39265,'udp','entry')]:
            info=inventory();info['listeners']=proto+' LISTEN 0 128 [::]:'+str(port)+' [::]:*'
            with self.subTest(port=port),self.assertRaises(InstallError):provision.validate_inventory(info,settings(),node)
    def test_subnet_collision(self):
        info=inventory();info['routes']=[{'dst':'172.30.220.0/28'},{'dst':'10.241.0.0/24'}]
        result=provision.networks([info]);self.assertNotEqual(result['panel'],'172.30.220.0/28');self.assertNotEqual(result['clients'],'10.241.0.0/24')
        nets=list(map(ipaddress.IPv4Network,result.values()))
        for index,net in enumerate(nets):self.assertFalse(any(net.overlaps(other) for other in nets[index+1:]))
    def test_no_safe_subnet_is_error(self):
        info=inventory();info['routes']=[{'dst':'172.16.0.0/12'}]
        with self.assertRaises(InstallError):provision.networks([info])

class MetadataTests(unittest.TestCase):
    def test_only_official_repositories(self):
        with self.assertRaises(InstallError):versions.release('someone/fork')
        with self.assertRaises(InstallError):versions.image('someone/image','latest')
    def test_prerelease_rejected(self):
        with patch.object(versions,'get_json',return_value=({'tag_name':'5.0.3.0','prerelease':True},{})):
            with self.assertRaises(InstallError):versions.release('amnezia-vpn/amnezia-client')
    def test_exact_release_commit(self):
        replies=[({'tag_name':'3.1.6'},{}),({'object':{'type':'tag','sha':'b'*40}},{}),({'object':{'type':'commit','sha':'c'*40}}, {})]
        with patch.object(versions,'get_json',side_effect=replies):self.assertEqual(versions.release('acmesh-official/acme.sh')['commit'],'c'*40)
    def test_image_normalized_and_pinned(self):
        replies=[({'token':'public-ephemeral-token'},{}),({'manifests':[{'platform':{'architecture':'amd64','os':'linux'}}]},{'Docker-Content-Digest':'sha256:'+'a'*64})]
        with patch.object(versions,'get_json',side_effect=replies):
            value=versions.image('library/python','3.12-slim-bookworm')
        self.assertEqual(value['image'],'python@sha256:'+'a'*64);self.assertNotIn('token',str(value))
    def test_lookup_failure_never_falls_back(self):
        with patch.object(versions,'release',side_effect=OSError('offline')):
            with self.assertRaises(InstallError):versions.discover()

class ConfigTests(unittest.TestCase):
    def test_keys_are_valid_and_distinct(self):
        one,two=crypto_config.wg_key(),crypto_config.wg_key();self.assertNotEqual(one,two)
        key=x25519.X25519PrivateKey.from_private_bytes(base64.b64decode(one['private']))
        self.assertEqual(base64.b64decode(one['public']),key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw))
    def test_cascade_key_and_route_pairs(self):
        value=crypto_config.vpn_configs(settings(),'10.241.0.0/24','10.242.0.0/30')
        front=value['entry']['awg/awgout.conf'];back=value['foreign']['awg/awgout.conf']
        def fields(text):return dict(line.split(' = ',1) for line in text.splitlines() if ' = ' in line)
        a,b=fields(front),fields(back)
        self.assertEqual(a['PresharedKey'],b['PresharedKey']);self.assertEqual(a['HeaderProtectionKey'],b['HeaderProtectionKey'])
        self.assertIn('10.241.0.0/24',b['AllowedIPs']);self.assertEqual(a['Endpoint'],'127.0.0.1:15543')
        self.assertEqual(a['AllowedIPs'],'0.0.0.0/0')
    def test_direct_has_no_outer(self):self.assertNotIn('awg/awgout.conf',crypto_config.vpn_configs(settings('direct'),'10.241.0.0/24','10.242.0.0/30')['entry'])
    def test_private_ca_not_distributed(self):
        data=crypto_config.mutual_tls('127.0.0.1');self.assertNotIn('ca.key',data)
        cert=x509.load_pem_x509_certificate(data['server.pem'].encode())
        self.assertIn(ipaddress.IPv4Address('127.0.0.1'),cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress))
    def test_compose_is_isolated_and_bounded(self):
        spec={'role':'cascade-entry','vpn_port':39265,'relay_port':443,'vpn_image':'local/test:1','run_id':'a'*12,'vpn_ip':'172.31.220.2','vpn_ram_mib':256,'vpn_cpu':.65}
        data=provision.vpn_compose(spec,'172.31.220.0/28');vpn=data['services']['vpn']
        self.assertNotIn('privileged',vpn);self.assertNotIn('network_mode',vpn)
        self.assertEqual(vpn['cap_add'],['NET_ADMIN']);self.assertEqual(vpn['ports'],['39265:39265/udp'])
        self.assertNotIn('docker.sock',json.dumps(data));self.assertTrue(vpn['read_only'])
    def test_renderer_contract_with_discovered_image_format(self):
        spec=importlib.util.spec_from_file_location('portable_renderer_test',ROOT/'portable/configure.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for mode in ('direct','cascade'):
            config=json.loads((ROOT/'portable/examples'/(mode+'.json')).read_text(encoding='utf-8'))
            lock=version_lock();config['images']={name:lock[name]['image'] for name in ('python','nginx')}
            with tempfile.TemporaryDirectory() as temp:
                module.render(config,Path(temp)/'deployment')
                self.assertTrue((Path(temp)/'deployment/app/panel.py').is_file())
    def test_compatibility_version_parser(self):
        for version,ok in [('amneziawg-tools v3.1.20260812',True),('v3.0.20260101',False),('v4.0.1',True),('v2.0.1',False)]:
            with tempfile.TemporaryDirectory() as temp,patch.object(node_install,'WORK',Path(temp)),patch.object(node_install,'SPEC',{'vpn_image':'local/test'}),patch.object(node_install,'own'),patch.object(node_install,'execute',side_effect=[0,version.encode()]):
                if ok:self.assertTrue(node_install.build()['vpn_image_built'])
                else:
                    with self.assertRaises(RuntimeError):node_install.build()

class RuntimeSafetyTests(unittest.TestCase):
    def test_host_execution_refused_before_network_commands(self):
        with patch.dict(os.environ,{'AMDASH_PRIVATE_NETNS':'0'}),patch.object(vpn_runtime,'run') as command:
            with self.assertRaises(RuntimeError):vpn_runtime.start({'role':'direct'})
            command.assert_not_called()
    def test_cascade_no_direct_masquerade_or_eth0_forward(self):
        calls=[]
        with patch.object(vpn_runtime,'run',side_effect=lambda *args:calls.append(args)),patch.object(vpn_runtime,'rule',side_effect=lambda *args:calls.append(args)),patch.object(vpn_runtime.subprocess,'check_output',return_value=b'[]'):
            vpn_runtime.forwarding({'role':'cascade-entry','client_subnet':'10.241.0.0/24'})
        joined=json.dumps(calls);self.assertIn('blackhole',joined);self.assertNotIn('MASQUERADE',joined);self.assertNotIn('eth0',joined)
        self.assertEqual(calls[0],('iptables','-P','FORWARD','DROP'))
    def test_direct_nat_only_own_pool(self):
        with patch.object(vpn_runtime,'run'),patch.object(vpn_runtime,'rule') as command:
            vpn_runtime.forwarding({'role':'direct','client_subnet':'10.241.0.0/24'})
        nat=[c.args for c in command.call_args_list if 'MASQUERADE' in c.args]
        self.assertEqual(len(nat),1);self.assertIn('10.241.0.0/24',nat[0])
    def test_idempotent_rule(self):
        with patch.object(vpn_runtime.subprocess,'run',return_value=types.SimpleNamespace(returncode=0)),patch.object(vpn_runtime,'run') as command:
            vpn_runtime.rule('iptables','-A','FORWARD','-j','ACCEPT');command.assert_not_called()

class FakeRemote:
    calls=[]
    def __init__(self,login,*args):self.login=login;self.closed=False
    def connect(self):return self
    def run(self,args,**kwargs):self.calls.append(('run',self.login.host,args));return b'{}'
    def put(self,*args,**kwargs):self.calls.append(('put',self.login.host,args[0]))
    def close(self):self.closed=True

class FakeRunner(provision.Runner):
    def mkdir(self,*args,**kwargs):pass
    def backup(self,node,after=False):self.events.append(('backup-after' if after else 'backup-before',node))
    def put(self,*args,**kwargs):pass
    def action(self,node,action,*args,**kwargs):
        self.events.append((action,node))
        if action==self.fail:raise InstallError('Simulated failure')
        return {'outside_ip':'203.0.113.2'}
    def configure_nodes(self,*args):self.events.append(('configure','both'))
    def tests(self,*args):self.events.append(('live-gate','both'))
    def finish_panel(self,*args):return 'NEW_PANEL_TEST_PASSWORD'

class RunnerTests(unittest.TestCase):
    def make(self,temp,fail=None,mode='cascade'):
        runner=FakeRunner(settings(mode),temp,lambda text:None,lambda *a:True,lambda plan:True,threading.Event(),FakeRemote,version_lock)
        runner.events=[];runner.fail=fail;return runner
    def test_backup_all_before_packages(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(provision,'read_inventory',return_value=inventory()):
            runner=self.make(temp);result=runner.run()
            self.assertLess(max(i for i,e in enumerate(runner.events) if e[0]=='backup-before'),min(i for i,e in enumerate(runner.events) if e[0]=='prepare'))
            self.assertIn(('live-gate','both'),runner.events);self.assertEqual(result['mode'],'cascade')
            for path in Path(temp).rglob('*.json'):
                self.assertNotIn('FOREIGN_TEST_PASSWORD',path.read_text());self.assertNotIn('ENTRY_TEST_PASSWORD',path.read_text())
            self.assertTrue(all(remote.closed for remote in runner.remotes.values()))
    def test_failure_cannot_report_ready_and_stops_owned(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(provision,'read_inventory',return_value=inventory()):
            runner=self.make(temp,fail='vpn-up')
            with self.assertRaises(InstallError):runner.run()
            self.assertIn(('stop-owned','foreign'),runner.events);self.assertIn(('stop-owned','entry'),runner.events)
            self.assertFalse((runner.session/'result-private.json').exists());self.assertNotIn(('panel','foreign'),runner.events)
    def test_preflight_failure_no_mutations(self):
        info=inventory();info['existing_containers']=1;FakeRemote.calls=[]
        with tempfile.TemporaryDirectory() as temp,patch.object(provision,'read_inventory',return_value=info):
            runner=self.make(temp)
            with self.assertRaises(InstallError):runner.run()
            self.assertEqual(runner.events,[]);self.assertEqual(FakeRemote.calls,[])
    def test_direct_uses_only_one_node(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(provision,'read_inventory',return_value=inventory()):
            runner=self.make(temp,mode='direct');runner.run();self.assertEqual(set(runner.remotes),{'foreign'})
    def test_declined_plan_no_mutation(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(provision,'read_inventory',return_value=inventory()):
            runner=self.make(temp);runner.approve_plan=lambda plan:False
            with self.assertRaises(InstallError):runner.run()
            self.assertEqual(runner.events,[])

class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        for name,data in crypto_config.mutual_tls('127.0.0.1').items():(self.root/name).write_text(data)
        self.tasks=[];self.transports=[];self.servers=[]
    async def asyncTearDown(self):
        for task in self.tasks:task.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
        for server in self.servers:server.close();await server.wait_closed()
        for transport in self.transports:transport.close()
        await asyncio.sleep(.05);self.temp.cleanup()
    async def server(self):
        active=[]
        class Echo(asyncio.DatagramProtocol):
            def connection_made(self,transport):self.transport=transport
            def datagram_received(self,data,address):self.transport.sendto(b'reply:'+data,address)
        transport,_=await asyncio.get_running_loop().create_datagram_endpoint(Echo,local_addr=('127.0.0.1',0));self.transports.append(transport)
        async def accept(reader,writer):
            udp_transport,udp=await asyncio.get_running_loop().create_datagram_endpoint(relay.Datagram,remote_addr=transport.get_extra_info('sockname'))
            self.transports.append(udp_transport)
            try:await relay.bridge(reader,writer,udp)
            except (asyncio.IncompleteReadError,ConnectionError,ValueError):pass
            finally:udp_transport.close()
        def dispatch(reader,writer):self.tasks.append(asyncio.create_task(accept(reader,writer)))
        server=await asyncio.start_server(dispatch,'127.0.0.1',0,ssl=relay.context({'cert_dir':str(self.root)},True),ssl_handshake_timeout=2)
        self.servers.append(server);return server.sockets[0].getsockname()[1]
    async def test_real_mtls_udp_multiple_packets(self):
        port=await self.server();reader,writer=await asyncio.open_connection('127.0.0.1',port,ssl=relay.context({'cert_dir':str(self.root)}),server_hostname='127.0.0.1')
        try:
            self.assertEqual(writer.get_extra_info('ssl_object').version(),'TLSv1.3')
            for packet in (b'one',b'two',os.urandom(1300)):
                writer.write(struct.pack('!H',len(packet))+packet);await writer.drain()
                size=struct.unpack('!H',await asyncio.wait_for(reader.readexactly(2),3))[0]
                self.assertEqual(await asyncio.wait_for(reader.readexactly(size),3),b'reply:'+packet)
        finally:writer.close();await writer.wait_closed()
    async def test_wrong_ca_rejected(self):
        port=await self.server()
        with tempfile.TemporaryDirectory() as temp:
            for name,data in crypto_config.mutual_tls('127.0.0.1').items():(Path(temp)/name).write_text(data)
            with self.assertRaises(ssl.SSLCertVerificationError):
                await asyncio.open_connection('127.0.0.1',port,ssl=relay.context({'cert_dir':temp}),server_hostname='127.0.0.1')
    async def test_wrong_server_identity_rejected(self):
        port=await self.server()
        with self.assertRaises(ssl.SSLCertVerificationError):
            await asyncio.open_connection('127.0.0.1',port,ssl=relay.context({'cert_dir':str(self.root)}),server_hostname='wrong.example')
    async def test_udp_filter_and_queue_limit(self):
        udp=relay.Datagram(('127.0.0.1',51821));udp.datagram_received(b'bad',('127.0.0.1',12345));self.assertTrue(udp.queue.empty())
        for _ in range(300):udp.datagram_received(b'good',('127.0.0.1',51821))
        self.assertEqual(udp.queue.qsize(),256)
    async def test_oversized_frame_closes_bridge(self):
        port=await self.server();reader,writer=await asyncio.open_connection('127.0.0.1',port,ssl=relay.context({'cert_dir':str(self.root)}),server_hostname='127.0.0.1')
        writer.write(struct.pack('!H',65535));await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.read(),3),b'');writer.close();await writer.wait_closed()

if __name__=='__main__':unittest.main(verbosity=2)
