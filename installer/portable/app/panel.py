"""Small self-hosted Amnezia portal. One worker, scoped roles, no public SSH API."""
from contextlib import contextmanager
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import threading
import time
import uuid
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from cryptography.fernet import Fernet
from flask import Flask, abort, g, jsonify, request, send_from_directory, make_response, has_request_context, redirect
from werkzeug.middleware.proxy_fix import ProxyFix
from downloads import ReleaseDownloads, DownloadUnavailable, PLATFORMS
from awg_export import conf_from_vpn
from api_i18n import error_text,current_language

HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
HERE = Path(__file__).parent
SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,max_devices INTEGER NOT NULL DEFAULT 25,deleted_at INTEGER);
CREATE TABLE IF NOT EXISTS groups_(id INTEGER PRIMARY KEY,owner_id INTEGER NOT NULL REFERENCES users(id),name TEXT NOT NULL,token_hash TEXT UNIQUE,token_enc TEXT,device_limit INTEGER NOT NULL DEFAULT 10,enabled INTEGER NOT NULL DEFAULT 1,created INTEGER NOT NULL,deleted_at INTEGER);
CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY,group_id INTEGER NOT NULL REFERENCES groups_(id),name TEXT NOT NULL,ip TEXT NOT NULL DEFAULT '',legacy INTEGER NOT NULL DEFAULT 0,state TEXT NOT NULL DEFAULT 'pending',created INTEGER NOT NULL,rx INTEGER NOT NULL DEFAULT 0,tx INTEGER NOT NULL DEFAULT 0,last_rx INTEGER NOT NULL DEFAULT 0,last_tx INTEGER NOT NULL DEFAULT 0,last_sample INTEGER NOT NULL DEFAULT 0,handshake INTEGER NOT NULL DEFAULT 0,up_bps REAL NOT NULL DEFAULT 0,down_bps REAL NOT NULL DEFAULT 0,download_hash TEXT,download_expires INTEGER);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),csrf TEXT NOT NULL,expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS limits_(key TEXT NOT NULL,bucket INTEGER NOT NULL,n INTEGER NOT NULL,PRIMARY KEY(key,bucket));
CREATE TABLE IF NOT EXISTS traffic(device_id TEXT NOT NULL REFERENCES devices(id),minute INTEGER NOT NULL,rx INTEGER NOT NULL,tx INTEGER NOT NULL,PRIMARY KEY(device_id,minute));
CREATE TABLE IF NOT EXISTS traffic_daily(device_id TEXT NOT NULL REFERENCES devices(id),day INTEGER NOT NULL,rx INTEGER NOT NULL,tx INTEGER NOT NULL,PRIMARY KEY(device_id,day));
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at INTEGER NOT NULL,user_id INTEGER,event TEXT NOT NULL,detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS devices_group ON devices(group_id);
CREATE INDEX IF NOT EXISTS traffic_time ON traffic(minute);
CREATE INDEX IF NOT EXISTS traffic_daily_time ON traffic_daily(day);
'''
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def moscow_day(seconds): return (int(seconds)+10800)//86400*86400-10800

def retain_traffic(conn, now):
    """Roll up once before pruning; caller owns the atomic transaction.

    Retain 24h minute detail and 31 completed Moscow days plus today's daily row.
    Cumulative device counters and client configuration are never trimmed here.
    """
    if not conn.execute("SELECT 1 FROM meta WHERE key='traffic_daily_v1'").fetchone():
        conn.execute('INSERT INTO traffic_daily(device_id,day,rx,tx) '
                     'SELECT device_id,(minute+10800)/86400*86400-10800,SUM(rx),SUM(tx) '
                     'FROM traffic GROUP BY device_id,(minute+10800)/86400*86400-10800')
        conn.execute("INSERT INTO meta VALUES('traffic_daily_v1',?)", (str(int(now)),))
    conn.execute('DELETE FROM traffic WHERE minute<?', ((int(now)-86400)//60*60,))
    conn.execute('DELETE FROM traffic_daily WHERE day<?', (moscow_day(now)-31*86400,))

def access_days(value):
    if value is None:return None
    if type(value) is not int or not 1<=value<=3650:abort(400,'Срок группы: 1–3650 дней или пустое поле')
    return value
def title(value):
    value = str(value or '').strip()
    if not 1 <= len(value) <= 64 or any(ord(c)<32 for c in value): abort(400, 'Название должно содержать 1–64 символа')
    return value

from portable_settings import PortableSSHAgent as SSHAgent


def create_app(config=None, agent=None):
    app = Flask(__name__, static_folder=None)
    app.config.update(DATA_DIR=os.getenv('PANEL_DATA','/data'),PUBLIC_ORIGIN=os.getenv('PUBLIC_ORIGIN','https://localhost:10443'),MAX_CONTENT_LENGTH=16384,TESTING=False,COLLECTOR=True,COOKIE_SECURE=True)
    if config: app.config.update(config)
    app.wsgi_app = ProxyFix(app.wsgi_app,x_for=1,x_proto=1)
    root = Path(app.config['DATA_DIR']); root.mkdir(parents=True,exist_ok=True,mode=0o700)
    key_path = Path(os.getenv('PANEL_MASTER_KEY',str(root/'master.key')))
    if not key_path.exists(): key_path.write_bytes(Fernet.generate_key()); key_path.chmod(0o600)
    cipher = Fernet(key_path.read_bytes())
    dbfile = root/'panel.sqlite3'; rpc = agent or SSHAgent(); sync_lock=threading.Lock(); creating=threading.Lock()
    downloads=app.config.get('DOWNLOADS') or ReleaseDownloads()
    @contextmanager
    def db():
        conn=sqlite3.connect(dbfile,timeout=8); conn.row_factory=sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON'); conn.execute('PRAGMA busy_timeout=8000')
        try: yield conn; conn.commit()
        except: conn.rollback(); raise
        finally: conn.close()
    def log(conn, event, detail='', uid=None):
        conn.execute('INSERT INTO audit(at,user_id,event,detail) VALUES(?,?,?,?)',(int(time.time()),uid if uid is not None else (g.user['id'] if has_request_context() and getattr(g,'user',None) else None),event,str(detail)[:200]))
    with db() as c:
        c.executescript(SCHEMA); c.execute('PRAGMA journal_mode=WAL')
        if 'deleted_at' not in {row[1] for row in c.execute('PRAGMA table_info(users)')}:
            c.execute('ALTER TABLE users ADD COLUMN deleted_at INTEGER')
        if 'deleted_at' not in {row[1] for row in c.execute('PRAGMA table_info(groups_)')}:
            c.execute('ALTER TABLE groups_ ADD COLUMN deleted_at INTEGER')
        columns={row[1] for row in c.execute('PRAGMA table_info(devices)')}
        if 'default_access_days' not in {row[1] for row in c.execute('PRAGMA table_info(groups_)')}:
            c.execute('ALTER TABLE groups_ ADD COLUMN default_access_days INTEGER')
        if 'manual_paused' not in columns:c.execute('ALTER TABLE devices ADD COLUMN manual_paused INTEGER NOT NULL DEFAULT 0')
        if 'expires_at' not in columns:c.execute('ALTER TABLE devices ADD COLUMN expires_at INTEGER')
        if 'traffic_limit_bytes' not in columns:c.execute('ALTER TABLE devices ADD COLUMN traffic_limit_bytes INTEGER')
        if not c.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            pwfile=Path(os.getenv('BOOTSTRAP_PASSWORD_FILE',str(root/'bootstrap-password.txt')))
            if pwfile.exists(): password=pwfile.read_text().strip()
            else: password=secrets.token_urlsafe(22); pwfile.write_text(password+'\n'); pwfile.chmod(0o600)
            c.execute('INSERT INTO users(username,password,role,max_devices) VALUES(?,?,?,?)',('owner',HASHER.hash(password),'super',150))
            c.execute('INSERT INTO groups_(owner_id,name,device_limit,enabled,created) VALUES(1,?,?,0,?)',('Существующие подключения',0,int(time.time())))
        retain_traffic(c, int(time.time()))
    dbfile.chmod(0o600)
    def rate(key, maximum, window=900):
        bucket=int(time.time())//window*window
        with db() as c:
            c.execute('INSERT INTO limits_ VALUES(?,?,1) ON CONFLICT(key,bucket) DO UPDATE SET n=n+1',(key,bucket))
            count=c.execute('SELECT n FROM limits_ WHERE key=? AND bucket=?',(key,bucket)).fetchone()[0]
        if count>maximum: abort(429,'Слишком много запросов. Повторите позже')
    def authenticate():
        token=request.cookies.get('panel_session','')
        with db() as c:
            row=c.execute('SELECT u.*,s.csrf,s.expires FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>? AND u.enabled=1 AND u.deleted_at IS NULL',(digest(token),int(time.time()))).fetchone()
        if not row: abort(401,'Войдите в кабинет')
        g.user=dict(row)
    def restricted(super_only=False):
        def decorate(fn):
            @functools.wraps(fn)
            def wrapped(*a,**kw):
                authenticate()
                if super_only and g.user['role']!='super': abort(403,'Только для главного администратора')
                if request.method not in {'GET','HEAD'}:
                    if not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),g.user['csrf']): abort(403,'Обновите страницу')
                return fn(*a,**kw)
            return wrapped
        return decorate
    def visible(c, uid, include_revoked=False):
        row=c.execute('SELECT d.*,g.owner_id,g.name AS group_name,g.deleted_at AS group_deleted,u.username AS owner_name FROM devices d JOIN groups_ g ON g.id=d.group_id JOIN users u ON u.id=g.owner_id WHERE d.id=?',(uid,)).fetchone()
        if not row or row['group_deleted'] is not None or (g.user['role']!='super' and row['owner_id']!=g.user['id']) or (row['state']=='revoked' and not include_revoked): abort(404,'Профиль не найден')
        return dict(row)
    def group(c, gid, include_deleted=False):
        row=c.execute('SELECT g.*,u.enabled AS owner_enabled,u.max_devices FROM groups_ g JOIN users u ON u.id=g.owner_id WHERE g.id=?',(gid,)).fetchone()
        if not row or (g.user['role']!='super' and row['owner_id']!=g.user['id']) or (row['deleted_at'] is not None and not include_deleted): abort(404,'Группа не найдена')
        return dict(row)
    def issue(gid, uid, name, download_token):
        try: uid=str(uuid.UUID(uid))
        except (ValueError,TypeError,AttributeError): abort(400,'Некорректный запрос')
        name=title(name)
        if not isinstance(download_token,str) or not 24<=len(download_token)<=128: abort(400,'Некорректный запрос')
        # One Gunicorn worker: serialize enrollment, not statistics/downloads.
        with creating:
            with db() as c:
                row=c.execute('SELECT g.*,u.enabled AS owner_enabled,u.max_devices FROM groups_ g JOIN users u ON u.id=g.owner_id WHERE g.id=?',(gid,)).fetchone()
                if not row or row['deleted_at'] is not None:abort(404,'Группа не найдена')
                if not row or not row['enabled'] or not row['owner_enabled']: abort(403,'Выдача для этой группы закрыта')
                prior=c.execute('SELECT * FROM devices WHERE id=?',(uid,)).fetchone()
                if prior:
                    if prior['group_id']!=gid or not secrets.compare_digest(prior['download_hash'] or '',digest(download_token)): abort(409,'Запрос уже принадлежит другому устройству')
                    if prior['state']=='revoked': abort(409,'Этот профиль отключён')
                    if prior['state'] in {'paused','expired','limited'}:abort(409,'Доступ приостановлен. Обратитесь к администратору')
                    if prior['state']=='active': return {'id':uid,'name':prior['name'],'ip':prior['ip'],'state':'active','expires_at':prior['expires_at']}
                    expires_at=prior['expires_at']
                else:
                    amount=c.execute("SELECT count(*) FROM devices WHERE group_id=? AND legacy=0 AND state!='revoked'",(gid,)).fetchone()[0]
                    total=c.execute("SELECT count(*) FROM devices d JOIN groups_ g ON g.id=d.group_id WHERE g.owner_id=? AND d.legacy=0 AND d.state!='revoked'",(row['owner_id'],)).fetchone()[0]
                    if amount>=row['device_limit'] or total>=row['max_devices']: abort(409,'Лимит подключений исчерпан')
                    now=int(time.time());days=access_days(row['default_access_days'])
                    expires_at=now+days*86400 if days is not None else None
                    if expires_at is not None and expires_at>4133969999:abort(400,'Срок выходит за допустимый диапазон дат')
                    c.execute('INSERT INTO devices(id,group_id,name,created,download_hash,download_expires,expires_at) VALUES(?,?,?,?,?,?,?)',(uid,gid,name,now,digest(download_token),now+86400,expires_at))
                    log(c,'device.requested',uid)
            try:
                payload={'action':'create','id':uid,'name':name}
                if expires_at is not None:payload.update(action='create_limited',expires_at=expires_at)
                result=rpc(payload)
                if result.get('expires_at')!=expires_at:raise ValueError('Worker expiry confirmation mismatch')
                state=result.get('state','active')
                if state not in {'active','expired'}:raise ValueError('Worker issuance state mismatch')
            except Exception:
                with db() as c: c.execute("UPDATE devices SET state='error' WHERE id=? AND state!='revoked'",(uid,))
                abort(503,'Не удалось выдать профиль. Повторите запрос — второй профиль не создастся')
            with db() as c:
                updated=c.execute("UPDATE devices SET state=?,ip=? WHERE id=? AND state!='revoked'",(state,result['ip'],uid))
                if not updated.rowcount: abort(409,'Профиль уже удалён администратором')
                log(c,'device.created',uid)
            return {'id':uid,'name':name,'ip':result['ip'],'state':state,'expires_at':expires_at}
    def download(uid, public=False):
        fmt=request.args.get('format','vpn')
        if fmt not in {'vpn','conf'}:abort(400,'Неподдерживаемый формат профиля')
        with db() as c:
            if public:
                row=c.execute('SELECT * FROM devices WHERE id=?',(uid,)).fetchone()
                token=request.headers.get('Authorization','').removeprefix('Bearer ')
                if not row or row['state']=='revoked' or not secrets.compare_digest(row['download_hash'] or '',digest(token)) or not row['download_expires'] or row['download_expires']<time.time(): abort(404,'Ссылка недоступна или истекла')
                row=dict(row)
            else: row=visible(c,uid)
            if row['legacy'] or row['state'] not in {'active','paused','expired','limited'}: abort(409,'Этот профиль нельзя скачать из панели')
        try: vpn=rpc({'action':'export','id':uid})['vpn']
        except Exception: abort(503,'Сервис выдачи временно недоступен')
        if fmt=='conf':
            try:content=conf_from_vpn(vpn)
            except Exception:abort(503,'Не удалось подготовить конфиг AmneziaWG. Исходный профиль не изменён')
            response=make_response(content);response.mimetype='application/octet-stream'
            response.headers['Content-Disposition']='attachment; filename="AmneziaWG-'+uid[:8]+'.conf"'
            return response
        response=make_response(vpn+'\n'); response.mimetype='application/octet-stream'
        response.headers['Content-Disposition']='attachment; filename="AmneziaVPN-'+uid[:8]+'.vpn"'
        return response
    def sync_once():
        if not sync_lock.acquire(False): return
        creating.acquire()
        try:
            stats=rpc({'action':'stats'}); now=int(stats['sampled_at']); minute=now//60*60
            with db() as c:
                legacy=1  # Stable identity: renaming/moving a device must not break collection.
                for peer in stats['peers']:
                    old=c.execute('SELECT * FROM devices WHERE id=?',(peer['id'],)).fetchone()
                    if not old:
                        if not peer['legacy']: continue
                        c.execute("INSERT INTO devices(id,group_id,name,ip,legacy,state,created,last_rx,last_tx,last_sample,handshake) VALUES(?,?,?,?,1,'active',?,?,?,?,?)",(peer['id'],legacy,peer['name'],peer['ip'],now,peer['rx'],peer['tx'],now,peer['handshake']))
                        continue
                    # A deletion is terminal. An in-flight/stale stats response
                    # must never resurrect it or count its lifetime traffic twice.
                    if old['state']=='revoked':continue
                    if not peer['active'] and old['state'] in {'pending','error'} and peer.get('state') not in {'paused','expired','limited'}:continue
                    elapsed=max(1,now-old['last_sample']) if old['last_sample'] else 15
                    rx=max(0,peer['rx']-old['last_rx']) if peer['rx']>=old['last_rx'] else peer['rx']
                    tx=max(0,peer['tx']-old['last_tx']) if peer['tx']>=old['last_tx'] else peer['tx']
                    state=peer.get('state') or ('active' if peer['active'] else 'revoked')
                    if state not in {'active','paused','expired','limited','revoked'}:raise ValueError('Unexpected client state')
                    metered=peer.get('traffic_meter') is True
                    if metered:
                        if any(type(peer.get(key)) is not int or peer[key]<old[column] for key,column in (('total_rx','rx'),('total_tx','tx'))):raise ValueError('Worker traffic total regressed')
                        rx=peer['total_rx']-old['rx'];tx=peer['total_tx']-old['tx']
                    elif state!='active':rx=tx=0
                    updated=c.execute("UPDATE devices SET ip=?,state=?,rx=rx+?,tx=tx+?,last_rx=?,last_tx=?,last_sample=?,handshake=?,up_bps=?,down_bps=? WHERE id=? AND state!='revoked'",(peer['ip'],state,rx,tx,peer['rx'],peer['tx'],now,peer['handshake'],rx/elapsed,tx/elapsed,peer['id']))
                    if not old['legacy']:
                        c.execute("UPDATE devices SET manual_paused=?,expires_at=?,traffic_limit_bytes=? WHERE id=? AND state!='revoked'",(int(bool(peer.get('manual_paused',False))),peer.get('expires_at'),peer.get('traffic_limit_bytes'),peer['id']))
                    if state in {'paused','expired','limited'} and old['state']!=state:
                        owner=c.execute('SELECT owner_id FROM groups_ WHERE id=?',(old['group_id'],)).fetchone()[0]
                        log(c,'device.'+state,old['name']+' · '+peer['id'],owner)
                    if updated.rowcount:
                        if rx or tx:c.execute('INSERT INTO traffic VALUES(?,?,?,?) ON CONFLICT(device_id,minute) DO UPDATE SET rx=rx+excluded.rx,tx=tx+excluded.tx',(peer['id'],minute,rx,tx))
                        c.execute('INSERT INTO traffic_daily VALUES(?,?,?,?) ON CONFLICT(device_id,day) DO UPDATE SET rx=rx+excluded.rx,tx=tx+excluded.tx',(peer['id'],moscow_day(now),rx,tx))
                c.execute("INSERT INTO meta VALUES('last_sync',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(now),))
                c.execute("INSERT INTO meta VALUES('sync_error','') ON CONFLICT(key) DO UPDATE SET value='' ")
                retain_traffic(c, now); c.execute('DELETE FROM sessions WHERE expires<?',(now,))
                c.execute('DELETE FROM limits_ WHERE bucket<?',(now-2*86400,))
        except Exception:
            with db() as c: c.execute("INSERT INTO meta VALUES('sync_error',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",('Статистика VPN-сервера временно недоступна',))
        finally:creating.release();sync_lock.release()
    app.extensions['panel_db']=db; app.extensions['panel_sync']=sync_once
    @app.before_request
    def protect():
        if request.method not in {'GET','HEAD','OPTIONS'}:
            if request.headers.get('Origin')!=app.config['PUBLIC_ORIGIN']: abort(403,'Недопустимый источник запроса')
            if not request.is_json: abort(415,'Нужен JSON')
            if not isinstance(request.get_json(),dict): abort(400,'Нужен объект JSON')
    @app.after_request
    def headers(r):
        r.headers['Content-Language']=current_language()
        r.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        return r
    @app.errorhandler(Exception)
    def errors(e):
        if isinstance(e,(ValueError,KeyError,TypeError)): return jsonify(error=error_text('Проверьте заполненные поля')),400
        code=getattr(e,'code',500)
        return jsonify(error=error_text(getattr(e,'description','Внутренняя ошибка сервера'))),code
    @app.get('/healthz')
    def health(): return jsonify(status='ok')
    @app.get('/api/downloads')
    def installers():
        try:return jsonify(downloads.metadata())
        except DownloadUnavailable:abort(503,'GitHub временно недоступен. Попробуйте скачать приложение позже')
    @app.get('/download/<platform>')
    def installer(platform):
        if platform not in PLATFORMS:abort(404)
        version=request.args.get('os')
        if version is not None and not re.fullmatch(r'\d{1,2}',version):abort(400)
        try:asset=downloads.resolve(platform,request.args.get('arch'),int(version) if version else None)
        except ValueError:abort(400,'Неподдерживаемый вариант установщика')
        except DownloadUnavailable:return make_response(send_from_directory(HERE/'static','download-unavailable.html'),503)
        return redirect(asset['url'],code=302)
    @app.get('/')
    @app.get('/j/<token>')
    def welcome(token=None): return send_from_directory(HERE/'static','join.html')
    @app.get('/admin')
    @app.get('/admin/')
    def admin(): return send_from_directory(HERE/'static','admin.html')
    @app.get('/static/<path:name>')
    def static_file(name): return send_from_directory(HERE/'static',name)
    @app.post('/api/login')
    def login():
        rate('login:'+digest(request.remote_addr or ''),8)
        data=request.get_json(); username=str(data.get('username',''))[:64]; password=str(data.get('password',''))
        if len(password)>128: abort(401,'Неверный логин или пароль')
        with db() as c:
            user=c.execute('SELECT * FROM users WHERE username=? AND enabled=1 AND deleted_at IS NULL',(username,)).fetchone()
            candidate=user['password'] if user else HASHER.hash('nonexistent-account-placeholder')
            try: ok=HASHER.verify(candidate,password)
            except (VerifyMismatchError,InvalidHashError): ok=False
            if not user or not ok: abort(401,'Неверный логин или пароль')
            token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(24)
            c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(digest(token),user['id'],csrf,int(time.time())+43200)); log(c,'login',username,user['id'])
        r=jsonify(ok=True); r.set_cookie('panel_session',token,max_age=43200,secure=app.config['COOKIE_SECURE'],httponly=True,samesite='Strict'); return r
    @app.post('/api/logout')
    @restricted()
    def logout():
        with db() as c: c.execute('DELETE FROM sessions WHERE token_hash=?',(digest(request.cookies.get('panel_session','')),))
        r=jsonify(ok=True); r.delete_cookie('panel_session'); return r
    @app.get('/api/session')
    @restricted()
    def session(): return jsonify(id=g.user['id'],username=g.user['username'],role=g.user['role'],csrf=g.user['csrf'])
    @app.get('/api/dashboard')
    @restricted()
    def dashboard():
        with db() as c:
            scope='' if g.user['role']=='super' else ' WHERE gr.owner_id=?'
            params=() if not scope else (g.user['id'],)
            group_scope=scope+(" AND " if scope else " WHERE ")+"gr.deleted_at IS NULL"
            device_scope=group_scope+" AND d.state!='revoked'"
            devices=[dict(r) for r in c.execute('SELECT d.*,gr.name AS group_name,gr.owner_id,u.username AS owner_name FROM devices d JOIN groups_ gr ON gr.id=d.group_id JOIN users u ON u.id=gr.owner_id'+device_scope+' ORDER BY d.created DESC',params)]
            groups=[dict(r) for r in c.execute('SELECT gr.*,u.username AS owner_name FROM groups_ gr JOIN users u ON u.id=gr.owner_id'+group_scope+' ORDER BY gr.id',params)]
            history={r['group_id']:dict(r) for r in c.execute('SELECT d.group_id,SUM(d.rx) AS rx,SUM(d.tx) AS tx FROM devices d JOIN groups_ gr ON gr.id=d.group_id'+scope+' GROUP BY d.group_id',params)}
            summary={'rx':sum(r['rx'] for r in history.values()),'tx':sum(r['tx'] for r in history.values())}
            for row in groups:
                row['rx']=history.get(row['id'],{}).get('rx',0);row['tx']=history.get(row['id'],{}).get('tx',0)
                row['link']=app.config['PUBLIC_ORIGIN']+'/j/'+cipher.decrypt(row['token_enc'].encode()).decode() if row['token_enc'] else None
                row.pop('token_enc',None); row.pop('token_hash',None)
            for d in devices:
                d.pop('download_hash',None); d.pop('download_expires',None)
                d['online']=d['state']=='active' and 0<time.time()-d['handshake']<180
            chart_scope='' if g.user['role']=='super' else ' AND gr.owner_id=?'
            chart_now=int(time.time())
            chart_args=(chart_now-86400,)+(() if not chart_scope else (g.user['id'],))
            chart=[dict(r) for r in c.execute('SELECT t.minute/3600*3600 AS at,SUM(t.rx) AS rx,SUM(t.tx) AS tx FROM traffic t JOIN devices d ON d.id=t.device_id JOIN groups_ gr ON gr.id=d.group_id WHERE t.minute>?'+chart_scope+' GROUP BY at ORDER BY at',chart_args)]
            chart_samples=[dict(r) for r in c.execute('SELECT t.minute AS at,SUM(t.rx) AS rx,SUM(t.tx) AS tx FROM traffic t JOIN devices d ON d.id=t.device_id JOIN groups_ gr ON gr.id=d.group_id WHERE t.minute>?'+chart_scope+' GROUP BY t.minute ORDER BY t.minute',chart_args)]
            daily_end=moscow_day(chart_now)
            daily_args=(daily_end-31*86400,daily_end)+(() if not chart_scope else (g.user['id'],))
            chart_daily=[dict(r) for r in c.execute('SELECT t.day AS at,SUM(t.rx) AS rx,SUM(t.tx) AS tx FROM traffic_daily t JOIN devices d ON d.id=t.device_id JOIN groups_ gr ON gr.id=d.group_id WHERE t.day>=? AND t.day<?'+chart_scope+' GROUP BY t.day ORDER BY t.day',daily_args)]
            chart_started=c.execute('SELECT MIN(d.created) FROM devices d JOIN groups_ gr ON gr.id=d.group_id'+scope,params).fetchone()[0]
            meta=dict(c.execute('SELECT key,value FROM meta'))
            if meta.get('sync_error'):meta['sync_error']=error_text(meta['sync_error'])
            chart_info={'window_end':chart_now,'started_at':chart_started,'sampled_at':int(meta.get('last_sync',0)),'timezone':'Europe/Moscow','sample_interval':60,'daily_end':daily_end,'detail_retention_seconds':86400,'daily_retention_days':31}
        return jsonify(devices=devices,groups=groups,chart=chart,chart_samples=chart_samples,chart_daily=chart_daily,chart_info=chart_info,meta=meta,summary=summary)
    @app.post('/api/groups')
    @restricted()
    def new_group():
        data=request.get_json(); owner=int(data.get('owner_id',g.user['id']))
        if owner!=g.user['id'] and g.user['role']!='super': abort(403)
        limit=int(data.get('limit',10))
        if not 1<=limit<=150: abort(400,'Лимит 1–150')
        days=access_days(data.get('default_access_days'))
        token=secrets.token_urlsafe(28)
        with creating, db() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute('SELECT 1 FROM users WHERE id=? AND enabled=1 AND deleted_at IS NULL',(owner,)).fetchone(): abort(400)
            cur=c.execute('INSERT INTO groups_(owner_id,name,token_hash,token_enc,device_limit,created,default_access_days) VALUES(?,?,?,?,?,?,?)',(owner,title(data.get('name')),digest(token),cipher.encrypt(token.encode()).decode(),limit,int(time.time()),days))
            log(c,'group.created',cur.lastrowid)
        return jsonify(ok=True,id=cur.lastrowid)
    @app.patch('/api/groups/<int:gid>')
    @restricted()
    def update_group(gid):
        data=request.get_json()
        with creating, db() as c:
            group(c,gid)
            if gid==1 and any(k in data for k in ('enabled','limit','default_access_days')): abort(403,'Для выдачи создайте отдельную группу')
            if 'default_access_days' in data:c.execute('UPDATE groups_ SET default_access_days=? WHERE id=?',(access_days(data['default_access_days']),gid))
            if 'enabled' in data:c.execute('UPDATE groups_ SET enabled=? WHERE id=?',(int(bool(data['enabled'])),gid))
            if 'name' in data:c.execute('UPDATE groups_ SET name=? WHERE id=?',(title(data['name']),gid))
            if 'limit' in data:
                n=int(data['limit'])
                if not 1<=n<=150:abort(400)
                c.execute('UPDATE groups_ SET device_limit=? WHERE id=?',(n,gid))
            log(c,'group.updated',gid)
        return jsonify(ok=True)
    @app.delete('/api/groups/<int:gid>')
    @restricted()
    def delete_group(gid):
        # Serialize against issuance and reassignment: no peer can be created
        # in or moved into a group between the empty check and its deletion.
        with creating, db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=group(c,gid,include_deleted=True)
            if gid==1:abort(403,'Служебная группа со старыми конфигами защищена')
            if row['deleted_at'] is not None:return jsonify(ok=True,deleted=True)
            if c.execute("SELECT 1 FROM devices WHERE group_id=? AND state!='revoked' LIMIT 1",(gid,)).fetchone():
                abort(409,'В группе ещё есть клиенты. Сначала перенесите их в другую группу или отзовите доступ')
            c.execute('UPDATE groups_ SET deleted_at=?,enabled=0,token_hash=NULL,token_enc=NULL WHERE id=?',(int(time.time()),gid))
            log(c,'group.deleted',row['name']+' · '+str(gid))
        return jsonify(ok=True,deleted=True)
    @app.post('/api/devices')
    @restricted()
    def new_device():
        data=request.get_json(); gid=int(data['group_id'])
        with db() as c:group(c,gid)
        secret=data.get('download_token') or secrets.token_urlsafe(32)
        return jsonify(issue(gid,data.get('id') or str(uuid.uuid4()),data.get('name'),secret))
    @app.get('/api/devices/<uid>/download')
    @restricted()
    def admin_download(uid):return download(uid)
    @app.post('/api/devices/<uid>/revoke')
    @restricted()
    def revoke(uid):
        with creating:
            with db() as c:
                row=visible(c,uid,include_revoked=True)
                if row['legacy']:abort(403,'Старые конфиги защищены от отзыва панелью')
                if row['state']=='revoked':return jsonify(ok=True,deleted=True)
            try:rpc({'action':'revoke','id':uid})
            except Exception:abort(503,'Отзыв не подтверждён VPN-сервером')
            with db() as c:
                c.execute("UPDATE devices SET state='revoked',up_bps=0,down_bps=0,download_hash=NULL,download_expires=NULL WHERE id=?",(uid,))
                log(c,'device.revoked',row['name']+' · '+uid)
        return jsonify(ok=True,deleted=True)
    @app.patch('/api/devices/<uid>/access')
    @restricted()
    def device_access(uid):
        payload=request.get_json()
        if not set(payload)<= {'paused','expires_at'} or not payload:abort(400,'Укажите паузу или срок доступа')
        if 'paused' in payload and type(payload['paused']) is not bool:abort(400,'Некорректный режим доступа')
        if 'expires_at' in payload and payload['expires_at'] is not None and (type(payload['expires_at']) is not int or not 946684800<=payload['expires_at']<=4133969999):abort(400,'Некорректная дата окончания')
        with creating:
            with db() as c:
                row=visible(c,uid)
                if row['legacy']:abort(403,'Старые конфиги защищены: пауза доступна для клиентов панели')
                if row['state'] not in {'active','paused','expired','limited'}:abort(409,'Сначала завершите выдачу профиля')
            try:result=rpc({'action':'access','id':uid,**payload})
            except Exception:abort(503,'VPN-сервер не подтвердил изменение доступа. Обновите список и повторите при необходимости')
            if result.get('state') not in {'active','paused','expired','limited'}:abort(503,'VPN-сервер не подтвердил состояние клиента')
            with db() as c:
                c.execute("UPDATE devices SET state=?,manual_paused=?,expires_at=?,up_bps=0,down_bps=0 WHERE id=? AND state!='revoked'",(result['state'],int(bool(result['manual_paused'])),result['expires_at'],uid))
                log(c,'device.access_updated',row['name']+' · '+uid+' · '+result['state'])
            return jsonify(ok=True,**result)
    @app.patch('/api/devices/<uid>/traffic')
    @restricted()
    def device_traffic_limit(uid):
        payload=request.get_json()
        if set(payload)!={'limit_bytes'}:abort(400,'Укажите лимит трафика')
        limit=payload['limit_bytes']
        if limit is not None and (type(limit) is not int or not 1<=limit<=2**53-1):abort(400,'Лимит должен быть положительным числом байтов или без ограничения')
        with creating:
            with db() as c:
                row=visible(c,uid)
                if row['legacy']:abort(403,'Старые конфиги защищены: лимит доступен только клиентам панели')
                if row['state'] not in {'active','paused','expired','limited'}:abort(409,'Сначала завершите выдачу профиля')
            seed={key:row[key] for key in ('rx','tx','last_rx','last_tx')}
            try:result=rpc({'action':'traffic_limit','id':uid,'limit_bytes':limit,'seed':seed})
            except Exception:abort(503,'VPN-сервер не подтвердил лимит трафика. Настройка в панели не сохранена.')
            if not isinstance(result,dict) or result.get('traffic_meter') is not True or result.get('traffic_limit_bytes')!=limit or result.get('state') not in {'active','paused','expired','limited'}:
                abort(503,'VPN-сервер не подтвердил поддержку лимита трафика')
            if any(type(result.get(key)) is not int or result[key]<row[column] for key,column in (('total_rx','rx'),('total_tx','tx'))):abort(503,'VPN-сервер не подтвердил накопленный расход')
            with db() as c:
                c.execute("UPDATE devices SET traffic_limit_bytes=?,state=?,manual_paused=?,expires_at=?,up_bps=0,down_bps=0 WHERE id=? AND state!='revoked'",(limit,result['state'],int(bool(result['manual_paused'])),result['expires_at'],uid))
                log(c,'device.traffic_limit_updated',uid+' · '+('unlimited' if limit is None else str(limit)))
            return jsonify(ok=True,**result)
    @app.patch('/api/devices/<uid>')
    @restricted()
    def move_device(uid):
        data=request.get_json()
        with creating, db() as c:
            c.execute('BEGIN IMMEDIATE')
            visible(c,uid); gid=int(data['group_id']);group(c,gid)
            c.execute('UPDATE devices SET group_id=? WHERE id=?',(gid,uid));log(c,'device.group_changed',uid)
        return jsonify(ok=True)
    @app.get('/api/users')
    @restricted(True)
    def users():
        with db() as c:return jsonify(users=[dict(r) for r in c.execute('SELECT id,username,role,enabled,max_devices FROM users WHERE deleted_at IS NULL')])
    @app.post('/api/users')
    @restricted(True)
    def new_user():
        data=request.get_json(); username=str(data.get('username',''))
        if not re.fullmatch(r'[A-Za-z0-9_.-]{3,32}',username):abort(400,'Логин: 3–32 латинских символа')
        password=str(data.get('password') or secrets.token_urlsafe(20)); role=data.get('role','admin'); limit=int(data.get('limit',25))
        if role not in {'admin','super'} or not 12<=len(password)<=128 or not 1<=limit<=150:abort(400,'Проверьте пароль, роль и лимит')
        with db() as c:
            if c.execute('SELECT 1 FROM users WHERE username=?',(username,)).fetchone():abort(409,'Логин уже занят')
            cur=c.execute('INSERT INTO users(username,password,role,max_devices) VALUES(?,?,?,?)',(username,HASHER.hash(password),role,limit));log(c,'admin.created',username)
        return jsonify(id=cur.lastrowid,username=username,password=password)
    @app.post('/api/password')
    @restricted()
    def password():
        data=request.get_json(); old=str(data.get('old','')); new=str(data.get('new',''))
        try:ok=HASHER.verify(g.user['password'],old)
        except Exception:ok=False
        if not ok or not 12<=len(new)<=128:abort(400,'Неверный старый пароль или новый короче 12 символов')
        with db() as c:
            c.execute('UPDATE users SET password=? WHERE id=?',(HASHER.hash(new),g.user['id']));c.execute('DELETE FROM sessions WHERE user_id=?',(g.user['id'],));log(c,'password.changed')
        r=jsonify(ok=True);r.delete_cookie('panel_session');return r
    @app.patch('/api/users/<int:uid>')
    @restricted(True)
    def update_user(uid):
        data=request.get_json()
        with creating, db() as c:
            c.execute('BEGIN IMMEDIATE')
            user=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
            if not user or user['deleted_at'] is not None: abort(404)
            if uid==g.user['id'] and ('enabled' in data or 'role' in data): abort(400,'Нельзя отключить свою учётную запись')
            if 'enabled' in data:
                if uid==1: abort(403,'Основная учётная запись защищена')
                c.execute('UPDATE users SET enabled=? WHERE id=?',(int(bool(data['enabled'])),uid))
                c.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
            if 'limit' in data:
                n=int(data['limit'])
                if not 1<=n<=150: abort(400)
                c.execute('UPDATE users SET max_devices=? WHERE id=?',(n,uid))
            if 'password' in data:
                pw=str(data['password'])
                if not 12<=len(pw)<=128: abort(400)
                c.execute('UPDATE users SET password=? WHERE id=?',(HASHER.hash(pw),uid));c.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
            log(c,'admin.updated',uid)
        return jsonify(ok=True)
    @app.delete('/api/users/<int:uid>')
    @restricted(True)
    def delete_user(uid):
        # Keep the identity row for historical FK/audit attribution. Deletion
        # never cascades into groups, VPN peers, profiles or traffic counters.
        with creating, db() as c:
            c.execute('BEGIN IMMEDIATE')
            user=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
            if not user:abort(404,'Администратор не найден')
            if uid==1 or uid==g.user['id']:abort(403,'Основную или свою учётную запись удалить нельзя')
            if user['deleted_at'] is not None:return jsonify(ok=True,deleted=True)
            if user['enabled']:abort(409,'Сначала закройте кабинет администратора')
            if c.execute('SELECT 1 FROM groups_ WHERE owner_id=? AND deleted_at IS NULL LIMIT 1',(uid,)).fetchone():
                abort(409,'У администратора ещё есть группы. Сначала перенесите клиентов в другие группы и удалите его пустые группы')
            if c.execute("SELECT 1 FROM devices d JOIN groups_ gr ON gr.id=d.group_id WHERE gr.owner_id=? AND d.state!='revoked' LIMIT 1",(uid,)).fetchone():
                abort(409,'У администратора ещё есть клиенты. Сначала перенесите их в другие группы')
            c.execute('UPDATE users SET enabled=0,deleted_at=? WHERE id=?',(int(time.time()),uid))
            c.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
            log(c,'admin.deleted',user['username']+' · '+str(uid))
        return jsonify(ok=True,deleted=True)
    @app.get('/api/audit')
    @restricted()
    def audit():
        with db() as c:
            where='' if g.user['role']=='super' else ' WHERE a.user_id=?'; params=() if not where else (g.user['id'],)
            rows=[dict(r) for r in c.execute('SELECT a.at,a.event,a.detail,u.username FROM audit a LEFT JOIN users u ON u.id=a.user_id'+where+' ORDER BY a.id DESC LIMIT 100',params)]
        return jsonify(events=rows)
    def public_group(token):
        with db() as c: row=c.execute('SELECT g.*,u.enabled AS owner_enabled FROM groups_ g JOIN users u ON u.id=g.owner_id WHERE g.token_hash=?',(digest(token),)).fetchone()
        if not row or row['deleted_at'] is not None or not row['enabled'] or not row['owner_enabled']:abort(404,'Приглашение недоступно')
        return dict(row)
    @app.get('/api/join/<token>')
    def join_info(token):
        row=public_group(token);return jsonify(name=row['name'],default_access_days=row['default_access_days'])
    @app.post('/api/join/<token>')
    def join_create(token):
        row=public_group(token);rate('join:'+str(row['id'])+':'+digest(request.remote_addr or ''),6,3600)
        data=request.get_json();return jsonify(issue(row['id'],data.get('id'),data.get('name'),data.get('download_token')))
    @app.get('/api/receive/<uid>')
    def public_download(uid):return download(uid,True)
    def loop():
        while True:sync_once();time.sleep(15)
    if app.config['COLLECTOR']:threading.Thread(target=loop,daemon=True,name='awg-stats').start()
    return app
