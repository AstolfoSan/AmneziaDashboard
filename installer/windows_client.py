"""Download an official, digest-verified client. Never silently accept its setup."""
import hashlib
from pathlib import Path
import json
import os
import re
import ssl
import subprocess
import urllib.parse
import urllib.request
import uuid

API='https://api.github.com/repos/amnezia-vpn/amnezia-client/releases/latest'
PREFIX='https://github.com/amnezia-vpn/amnezia-client/releases/download/'
HOSTS={'github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'}
MAX_SIZE=512*1024**2


def open_url(url):
    request=urllib.request.Request(url,headers={'User-Agent':'AmneziaDashboardSetup','Accept':'application/vnd.github+json' if url==API else 'application/octet-stream'})
    response=urllib.request.urlopen(request,timeout=45,context=ssl.create_default_context())
    final=urllib.parse.urlsplit(response.url)
    allowed={'api.github.com'} if url==API else HOSTS
    if final.scheme!='https' or final.hostname not in allowed:
        response.close();raise ValueError('Unexpected download redirect')
    return response


def resolve():
    with open_url(API) as response:data=response.read(2*1024**2+1)
    if len(data)>2*1024**2:raise ValueError('Release metadata too large')
    release=json.loads(data)
    if release.get('prerelease') or release.get('draft'):raise ValueError('Stable release required')
    assets=[a for a in release.get('assets',[]) if re.fullmatch(r'AmneziaVPN_[0-9.]+_windows_x64\.exe',a.get('name',''))]
    if len(assets)!=1:raise ValueError('Expected one official Windows x64 installer')
    asset=assets[0];url=asset['browser_download_url'];parsed=urllib.parse.urlsplit(url)
    digest=asset.get('digest','');size=asset.get('size')
    if not url.startswith(PREFIX) or parsed.query or parsed.fragment or not re.fullmatch(r'sha256:[0-9a-f]{64}',digest):raise ValueError('Official URL and SHA-256 required')
    if type(size) is not int or not 0<size<=MAX_SIZE:raise ValueError('Unexpected installer size')
    return {'url':url,'sha256':digest[7:],'size':size,'name':asset['name']}


def download(cache,progress=lambda value:None):
    asset=resolve();cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    target=cache/(uuid.uuid4().hex+'-'+asset['name']);partial=target.with_suffix('.part');digest=hashlib.sha256();size=0
    try:
        with open_url(asset['url']) as response,partial.open('xb') as output:
            while chunk:=response.read(1024**2):
                size+=len(chunk)
                if size>asset['size']:raise ValueError('File exceeds official size')
                digest.update(chunk);output.write(chunk);progress(round(100*size/asset['size']))
        if size!=asset['size'] or digest.hexdigest()!=asset['sha256']:raise ValueError('Client SHA-256 or length mismatch')
        partial.replace(target);return target
    except BaseException:
        partial.unlink(missing_ok=True);raise


def launch(path):
    if os.name!='nt':raise RuntimeError('Client setup is Windows-only')
    return subprocess.Popen([str(Path(path).resolve())],shell=False)
