"""Run local safety/regression checks; never provision a server."""
import ast
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}


def run(args,cwd=ROOT):subprocess.run(args,cwd=cwd,env=env,check=True)


if __name__=='__main__':
    node=os.environ.get('DASHBOARD_NODE') or shutil.which('node')
    if not node:raise SystemExit('Node.js 20+ is needed; set DASHBOARD_NODE to its path')
    version=(ROOT/'VERSION').read_text().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise SystemExit('VERSION must be MAJOR.MINOR.PATCH')
    scope={};exec(compile((ROOT/'installer/version.py').read_text(),'<version>','exec'),scope)
    if scope['VERSION']!=version:raise SystemExit('Installer and project versions differ')
    run([sys.executable,'tools/privacy_check.py'])
    run([sys.executable,'tools/manifest.py','--check'])
    run([sys.executable,'-m','unittest','discover','-s','tools','-p','test_*.py','-q'])
    for path in ROOT.rglob('*.py'):
        if not any(p in {'.venv','__pycache__','dist','build'} for p in path.relative_to(ROOT).parts):ast.parse(path.read_text(encoding='utf-8'),filename=path.relative_to(ROOT).as_posix())
    for path in ROOT.rglob('*.md'):
        for link in re.findall(r'\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
            if '://' in link or link.startswith('#'):continue
            destination=(path.parent/link.split('#',1)[0]).resolve()
            if not destination.is_relative_to(ROOT) or not destination.exists():raise SystemExit('Broken local documentation link: '+path.relative_to(ROOT).as_posix())
    run([sys.executable,'-m','unittest','discover','-s','installer','-p','test_*.py','-q'])
    run([sys.executable,'installer/portable/run_checks.py','--node',node])
    run([sys.executable,'installer/cli.py','--self-test'])
    print(json.dumps({'version':version,'local_checks_passed':True,'fresh_vps_acceptance':False}))
