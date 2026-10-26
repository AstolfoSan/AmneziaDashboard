"""Validate five generated Compose variants; no engine, SSH or VPS required."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'installer'))
from provision import vpn_compose


if __name__=='__main__':
    docker=shutil.which('docker')
    if not docker:raise SystemExit('Docker CLI and Compose are needed; no running engine is required')
    spec=importlib.util.spec_from_file_location('compose_renderer',ROOT/'installer/portable/configure.py')
    renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)
    with tempfile.TemporaryDirectory(prefix='dashboard-compose-') as temporary:
        root=Path(temporary)
        for mode in ('direct','cascade'):
            config=json.loads((ROOT/'installer/portable/examples'/(mode+'.json')).read_text(encoding='utf-8'))
            config['publish_http_challenge']=True;directory=root/mode;renderer.render(config,directory)
            data=json.loads((directory/'compose.yaml').read_text(encoding='utf-8'));web=data['services']['web']
            # A directory bind avoids Windows drive/file-bind parser ambiguity.
            web['volumes']=['./nginx:/config:ro' if v=='./nginx.conf:/etc/nginx/nginx.conf:ro' else v for v in web['volumes']]
            web['entrypoint']=['nginx','-c','/config/nginx.conf','-g','daemon off;']
            path=directory/'compose.yaml';path.write_text(json.dumps(data),encoding='utf-8')
            subprocess.run([docker,'compose','-f',str(path),'config','--quiet'],check=True)
        for role in ('direct','cascade-entry','cascade-exit'):
            data=vpn_compose({'role':role,'vpn_port':39265,'relay_port':443,'vpn_image':'local/installer-test:1','run_id':'abcdef123456',
                              'vpn_ip':'172.31.220.2','vpn_ram_mib':256,'vpn_cpu':.65},'172.31.220.0/28')
            path=root/(role+'.json');path.write_text(json.dumps(data),encoding='utf-8')
            subprocess.run([docker,'compose','-f',str(path),'config','--quiet'],check=True)
    print(json.dumps({'compose_variants_passed':5,'docker_engine_used':False,'vps_changes':False}))
