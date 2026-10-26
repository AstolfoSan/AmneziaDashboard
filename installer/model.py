"""Installer inputs. Credentials never enter serializable plans or logs."""
from i18n import tr
from dataclasses import dataclass,field
import ipaddress
from pathlib import Path
import re

class InstallError(Exception):pass

@dataclass
class Login:
    host:str
    port:int=22
    password:str=field(default='',repr=False)
    key_file:str=field(default='',repr=False)
    passphrase:str=field(default='',repr=False)
    def validate(self):
        try:address=ipaddress.IPv4Address(self.host)
        except ValueError:raise InstallError(tr('Введите корректный IPv4 сервера'))
        if address.is_unspecified or address.is_loopback or address.is_multicast:raise InstallError(tr('Нужен адрес VPS, не loopback/multicast'))
        if type(self.port) is not int or not 1<=self.port<=65535:raise InstallError(tr('SSH-порт должен быть 1–65535'))
        if bool(self.password)==bool(self.key_file):raise InstallError(tr('Укажите пароль root ИЛИ SSH-ключ'))
        if '\n' in self.password or len(self.password)>1024:raise InstallError(tr('Проверьте поле пароля: SSH-ключ выбирается отдельным файлом'))
        if self.key_file and not Path(self.key_file).is_file():raise InstallError(tr('Файл SSH-ключа не найден'))
        if self.key_file.lower().endswith('.pub'):raise InstallError(tr('Нужен приватный SSH-ключ, не файл .pub'))
        return self

@dataclass
class Settings:
    mode:str
    foreign:Login
    entry:Login|None=None
    vpn_port:int=39265
    panel_port:int=10443
    relay_port:int=443
    email:str=''
    ca_terms_accepted:bool=False
    def validate(self):
        if self.mode not in {'direct','cascade'}:raise InstallError(tr('Выберите прямой VPN или каскад'))
        self.foreign.validate()
        if self.mode=='cascade':
            if not self.entry:raise InstallError(tr('Укажите RU-вход каскада'))
            self.entry.validate()
            if self.entry.host==self.foreign.host:raise InstallError(tr('Для каскада нужны два разных сервера'))
        elif self.entry is not None:raise InstallError(tr('В прямом режиме RU-сервер не используется'))
        for p in (self.vpn_port,self.panel_port,self.relay_port):
            if type(p) is not int or not 1024<=p<=65535:
                if p!=443:raise InstallError(tr('Порты: 1024–65535, либо 443 для TLS'))
        if self.panel_port in {80,self.foreign.port} or (self.mode=='cascade' and self.panel_port==self.relay_port):
            raise InstallError(tr('Порт панели конфликтует с SSH или TLS каскада'))
        if self.mode=='cascade' and self.relay_port==self.foreign.port:raise InstallError(tr('TLS каскада конфликтует с SSH зарубежного сервера'))
        if self.email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',self.email):raise InstallError(tr('Некорректный email'))
        if not self.ca_terms_accepted:raise InstallError(tr('Для HTTPS нужно принять условия центра сертификации'))
        return self
    @property
    def entrance(self):return self.entry if self.mode=='cascade' else self.foreign
    def public_plan(self):
        return {'mode':self.mode,'foreign_ip':self.foreign.host,'entry_ip':self.entrance.host,
                'vpn_udp_port':self.vpn_port,'panel_url':'https://'+self.foreign.host+':'+str(self.panel_port),
                'cascade_transport':'mutually-authenticated TLS 1.3' if self.mode=='cascade' else None,
                'fresh_ubuntu_24_04_only':True,'changes_existing_vpn':False}
