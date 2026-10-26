"""Windows wizard; no installation begins before SSH fingerprints and plan consent."""
import argparse
import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import webbrowser
from model import Login,Settings,InstallError
from provision import Runner
from version import VERSION

TERMS='https://letsencrypt.org/repository/'

class NodeForm(ttk.LabelFrame):
    def __init__(self,parent,title):
        super().__init__(parent,text=title,padding=14)
        self.ip=tk.StringVar();self.port=tk.StringVar(value='22');self.auth=tk.StringVar(value='password')
        self.password=tk.StringVar();self.key=tk.StringVar();self.passphrase=tk.StringVar()
        self.columnconfigure(1,weight=1)
        for row,(caption,var,secret) in enumerate([('Публичный IPv4',self.ip,False),('SSH-порт',self.port,False),
             ('Пароль root',self.password,True),('Файл SSH-ключа',self.key,False),('Пароль ключа',self.passphrase,True)]):
            ttk.Label(self,text=caption).grid(row=row,column=0,sticky='w',padx=(0,10),pady=5)
            entry=ttk.Entry(self,textvariable=var,show='●' if secret else '',width=23)
            entry.grid(row=row,column=1,sticky='ew',pady=5)
            if var is self.key:ttk.Button(self,text='…',width=3,command=self.choose).grid(row=row,column=2,padx=(5,0))
        methods=ttk.Frame(self);methods.grid(row=5,column=0,columnspan=3,sticky='w',pady=(10,0))
        ttk.Radiobutton(methods,text='Пароль',variable=self.auth,value='password').pack(side='left')
        ttk.Radiobutton(methods,text='SSH-ключ',variable=self.auth,value='key').pack(side='left',padx=10)
        ttk.Label(self,text='Пользователь SSH: root',style='Muted.TLabel').grid(row=6,column=0,columnspan=3,sticky='w',pady=(8,0))
    def choose(self):
        value=filedialog.askopenfilename(title='Приватный SSH-ключ (не .pub)')
        if value:self.key.set(value);self.auth.set('key')
    def login(self):
        return Login(self.ip.get().strip(),int(self.port.get()),password=self.password.get() if self.auth.get()=='password' else '',
                     key_file=self.key.get().strip() if self.auth.get()=='key' else '',
                     passphrase=self.passphrase.get() if self.auth.get()=='key' else '')
    def clear_passwords(self):self.password.set('');self.passphrase.set('')

