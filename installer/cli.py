"""Interactive terminal wizard. Passwords are hidden; no credentials in argv."""
from i18n import tr,set_language
import argparse
import getpass
import hashlib
import json
from pathlib import Path
import queue
import ssl
import sys
import threading
from model import Login,Settings,InstallError
from provision import Runner,ROOT
import crypto_config
import versions
from version import VERSION

def ask(text,default=''):
    value=input(text+(' ['+str(default)+']' if default!='' else '')+': ').strip()
    return value if value else str(default)

def yes(text):return ask(text+tr(' (да/нет)'),tr('нет')).lower() in {tr('да'),'yes','y'}

def number(text,default):
    while True:
        try:return int(ask(text,default))
        except ValueError:print(tr('Введите целое число.'))

def node(title):
    print('\n'+title+tr(' · SSH-пользователь root'))
    while True:
        host=ask(tr('Публичный IPv4'));port=number(tr('SSH-порт'),22)
        method=ask(tr('Доступ: 1 — пароль root, 2 — приватный SSH-ключ'),'1')
        if method not in {'1','2'}:print(tr('Выберите 1 или 2.'));continue
        if method=='1':login=Login(host,port,password=getpass.getpass(tr('Пароль root (ввод скрыт): ')))
        else:
            path=ask(tr('Путь к приватному ключу (не .pub)')).strip('"')
            login=Login(host,port,key_file=path,passphrase=getpass.getpass(tr('Пароль ключа, если есть (Enter — без пароля): ')))
        try:return login.validate()
        except InstallError as error:print(tr('Ошибка: ')+str(error))

def collect():
    if not sys.stdin.isatty():raise InstallError(tr('Нужен интерактивный терминал: ввод SSH-паролей через pipe/файл запрещён'))
    print('AmneziaDashboard '+VERSION+tr(' — пошаговый установщик'))
    print(tr('PREVIEW: первый полный прогон на чистых VPS ещё необходим.'))
    print(tr('Нужны новые Ubuntu 24.04, root, TUN, от 1 ГБ RAM и 3 ГБ свободного диска.'))
    print(tr('Существующие VPN не перезаписываются. Ctrl+C — безопасная остановка между этапами.'))
    while True:
        choice=ask(tr('\nРежим: 1 — каскад RU → зарубежный, 2 — только зарубежный'),'1')
        if choice in {'1','2'}:break
        print(tr('Выберите 1 или 2.'))
    mode='cascade' if choice=='1' else 'direct'
    foreign=node(tr('Зарубежный VPS (здесь будет панель)'))
    entry=node(tr('RU-вход каскада')) if mode=='cascade' else None
    print(tr('\nПорты по умолчанию: VPN 39265/udp, панель 10443/tcp, каскад 443/tcp.'))
    vpn,panel,tls=39265,10443,443
    if yes(tr('Изменить порты?')):
        vpn=number('VPN UDP',vpn);panel=number(tr('Панель TCP'),panel)
        if mode=='cascade':tls=number(tr('TLS каскада TCP'),tls)
    email=ask(tr('Email для центра сертификации (необязательно)'))
    print(tr('\nHTTPS по IP: ознакомьтесь с условиями Let’s Encrypt:'))
    print('https://letsencrypt.org/repository/')
    print(tr('IP панели будет передан CA и опубликован в журналах сертификатов. На зарубежном нужен открытый TCP 80.'))
    consent=yes(tr('Вы принимаете условия Let’s Encrypt для этого выпуска сертификата?'))
    return Settings(mode,foreign,entry,vpn,panel,tls,email,consent).validate()

def confirm_host(host,fingerprint):
    print(tr('\nНовый SSH-сервер: ')+host+tr('\nОтпечаток: ')+fingerprint)
    print(tr('Сверьте отпечаток с консолью хостинга или доверенным подключением.'))
    return yes(tr('Подтвердить этот SSH-сервер?'))

def confirm_plan(plan):
    print(tr('\nПлан изменений:'))
    print(tr('  Режим: ')+(tr('каскад') if plan['mode']=='cascade' else tr('прямой VPN')))
    print(tr('  VPN-вход: ')+plan['entry_ip']+' · UDP '+str(plan['vpn_udp_port']))
    print(tr('  Зарубежный VPS: ')+plan['foreign_ip']+tr(' · Панель: ')+plan['panel_url'])
    print(tr('  Актуальный клиент: ')+plan['versions']['amnezia_client']['tag'])
    print(tr('  Серверный образ: ')+plan['versions']['awg']['image'])
    print(tr('  Сначала — приватные резервные копии обоих VPS (для прямого режима одного).'))
    print(tr('  Затем — Docker, AmneziaWG, панель, новые ключи, правила её портов и таймеры.'))
    print(tr('  Профили VPN-входа: ')+plan['networks']['clients'])
    print(tr('  Это не обновление существующей VPN-установки. Платные услуги не приобретаются.'))
    return ask(tr('Для начала изменений напишите УСТАНОВИТЬ'))==tr('УСТАНОВИТЬ')

