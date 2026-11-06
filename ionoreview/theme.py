"""Shared native ttk theme with rounded outlined buttons drawn as images; no web view, extra runtime, or global UI scaling."""
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

ICON=Path(__file__).resolve().parent/'assets'/'icon'/'ionoreview.png'
BG='#f3f6fb'
SURFACE='#ffffff'
TEXT='#17243b'
MUTED='#66758b'
BLUE='#2563eb'
BORDER='#dbe3ef'
EDGE='#aebbd0'
FACES={
    'Plain':[('#ffffff',EDGE),('#eef4ff',BLUE),('#dbe8ff','#1d4ed8'),('#f4f6f9','#dbe1ea')],
    'Primary':[(BLUE,'#1d4ed8'),('#1d4ed8','#1e3a8a'),('#1e40af','#1e3a8a'),('#b6c7e4','#b6c7e4')],
    'Danger':[('#fff7f7','#e3a1aa'),('#ffe9ec','#c92a3e'),('#ffd6dc','#b42338'),('#f4f6f9','#dbe1ea')],
    'Tool':[('#ffffff',EDGE),('#eef4ff',BLUE),('#dbe8ff',BLUE),('#f4f6f9','#dbe1ea')],
}


def face(fill, edge, size=(18, 18), radius=6):
    scale=4
    big=Image.new('RGBA',(size[0]*scale,size[1]*scale),(0,0,0,0))
    ImageDraw.Draw(big).rounded_rectangle((0,0,big.width-1,big.height-1),radius*scale,fill=fill,outline=edge,width=scale)
    small=big.resize(size,Image.LANCZOS)
    ImageDraw.Draw(small).line((radius,0,size[0]-radius-1,0),fill=edge)
    return small


def _faces(root, style):
    kept=root.__dict__.setdefault('_button_faces',{})
    for name,states in FACES.items():
        if f'{name}.face' in style.element_names():
            continue
        images=[ImageTk.PhotoImage(face(*s),master=root) for s in states]
        kept[name]=images
        pressed='selected' if name=='Tool' else 'pressed'
        style.element_create(f'{name}.face','image',images[0],('disabled',images[3]),(pressed,images[2]),('active',images[1]),
                             border=7,sticky='nsew')


def _button(style, name, element):
    style.layout(name,[(element,{'sticky':'nsew','children':[('Button.padding',{'sticky':'nsew','children':[
        ('Button.label',{'sticky':'nsew'})]})]})])


def apply_theme(root):
    style=ttk.Style(root)
    style.theme_use('clam')
    root.configure(background=BG)
    _faces(root,style)
    if 'icon' not in root.__dict__.get('_button_faces',{}):
        drawn=ImageTk.PhotoImage(Image.open(ICON).convert('RGBA'),master=root)
        root._button_faces['icon']=tk.PhotoImage(name='ionoreview_icon',master=root)
        root._button_faces['icon'].tk.call(root._button_faces['icon'].name,'copy',str(drawn))
        root.iconphoto(True,root._button_faces['icon'])
    style.configure('.',font=('Segoe UI',10),background=SURFACE,foreground=TEXT)
    style.configure('TFrame',background=SURFACE)
    style.configure('Surface.TFrame',background=BG)
    style.configure('TLabel',background=SURFACE,foreground=TEXT)
    style.configure('Muted.TLabel',foreground=MUTED)
    style.configure('Section.TLabel',font=('Segoe UI',9,'bold'),foreground=MUTED)
    style.configure('Title.TLabel',font=('Segoe UI',17,'bold'),foreground=TEXT)
    for name,element in [('TButton','Plain.face'),('Primary.TButton','Primary.face'),('Danger.TButton','Danger.face')]:
        _button(style,name,element)
    style.configure('TButton',padding=(10,3),background=SURFACE,anchor='center')
    style.map('TButton',foreground=[('disabled','#9ba8b9')])
    style.configure('Primary.TButton',foreground='white',font=('Segoe UI',10,'bold'))
    style.map('Primary.TButton',foreground=[('disabled','#f8fafc')])
    style.configure('Danger.TButton',foreground='#b42338')
    style.configure('TMenubutton',padding=(10,4),background=SURFACE,bordercolor=SURFACE,lightcolor=SURFACE,darkcolor=SURFACE,relief='flat',arrowcolor=MUTED)
    style.map('TMenubutton',background=[('active','#eef4ff')],bordercolor=[('active',EDGE)])
    style.configure('TEntry',fieldbackground=SURFACE,bordercolor=EDGE,lightcolor=SURFACE,darkcolor=SURFACE,padding=5)
    style.map('TEntry',bordercolor=[('focus',BLUE)])
    style.configure('TCombobox',fieldbackground=SURFACE,bordercolor=EDGE,lightcolor=SURFACE,darkcolor=SURFACE,padding=4,arrowsize=12)
    style.map('TCombobox',fieldbackground=[('readonly',SURFACE)],selectbackground=[('readonly',SURFACE)],selectforeground=[('readonly',TEXT)],
              bordercolor=[('focus',BLUE)])
    style.configure('TRadiobutton',padding=(4,4),background=SURFACE)
    style.configure('TCheckbutton',padding=(2,3),background=SURFACE,indicatorbackground=SURFACE,indicatorforeground=BLUE,
                    bordercolor=EDGE,lightcolor=SURFACE,darkcolor=SURFACE)
    style.map('TCheckbutton',indicatorbackground=[('selected','#eef4ff')])
    style.configure('TRadiobutton',indicatorbackground=SURFACE,indicatorforeground=BLUE,bordercolor=EDGE,lightcolor=SURFACE,darkcolor=SURFACE)
    style.configure('Horizontal.TScale',troughcolor='#dbe4f0',background=SURFACE,bordercolor=EDGE,lightcolor=SURFACE,darkcolor='#c9d4e5',
                    sliderlength=14,sliderthickness=14,gripcount=0,troughrelief='flat')
    style.map('Horizontal.TScale',background=[('active','#eef4ff')],bordercolor=[('active',BLUE)])
    style.layout('Tool.TRadiobutton',[('Tool.face',{'sticky':'nswe','children':[('Radiobutton.padding',{'sticky':'nswe','children':[
        ('Radiobutton.label',{'sticky':'nswe'})]})]})])
    style.configure('Tool.TRadiobutton',padding=(10,4),font=('Segoe UI',9),background=SURFACE,anchor='center')
    style.map('Tool.TRadiobutton',foreground=[('selected','#1d4ed8')],font=[('selected',('Segoe UI',9,'bold'))])
    style.configure('Horizontal.TProgressbar',background=BLUE,troughcolor='#e8eef8',bordercolor='#e8eef8',lightcolor=BLUE,darkcolor=BLUE,borderwidth=0,thickness=6)
    style.configure('Treeview',rowheight=37,fieldbackground=SURFACE,background=SURFACE,foreground=TEXT,borderwidth=0)
    style.map('Treeview',background=[('selected','#e7efff')],foreground=[('selected','#1d4ed8')])
    style.configure('Treeview.Heading',font=('Segoe UI',9,'bold'),foreground=MUTED,background=BG,padding=(8,9),relief='flat')
    style.configure('TPanedwindow',background=BORDER)
    style.configure('Pending.TLabel',foreground='#a5630a',font=('Segoe UI',10,'bold'))
    style.configure('Accepted.TLabel',foreground='#087f5b',font=('Segoe UI',10,'bold'))
    style.configure('Changes.TLabel',foreground='#b42338',font=('Segoe UI',10,'bold'))
    style.configure('Ambiguous.TLabel',foreground='#7950b3',font=('Segoe UI',10,'bold'))
    return style
