"""Bilingual, dependency-bundled Windows wizard. Demo cannot access a VPS."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import webbrowser

from i18n import set_language,language
from model import Login,Settings
from provision import Runner
from version import VERSION
import windows_client
from gui_theme import COLORS as C,apply_theme,brand_icon,dark_titlebar

TERMS='https://letsencrypt.org/repository/'


def t(ru,en):return en if language()=='en' else ru


class NodeFields:
    def __init__(self,master,host=''):
        self.ip=tk.StringVar(master,value=host);self.port=tk.StringVar(master,value='22')
        self.auth=tk.StringVar(master,value='password');self.password=tk.StringVar(master)
        self.key=tk.StringVar(master);self.passphrase=tk.StringVar(master)

    def render(self,parent,title):
        box=ttk.Frame(parent,style='Card.TFrame',padding=20)
        ttk.Label(box,text=t('ПОДКЛЮЧЕНИЕ ПО SSH','SSH CONNECTION'),style='Eyebrow.TLabel').pack(anchor='w')
        ttk.Label(box,text=title,style='CardTitle.TLabel').pack(anchor='w',pady=(5,15))
        address=ttk.Frame(box,style='Surface.TFrame');address.pack(fill='x');address.columnconfigure(0,weight=1)
        for column,(caption,var,width) in enumerate([(t('Публичный IPv4','Public IPv4'),self.ip,24),(t('SSH-порт','SSH port'),self.port,7)]):
            field=ttk.Frame(address,style='Surface.TFrame');field.grid(row=0,column=column,sticky='ew',padx=(0,12) if column==0 else 0)
            ttk.Label(field,text=caption,style='CardMuted.TLabel').pack(anchor='w',pady=(0,6))
            ttk.Entry(field,textvariable=var,width=width).pack(fill='x')
        methods=ttk.Frame(box,style='Surface.TFrame');methods.pack(fill='x',pady=(15,12))
        for value,caption in [('password',t('Пароль','Password')),('key',t('SSH-ключ','SSH key'))]:
            ttk.Radiobutton(methods,text=caption,variable=self.auth,value=value,style='Segment.TRadiobutton',command=self.render_auth).pack(side='left',padx=(0,8))
        self.auth_frame=ttk.Frame(box,style='Surface.TFrame');self.auth_frame.pack(fill='x');self.render_auth()
        ttk.Label(box,text=t('Пользователь: root · секреты только в памяти','User: root · secrets stay in memory'),style='CardMuted.TLabel').pack(anchor='w',pady=(13,0))
        return box

    def render_auth(self):
        for widget in self.auth_frame.winfo_children():widget.destroy()
        fields=[(t('Пароль root','Root password'),self.password,True)] if self.auth.get()=='password' else [
            (t('Файл приватного ключа','Private key file'),self.key,False),
            (t('Пароль ключа (если есть)','Key passphrase (if set)'),self.passphrase,True)]
        for caption,var,secret in fields:
            ttk.Label(self.auth_frame,text=caption,style='CardMuted.TLabel').pack(anchor='w',pady=(0,6))
            row=ttk.Frame(self.auth_frame,style='Surface.TFrame');row.pack(fill='x',pady=(0,4))
            if var is self.key:ttk.Button(row,text='…',width=3,command=self.choose).pack(side='right',padx=(8,0))
            ttk.Entry(row,textvariable=var,show='●' if secret else '',width=20).pack(side='left',fill='x',expand=True)

    def choose(self):
        value=filedialog.askopenfilename(title=t('Приватный SSH-ключ (не .pub)','SSH private key (not .pub)'))
        if value:self.key.set(value);self.auth.set('key');self.render_auth()

    def login(self):
        return Login(self.ip.get().strip(),int(self.port.get()),password=self.password.get() if self.auth.get()=='password' else '',
                     key_file=self.key.get().strip() if self.auth.get()=='key' else '',passphrase=self.passphrase.get() if self.auth.get()=='key' else '')

    def clear(self):self.password.set('');self.passphrase.set('')


class App:
    def __init__(self,lang='auto',demo=False,mode='direct'):
        set_language(lang);self.demo=demo;self.running=False;self.client_busy=False
        self.root=tk.Tk();width=min(1120,self.root.winfo_screenwidth()-60);height=min(880,self.root.winfo_screenheight()-70)
        self.root.geometry(str(width)+'x'+str(height));self.root.minsize(min(920,width),min(680,height));self.root.configure(bg=C['bg'])
        self.mode=tk.StringVar(self.root,value=mode);self.lang=tk.StringVar(self.root,value='English' if language()=='en' else 'Русский')
        self.foreign=NodeFields(self.root,'203.0.113.20' if demo else '');self.entry=NodeFields(self.root,'203.0.113.10' if demo else '')
        self.vpn_port=tk.StringVar(self.root,value='39265');self.panel_port=tk.StringVar(self.root,value='10443');self.relay_port=tk.StringVar(self.root,value='443')
        self.email=tk.StringVar(self.root);self.terms=tk.BooleanVar(self.root);self.advanced=tk.BooleanVar(self.root)
        self.events=queue.Queue();self.cancel=threading.Event()
        self.home=Path(os.getenv('LOCALAPPDATA',str(Path.home()/'.local/share')))/'AmneziaDashboardInstaller'
        self.style();self.render();dark_titlebar(self.root);self.root.protocol('WM_DELETE_WINDOW',self.close);self.root.after(100,self.poll)
        self.root.bind('<MouseWheel>',self.scroll_form)

    def style(self):
        self.theme=apply_theme(self.root)

    def render(self):
        if self.running or self.client_busy:return
        position=self.form_canvas.yview()[0] if hasattr(self,'form_canvas') and self.form_canvas.winfo_exists() else 0
        for widget in self.root.winfo_children():widget.destroy()
        self.root.title('AmneziaDashboard Setup '+VERSION+(' · DEMO' if self.demo else ''))
        container=ttk.Frame(self.root,padding=(26,22,26,18));container.pack(fill='both',expand=True)
        top=ttk.Frame(container);top.pack(fill='x')
        brand_icon(top).pack(side='left',padx=(0,12))
        title=ttk.Frame(top);title.pack(side='left')
        ttk.Label(title,text='AmneziaDashboard',style='Title.TLabel').pack(anchor='w')
        ttk.Label(title,text=t('Установка VPN и панели управления','VPN & dashboard setup'),style='Subtitle.TLabel').pack(anchor='w',pady=(1,0))
        self.langbox=ttk.Combobox(top,textvariable=self.lang,values=['Русский','English'],state='readonly',width=10)
        self.langbox.pack(side='right');self.langbox.bind('<<ComboboxSelected>>',self.change_language)
        ttk.Label(top,text='v'+VERSION,style='Version.TLabel',padding=(10,5)).pack(side='right',padx=14)
        if self.demo:
            ttk.Label(container,text=t('ДЕМО · вымышленные адреса · установка и загрузки отключены','DEMO · example addresses · installation and downloads disabled'),style='Demo.TLabel',padding=(12,7)).pack(fill='x',pady=(18,14))
        else:ttk.Label(container,text=t('Только новые Ubuntu 24.04 VPS · существующий VPN не перезаписывается','Fresh Ubuntu 24.04 VPSs only · existing VPNs are never overwritten'),style='Muted.TLabel').pack(anchor='w',pady=(18,14))
        self.tabs=ttk.Notebook(container);self.tabs.pack(fill='both',expand=True)
        viewport=ttk.Frame(self.tabs);progress=ttk.Frame(self.tabs,padding=(0,10,0,0))
        self.tabs.add(viewport,text=t('01   Подключение и настройки','01   Connection & settings'));self.tabs.add(progress,text=t('02   Ход установки','02   Installation progress'))
        self.form_canvas=tk.Canvas(viewport,bg=C['bg'],highlightthickness=0)
        scrollbar=ttk.Scrollbar(viewport,orient='vertical',command=self.form_canvas.yview)
        scrollbar.pack(side='right',fill='y');self.form_canvas.pack(side='left',fill='both',expand=True)
        self.form_canvas.configure(yscrollcommand=scrollbar.set)
        form=ttk.Frame(self.form_canvas,padding=(0,10,14,8));form_id=self.form_canvas.create_window((0,0),window=form,anchor='nw')
        form.bind('<Configure>',lambda event:self.form_canvas.configure(scrollregion=self.form_canvas.bbox('all')))
        self.form_canvas.bind('<Configure>',lambda event:self.form_canvas.itemconfigure(form_id,width=event.width))
        ttk.Label(form,text=t('Выберите схему подключения','Choose your connection'),font=('Segoe UI',14,'bold')).pack(anchor='w')
        ttk.Label(form,text=t('От 1 ГБ RAM, 3 ГБ свободного диска и /dev/net/tun на каждом VPS.','Each VPS needs 1 GB RAM, 3 GB free disk and /dev/net/tun.'),style='Muted.TLabel').pack(anchor='w',pady=(4,12))
        modes=ttk.Frame(form);modes.pack(fill='x',pady=(0,16));modes.columnconfigure((0,1),weight=1,uniform='modes')
        for index,(value,caption) in enumerate([('direct',t('Один зарубежный VPS','One foreign VPS')),('cascade',t('Каскад: RU → зарубежный VPS','Cascade: RU → foreign VPS'))]):
            ttk.Radiobutton(modes,text=caption,variable=self.mode,value=value,command=self.render,style='Mode.TRadiobutton').grid(row=0,column=index,sticky='ew',padx=(0,8) if index==0 else (8,0))
        nodes=ttk.Frame(form);nodes.pack(fill='x');nodes.columnconfigure(0,weight=1);nodes.columnconfigure(1,weight=1)
        self.foreign.render(nodes,t('Зарубежный сервер + панель','Foreign server + dashboard')).grid(row=0,column=0,sticky='nsew',padx=(0,8))
        if self.mode.get()=='cascade':self.entry.render(nodes,t('RU-вход каскада','RU cascade entry')).grid(row=0,column=1,sticky='nsew',padx=(8,0))
        else:
            route=ttk.Frame(nodes,style='Card.TFrame',padding=20);route.grid(row=0,column=1,sticky='nsew',padx=(8,0))
            ttk.Label(route,text=t('ПРЯМОЙ VPN','DIRECT VPN'),style='Eyebrow.TLabel').pack(anchor='w')
            ttk.Label(route,text=t('Всё на одном сервере','Everything on one server'),style='CardTitle.TLabel').pack(anchor='w',pady=(5,16))
            for caption,color in [(t('Телефон / компьютер','Phone / computer'),C['text']),('↓',C['purple']),(t('Зарубежный VPS','Foreign VPS'),C['blue']),('↓',C['purple']),(t('Интернет','Internet'),C['orange'])]:
                ttk.Label(route,text=caption,style='Card.TLabel',foreground=color,font=('Segoe UI',11,'bold')).pack(anchor='w',pady=3)
            ttk.Label(route,text=t('Панель и AmneziaWG — вместе.\nRU-сервер не нужен.','Dashboard and AmneziaWG together.\nNo RU server needed.'),style='CardMuted.TLabel',justify='left').pack(anchor='w',pady=(12,0))
        options=ttk.Frame(form,style='Card.TFrame',padding=20);options.pack(fill='x',pady=(16,0))
        ttk.Label(options,text=t('Параметры установки','Installation options'),style='CardTitle.TLabel').pack(anchor='w',pady=(0,10))
        ttk.Checkbutton(options,text=t('Дополнительно: порты','Advanced: ports'),variable=self.advanced,command=self.render).pack(anchor='w',pady=(0,6))
        if self.advanced.get():
            ports=ttk.Frame(options,style='Surface.TFrame');ports.pack(fill='x',pady=(0,10))
            for caption,var in [('VPN UDP',self.vpn_port),('Dashboard TCP',self.panel_port),('Cascade TLS TCP',self.relay_port)]:
                if caption=='Cascade TLS TCP' and self.mode.get()!='cascade':continue
                ttk.Label(ports,text=caption,style='CardMuted.TLabel').pack(side='left',padx=(0,6));ttk.Entry(ports,textvariable=var,width=7).pack(side='left',padx=(0,18))
        cert=ttk.Frame(options,style='Surface.TFrame');cert.pack(fill='x',pady=5)
        ttk.Label(cert,text=t('Email для сертификата (необязательно)','Certificate email (optional)'),style='CardMuted.TLabel').pack(side='left',padx=(0,12))
        ttk.Entry(cert,textvariable=self.email,width=32).pack(side='left')
        consent=ttk.Frame(options,style='Surface.TFrame');consent.pack(fill='x',pady=5)
        ttk.Checkbutton(consent,text=t('Я принимаю условия Let’s Encrypt','I accept the Let’s Encrypt terms'),variable=self.terms).pack(side='left')
        ttk.Button(consent,text=t('Прочитать ↗','Read terms ↗'),command=lambda:webbrowser.open(TERMS)).pack(side='left',padx=8)
        ttk.Label(options,text=t('Для HTTPS нужен TCP 80. IP появится в публичном журнале сертификатов.',
                             'HTTPS needs TCP 80. IPs appear in public certificate logs.'),style='CardMuted.TLabel').pack(anchor='w',pady=(4,0))
        logcard=ttk.Frame(progress,style='Card.TFrame',padding=20);logcard.pack(fill='both',expand=True)
        ttk.Label(logcard,text=t('Ход установки','Installation progress'),style='CardTitle.TLabel').pack(anchor='w')
        ttk.Label(logcard,text=t('Проверка → подтверждение → бэкапы → установка','Checks → approval → backups → installation'),style='CardMuted.TLabel').pack(anchor='w',pady=(6,15))
        logarea=ttk.Frame(logcard,style='Surface.TFrame');logarea.pack(fill='both',expand=True)
        self.logbox=tk.Text(logarea,bg=C['surface'],fg=C['text'],insertbackground=C['orange'],wrap='word',height=16,state='disabled',font=('Consolas',10),borderwidth=0,highlightthickness=0,padx=2,pady=8)
        logscroll=ttk.Scrollbar(logarea,orient='vertical',command=self.logbox.yview);logscroll.pack(side='right',fill='y')
        self.logbox.configure(yscrollcommand=logscroll.set);self.logbox.pack(side='left',fill='both',expand=True)
        self.resultframe=ttk.Frame(progress);self.resultframe.pack(fill='x',pady=(8,0))
        self.append(t('Здесь появятся результаты проверки и этапы установки.\nБез подтверждения серверов и плана изменения не начнутся.',
                      'Checks and installation stages will appear here.\nNo changes begin before server and plan approval.'))
        footer=ttk.Frame(container);footer.pack(fill='x',pady=(14,0))
        self.client_button=ttk.Button(footer,text=t('AmneziaVPN для этого ПК…','AmneziaVPN for this PC…'),command=self.install_client);self.client_button.pack(side='left')
        self.cancel_button=ttk.Button(footer,text=t('Остановить после этапа','Stop after this stage'),command=self.stop,state='disabled');self.cancel_button.pack(side='left',padx=10)
        self.start_button=ttk.Button(footer,text=t('Проверить и установить','Check and install'),style='Primary.TButton',command=self.start);self.start_button.pack(side='right')
        if self.demo:self.start_button.configure(state='disabled');self.client_button.configure(state='disabled')
        self.root.after_idle(lambda:self.form_canvas.yview_moveto(position))

    def change_language(self,event=None):
        if self.running or self.client_busy:return
        set_language('en' if self.lang.get()=='English' else 'ru');self.render()

    def scroll_form(self,event):
        if self.tabs.select()==self.tabs.tabs()[0] and not isinstance(event.widget,ttk.Combobox):
            self.form_canvas.yview_scroll(-int(event.delta/120),'units')

    def busy(self,value):
        self.langbox.configure(state='disabled' if value else 'readonly')
        self.tabs.tab(0,state='disabled' if value else 'normal')
        for button in (self.start_button,self.client_button):button.configure(state='disabled' if value or self.demo else 'normal')
        self.cancel_button.configure(state='normal' if self.running else 'disabled')

    def start(self):
        if self.demo or self.running or self.client_busy:return
        try:
            settings=Settings(self.mode.get(),self.foreign.login(),self.entry.login() if self.mode.get()=='cascade' else None,
                              int(self.vpn_port.get()),int(self.panel_port.get()),int(self.relay_port.get()),self.email.get().strip(),self.terms.get()).validate()
        except ValueError:
            messagebox.showerror(t('Проверьте настройки','Check settings'),t('Порты должны быть целыми числами.','Ports must be whole numbers.'));return
        except Exception as error:messagebox.showerror(t('Проверьте настройки','Check settings'),str(error));return
        self.running=True;self.cancel.clear();self.tabs.select(1);self.busy(True);self.foreign.clear();self.entry.clear()
        def work():
            try:
                runner=Runner(settings,self.home,lambda msg:self.events.put(('log',msg)),lambda host,fp:self.ask('host',(host,fp)),lambda plan:self.ask('plan',plan),self.cancel)
                self.events.put(('done',runner.run()))
            except Exception as error:self.events.put(('error',str(error)))
        threading.Thread(target=work,daemon=False,name='installer').start()

    def ask(self,kind,value):
        reply=queue.Queue();self.events.put(('ask',(kind,value,reply)))
        while not self.cancel.is_set():
            try:return reply.get(timeout=.3)
            except queue.Empty:pass
        return False

    def append(self,value):
        self.logbox.configure(state='normal');self.logbox.insert('end',value+'\n');self.logbox.see('end');self.logbox.configure(state='disabled')

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='log':self.append(value)
                elif kind=='ask':
                    what,data,reply=value
                    if what=='host':
                        title=t('Подтверждение SSH-сервера','Verify SSH server')
                        text=t('Сервер: ','Server: ')+data[0]+'\n\nSHA-256: '+data[1]+t('\n\nСверьте отпечаток в консоли хостинга. Подтвердить?','\n\nCompare this fingerprint in the hosting console. Trust this server?')
                    else:
                        title=t('Подтвердите план','Approve installation plan')
                        text=(t('Режим: ','Mode: ')+(t('Каскад','Cascade') if data['mode']=='cascade' else t('Прямой VPN','Direct VPN'))+
                              t('\nVPN-вход: ','\nVPN entry: ')+data['entry_ip']+' · UDP '+str(data['vpn_udp_port'])+
                              t('\nЗарубежный сервер: ','\nForeign server: ')+data['foreign_ip']+
                              t('\nПанель: ','\nDashboard: ')+data['panel_url']+
                              t('\nПоследний стабильный клиент: ','\nLatest stable client: ')+data['versions']['amnezia_client']['tag']+
                              t('\n\nСначала — проверенные резервные копии всех выбранных VPS.\nЗатем — Docker, AmneziaWG, панель, новые ключи, правила её портов и автопродление TLS.\n\nСуществующий VPN не перезаписывается. Начать изменения?',
                                '\n\nFirst: verified backups of all selected VPSs.\nThen: Docker, AmneziaWG, dashboard, new keys, scoped port rules and TLS renewal.\n\nExisting VPNs are not overwritten. Begin changes?'))
                    reply.put(messagebox.askyesno(title,text,default='no'))
                elif kind in {'done','error'}:
                    self.running=False;self.busy(False)
                    if kind=='error':self.append(t('Установка не завершена: ','Installation not completed: ')+value);messagebox.showerror(t('Установка не завершена','Installation not completed'),value)
                    else:
                        ttk.Label(self.resultframe,text=t('Готово. Логин: owner','Completed. Login: owner'),foreground='#7EBAD2').pack(anchor='w')
                        ttk.Button(self.resultframe,text=t('Открыть панель ↗','Open dashboard ↗'),command=lambda url=value['url']:webbrowser.open(url+'/admin')).pack(anchor='w',pady=5)
                        self.append(t('Первый пароль: result-private.json в приватной папке. Не пересылайте её.\n','Initial password: result-private.json in this private folder. Do not share it.\n')+value['backup_directory'])
                elif kind in {'client_done','client_error'}:
                    self.client_busy=False;self.busy(False)
                    if kind=='client_error':messagebox.showerror(t('Не удалось загрузить клиент','Client download failed'),value)
                    else:messagebox.showinfo('AmneziaVPN',t('Открыт официальный установщик. Завершите его шаги и подтверждения Windows.','Official setup opened. Complete its steps and Windows confirmations.'))
        except queue.Empty:pass
        self.root.after(100,self.poll)

    def install_client(self):
        if self.demo or self.running or self.client_busy:return
        if not messagebox.askyesno('AmneziaVPN',t('Загрузить последнюю стабильную версию с официального GitHub, проверить SHA-256 и открыть установщик?','Download the latest stable version from official GitHub, verify SHA-256 and open its installer?'),default='no'):return
        self.client_busy=True;self.tabs.select(1);self.busy(True)
        def work():
            try:
                last=[-1]
                def progress(percent):
                    if percent//10!=last[0]:last[0]=percent//10;self.events.put(('log','AmneziaVPN: '+str(percent)+'%'))
                path=windows_client.download(self.home/'client-downloads',progress);windows_client.launch(path);self.events.put(('client_done',None))
            except Exception as error:self.events.put(('client_error',str(error)))
        threading.Thread(target=work,daemon=False,name='client-download').start()

    def stop(self):
        if self.running and messagebox.askyesno(t('Остановить?','Stop installation?'),t('Текущий этап завершится, затем остановится только новая установка. Резервные копии сохранятся.','Finish the current stage, then stop only the new installation. Backups are preserved.'),default='no'):
            self.cancel.set();self.append(t('Остановка запрошена. Дождитесь завершения этапа.','Stop requested. Wait for the current stage to finish.'))

    def close(self):
        if self.running:self.stop();return
        if self.client_busy:messagebox.showinfo('AmneziaVPN',t('Дождитесь завершения загрузки.','Wait for the download to finish.'));return
        self.root.destroy()

    def run(self):self.root.mainloop()


def main():
    parser=argparse.ArgumentParser(description='AmneziaDashboard Windows setup')
    parser.add_argument('--lang',choices=('auto','ru','en'),default='auto')
    parser.add_argument('--mode',choices=('direct','cascade'),default='direct')
    parser.add_argument('--demo',action='store_true',help='Synthetic UI only; SSH and downloads disabled')
    parser.add_argument('--self-test',action='store_true');parser.add_argument('--report',type=Path)
    args=parser.parse_args();set_language(args.lang)
    if args.self_test:
        from cli import self_test
        with contextlib.redirect_stdout(io.StringIO()):self_test()
        if args.report:
            args.report.parent.mkdir(parents=True,exist_ok=True)
            with args.report.open('x',encoding='utf-8') as output:json.dump({'version':VERSION,'passed':True,'vps_accessed':False},output)
        return 0
    App(args.lang,args.demo,args.mode).run();return 0
