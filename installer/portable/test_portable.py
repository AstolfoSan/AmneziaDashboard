import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import uuid
import zlib

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'app'))
if os.name=='nt':sys.modules['fcntl']=types.SimpleNamespace(LOCK_EX=2,flock=lambda *a:None)
import agent
from panel import create_app
from test_panel import Engine
from portable_settings import PortableSSHAgent,bind_deployment,validate_agent
import configure

def document(vpn):
    value=vpn.strip()[6:];raw=base64.urlsafe_b64decode(value+'='*(-len(value)%4))
    return json.loads(zlib.decompress(raw[4:]))

class PortableTests(unittest.TestCase):
    def config(self,mode='direct'):
        return json.loads((ROOT/'examples'/(mode+'.json')).read_text(encoding='utf-8'))
    def test_direct_and_cascade_render_without_production_hosts_or_unresolved_tokens(self):
        for mode in ('direct','cascade'):
            with tempfile.TemporaryDirectory() as temp:
                out=Path(temp)/mode;configure.render(self.config(mode),out)
                composed=json.loads((out/'compose.yaml').read_text(encoding='utf-8'))
                self.assertNotIn('ports',composed['services']['app'])
                self.assertEqual(composed['services']['app']['mem_limit'],'128m')
                self.assertNotIn('/var/run/docker.sock',json.dumps(composed))
                self.assertEqual(len(composed['services']['web']['ports']),1)
                self.assertEqual(composed['services']['app']['environment']['AGENT_HOST'],
                                 'host.docker.internal' if mode=='direct' else '203.0.113.10')
                key=(out/'authorized-key.example').read_text();self.assertIn('restrict,command=',key)
                self.assertIn('/usr/bin/env -i PATH=',key);self.assertIn('python -E -s ',key)
                self.assertIn('DOCKER_HOST=unix:///var/run/docker.sock',key)
                self.assertIn('172.30.240.2/32' if mode=='direct' else '203.0.113.20/32',key)
                for path in (out/'app'/'static').iterdir():
                    if path.suffix in {'.html','.js'}:self.assertNotIn('__DASHBOARD_',path.read_text(encoding='utf-8'))
                subprocess.run([os.environ['DASHBOARD_NODE'],'--check',str(out/'app'/'static'/'admin.js')],check=True,capture_output=True)
    def test_refuses_overwrite_and_invalid_config_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'existing';output.mkdir();(output/'keep').write_text('preserve')
            with self.assertRaises(ValueError):configure.render(self.config(),output)
            self.assertEqual((output/'keep').read_text(),'preserve')
            bad=self.config();bad['public_origin']='https://bad.example; touch /tmp/injected'
            with self.assertRaises(ValueError):configure.render(bad,Path(temp)/'bad')
            self.assertFalse((Path(temp)/'bad').exists())
        with self.assertRaises(ValueError):configure.render(self.config(),ROOT/'app'/'forbidden-output')
        self.assertFalse((ROOT/'app'/'forbidden-output').exists())
    def test_rejects_shell_parameters_unknown_protocol_and_untrusted_images(self):
        for field,value in [('config_path','/tmp/a;id'),('clients_table','/tmp/a b'),('interface','awg0;id'),
                            ('container','--privileged'),('state_dir','/'),('public_host','-oProxyCommand=bad'),
                            ('mtu',500),('endpoint_port',0),('protocol_version','2.0')]:
            with self.assertRaises(ValueError):validate_agent({'public_host':'203.0.113.10',field:value})
        for bad in ('python:latest','evil@sha256:'+'a'*64):
            config=self.config();config['images']['python']=bad
            with self.assertRaises(ValueError):configure.validate(config)
    def test_network_and_key_source_are_narrow_and_validated(self):
        for cidr in ('0.0.0.0/0','203.0.113.0/28','172.30.240.0/16'):
            config=self.config();config['panel_network_cidr']=cidr
            with self.assertRaises(ValueError):configure.validate(config)
        config=self.config('cascade');config['agent']['source_cidr']='0.0.0.0/0'
        with self.assertRaises(ValueError):configure.validate(config)
    def test_route_labels_are_escaped_without_changing_the_javascript_program(self):
        config=self.config();config['route_label']="Foreign <script>alert('x')</script> \\"
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'rendered';configure.render(config,out)
            self.assertNotIn("<script>alert('x')",(out/'app'/'static'/'admin.html').read_text(encoding='utf-8'))
            subprocess.run([os.environ['DASHBOARD_NODE'],'--check',str(out/'app'/'static'/'admin.js')],check=True,capture_output=True)
    def test_ssh_transport_is_configurable_and_never_disables_host_key_validation(self):
        env={'AGENT_HOST':'foreign.example.com','AGENT_PORT':'2222','AGENT_USER':'root'}
        result=types.SimpleNamespace(returncode=0,stdout=json.dumps({'ok':True,'result':{'peers':[]}}))
        with patch.dict(os.environ,env),patch('portable_settings.subprocess.run',return_value=result) as run:
            self.assertEqual(PortableSSHAgent()({'action':'stats'}),{'peers':[]})
        argv=run.call_args.args[0];self.assertEqual(argv[-1],'root@foreign.example.com')
        self.assertIn('2222',argv);self.assertIn('StrictHostKeyChecking=yes',argv)
        self.assertIn('UserKnownHostsFile=/run/secrets/agent_known_hosts',argv)
        self.assertNotIn('StrictHostKeyChecking=no',argv)
    def test_direct_and_cascade_conf_reuse_the_same_guest_and_configured_endpoint(self):
        import base64
        from awg_export import conf_from_vpn
        valid=base64.b64encode(bytes([7])*32).decode()
        for host in ('203.0.113.99','203.0.113.10'):
            with tempfile.TemporaryDirectory() as temp,patch.object(agent,'HOST',host),patch.dict(agent.SETTINGS,
                 {'endpoint_port':55123,'mtu':1360,'dns1':'9.9.9.9','dns2':'1.0.0.1'}):
                engine=Engine();engine.cfg=engine.cfg.replace('HeaderProtectionKey = HEADER','HeaderProtectionKey = '+valid)
                engine.wg=lambda field:{valid:[]} if field=='public-key' else {}
                worker=agent.Agent(Path(temp),engine);uid=str(uuid.uuid4());worker.create(uid,'Synthetic phone')
                before=engine.cfg;records={p.name:p.read_bytes() for p in Path(temp).glob('*.enc')}
                vpn=worker.export(uid)['vpn'];conf=conf_from_vpn(vpn)
                self.assertIn('Endpoint = '+host+':55123',conf);self.assertIn('MTU = 1360',conf)
                self.assertIn('DNS = 9.9.9.9, 1.0.0.1',conf)
                self.assertEqual(worker.export(uid)['vpn'],vpn);self.assertEqual(engine.cfg,before)
                self.assertEqual({p.name:p.read_bytes() for p in Path(temp).glob('*.enc')},records)

    def test_direct_vpn_export_uses_foreign_endpoint_port_dns_and_description(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(agent,'HOST','203.0.113.99'),patch.dict(agent.SETTINGS,
             {'route_label':'Прямой зарубежный VPN','endpoint_port':55123,'mtu':1360,'dns1':'9.9.9.9','dns2':'1.0.0.1'}):
            engine=Engine();before=engine.cfg;worker=agent.Agent(Path(temp),engine);uid=str(uuid.uuid4())
            worker.create(uid,'Телефон');vpn=worker.export(uid)['vpn'];doc=document(vpn)
            last=json.loads(doc['containers'][0]['awg']['last_config'])
            self.assertEqual(doc['hostName'],'203.0.113.99');self.assertEqual(doc['dns1'],'9.9.9.9')
            self.assertEqual(doc['description'],'Прямой зарубежный VPN · Телефон')
            self.assertIn('Endpoint = 203.0.113.99:55123',last['config']);self.assertIn('MTU = 1360',last['config'])
            self.assertEqual(last['port'],55123);self.assertEqual(last['mtu'],'1360')
            self.assertNotIn('userName',doc);self.assertNotIn('password',doc)
            worker.access({'id':uid,'paused':True});worker.access({'id':uid,'paused':False})
            self.assertEqual(worker.export(uid)['vpn'],vpn)
            worker.revoke(uid);self.assertEqual(engine.cfg.rstrip(),before.rstrip())
    def test_direct_panel_issues_and_downloads_config_through_the_restricted_worker_api(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);worker=agent.Agent(root/'agent',Engine())
            app=create_app({'DATA_DIR':str(root/'panel'),'COLLECTOR':False,'COOKIE_SECURE':False,'PUBLIC_ORIGIN':'http://localhost'},worker.dispatch)
            client=app.test_client();headers={'Origin':'http://localhost'}
            password=(root/'panel'/'bootstrap-password.txt').read_text().strip()
            self.assertEqual(client.post('/api/login',json={'username':'owner','password':password},headers=headers).status_code,200)
            headers['X-CSRF-Token']=client.get('/api/session').json['csrf']
            gid=client.post('/api/groups',json={'name':'Direct'},headers=headers).json['id']
            uid=str(uuid.uuid4());self.assertEqual(client.post('/api/devices',json={'id':uid,'group_id':gid,'name':'Phone','download_token':'x'*32},headers=headers).status_code,200)
            response=client.get('/api/devices/'+uid+'/download')
            self.assertEqual(response.status_code,200);self.assertEqual(document(response.get_data(as_text=True))['hostName'],'203.0.113.10')
            self.assertIn('AmneziaVPN-',response.headers['Content-Disposition'])
    def test_cascade_export_uses_the_entry_not_the_exit_and_meters_are_unchanged(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(agent.SETTINGS,{'route_label':'Вход → Выход'}):
            worker=agent.Agent(Path(temp),Engine());uid=str(uuid.uuid4());worker.create(uid,'Laptop')
            self.assertEqual(document(worker.export(uid)['vpn'])['hostName'],'203.0.113.10')
            self.assertEqual(document(worker.export(uid)['vpn'])['description'],'Вход → Выход · Laptop')
    def test_state_binding_prevents_accidental_reuse_on_another_server(self):
        with tempfile.TemporaryDirectory() as temp:
            settings=validate_agent({'public_host':'203.0.113.10'})
            bind_deployment(temp,settings);bind_deployment(temp,settings)
            with self.assertRaises(ValueError):bind_deployment(temp,{**settings,'public_host':'203.0.113.99'})
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp)/'master.key').write_text('synthetic-existing-state')
            with self.assertRaises(ValueError):bind_deployment(temp,settings)
    def test_custom_docker_name_does_not_change_the_client_protocol_container_type(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(agent,'CONTAINER','custom-awg-runtime'):
            worker=agent.Agent(Path(temp),Engine());uid=str(uuid.uuid4());worker.create(uid,'Phone')
            doc=document(worker.export(uid)['vpn'])
            self.assertEqual(doc['defaultContainer'],'amnezia-awg2')
            self.assertEqual(doc['containers'][0]['container'],'amnezia-awg2')
            self.assertEqual(doc['containers'][0]['awg']['protocol_version'],'3.1')
    def test_docker_worker_uses_configured_container_interface_and_in_container_keygen(self):
        engine=agent.Docker()
        with patch.object(engine,'run',return_value=b'PUBLIC\n') as run:engine.key(public=True,private='PRIVATE')
        self.assertEqual(run.call_args.args[0],['docker','exec','-i',agent.CONTAINER,agent.AWG,'pubkey'])
        with patch.object(engine,'run',return_value=b'PUB 1 2\n') as run:engine.wg('transfer')
        self.assertIn(agent.IFACE,run.call_args.args[0]);self.assertIn(agent.CONTAINER,run.call_args.args[0])

if __name__=='__main__':unittest.main()
