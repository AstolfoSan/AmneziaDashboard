"""Fail closed on private files, credentials, non-example IPs and unsafe ZIP paths."""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path,PurePosixPath
import re
import zipfile

ROOT=Path(__file__).resolve().parents[1]
SKIP={'.git','.venv','venv','__pycache__','.pytest_cache','dist','build'}
PRIVATE_DIRS={'data','secrets','certs','sessions','backups','.ssh'}
PRIVATE_SUFFIXES={'.vpn','.conf','.pem','.key','.enc','.db','.sqlite','.sqlite3','.log','.exe'}
PRIVATE_NAMES={'result-private.json','bootstrap-password.txt','master.key','known_hosts','authorized_keys','.env'}
TEXT_SUFFIXES={'.py','.cjs','.js','.html','.css','.svg','.md','.yml','.yaml','.json','.txt','.toml','.ps1','.sh'}
PLAIN_NAMES={'VERSION','LICENSE','Dockerfile','.gitignore','.gitattributes','.dockerignore','SHA256SUMS'}
PUBLIC_IPS={'1.1.1.1','1.0.0.1','8.8.8.8','8.8.4.4','9.9.9.9'}
TEST_ADDRESSES={'224.0.0.1'} # Deliberately rejected multicast input in validation tests.
# These are version strings in synthetic upstream test metadata, not host addresses.
TEST_VERSIONS={'5.0.3.0','5.0.3.1','6.0.0.0'}
PNG_HASHES={'amnezia-add-key.png':'b832bb8bda0b9be8604424e1702991378804ff85b7dd9435a52f616f7f1c063a',
            'amnezia-paste-key.png':'67742294337769a419f2b70ee49657b7613a170199c66d91a41c59366ab807da'}
DOC_PNG_HASHES=json.loads((ROOT/'docs/images/REVIEWED.json').read_text(encoding='utf-8'))
PATTERNS=[re.compile(rb'-----BEGIN (?:OPENSSH |RSA |EC |ENCRYPTED )?PRIVATE KEY-----'),
          re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}'),
          re.compile(rb'vpn://[A-Za-z0-9_-]{80,}'),
          re.compile(rb'(?i)[a-z]:[\\/]Users[\\/](?!Public[\\/])[^\s"<>]+'),
          re.compile(rb'(?i)/(?:home|Users)/[a-z][a-z0-9_-]+/'),
          re.compile(rb'(?i)ssh-ed25519 AAAA[A-Za-z0-9+/]{30,}')]


def inspect(name,payload):
    path=PurePosixPath(name);issues=[]
    if path.is_absolute() or '..' in path.parts or '\\' in name:issues.append('unsafe path')
    if any(part in PRIVATE_DIRS for part in path.parts) or path.name in PRIVATE_NAMES or path.name.startswith('.env.') or path.suffix.lower() in PRIVATE_SUFFIXES:
        issues.append('private/runtime file')
    if path.suffix=='.png':
        canonical=name.removeprefix('AmneziaDashboard/')
        expected=DOC_PNG_HASHES.get(canonical) or (PNG_HASHES.get(path.name) if canonical.startswith('installer/portable/app/static/') else None)
        if not expected or hashlib.sha256(payload).hexdigest()!=expected:issues.append('unreviewed image')
        offset=8
        if payload[:8]!=b'\x89PNG\r\n\x1a\n':issues.append('invalid PNG')
        while offset+12<=len(payload):
            length=int.from_bytes(payload[offset:offset+4],'big');kind=payload[offset+4:offset+8]
            if kind in {b'tEXt',b'iTXt',b'zTXt',b'eXIf'}:issues.append('image metadata')
            offset+=length+12
    elif path.suffix not in TEXT_SUFFIXES and path.name not in PLAIN_NAMES:issues.append('unexpected file type')
    else:
        try:text=payload.decode('utf-8')
        except UnicodeDecodeError:return issues+['non-UTF8 source']
        if any(pattern.search(payload) for pattern in PATTERNS):issues.append('credential or private identity pattern')
        for value in set(re.findall(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])',text)):
            try:address=ipaddress.ip_address(value)
            except ValueError:continue
            example=any(address in ipaddress.ip_network(net) for net in ('192.0.2.0/24','198.51.100.0/24','203.0.113.0/24'))
            private=any(address in ipaddress.ip_network(net) for net in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))
            if not (example or private or address.is_loopback or address.is_unspecified or value in PUBLIC_IPS|TEST_VERSIONS|TEST_ADDRESSES):
                issues.append('non-example public IPv4');break
    return sorted(set(issues))


def source_files(root=ROOT):
    for path in sorted(root.rglob('*')):
        relative=path.relative_to(root)
        if any(part in SKIP for part in relative.parts):continue
        if path.is_symlink():raise ValueError('Symlink is not a release input: '+relative.as_posix())
        if path.is_file():yield relative.as_posix(),path


def scan(root=ROOT,archive=None):
    failures={};count=0
    if archive:
        with zipfile.ZipFile(archive) as zipped:
            if zipped.testzip():raise ValueError('Archive CRC error')
            for item in zipped.infolist():
                if item.is_dir():continue
                if item.file_size>5*1024**2:raise ValueError('Unexpected oversized source asset')
                errors=inspect(item.filename,zipped.read(item));count+=1
                if errors:failures[item.filename]=errors
    else:
        for name,path in source_files(root):
            errors=inspect(name,path.read_bytes());count+=1
            if errors:failures[name]=errors
    return {'files_checked':count,'passed':not failures,'findings':failures}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--archive',type=Path);args=parser.parse_args()
    result=scan(archive=args.archive);print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