def run_wizard(settings,home):
    events=queue.Queue();cancel=threading.Event()
    def approve(kind,value):
        reply=queue.Queue();events.put((kind,(value,reply)))
        while not cancel.is_set():
            try:return reply.get(timeout=.25)
            except queue.Empty:pass
        return False
    def work():
        try:
            runner=Runner(settings,home,lambda value:events.put(('log',value)),
                lambda host,fp:approve('host',(host,fp)),lambda plan:approve('plan',plan),cancel)
            events.put(('done',runner.run()))
        except Exception as error:events.put(('error',str(error)))
    thread=threading.Thread(target=work,name='installer',daemon=False);thread.start()
    while True:
        try:
            try:kind,value=events.get(timeout=.2)
            except queue.Empty:continue
            if kind=='log':print(value,flush=True)
            elif kind in {'host','plan'}:
                data,reply=value
                reply.put(False if cancel.is_set() else confirm_host(*data) if kind=='host' else confirm_plan(data))
            elif kind=='error':
                thread.join();print(tr('\nУстановка НЕ завершена: ')+value);print(tr('Состояние и приватные материалы: ')+str(home/'sessions'));return 1
            elif kind=='done':
                thread.join();print(tr('\nГОТОВО. Панель: ')+value['url']+tr('/admin\nЛогин: owner'))
                print(tr('Новый первый пароль и резервные копии: ')+value['backup_directory'])
                print(tr('Откройте result-private.json в этой папке и смените первый пароль в панели.'))
                print(tr('Не пересылайте приватную папку другим людям.'))
                try:show=yes(tr('Показать первый пароль здесь (он останется в прокрутке терминала)?'))
                except (KeyboardInterrupt,EOFError):show=False
                if show:print(tr('Первый пароль: ')+value['password'])
                return 0
        except (KeyboardInterrupt,EOFError):
            cancel.set();print(tr('\nЗапрошена остановка. Дождитесь окончания текущего этапа и очистки только новой установки.'),flush=True)

def self_test():
    # No metadata lookups, SSH, terms acceptance, writes or network calls.
    manifest=json.loads((ROOT/'portable/MANIFEST.sha256.json').read_text(encoding='utf-8'))
    for name,digest in manifest.items():
        path=(ROOT/'portable'/name).resolve()
        if not path.is_relative_to((ROOT/'portable').resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise RuntimeError('Embedded source hash mismatch')
    for name in ('node_install.py','relay.py','vpn_runtime.py'):
        compile((ROOT/name).read_text(encoding='utf-8'),name,'exec')
    if len(crypto_config.wg_key()['public'])!=44:raise RuntimeError('Crypto self-test failed')
    context=ssl.create_default_context()
    if context.verify_mode!=ssl.CERT_REQUIRED or not context.check_hostname:raise RuntimeError('Unsafe TLS defaults')
    print(json.dumps({'version':VERSION,'embedded_hashes':len(manifest),'tls_context_verified':True,'self_test_passed':True,'vps_accessed':False}))

def main():
    parser=argparse.ArgumentParser(description='AmneziaDashboard terminal installer')
    parser.add_argument('--self-test',action='store_true',help='Offline embedded-resource check; no SSH or network')
    parser.add_argument('--check-sources',action='store_true',help='Read only public official release metadata; no SSH')
    parser.add_argument('--home',type=Path,help='Private local installer state directory')
    parser.add_argument('--lang',choices=('auto','ru','en'),default='auto',help='Interface language')
    args=parser.parse_args()
    set_language(args.lang)
    if args.self_test:self_test();return 0
    if args.check_sources:
        try:print(json.dumps(versions.discover(),indent=2));return 0
        except InstallError as error:print(str(error));return 1
    import os
    home=args.home or Path(os.getenv('LOCALAPPDATA',str(Path.home()/'.local/share')))/'AmneziaDashboardInstaller'
    try:return run_wizard(collect(),home)
    except (KeyboardInterrupt,EOFError):print(tr('\nУстановка не начиналась.'));return 1
    except InstallError as error:print('\n'+str(error));return 1

if __name__=='__main__':
    result=main()
    if getattr(sys,'frozen',False) and len(sys.argv)==1 and sys.stdin.isatty():
        try:input(tr('\nНажмите Enter, чтобы закрыть мастер…'))
        except (KeyboardInterrupt,EOFError):pass
    raise SystemExit(result)
