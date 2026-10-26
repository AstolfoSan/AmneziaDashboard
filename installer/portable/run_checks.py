"""Verify release hashes and run the retained suite plus portability tests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--node',default=shutil.which('node'));args=parser.parse_args()
if not args.node:raise SystemExit('Node.js is required for UI checks; supply --node /absolute/path/to/node')
manifest=json.loads((ROOT/'MANIFEST.sha256.json').read_text(encoding='utf-8'))
for name,expected in manifest.items():
    path=(ROOT/name).resolve()
    assert path.is_relative_to(ROOT) and hashlib.sha256(path.read_bytes()).hexdigest()==expected,'Release hash mismatch: '+name
with tempfile.TemporaryDirectory(prefix='amnezia-portable-check-') as temp:
    settings=Path(temp)/'agent.json';settings.write_text(json.dumps({'public_host':'203.0.113.10'}),encoding='utf-8');settings.chmod(0o600)
    env={**os.environ,'AMNEZIA_AGENT_CONFIG':str(settings),'PYTHONDONTWRITEBYTECODE':'1','DASHBOARD_NODE':str(args.node)}
    subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT/'app'),'-p','test_*.py','-q'],cwd=ROOT,env=env,check=True)
    subprocess.run([sys.executable,'-m','unittest','test_portable','-v'],cwd=ROOT,env=env,check=True)
    for path in sorted((ROOT/'app').glob('test_*.cjs')):subprocess.run([args.node,str(path)],cwd=ROOT,env=env,check=True)
print(json.dumps({'release_hashes_verified':len(manifest),'all_checks_passed':True,'real_server_changes':False}))
