"""Dashboard-inspired Tk theme. Standard library only; no network or install work."""
import math
import base64
import tkinter as tk
from tkinter import ttk

COLORS = {
    'bg': '#141414', 'surface': '#1f1f1f', 'raised': '#282828',
    'line': '#3a3a3a', 'text': '#f2f2f2', 'muted': '#bcbcbc',
    'blue': '#7EBAD2', 'purple': '#9B8BC1', 'orange': '#F6A453',
    'blue_soft': '#2a3236', 'purple_soft': '#2b2832', 'orange_soft': '#392d22',
}


def rounded_image(master, fill, border, radius=9):
    """Small antialiased nine-slice, stretched by ttk without extra packages."""
    # Tk tiles the middle of an image element. A 3x3 centre made large cards
    # require tens of thousands of blits on every repaint, especially at HiDPI.
    # A 256x256 centre also keeps idle/focus repaints cheap at Windows HiDPI.
    # Fill straight regions in Tcl; calculate only the small corner pixels.
    size = radius * 2 + 258
    image = tk.PhotoImage(master=master, width=size, height=size)
    def rgb(value):return tuple(int(value[i:i+2], 16) for i in (1, 3, 5))
    surface = rgb(COLORS['bg']); edge = rgb(border); inside = rgb(fill)
    def hex_color(values):return '#%02x%02x%02x' % tuple(values)
    image.put(fill,to=(0,0,size,size))
    for inset,color in [(0,hex_color([round((surface[n]+edge[n])/2) for n in range(3)])),
                         (1,hex_color([round((inside[n]+edge[n])/2) for n in range(3)]))]:
        image.put(color,to=(inset,inset,size-inset,inset+1))
        image.put(color,to=(inset,size-inset-1,size-inset,size-inset))
        image.put(color,to=(inset,inset,inset+1,size-inset))
        image.put(color,to=(size-inset-1,inset,size-inset,size-inset))
    for y in range(radius+1):
        row = []
        for x in range(radius+1):
            dx = radius-x;dy = radius-y
            distance = math.hypot(dx, dy)
            outer = max(0., min(1., radius + .5-distance))
            inner = max(0., min(1., radius - .5-distance))
            color = tuple(round(surface[n]*(1-outer)+edge[n]*(outer-inner)+inside[n]*inner) for n in range(3))
            row.append('#%02x%02x%02x' % color)
        for yy in (y,size-1-y):
            image.put('{'+' '.join(row)+'}', to=(0,yy))
            image.put('{'+' '.join(reversed(row))+'}', to=(size-radius-1,yy))
    return image


