"""Compose parser and Python AST checks; no Docker engine or VPS is used."""
import ast
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from provision import vpn_compose

ROOT=Path(__file__).resolve().parent

def main():
    docker=shutil.which('docker')
    if not docker:raise SystemExit('Docker CLI with Compose is required; engine is not needed')
    count=0
    for source in ROOT.rglob('*.py'):
        if '__pycache__' not in source.parts:ast.parse(source.read_text(encoding='utf-8'),filename=str(source));count+=1
    spec=importlib.util.spec_from_file_location('compose_renderer',ROOT/'portable/configure.py');renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)
    with tempfile.TemporaryDirectory(prefix='amnezia-installer-compose-') as temp:
        temp=Path(temp)
        for mode in ('direct','cascade'):
            config=json.loads((ROOT/'portable/examples'/(mode+'.json')).read_text(encoding='utf-8'))
            config['publish_http_challenge']=True;directory=temp/mode;renderer.render(config,directory)
            data=json.loads((directory/'compose.yaml').read_text(encoding='utf-8'))
            web=data['services']['web'];web['volumes']=['./nginx:/config:ro' if v=='./nginx.conf:/etc/nginx/nginx.conf:ro' else v for v in web['volumes']]
            web['entrypoint']=['nginx','-c','/config/nginx.conf','-g','daemon off;']
            (directory/'compose.yaml').write_text(json.dumps(data),encoding='utf-8')
            subprocess.run([docker,'compose','-f',str(directory/'compose.yaml'),'config','--quiet'],check=True)
        for role in ('direct','cascade-entry','cascade-exit'):
            data=vpn_compose({'role':role,'vpn_port':39265,'relay_port':443,'vpn_image':'local/installer-test:1','run_id':'abcdef123456',
                              'vpn_ip':'172.31.220.2','vpn_ram_mib':256,'vpn_cpu':.65},'172.31.220.0/28')
            path=temp/(role+'.json');path.write_text(json.dumps(data),encoding='utf-8')
            subprocess.run([docker,'compose','-f',str(path),'config','--quiet'],check=True)
    print(json.dumps({'python_ast_files':count,'compose_variants_passed':5,'docker_engine_used':False,'vps_changes':False}))

if __name__=='__main__':main()
