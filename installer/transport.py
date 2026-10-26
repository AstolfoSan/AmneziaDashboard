"""Verified SSH. No credentials in argv, transcripts or provisioning plans."""
from i18n import tr
import base64
import hashlib
from pathlib import Path
import shlex
import time
import paramiko
from model import InstallError

def fingerprint(key):return 'SHA256:'+base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')

class VerifyHost(paramiko.MissingHostKeyPolicy):
    def __init__(self,approve):self.approve=approve
    def missing_host_key(self,client,hostname,key):
        if not self.approve(hostname,fingerprint(key)):raise InstallError(tr('Отпечаток SSH-сервера не подтверждён'))
        client.get_host_keys().add(hostname,key.get_name(),key)

class Remote:
    def __init__(self,login,known_hosts,approve):
        self.login=login;self.known_hosts=Path(known_hosts);self.client=paramiko.SSHClient()
        self.client.load_system_host_keys()
        if self.known_hosts.exists():self.client.load_host_keys(str(self.known_hosts))
        self.client.set_missing_host_key_policy(VerifyHost(approve))
    def connect(self):
        try:
            self.client.connect(self.login.host,port=self.login.port,username='root',password=self.login.password or None,
                key_filename=self.login.key_file or None,passphrase=self.login.passphrase or None,
                look_for_keys=False,allow_agent=False,timeout=15,auth_timeout=20,banner_timeout=20)
            self.known_hosts.parent.mkdir(parents=True,exist_ok=True)
            self.client.save_host_keys(str(self.known_hosts));self.known_hosts.chmod(0o600)
            self.key=self.client.get_transport().get_remote_server_key();self.sftp=self.client.open_sftp()
        except paramiko.BadHostKeyException:
            self.client.close();raise InstallError(tr('SSH-ключ сервера изменился. Автоматическое подключение запрещено.'))
        except InstallError:self.client.close();raise
        except Exception as error:
            self.client.close();raise InstallError(tr('Не удалось войти по SSH. Проверьте IP, порт и данные root.')) from error
        return self
    def run(self,args,timeout=120,input_data=None):
        command=' '.join(shlex.quote(str(arg)) for arg in args)
        channel=None
        try:
            channel=self.client.get_transport().open_session(timeout=15);channel.exec_command(command)
            if input_data is not None:channel.sendall(input_data)
            channel.shutdown_write();out=bytearray();err=bytearray();until=time.monotonic()+timeout
            while True:
                while channel.recv_ready():out.extend(channel.recv(65536))
                while channel.recv_stderr_ready():err.extend(channel.recv_stderr(65536))
                if len(out)+len(err)>4*1024**2:raise InstallError(tr('Превышен безопасный размер ответа сервера'))
                if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():break
                if time.monotonic()>until:raise InstallError(tr('Этап установки превысил время ожидания; состояние сохранено для диагностики'))
                time.sleep(.03)
            code=channel.recv_exit_status();channel.close()
            if code:raise InstallError(tr('Сервер не выполнил этап. Приватный диагностический журнал сохранён на сервере.'))
            return bytes(out)
        except InstallError:raise
        except Exception as error:raise InstallError(tr('SSH-соединение прервано; установка не подтверждена')) from error
        finally:
            if channel is not None:channel.close()
    def put(self,path,data,mode=0o600):
        with self.sftp.open(path,'wb') as stream:stream.write(data)
        self.sftp.chmod(path,mode)
    def read(self,path):
        with self.sftp.open(path,'rb') as stream:return stream.read()
    def get(self,source,destination):
        self.sftp.get(source,str(destination));Path(destination).chmod(0o600)
    def host_key_line(self,alias,port):
        return (alias if port==22 else '['+alias+']:'+str(port))+' '+self.key.get_name()+' '+self.key.get_base64()+'\n'
    def close(self):
        try:self.sftp.close()
        except Exception:pass
        self.client.close()
