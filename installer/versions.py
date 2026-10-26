"""Public official release discovery. A failed lookup is not silently 'latest'."""
import json
import re
import urllib.parse
import urllib.request
from model import InstallError
from version import VERSION

def get_json(url,headers=None):
    if not url.startswith('https://'):raise InstallError('Источник должен использовать HTTPS')
    request=urllib.request.Request(url,headers={'User-Agent':'AmneziaDashboardInstaller/'+VERSION,**(headers or {})})
    with urllib.request.urlopen(request,timeout=25) as response:
        if not response.url.startswith('https://'):raise InstallError('Небезопасное перенаправление источника релизов')
        raw=response.read(2*1024**2+1)
        if len(raw)>2*1024**2:raise InstallError('Слишком большой ответ источника релизов')
        return json.loads(raw),response.headers

def release(repo):
    if repo not in {'amnezia-vpn/amnezia-client','acmesh-official/acme.sh'}:raise InstallError('Неофициальный репозиторий')
    meta,_=get_json('https://api.github.com/repos/'+repo+'/releases/latest')
    tag=meta.get('tag_name','')
    if meta.get('draft') or meta.get('prerelease') or not re.fullmatch(r'v?\d+(?:\.\d+){1,4}',tag):raise InstallError('Не найден стабильный официальный релиз')
    ref,_=get_json('https://api.github.com/repos/'+repo+'/git/ref/tags/'+urllib.parse.quote(tag,safe=''))
    obj=ref['object']
    if obj['type']=='tag':obj=get_json('https://api.github.com/repos/'+repo+'/git/tags/'+obj['sha'])[0]['object']
    if obj['type']!='commit' or not re.fullmatch(r'[0-9a-f]{40}',obj['sha']):raise InstallError('Релиз не привязан к проверяемому commit')
    return {'repository':repo,'tag':tag,'commit':obj['sha']}

def image(repo,tag):
    allowed={'amneziavpn/amneziawg-go','library/python','library/nginx','library/alpine'}
    if repo not in allowed or not re.fullmatch(r'[A-Za-z0-9._-]+',tag):raise InstallError('Неофициальный Docker-источник')
    token=get_json('https://auth.docker.io/token?service=registry.docker.io&scope=repository:'+repo+':pull')[0]['token']
    meta,headers=get_json('https://registry-1.docker.io/v2/'+repo+'/manifests/'+tag,
        {'Authorization':'Bearer '+token,'Accept':'application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json'})
    digest=headers.get('Docker-Content-Digest','')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}',digest):raise InstallError('Registry не вернул digest образа')
    platforms=sorted({p.get('platform',{}).get('architecture') for p in meta.get('manifests',[]) if p.get('platform',{}).get('os')=='linux'}- {None})
    if not platforms and re.fullmatch(r'sha256:[0-9a-f]{64}',meta.get('config',{}).get('digest','')):
        config,_=get_json('https://registry-1.docker.io/v2/'+repo+'/blobs/'+meta['config']['digest'],{'Authorization':'Bearer '+token})
        if config.get('os')=='linux':platforms=[config['architecture']]
    canonical=repo.removeprefix('library/')
    return {'image':canonical+'@'+digest,'tag_at_resolution':tag,'platforms':platforms}

def discover():
    try:
        return {'amnezia_client':release('amnezia-vpn/amnezia-client'),'acme':release('acmesh-official/acme.sh'),
                'awg':image('amneziavpn/amneziawg-go','latest'),'alpine':image('library/alpine','latest'),
                'python':image('library/python','3.12-slim-bookworm'),'nginx':image('library/nginx','stable-alpine')}
    except InstallError:raise
    except Exception as error:raise InstallError('Не удалось проверить актуальные официальные релизы. Серверы не изменены.') from error
