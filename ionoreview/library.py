"""Searchable local catalog of portable annotation packs."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .data import read_json, safe_child


def entries(root):
    root=Path(root).resolve()
    data=read_json(root/'catalog.json')
    if data.get('schema')!='ionoreview-library/1':
        raise ValueError('Неподдерживаемый каталог')
    result=[]
    for row in data['datasets']:
        pack=safe_child(root,row['path'])
        if not (pack/'manifest.json').is_file():
            continue
        result.append(dict(row,full_path=pack))
    return result


def choose(root, library):
    rows=entries(library)
    from .theme import apply_theme
    apply_theme(root)
    window=tk.Toplevel(root)
    window.title('Каталог ионограмм')
    window.geometry(f"{min(1100,max(700,root.winfo_screenwidth()-80))}x{min(700,max(450,root.winfo_screenheight()-100))}")
    window.minsize(700,450)
    if root.state()!='withdrawn':window.transient(root)
    frame=ttk.Frame(window,padding=22)
    frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='Библиотека ионограмм',style='Title.TLabel').pack(anchor='w')
    ttk.Label(frame,text=f"{len(rows)} наборов  ·  {sum(r['count'] for r in rows):,} изображений",style='Muted.TLabel').pack(anchor='w',pady=(4,16))
    query=tk.StringVar()
    ttk.Label(frame,text='Поиск по станции, типу или дате',style='Section.TLabel').pack(anchor='w',pady=(0,5))
    entry=ttk.Entry(frame,textvariable=query)
    entry.pack(fill='x')
    pane=ttk.Frame(frame)
    pane.pack(fill='both',expand=True,pady=16)
    scrollbar=ttk.Scrollbar(pane,orient='vertical')
    scrollbar.pack(side='right',fill='y')
    listing=ttk.Treeview(pane,columns=('title','count','stations'),show='headings',selectmode='browse',yscrollcommand=scrollbar.set)
    for key,title,width in [('title','Набор',480),('count','Изображений',100),('stations','Станции',320)]:
        listing.heading(key,text=title);listing.column(key,width=width,anchor='w' if key!='count' else 'center',stretch=key!='count')
    listing.tag_configure('alternate',background='#f8fafd')
    listing.pack(fill='both',expand=True)
    scrollbar.configure(command=listing.yview)
    path=ttk.Label(frame,text='',wraplength=1000,style='Muted.TLabel',font=('Segoe UI',9))
    path.pack(anchor='w',pady=5)
    stations=ttk.Label(frame,text='',wraplength=1000,style='Muted.TLabel')
    stations.pack(anchor='w',pady=5)
    selected=[]
    filtered=[]
    def update(*unused):
        filtered.clear();listing.delete(*listing.get_children())
        term=query.get().casefold().strip()
        for row in rows:
            text=row['title']+' '+' '.join(row.get('stations',[]))
            if term and term not in text.casefold():continue
            filtered.append(row)
            index=len(filtered)-1
            listing.insert('','end',iid=str(index),values=(row['title'],row['count'],', '.join(row.get('stations',[]))),tags=('alternate',) if index%2 else ())
        if filtered:listing.selection_set('0')
        open_button.configure(state='normal' if filtered else 'disabled')
        selection()
    def selection(event=None):
        indices=listing.selection()
        path.configure(text=str(filtered[int(indices[0])]['full_path']) if indices else 'По запросу ничего не найдено')
        stations.configure(text='Станции: '+', '.join(filtered[int(indices[0])].get('stations',[])) if indices else '')
    def open_pack(event=None):
        indices=listing.selection()
        if indices:
            selected.append(filtered[int(indices[0])]['full_path'])
            window.destroy()
    def open_folder():
        from .folders import resolve_pack_folder, require_image_files, import_image_folder, unique_folder
        folder = filedialog.askdirectory(parent=window, initialdir=str(library),
                                         title='Выберите другой набор или папку изображений')
        if not folder:
            return
        try:
            destination = resolve_pack_folder(folder)
            if destination is None:
                require_image_files(folder)
                parent = filedialog.askdirectory(parent=window, title='Где создать рабочую папку с PNG и разметкой?')
                if not parent:
                    return
                destination = import_image_folder(folder, unique_folder(parent, 'images'))
            from .data import ReviewStore
            ReviewStore(destination)
            selected.append(destination)
            window.destroy()
        except Exception as exc:
            messagebox.showerror('Не удалось открыть папку', str(exc), parent=window)
    listing.bind('<<TreeviewSelect>>',selection)
    listing.bind('<Double-Button-1>',open_pack)
    listing.bind('<Return>',open_pack)
    open_button=ttk.Button(frame,text='Открыть набор',command=open_pack,style='Primary.TButton')
    open_button.pack(side='left',pady=(12,0))
    ttk.Button(frame,text='Открыть другую папку…',command=open_folder).pack(side='left',padx=12,pady=(12,0))
    ttk.Button(frame,text='Отмена',command=window.destroy).pack(side='right')
    query.trace_add('write',update)
    update();entry.focus_set()
    window.grab_set()
    root.wait_window(window)
    return selected[0] if selected else None
