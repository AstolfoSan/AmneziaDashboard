"""Build deterministic, scanned source assets for GitHub Releases."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

from privacy_check import ROOT,scan,source_files


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'dist');args=parser.parse_args()
    version=(ROOT/'VERSION').read_text().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise SystemExit('Invalid VERSION')
    before=scan()
    if not before['passed']:raise SystemExit(json.dumps(before))
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    archive=output/'AmneziaDashboard.zip';sums=output/'SHA256SUMS'
    if archive.exists() or sums.exists():raise SystemExit('Release output exists; do not overwrite a published build')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as zipped:
        for name,path in source_files():
            # Root allowlist: never package unrelated files from a development folder.
            if name.split('/')[0] not in {'installer','docs','tools','.github','README.md','README_RU.md','VERSION','LICENSE',
                'CHANGELOG.md','SECURITY.md','CONTRIBUTING.md','CODE_OF_CONDUCT.md','THIRD_PARTY_NOTICES.md',
                'AGENTS.md','.gitignore','.gitattributes','VALIDATION.json'}:raise SystemExit('Unexpected release input: '+name)
            info=zipfile.ZipInfo('AmneziaDashboard/'+name,date_time=(2020,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED;info.create_system=3;info.external_attr=0o100644<<16
            zipped.writestr(info,path.read_bytes())
    after=scan(archive=archive)
    if not after['passed']:raise SystemExit(json.dumps(after))
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    sums.write_text(digest+'  '+archive.name+'\n',encoding='ascii')
    print(json.dumps({'version':version,'archive':archive.name,'files':after['files_checked'],
                      'sha256':digest,'bytes':archive.stat().st_size,'privacy_scan_passed':True}))
