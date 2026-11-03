"""Searchable local catalog of portable annotation packs."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk

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
    window=tk.Toplevel(root)
    window.title('Каталог ионограмм')
    window.geometry('1000x640')
    window.minsize(700,450)
    if root.state()!='withdrawn':window.transient(root)
    frame=ttk.Frame(window,padding=12)
    frame.pack(fill='both',expand=True)
    ttk.Label(frame,text=f"Наборов: {len(rows)} · ионограмм: {sum(r['count'] for r in rows)}").pack(anchor='w')
    query=tk.StringVar()
    ttk.Label(frame,text='Поиск по станции, типу или дате').pack(anchor='w',pady=(10,3))
    entry=ttk.Entry(frame,textvariable=query)
    entry.pack(fill='x')
    pane=ttk.Frame(frame)
    pane.pack(fill='both',expand=True,pady=10)
    scrollbar=ttk.Scrollbar(pane,orient='vertical')
    scrollbar.pack(side='right',fill='y')
    listing=tk.Listbox(pane,exportselection=False,font=('Segoe UI',11),yscrollcommand=scrollbar.set)
    listing.pack(fill='both',expand=True)
    scrollbar.configure(command=listing.yview)
    path=ttk.Label(frame,text='',wraplength=930)
    path.pack(anchor='w',pady=5)
    stations=ttk.Label(frame,text='',wraplength=930)
    stations.pack(anchor='w',pady=5)
    selected=[]
    filtered=[]
    def update(*unused):
        filtered.clear();listing.delete(0,'end')
        term=query.get().casefold().strip()
        for row in rows:
            text=row['title']+' '+' '.join(row.get('stations',[]))
            if term and term not in text.casefold():continue
            filtered.append(row)
            listing.insert('end',f"{row['title']}   ({row['count']} шт.)")
        if filtered:listing.selection_set(0)
        selection()
    def selection(event=None):
        indices=listing.curselection()
        path.configure(text=str(filtered[indices[0]]['full_path']) if indices else '')
        stations.configure(text='Станции: '+', '.join(filtered[indices[0]].get('stations',[])) if indices else '')
    def open_pack(event=None):
        indices=listing.curselection()
        if indices:
            selected.append(filtered[indices[0]]['full_path'])
            window.destroy()
    listing.bind('<<ListboxSelect>>',selection)
    listing.bind('<Double-Button-1>',open_pack)
    listing.bind('<Return>',open_pack)
    ttk.Button(frame,text='Открыть набор',command=open_pack).pack(side='left')
    ttk.Button(frame,text='Отмена',command=window.destroy).pack(side='right')
    query.trace_add('write',update)
    update();entry.focus_set()
    window.grab_set()
    root.wait_window(window)
    return selected[0] if selected else None
