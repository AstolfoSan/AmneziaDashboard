"""Generate/check the embedded portable source manifest; no network or VPS use."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/'installer/portable'


def expected():
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(ROOT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts
            and p.name!='MANIFEST.sha256.json' and p.suffix!='.pyc'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    path=ROOT/'MANIFEST.sha256.json';value=expected()
    if args.check:
        if json.loads(path.read_text(encoding='utf-8'))!=value:raise SystemExit('Embedded manifest is stale; run python tools/manifest.py')
    else:path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'embedded_files':len(value),'manifest_matches':True}))