class App:
    def __init__(self):
        self.root=tk.Tk();self.root.title('AmneziaDashboard — Установщик '+VERSION)
        self.root.geometry('1000x880');self.root.minsize(960,820);self.root.configure(bg='#141414')
        style=ttk.Style();style.theme_use('clam')
        style.configure('.',background='#1c1c1c',foreground='#f2f2f2',font=('Segoe UI',10))
        style.configure('TFrame',background='#141414');style.configure('TLabel',background='#141414')
        style.configure('TLabelframe',background='#141414',bordercolor='#404040')
        style.configure('TLabelframe.Label',background='#141414',foreground='#7EBAD2')
        style.configure('TEntry',fieldbackground='#242424',foreground='#f2f2f2',insertcolor='#f2f2f2',padding=6)
        style.configure('TButton',background='#242424',padding=(12,8));style.map('TButton',background=[('active','#404040')])
        style.configure('Primary.TButton',background='#F6A453',foreground='#141414',font=('Segoe UI',11,'bold'))
        style.map('Primary.TButton',background=[('active','#F6A453')],foreground=[('disabled','#888888')])
        style.configure('Muted.TLabel',foreground='#bcbcbc',font=('Segoe UI',9))
        style.configure('TRadiobutton',background='#141414');style.configure('TCheckbutton',background='#141414')
        container=ttk.Frame(self.root,padding=22);container.pack(fill='both',expand=True)
        top=ttk.Frame(container);top.pack(fill='x')
        icon=tk.Canvas(top,width=46,height=46,bg='#242424',highlightthickness=0)
        icon.create_line(10,36,23,10,fill='#7EBAD2',width=4);icon.create_line(23,10,37,36,fill='#F6A453',width=4)
        icon.create_line(15,28,32,28,fill='#9B8BC1',width=4);icon.pack(side='left',padx=(0,12))
        ttk.Label(top,text='AmneziaDashboard',font=('Segoe UI',21,'bold')).pack(anchor='w')
        ttk.Label(top,text='Тестовая версия · первая установка требует проверки на чистых VPS',style='Muted.TLabel').pack(anchor='w')
        self.tabs=ttk.Notebook(container);self.tabs.pack(fill='both',expand=True,pady=18)
        form=ttk.Frame(self.tabs,padding=14);progress=ttk.Frame(self.tabs,padding=14)
        self.tabs.add(form,text='  Настройки  ');self.tabs.add(progress,text='  Ход установки  ')
        ttk.Label(form,text='Только чистые Ubuntu 24.04: от 1 ГБ RAM, 3 ГБ свободного места и доступный /dev/net/tun.',style='Muted.TLabel').pack(anchor='w')
        self.mode=tk.StringVar(value='cascade');modes=ttk.Frame(form);modes.pack(fill='x',pady=14)
        ttk.Radiobutton(modes,text='Каскад: RU → зарубежный VPS',variable=self.mode,value='cascade').pack(side='left',padx=(0,30))
        ttk.Radiobutton(modes,text='Только зарубежный VPS',variable=self.mode,value='direct').pack(side='left')
        nodes=ttk.Frame(form);nodes.pack(fill='x');nodes.columnconfigure(0,weight=1);nodes.columnconfigure(1,weight=1)
        self.foreign=NodeForm(nodes,'Зарубежный сервер + панель');self.foreign.grid(row=0,column=0,sticky='nsew',padx=(0,8))
        self.entry=NodeForm(nodes,'RU-вход (только для каскада)');self.entry.grid(row=0,column=1,sticky='nsew',padx=(8,0))
        advanced=ttk.LabelFrame(form,text='Порты и сертификат',padding=12);advanced.pack(fill='x',pady=14)
        self.vpn_port=tk.StringVar(value='39265');self.panel_port=tk.StringVar(value='10443');self.relay_port=tk.StringVar(value='443');self.email=tk.StringVar()
        for col,(caption,var) in enumerate([('VPN · UDP',self.vpn_port),('Панель · TCP',self.panel_port),('Каскад · TCP',self.relay_port)]):
            ttk.Label(advanced,text=caption).grid(row=0,column=col*2,padx=(0,7))
            ttk.Entry(advanced,textvariable=var,width=7).grid(row=0,column=col*2+1,padx=(0,15))
        ttk.Label(advanced,text='Email для CA (необязательно)').grid(row=1,column=0,columnspan=2,sticky='w',pady=(12,0))
        ttk.Entry(advanced,textvariable=self.email,width=35).grid(row=1,column=2,columnspan=4,sticky='ew',pady=(12,0))
        self.terms=tk.BooleanVar(value=False)
        ttk.Checkbutton(form,text='Принимаю условия Let’s Encrypt для выпуска HTTPS-сертификата по IP',variable=self.terms).pack(anchor='w')
        ttk.Button(form,text='Открыть условия центра сертификации ↗',command=lambda:webbrowser.open(TERMS)).pack(anchor='w',pady=(5,8))
        ttk.Label(form,text='IP панели будет передан центру сертификации и попадёт в публичные журналы сертификатов.\n'
                  'Пароли root не сохраняются. Приватные копии сохраняются на компьютере и в root-папке установки на VPS.',style='Muted.TLabel').pack(anchor='w')
        self.logbox=tk.Text(progress,bg='#1c1c1c',fg='#f2f2f2',insertbackground='#f2f2f2',wrap='word',font=('Consolas',10),height=16,state='disabled')
        self.logbox.pack(fill='both',expand=True)
        self.resultframe=ttk.Frame(progress);self.resultframe.pack(fill='x',pady=(14,0))
        footer=ttk.Frame(container);footer.pack(fill='x')
        self.start_button=ttk.Button(footer,text='Проверить и установить',style='Primary.TButton',command=self.start)
        self.start_button.pack(side='right')
        self.cancel_button=ttk.Button(footer,text='Остановить после этапа',command=self.stop,state='disabled');self.cancel_button.pack(side='left')
        self.events=queue.Queue();self.cancel=threading.Event();self.running=False
        self.home=Path(os.getenv('LOCALAPPDATA',str(Path.home()/'.local/share')))/'AmneziaDashboardInstaller'
        self.root.protocol('WM_DELETE_WINDOW',self.close);self.root.after(100,self.poll)
    def start(self):
        if self.running:return
        try:
            mode=self.mode.get();settings=Settings(mode,self.foreign.login(),self.entry.login() if mode=='cascade' else None,
                int(self.vpn_port.get()),int(self.panel_port.get()),int(self.relay_port.get()),self.email.get().strip(),self.terms.get()).validate()
        except Exception as error:messagebox.showerror('Проверьте настройки',str(error));return
        self.running=True;self.cancel.clear();self.start_button.configure(state='disabled');self.cancel_button.configure(state='normal')
        self.foreign.clear_passwords();self.entry.clear_passwords();self.tabs.select(1)
        def work():
            try:
                runner=Runner(settings,self.home,lambda msg:self.events.put(('log',msg)),
                    lambda host,fp:self.ask('host',(host,fp)),lambda plan:self.ask('plan',plan),self.cancel)
                result=runner.run();self.events.put(('done',result))
            except Exception as error:self.events.put(('error',str(error)))
        threading.Thread(target=work,daemon=True,name='installer').start()
    def ask(self,kind,value):
        reply=queue.Queue();self.events.put(('ask',(kind,value,reply)))
        while not self.cancel.is_set():
            try:return reply.get(timeout=.3)
            except queue.Empty:pass
        return False
    def append(self,text):
        self.logbox.configure(state='normal');self.logbox.insert('end',text+'\n');self.logbox.see('end');self.logbox.configure(state='disabled')
    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='log':self.append(value)
                elif kind=='ask':
                    what,data,reply=value
                    if what=='host':
                        text='Сервер: '+data[0]+'\n\nОтпечаток SSH:\n'+data[1]+'\n\nСверьте его в консоли хостинга или по доверенному SSH.\nПодтвердить этот сервер?'
                        accepted=messagebox.askyesno('Подтверждение SSH-сервера',text,default='no')
                    else:
                        text=('Режим: '+('каскад' if data['mode']=='cascade' else 'прямой VPN')+'\nVPN-вход: '+data['entry_ip']+
                              '\nЗарубежный: '+data['foreign_ip']+'\nПанель: '+data['panel_url']+
                              '\n\nБудут установлены Docker, AmneziaWG и панель, созданы VPN-ключи,\n'
                              'ограниченный SSH-ключ панели, правила её портов и автопродление TLS.\n'
                              'Сначала создаются резервные копии. Существующие VPN не перезаписываются.\n\nНачать изменения на этих серверах?')
                        accepted=messagebox.askyesno('Подтвердите план установки',text,default='no')
                    reply.put(accepted)
                elif kind in {'done','error'}:
                    self.running=False;self.cancel_button.configure(state='disabled');self.start_button.configure(state='normal')
                    if kind=='error':self.append('Установка не завершена: '+value);messagebox.showerror('Установка не завершена',value)
                    else:self.show_result(value)
        except queue.Empty:pass
        self.root.after(100,self.poll)
    def show_result(self,result):
        for widget in self.resultframe.winfo_children():widget.destroy()
        ttk.Label(self.resultframe,text='Готово: '+result['url']+'  ·  Логин: owner',foreground='#7EBAD2').pack(anchor='w')
        row=ttk.Frame(self.resultframe);row.pack(fill='x',pady=8)
        ttk.Label(row,text='Первый пароль:').pack(side='left',padx=(0,8))
        field=ttk.Entry(row,show='●',width=38);field.insert(0,result['password']);field.configure(state='readonly');field.pack(side='left')
        ttk.Button(row,text='Показать / скрыть',command=lambda:field.configure(show='' if field.cget('show') else '●')).pack(side='left',padx=8)
        ttk.Button(self.resultframe,text='Открыть панель ↗',command=lambda:webbrowser.open(result['url']+'/admin')).pack(anchor='w')
        self.append('Приватные резервные копии и первый пароль: '+result['backup_directory']+'\nНе пересылайте эту папку другим людям. Смените первый пароль в панели.')
    def stop(self):
        if self.running and messagebox.askyesno('Остановить?','Текущий этап будет завершён, затем установщик остановит только созданные им VPN-контейнеры. Резервные копии сохранятся.',default='no'):
            self.cancel.set();self.append('Остановка запрошена. Не закрывайте окно до завершения текущего этапа.')
    def close(self):
        if self.running:self.stop();return
        self.root.destroy()
    def run(self):self.root.mainloop()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='AmneziaDashboard Windows installer');parser.parse_args();App().run()
