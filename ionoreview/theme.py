"""Shared native ttk theme; no web view, extra runtime, or global UI scaling."""
from tkinter import ttk

BG='#f3f6fb'
SURFACE='#ffffff'
TEXT='#17243b'
MUTED='#66758b'
BLUE='#2563eb'
BORDER='#dbe3ef'


def apply_theme(root):
    style=ttk.Style(root)
    style.theme_use('clam')
    root.configure(background=BG)
    style.configure('.',font=('Segoe UI',10),background=SURFACE,foreground=TEXT)
    style.configure('TFrame',background=SURFACE)
    style.configure('Surface.TFrame',background=BG)
    style.configure('TLabel',background=SURFACE,foreground=TEXT)
    style.configure('Muted.TLabel',foreground=MUTED)
    style.configure('Section.TLabel',font=('Segoe UI',9,'bold'),foreground=MUTED)
    style.configure('Title.TLabel',font=('Segoe UI',17,'bold'),foreground=TEXT)
    style.configure('TButton',padding=(10,6),background=SURFACE,bordercolor=BORDER,
                    lightcolor=SURFACE,darkcolor=SURFACE,relief='flat',focuscolor=BORDER)
    style.map('TButton',background=[('active','#edf3ff'),('pressed','#dbeafe')],foreground=[('disabled','#9ba8b9')])
    style.configure('Primary.TButton',background=BLUE,foreground='white',bordercolor=BLUE,font=('Segoe UI',10,'bold'))
    style.map('Primary.TButton',background=[('active','#1d4ed8'),('pressed','#1e40af'),('disabled','#b6c7e4')],foreground=[('disabled','#f8fafc')])
    style.configure('Danger.TButton',foreground='#b42338')
    style.configure('TMenubutton',padding=(12,7),background=SURFACE,bordercolor=BORDER,relief='flat')
    style.configure('TEntry',fieldbackground=SURFACE,bordercolor=BORDER,padding=5)
    style.map('TEntry',bordercolor=[('focus',BLUE)])
    style.configure('TCombobox',fieldbackground=SURFACE,bordercolor=BORDER,padding=4,arrowsize=12)
    style.map('TCombobox',fieldbackground=[('readonly',SURFACE)],selectbackground=[('readonly',SURFACE)],selectforeground=[('readonly',TEXT)])
    style.configure('TRadiobutton',padding=(4,4),background=SURFACE)
    style.configure('TCheckbutton',padding=(2,3),background=SURFACE)
    style.layout('Tool.TRadiobutton',[('Radiobutton.padding',{'sticky':'nswe','children':[('Radiobutton.label',{'sticky':'nswe'})]})])
    style.configure('Tool.TRadiobutton',padding=(8,7),font=('Segoe UI',9),background=SURFACE)
    style.map('Tool.TRadiobutton',background=[('selected','#dbeafe'),('active','#eff6ff')],foreground=[('selected','#1d4ed8')])
    style.configure('Horizontal.TProgressbar',background=BLUE,troughcolor='#e8eef8',borderwidth=0,thickness=5)
    style.configure('Treeview',rowheight=37,fieldbackground=SURFACE,background=SURFACE,foreground=TEXT,borderwidth=0)
    style.map('Treeview',background=[('selected','#e7efff')],foreground=[('selected','#1d4ed8')])
    style.configure('Treeview.Heading',font=('Segoe UI',9,'bold'),foreground=MUTED,background=BG,padding=(8,9),relief='flat')
    style.configure('TPanedwindow',background=BORDER)
    style.configure('Pending.TLabel',foreground='#a5630a',font=('Segoe UI',10,'bold'))
    style.configure('Accepted.TLabel',foreground='#087f5b',font=('Segoe UI',10,'bold'))
    style.configure('Changes.TLabel',foreground='#b42338',font=('Segoe UI',10,'bold'))
    style.configure('Ambiguous.TLabel',foreground='#7950b3',font=('Segoe UI',10,'bold'))
    return style