def apply_theme(root):
    c=COLORS;style=ttk.Style(root);style.theme_use('clam')
    # Images must remain alive for the lifetime of their Tcl elements.
    root.dashboard_images=[]
    def element(name, colors, radius=9):
        images=[rounded_image(root, fill, border, radius) for fill,border in colors]
        root.dashboard_images.extend(images)
        specs=[images[0]]
        if len(images)>1:specs.extend([('active',images[1]),('focus',images[1])])
        if len(images)>2:specs.insert(1,('selected',images[2]))
        style.element_create(name,'image',*specs,border=radius+1,width=radius*2+5,height=radius*2+5,sticky='nsew')
    style.configure('.',background=c['bg'],foreground=c['text'],font=('Segoe UI',10),borderwidth=0)
    for name,bg in [('TFrame',c['bg']),('Surface.TFrame',c['surface'])]:style.configure(name,background=bg)
    for name,bg,fg,font in [
        ('TLabel',c['bg'],c['text'],('Segoe UI',10)),
        ('Muted.TLabel',c['bg'],c['muted'],('Segoe UI',9)),
        ('Card.TLabel',c['surface'],c['text'],('Segoe UI',10)),
        ('CardMuted.TLabel',c['surface'],c['muted'],('Segoe UI',9)),
        ('CardTitle.TLabel',c['surface'],c['text'],('Segoe UI',13,'bold')),
        ('Eyebrow.TLabel',c['surface'],c['blue'],('Segoe UI',9,'bold')),
        ('Title.TLabel',c['bg'],c['text'],('Segoe UI',21,'bold')),
        ('Subtitle.TLabel',c['bg'],c['muted'],('Segoe UI',10)),
        ('Demo.TLabel',c['purple_soft'],c['purple'],('Segoe UI',9)),
        ('Version.TLabel',c['raised'],c['purple'],('Segoe UI',9,'bold')),
    ]:style.configure(name,background=bg,foreground=fg,font=font)
    element('Dashboard.card',[(c['surface'],c['line'])],14)
    style.layout('Card.TFrame',[('Dashboard.card',{'sticky':'nsew','children':[('Frame.padding',{'sticky':'nsew'})]})])
    element('Dashboard.button',[(c['raised'],c['line']),(c['blue_soft'],c['blue'])])
    element('Dashboard.primary',[(c['orange'],c['orange']),( '#ffb46e',c['orange'])])
    element('Dashboard.segment',[(c['surface'],c['line']),(c['raised'],c['blue']),(c['orange_soft'],c['orange'])])
    for name,background in [('TButton','Dashboard.button'),('Primary.TButton','Dashboard.primary'),
                            ('Mode.TRadiobutton','Dashboard.segment'),('Segment.TRadiobutton','Dashboard.segment')]:
        style.layout(name,[(background,{'sticky':'nsew','children':[('Button.padding',{'sticky':'nsew','children':[('Button.label',{'sticky':'nsew'})]})]})])
        style.configure(name,padding=(14,10),anchor='center',borderwidth=0)
        style.map(name,foreground=[('disabled','#858585')])
    style.configure('Primary.TButton',foreground=c['bg'],font=('Segoe UI',10,'bold'))
    style.map('Primary.TButton',foreground=[('disabled','#69543e'),('!disabled',c['bg'])])
    style.configure('Mode.TRadiobutton',padding=(18,13),anchor='w',font=('Segoe UI',10,'bold'))
    style.configure('Segment.TRadiobutton',padding=(12,8),font=('Segoe UI',9))
    for name in ('Mode.TRadiobutton','Segment.TRadiobutton'):
        style.map(name,foreground=[('selected',c['orange']),('disabled','#858585'),('!selected',c['muted'])])
    element('Dashboard.field',[(c['bg'],c['line']),(c['bg'],c['blue'])],7)
    style.layout('TEntry',[('Dashboard.field',{'sticky':'nsew','children':[('Entry.padding',{'sticky':'nsew','children':[('Entry.textarea',{'sticky':'nsew'})]})]})])
    style.configure('TEntry',fieldbackground=c['bg'],foreground=c['text'],insertcolor=c['text'],padding=(11,9),selectbackground=c['purple_soft'],selectforeground=c['text'])
    style.configure('TCombobox',fieldbackground=c['raised'],background=c['raised'],foreground=c['text'],arrowcolor=c['blue'],bordercolor=c['line'],lightcolor=c['line'],darkcolor=c['line'],padding=(8,7))
    style.map('TCombobox',fieldbackground=[('readonly',c['raised'])],foreground=[('readonly',c['text'])],bordercolor=[('focus',c['blue'])])
    root.option_add('*TCombobox*Listbox.background',c['raised']);root.option_add('*TCombobox*Listbox.foreground',c['text'])
    root.option_add('*TCombobox*Listbox.selectBackground',c['purple_soft'])
    style.configure('TCheckbutton',background=c['surface'],indicatorbackground=c['bg'],indicatorforeground=c['orange'],padding=(0,4))
    style.map('TCheckbutton',background=[('active',c['surface'])],foreground=[('disabled','#858585'),('active',c['text'])],indicatorbackground=[('selected',c['orange'])])
    style.layout('TNotebook',[('Notebook.client',{'sticky':'nsew'})])
    style.configure('TNotebook',background=c['bg'],bordercolor=c['bg'],lightcolor=c['bg'],darkcolor=c['bg'],borderwidth=0,tabmargins=(0,0,0,12))
    style.layout('TNotebook.Tab',[('Dashboard.segment',{'sticky':'nsew','children':[('Notebook.padding',{'sticky':'nsew','children':[('Notebook.label',{'sticky':'nsew'})]})]})])
    style.configure('TNotebook.Tab',padding=(18,10),font=('Segoe UI',10,'bold'),expand=(0,0,0,0))
    style.map('TNotebook.Tab',padding=[],expand=[('selected',(0,0,0,0)),('!selected',(0,0,0,0))],foreground=[('selected',c['orange']),('disabled','#858585'),('!selected',c['muted'])])
    style.layout('Vertical.TScrollbar',[('Vertical.Scrollbar.trough',{'sticky':'ns','children':[('Vertical.Scrollbar.thumb',{'expand':True,'sticky':'nsew'})]})])
    style.configure('Vertical.TScrollbar',background=c['line'],troughcolor=c['bg'],borderwidth=0,width=8,arrowsize=0)
    style.map('Vertical.TScrollbar',background=[('active',c['purple']),('pressed',c['blue'])])
    style.configure('TProgressbar',background=c['orange'],troughcolor=c['raised'],borderwidth=0,thickness=4)
    return style


def brand_icon(parent,size=48):
    from branding import icon_png
    photo=tk.PhotoImage(master=parent,data=base64.b64encode(icon_png(size)))
    icon=ttk.Label(parent,image=photo);icon.dashboard_photo=photo
    parent.winfo_toplevel().iconphoto(True,photo)
    return icon


def dark_titlebar(root):
    """Ask supported Windows versions to match the native title bar to the app."""
    import sys
    if sys.platform!='win32':return
    try:
        import ctypes
        root.update_idletasks();hwnd=ctypes.windll.user32.GetParent(root.winfo_id())
        value=ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd),20,ctypes.byref(value),ctypes.sizeof(value))
    except (AttributeError,OSError):pass
