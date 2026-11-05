"""Small native desktop reviewer; all state stays in the selected local pack."""
from __future__ import annotations

import copy
import math
import os
import queue
import threading
import uuid
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import numpy as np
from PIL import Image, ImageDraw, ImageTk
from matplotlib import colormaps

from . import __version__
from .data import LABELS, ReviewStore, atomic_json, digest, read_json, safe_child
from .help import HELP_TEXT
from .geometry import contains, intersects_rect
from .theme import apply_theme,SURFACE,TEXT,MUTED,BORDER

COLORS = {"Signal": "#47e1ae", "1E": "#ffd166", "1F": "#55c7ff",
          "2F": "#f5a1fa", "3F": "#b9a4ff", "E": "#ffeaa0", "Es": "#ffa965",
          "Interference": "#ff807c"}
STATUS = {"pending": "Ожидает", "accepted": "Принято", "changes": "Исправить", "ambiguous": "Неоднозначно"}
RANGE_PRESETS = {
    "1000–5000": (1000, 5000), "1500–2000": (1500, 2000),
    "2000–2500": (2000, 2500), "2500–3000": (2500, 3000),
    "2700–3100": (2700, 3100), "3000–3500": (3000, 3500),
    "3500–4000": (3500, 4000), "4500–5000": (4500, 5000),
}
CLUSTER_COLORS = [(255,163,72), (86,223,255), (231,139,255), (255,225,85),
                  (105,240,157), (255,125,155)]


class Reviewer:
    @property
    def selected(self):
        return self._selected

    @selected.setter
    def selected(self, value):
        self._selected = value
        self.selection = set() if value is None else {value}
        self.selected_candidates = set()

    def __init__(self, root, folder):
        self.root = root
        self.store = ReviewStore(folder)
        self.index = 0
        self.item = None
        self.document = None
        self.dirty = False
        self.loading = False
        self.vertices = []
        self.undo_stack = []
        self.selected = None
        self.drag = None
        self.move_drag = None
        self.pan_start = None
        self.region_start = None
        self.region_end = None
        self.selection_box = None
        self.selection_additive = False
        self.view = None
        self.db = self.freq = self.ranges = None
        self.photo = None
        self.draw_job = None
        self.help_window = None
        self.cluster_window = None
        self.cluster_result = None
        self.cluster_generation = 0
        self.cluster_busy = False
        self.root.title(f"ИоноРазметка v{__version__} — экспертная приёмка")
        width=min(1520,max(1020,self.root.winfo_screenwidth()-100))
        height=min(1000,max(720,self.root.winfo_screenheight()-100))
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(1020,720)
        apply_theme(root)
        self.reviewer = tk.StringVar()
        settings = self.store.root / "settings.json"
        preferences = {}
        if settings.exists():
            preferences = read_json(settings)
            self.reviewer.set(preferences.get("reviewer", ""))
        self.source_path = tk.StringVar()
        self.image_path = tk.StringVar()
        self.result_path = tk.StringVar()
        self.export_path = tk.StringVar(value=preferences.get("last_export", "Ещё не выполнялся"))
        self.tool = tk.StringVar(value="select")
        self.label = tk.StringVar(value="Signal")
        self.visible = tk.BooleanVar(value=True)
        self.no_signal = tk.BooleanVar(value=False)
        self.move_group = tk.BooleanVar(value=False)
        self.opacity = tk.DoubleVar(value=0.28)
        self.low = tk.DoubleVar(value=25)
        self.high = tk.DoubleVar(value=60)
        self.show_proposal = tk.BooleanVar(value=False)
        self.range_low = tk.StringVar(value="1000")
        self.range_high = tk.StringVar(value="5000")
        self.range_preset = tk.StringVar(value="Весь кадр")
        self.path_details=tk.BooleanVar(value=False)
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Control-s>", lambda e: self.save())
        self.root.bind("<Control-z>", self.undo_shortcut)
        self.root.bind("<Control-Return>", lambda e: self.decide("accepted"))
        self.root.bind("<Control-o>",lambda e:self.open_folder())
        self.root.bind("<Escape>", lambda e: self.cancel_polygon())
        self.root.bind("<Return>", self.enter)
        self.canvas.bind("<Delete>", lambda e: self.delete_shape())
        self.canvas.bind("<BackSpace>", self.remove_last_point)
        initial = next((i for i, item in enumerate(self.store.items)
                        if item['id'] == preferences.get('last_case')), None)
        if initial is None:
            initial = next((i for i, item in enumerate(self.store.items)
                            if self.store.load(item)['review']['status'] == 'pending'), 0)
        self.load(initial)

    def _build(self):
        top = ttk.Frame(self.root, padding=(18, 12))
        top.pack(fill="x")
        ttk.Label(top, text="ИоноРазметка", style="Title.TLabel").pack(side="left")
        self.progress = ttk.Label(top, text="",style='Muted.TLabel')
        self.progress.pack(side="left", padx=(22,10))
        self.overall_progress=ttk.Progressbar(top,length=110,maximum=100)
        self.overall_progress.pack(side='left')
        ttk.Button(top,text='Правила',command=self.policy).pack(side='right')
        file_button=ttk.Menubutton(top,text='Файл ▾')
        menu=tk.Menu(file_button,tearoff=False,font=('Segoe UI',10))
        menu.add_command(label='Открыть папку…',accelerator='Ctrl+O',command=self.open_folder)
        menu.add_command(label='Каталог…',command=self.open_library)
        menu.add_separator()
        menu.add_command(label='Сохранить набор как…',command=self.save_pack_as)
        menu.add_command(label='Импорт разметки LabelMe…',command=self.import_candidate,
                         state='disabled' if self.store.manifest.get('assistance_disabled') else 'normal')
        menu.add_command(label='Экспорт принятых…',command=self.export)
        file_button.configure(menu=menu);file_button.pack(side='right',padx=8)
        ttk.Button(top,text='Каталог…',command=self.open_library).pack(side='right',padx=3)
        ttk.Button(top,text='Открыть папку…',command=self.open_folder).pack(side='right',padx=3)
        ttk.Separator(self.root).pack(fill='x')
        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True)
        self.left_shell = ttk.Frame(body, width=310)
        body.add(self.left_shell, weight=0)
        actions = ttk.Frame(self.left_shell, padding=8)
        actions.pack(side="bottom", fill="x")
        left_scroll = ttk.Scrollbar(self.left_shell, orient="vertical")
        left_scroll.pack(side="right", fill="y")
        self.left_canvas = tk.Canvas(self.left_shell, width=300, bg=SURFACE,
                                     highlightthickness=0, yscrollcommand=left_scroll.set)
        self.left_canvas.pack(fill="both", expand=True)
        left_scroll.config(command=self.left_canvas.yview)
        self.left = ttk.Frame(self.left_canvas, padding=8)
        left_window = self.left_canvas.create_window((0, 0), window=self.left, anchor="nw")
        self.left.bind("<Configure>", lambda e: self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all")))
        self.left_canvas.bind("<Configure>", lambda e: self.left_canvas.itemconfigure(left_window, width=e.width))
        def scroll_form(event):
            # Tk sibling names may be '.!frame' and '.!frame2': a raw
            # startswith test incorrectly treats the graph as the sidebar.
            widget = str(event.widget)
            sidebar = str(self.left_shell)
            if widget == sidebar or widget.startswith(sidebar + "."):
                if isinstance(event.widget, (tk.Listbox, tk.Text)):
                    return "break"  # Their class binding already scrolls them.
                bounds = self.left_canvas.bbox("all")
                if bounds and bounds[3] - bounds[1] > self.left_canvas.winfo_height():
                    self.left_canvas.yview_scroll(-int(event.delta / 120), "units")
                else:
                    self.left_canvas.yview_moveto(0)
                return "break"
        self.root.bind("<MouseWheel>", scroll_form, add="+")
        ttk.Label(self.left, text="ИОНОГРАММЫ",style='Section.TLabel').pack(anchor="w")
        self.cases = tk.Listbox(self.left, width=31, height=5, exportselection=False,
                                font=("Segoe UI", 10),bg=SURFACE,fg=TEXT,borderwidth=0,highlightthickness=1,
                                highlightbackground=BORDER,selectbackground='#e7efff',selectforeground='#1d4ed8',activestyle="none")
        self.cases.pack(fill="x", pady=(5, 10))
        self.cases.bind("<<ListboxSelect>>", self.choose_case)
        ttk.Label(self.left, text="Эксперт").pack(anchor="w")
        ttk.Entry(self.left, textvariable=self.reviewer).pack(fill="x", pady=(3, 8))
        self.case_info = ttk.Label(self.left, wraplength=270, justify="left",style='Muted.TLabel',font=('Segoe UI',9))
        self.case_info.pack(fill="x", pady=5)
        self.current_status = ttk.Label(self.left, font=("Segoe UI", 11, "bold"))
        self.current_status.pack(anchor="w", pady=7)
        ttk.Label(self.left, text="ОБЪЕКТЫ",style='Section.TLabel').pack(anchor="w")
        self.objects = tk.Listbox(self.left, height=4, exportselection=False, selectmode="extended",
                                  bg=SURFACE,fg=TEXT,borderwidth=0,highlightthickness=1,highlightbackground=BORDER,
                                  selectbackground='#e7efff',selectforeground='#1d4ed8',font=("Segoe UI", 10))
        self.objects.pack(fill="x", pady=4)
        self.objects.bind("<<ListboxSelect>>", self.choose_object)
        row = ttk.Frame(self.left)
        row.pack(fill="x", pady=3)
        ttk.Combobox(row, textvariable=self.label, values=LABELS, state="readonly", width=13).pack(side="left")
        ttk.Button(row, text="Сменить класс", command=self.relabel).pack(side="right")
        row = ttk.Frame(self.left)
        row.pack(fill="x", pady=3)
        ttk.Button(row, text="Удалить", command=self.delete_shape,style='Danger.TButton').pack(side="left")
        ttk.Button(row, text="Группа…", command=self.group).pack(side="left", padx=4)
        ttk.Button(row, text="Отмена", command=self.undo).pack(side="right")
        ttk.Checkbutton(self.left, text="При переносе двигать всю группу", variable=self.move_group).pack(anchor="w", pady=4)
        ttk.Checkbutton(self.left, text="Полезный сигнал отсутствует", variable=self.no_signal,
                        command=self.changed).pack(anchor="w", pady=8)
        ttk.Label(self.left, text="Замечание эксперта").pack(anchor="w")
        self.note = tk.Text(self.left, width=28, height=3, wrap="word", font=("Segoe UI", 10), undo=True)
        self.note.configure(bg=SURFACE,fg=TEXT,relief='flat',highlightthickness=1,highlightbackground=BORDER,
                            highlightcolor='#2563eb',padx=7,pady=6)
        self.note.pack(fill="x", pady=4)
        self.note.bind("<<Modified>>", self.note_modified)
        for text, status in (("Принять и далее   Ctrl+Enter", "accepted"),
                             ("На исправление и далее", "changes"),
                             ("Неоднозначно и далее", "ambiguous")):
            ttk.Button(actions, text=text,style='Primary.TButton' if status=='accepted' else 'TButton',
                       command=lambda s=status: self.decide(s)).pack(fill="x", pady=3)
        self.import_button=ttk.Button(actions, text="Импорт разметки LabelMe…", command=self.import_candidate,
            state='disabled' if self.store.manifest.get('assistance_disabled') else 'normal')
        self.import_button.pack(fill="x", pady=(9, 0))

        right = ttk.Frame(body)
        body.add(right, weight=1)
        toolbar = ttk.Frame(right, padding=(8, 6))
        toolbar.pack(fill="x")
        ttk.Radiobutton(toolbar, text="Выбор / вершины", variable=self.tool, value="select",style='Tool.TRadiobutton').pack(side="left")
        ttk.Radiobutton(toolbar, text="Полигон", variable=self.tool, value="draw",style='Tool.TRadiobutton').pack(side="left", padx=3)
        ttk.Radiobutton(toolbar, text="Область", variable=self.tool, value="region",style='Tool.TRadiobutton').pack(side="left")
        ttk.Radiobutton(toolbar, text="Выделение", variable=self.tool, value="multi",style='Tool.TRadiobutton').pack(side="left", padx=3)
        ttk.Button(toolbar, text="Замкнуть", command=self.finish_polygon).pack(side="left")
        self.undo_point_button = ttk.Button(toolbar, text="Убрать точку",
                                             command=self.remove_last_point, state="disabled")
        self.undo_point_button.pack(side="left", padx=5)
        ttk.Checkbutton(toolbar, text="Маски", variable=self.visible, command=self.redraw).pack(side="right")
        navigation = ttk.Frame(right, padding=(8, 0, 8, 4))
        navigation.pack(fill="x")
        ttk.Button(navigation, text="Весь кадр", command=self.fit).pack(side="left")
        ttk.Button(navigation, text="Вокруг масок", command=self.focus_masks).pack(side="left", padx=4)
        ttk.Button(navigation, text="+", width=3, command=lambda: self.zoom_center(.8)).pack(side="left")
        ttk.Button(navigation, text="−", width=3, command=lambda: self.zoom_center(1.25)).pack(side="left", padx=4)
        ttk.Label(navigation, text="Shift + колесо: только дальность").pack(side="left", padx=8)
        ranges = ttk.Frame(right, padding=(8, 0, 8, 6))
        ranges.pack(fill="x")
        self.range_caption = ttk.Label(ranges, text="Дальность, км:")
        self.range_caption.pack(side="left")
        low_entry = ttk.Entry(ranges, textvariable=self.range_low, width=8)
        low_entry.pack(side="left", padx=(5, 2))
        ttk.Label(ranges, text="—").pack(side="left")
        high_entry = ttk.Entry(ranges, textvariable=self.range_high, width=8)
        high_entry.pack(side="left", padx=2)
        for entry in (low_entry, high_entry):
            entry.bind("<Return>", self.apply_range)
        range_button = ttk.Button(ranges, text="Показать", command=self.apply_range)
        range_button.pack(side="left", padx=5)
        presets = ttk.Combobox(ranges, textvariable=self.range_preset,
                               values=list(RANGE_PRESETS), state="readonly", width=14)
        presets.pack(side="left", padx=5)
        presets.bind("<<ComboboxSelected>>", self.preset_range)
        self.range_controls = (low_entry, high_entry, range_button, presets)
        auto = ttk.Frame(right, padding=(8, 0, 8, 5))
        auto.pack(fill="x")
        self.cluster_button = ttk.Button(auto, text="Авторазметка…", command=self.open_cluster_dialog,style='Primary.TButton')
        self.cluster_button.pack(side="left")
        self.add_clusters_button = ttk.Button(auto, text="Добавить кластеры", command=self.add_clusters, state="disabled")
        self.add_clusters_button.pack(side="left", padx=4)
        ttk.Button(auto, text="Скрыть кандидаты", command=lambda: self.clear_clusters(invalidate=True)).pack(side="left")
        self.cluster_summary = ttk.Label(auto, text="Кандидатов нет")
        self.cluster_summary.pack(side="left", padx=8)
        self.canvas = tk.Canvas(right, width=1, height=1, bg="#17212c", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.schedule_draw())
        self.canvas.bind("<Button-1>", self.click)
        self.canvas.bind("<B1-Motion>", self.motion)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<Motion>", self.hover)
        self.canvas.bind("<Button-3>", self.right_click)
        self.canvas.bind("<Control-a>", self.select_all)
        self.canvas.bind("<MouseWheel>", self.zoom)
        self.canvas.bind("<Shift-MouseWheel>", self.zoom)
        self.canvas.bind("<Button-2>", self.pan_begin)
        self.canvas.bind("<B2-Motion>", self.pan)
        self.label_menu = ttk.Frame(self.canvas, padding=5, relief="solid", borderwidth=1)
        self.label_menu_title = ttk.Label(self.label_menu, text="")
        self.label_menu_title.grid(row=0, column=0, columnspan=4, sticky="w")
        for index, label in enumerate(LABELS):
            ttk.Button(self.label_menu, text=label, width=9,
                       command=lambda value=label: self.apply_label(value)).grid(
                           row=1+index//4, column=index%4, padx=2, pady=2)
        ttk.Button(self.label_menu, text="Вся группа", command=self.expand_group_selection).grid(row=3,column=0,columnspan=2,sticky="ew")
        ttk.Button(self.label_menu, text="Снять выделение", command=self.deselect).grid(row=3,column=2,columnspan=2,sticky="ew")
        contrasts = ttk.Frame(right, padding=(8, 4))
        contrasts.pack(fill="x")
        ttk.Label(contrasts, text="Шкала дБ:").pack(side="left")
        ttk.Scale(contrasts, from_=0, to=45, variable=self.low, length=110, command=lambda v: self.schedule_draw()).pack(side="left")
        ttk.Scale(contrasts, from_=35, to=85, variable=self.high, length=110, command=lambda v: self.schedule_draw()).pack(side="left")
        ttk.Label(contrasts, text="Прозрачность:").pack(side="left", padx=(12, 0))
        ttk.Scale(contrasts, from_=0, to=.65, variable=self.opacity, length=90, command=lambda v: self.schedule_draw()).pack(side="left")
        self.cursor_text = ttk.Label(contrasts, text="", width=30, anchor="e")
        self.cursor_text.pack(side="right")
        self.help_text = ttk.Label(right, text="Колесо — масштаб  ·  Средняя кнопка — сдвиг  ·  Ctrl+Z — отмена  ·  Backspace — убрать точку  ·  Esc — отменить полигон",style='Muted.TLabel',font=('Segoe UI',9),padding=(8,4))
        self.help_text.pack(fill="x")
        bottom = ttk.Frame(self.root, padding=8)
        bottom.pack(side="bottom", fill="x", before=body)
        ttk.Button(bottom, text="← Назад", command=lambda: self.navigate(-1)).pack(side="left")
        ttk.Button(bottom, text="Далее →", command=lambda: self.navigate(1)).pack(side="left", padx=5)
        ttk.Button(bottom, text="Сохранить   Ctrl+S", command=self.save).pack(side="left")
        ttk.Button(bottom,text='Все пути ▾',command=self.toggle_paths).pack(side='right')
        self.feedback = ttk.Label(bottom, text="", width=35,style='Muted.TLabel')
        self.feedback.pack(side="left", padx=14, fill="x", expand=True)
        paths = ttk.Frame(self.root, padding=(8, 3))
        paths.pack(side="bottom", fill="x", before=body)
        paths.columnconfigure(1, weight=1)
        self.extra_path_widgets=[]
        for row, (label, variable) in enumerate((
            ("PNG для разметки", self.image_path), ("Результат JSON", self.result_path),
            ("Исходник", self.source_path), ("Последний экспорт", self.export_path)
        )):
            widgets=[ttk.Label(paths,text=label,width=18,style='Muted.TLabel',font=('Segoe UI',9)),
                ttk.Entry(paths,textvariable=variable,state='readonly',font=('Segoe UI',9)),
                ttk.Button(paths,text='Копировать',padding=(5,1),command=lambda value=variable:self.copy_path(value)),
                ttk.Button(paths,text='Открыть папку',padding=(5,1),command=lambda value=variable:self.open_path_folder(value))]
            for column,widget in enumerate(widgets):
                widget.grid(row=row,column=column,sticky='ew' if column==1 else 'w',padx=3,pady=2)
                if row>=2:widget.grid_remove();self.extra_path_widgets.append(widget)
        self.refresh_cases()

    def toggle_paths(self):
        self.path_details.set(not self.path_details.get())
        for widget in self.extra_path_widgets:
            if self.path_details.get():widget.grid()
            else:widget.grid_remove()

    def policy(self):
        if self.help_window is not None and self.help_window.winfo_exists():
            self.help_window.lift()
            return
        window = tk.Toplevel(self.root)
        self.help_window = window
        window.title("Правила и справка — ИоноРазметка")
        self.place_window(window, 900, 740)
        window.minsize(650, 450)
        window.transient(self.root)
        ttk.Button(window, text="Закрыть справку", command=window.destroy).pack(side="bottom", pady=8)
        scroll = ttk.Scrollbar(window, orient="vertical")
        scroll.pack(side="right", fill="y")
        text = tk.Text(window, wrap="word", font=("Segoe UI", 11), padx=16, pady=12,
                       yscrollcommand=scroll.set)
        text.pack(fill="both", expand=True)
        scroll.config(command=text.yview)
        text.insert("1.0", HELP_TEXT + "\n\nПРАВИЛА РАЗМЕТКИ ТЕКУЩЕГО НАБОРА\n\n" +
                    self.store.manifest.get("annotation_policy", ""))
        text.configure(state="disabled")

    def place_window(self, window, width, height):
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - width) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - height) // 2)
        window.geometry(f"{width}x{height}{x:+d}{y:+d}")

    def open_cluster_dialog(self):
        if self.store.manifest.get('assistance_disabled'):
            self.feedback.configure(text='Независимая разметка: автоматические подсказки отключены')
            return
        if self.cluster_window is not None and self.cluster_window.winfo_exists():
            self.cluster_window.lift()
            return
        from .clustering import ClusterParams
        pixels = self.db is None
        defaults = (ClusterParams(threshold_db=100, frequency_gap_mhz=3, range_gap_km=3,
                    min_span_mhz=5, coordinate_units="pixels") if pixels else ClusterParams())
        window = tk.Toplevel(self.root)
        self.cluster_window = window
        window.title("Авторазметка — кластеризация")
        window.transient(self.root)
        self.place_window(window, 620, 550)
        frame = ttk.Frame(window, padding=15)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Поиск кластеров сигнала", style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        method = tk.StringVar(value="Авто (DBSCAN)")
        methods = ttk.Combobox(frame, textvariable=method, values=["Авто (DBSCAN)", "Вручную (K-means)"], state="readonly", width=25)
        methods.grid(row=1, column=0, sticky="w", pady=5)
        manual = ttk.Frame(frame)
        manual.grid(row=1, column=1, sticky="w", padx=15)
        ttk.Label(manual, text="Число:").pack(side="left")
        k = tk.StringVar(value="2")
        k_entry = ttk.Entry(manual, textvariable=k, width=5, state="disabled")
        k_entry.pack(side="left", padx=4)
        methods.bind("<<ComboboxSelected>>", lambda e: k_entry.configure(state="normal" if method.get().startswith("Вручную") else "disabled"))
        fields = {}
        labels = (("Порог яркости, 0–255" if pixels else "Порог, дБ", "threshold_db"),
                  ("Связь по x, пиксели" if pixels else "Связь по частоте, МГц", "frequency_gap_mhz"),
                  ("Связь по y, пиксели" if pixels else "Связь по дальности, км", "range_gap_km"),
                  ("Соседей DBSCAN для плотной точки", "min_samples"),
                  ("Минимум точек в кластере", "min_cluster_points"),
                  ("Минимальная ширина, пиксели" if pixels else "Минимальная полоса, МГц", "min_span_mhz"))
        for row, (label, key) in enumerate(labels, 2):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
            variable = tk.StringVar(value=str(getattr(defaults, key)))
            fields[key] = variable
            ttk.Entry(frame, textvariable=variable, width=12).grid(row=row, column=1, sticky="w", padx=15)
        visible_only = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, text="Только видимая область", variable=visible_only).grid(row=8, column=0, columnspan=2, sticky="w", pady=7)
        ttk.Label(frame, text="Кандидаты будут показаны оранжевым. Существующие маски сохраняются.\n"
                  "Метки 1F / 2F / E назначает пользователь после добавления.\n"
                  "Расчёт не зависит от ползунков цветовой шкалы." +
                  ("\nPNG без осей: сначала выделите область графика без подписей." if pixels else ""),
                  wraplength=570).grid(row=9, column=0, columnspan=2, sticky="w", pady=10)
        error = ttk.Label(frame, text="", wraplength=530)
        error.grid(row=10, column=0, columnspan=2, sticky="w")
        def start():
            try:
                values = {key: (int(var.get()) if key in {"min_samples", "min_cluster_points"}
                               else float(var.get().replace(",", "."))) for key, var in fields.items()}
                values.update(method="K-means" if method.get().startswith("Вручную") else "DBSCAN",
                              n_clusters=int(k.get()) if method.get().startswith("Вручную") else 2,
                              coordinate_units="pixels" if pixels else "physical")
                params = ClusterParams(**values)
                params.validate()
                self.start_clustering(params, visible_only.get())
                error.config(text="Расчёт запущен. Кандидаты появятся на графике.")
            except (ValueError, ImportError) as exc:
                error.config(text=str(exc))
        ttk.Button(frame, text="Найти кластеры", command=start).grid(row=11, column=0, sticky="w", pady=10)
        ttk.Button(frame, text="Закрыть параметры", command=window.destroy).grid(row=11, column=1, sticky="w", padx=15)

    def start_clustering(self, params, visible_only=True):
        if self.cluster_busy:
            raise ValueError("Дождитесь текущего расчёта")
        if self.vertices:
            raise ValueError("Сначала замкните полигон или отмените незавершённые точки")
        params.validate()
        if (self.db is None) != (params.coordinate_units == "pixels"):
            raise ValueError("Единицы параметров не соответствуют текущему изображению")
        from .clustering import cluster_ionogram, image_features
        view = tuple(self.view) if visible_only else (0, 0, self.item["width"] - 1, self.item["height"] - 1)
        self.cluster_generation += 1
        generation, ident = self.cluster_generation, self.item["id"]
        if self.db is None:
            db = image_features(self.original_image)
            freq, ranges = np.arange(db.shape[1], dtype=float), np.arange(db.shape[0], dtype=float)[::-1]
        else:
            db, freq, ranges = self.db.copy(), self.freq.copy(), self.ranges.copy()
        result_queue = queue.Queue()
        self.clear_clusters()
        self.cluster_busy = True
        self.cluster_button.configure(state="disabled")
        self.cluster_summary.configure(text=f"{params.method}: расчёт…")
        def worker():
            try:
                result_queue.put((True, cluster_ionogram(db, freq, ranges, view, params)))
            except Exception as exc:
                result_queue.put((False, str(exc)))
        threading.Thread(target=worker, daemon=True).start()
        def receive():
            try:
                ok, result = result_queue.get_nowait()
            except queue.Empty:
                self.root.after(80, receive)
                return
            self.cluster_busy = False
            self.cluster_button.configure(state="normal")
            if self.item["id"] != ident or self.cluster_generation != generation:
                self.cluster_summary.configure(text="Кандидаты отменены или кадр сменился")
                return
            if ok:
                self.show_clusters(result)
            else:
                self.cluster_summary.configure(text="Расчёт не выполнен")
                self.feedback.configure(text=result)
        self.root.after(80, receive)

    def show_clusters(self, result):
        self.selected_candidates.clear()
        run = uuid.uuid4().hex
        for shape in result.shapes:
            shape.setdefault("flags", {})["proposal_run"] = run
        self.cluster_result = result
        count = result.stats["clusters"]
        self.cluster_summary.configure(text=f"Кластеров: {count}; полигонов: {len(result.shapes)}")
        self.add_clusters_button.configure(state="normal" if result.shapes else "disabled")
        self.feedback.configure(text=f"{result.params['method']}: {result.stats['points']} точек, шум {result.stats['noise_points']}. Кандидаты ещё не разметка.")
        self.redraw()

    def clear_clusters(self, invalidate=False):
        if invalidate:
            self.cluster_generation += 1
        self.cluster_result = None
        self.selected_candidates.clear()
        self.hide_label_menu()
        self.add_clusters_button.configure(state="disabled")
        self.cluster_summary.configure(text="Кандидатов нет")
        self.redraw()

    def add_clusters(self):
        if self.store.manifest.get('assistance_disabled'):
            self.feedback.configure(text="В независимом тесте автоматические подсказки отключены")
            return
        if self.cluster_result is None or not self.cluster_result.shapes:
            return
        existing = {tuple(tuple(p) for p in s["points"]) for s in self.document["shapes"]}
        candidates = [copy.deepcopy(s) for s in self.cluster_result.shapes
                      if tuple(tuple(p) for p in s["points"]) not in existing]
        if not candidates:
            self.feedback.configure(text="Эти полигоны уже есть в разметке")
            self.clear_clusters()
            return
        self.snapshot()
        offset = max((s.get("group_id") or 0 for s in self.document["shapes"]
                      if isinstance(s.get("group_id"), int)), default=0)
        for shape in candidates:
            shape["group_id"] += offset
        self.document["shapes"].extend(candidates)
        self.document.setdefault("auto_proposals", []).append({"method": self.cluster_result.params["method"],
            "params": self.cluster_result.params, "scope": self.cluster_result.scope,
            "added_polygons": len(candidates)})
        self.no_signal.set(False)
        self.selected = len(self.document["shapes"]) - len(candidates)
        self.label.set("Signal")
        self.changed()
        self.clear_clusters()
        self.refresh_objects()
        self.feedback.configure(text=f"Добавлено полигонов: {len(candidates)}. Исправьте и назначьте классы; затем примите.")

    def copy_path(self, variable):
        self.root.clipboard_clear()
        self.root.clipboard_append(variable.get())
        self.feedback.config(text="Путь скопирован")

    def open_path_folder(self, variable):
        path = Path(variable.get())
        if not path.is_absolute():
            self.feedback.config(text="Папка ещё не задана")
            return
        folder = path if path.is_dir() else path.parent
        while not folder.exists() and folder != folder.parent:
            folder = folder.parent
        try:
            os.startfile(str(folder))
        except OSError as exc:
            self.feedback.config(text=f"Не удалось открыть папку: {exc}")

    def switch_pack(self, destination):
        if (self.dirty or self.vertices) and not self.save():
            return False
        store = ReviewStore(destination)
        self.store = store
        self.index, self.item, self.document = 0, None, None
        self.view = None
        self.cluster_generation += 1
        self.clear_clusters()
        if self.cluster_window is not None and self.cluster_window.winfo_exists():
            self.cluster_window.destroy()
        self.export_path.set("Ещё не выполнялся")
        settings = store.root / "settings.json"
        if settings.exists():
            self.export_path.set(read_json(settings).get("last_export", "Ещё не выполнялся"))
        self.load(0)
        self.refresh_cases()
        return True

    def open_folder(self):
        if (self.dirty or self.vertices) and not self.save():
            return
        folder = filedialog.askdirectory(parent=self.root, initialdir=str(self.store.root),
                                        title="Открыть набор, папку images/annotations или папку изображений")
        if not folder:
            return
        try:
            folder = Path(folder)
            if (folder/'catalog.json').is_file():
                self.open_library(folder)
                return
            from .folders import resolve_pack_folder, require_image_files, import_image_folder, unique_folder
            pack_folder = resolve_pack_folder(folder)
            if pack_folder is not None:
                self.switch_pack(pack_folder)
                return
            require_image_files(folder)
            parent = filedialog.askdirectory(parent=self.root, title="Где создать рабочую папку с PNG и разметкой?")
            if not parent:
                return
            self.root.configure(cursor="watch")
            self.root.update_idletasks()
            destination = import_image_folder(folder, unique_folder(parent, "images"))
            self.switch_pack(destination)
        except Exception as exc:
            messagebox.showerror("Не удалось открыть папку", str(exc))
        finally:
            self.root.configure(cursor="")

    def open_library(self, folder=None):
        if (self.dirty or self.vertices) and not self.save():
            return
        from .library import choose
        folder=Path(folder) if folder is not None else Path(__file__).resolve().parent.parent/'datasets'
        try:
            target=choose(self.root,folder)
            if target:self.switch_pack(target)
        except Exception as exc:
            messagebox.showerror('Не удалось открыть каталог',str(exc))

    def save_pack_as(self):
        if (self.dirty or self.vertices) and not self.save():
            return
        parent = filedialog.askdirectory(title="Где сохранить копию всего рабочего набора?")
        if not parent:
            return
        from .folders import copy_pack, unique_folder
        try:
            destination = copy_pack(self.store.root, unique_folder(parent, "copy"))
            self.switch_pack(destination)
        except Exception as exc:
            messagebox.showerror("Не удалось сохранить набор", str(exc))

    def save_settings(self):
        path = self.store.root / "settings.json"
        preferences = read_json(path) if path.exists() else {}
        preferences["reviewer"] = self.reviewer.get().strip()
        preferences["last_export"] = self.export_path.get()
        if self.item is not None:
            preferences["last_case"] = self.item["id"]
        atomic_json(path, preferences)

    def refresh_cases(self):
        self.loading = True
        self.cases.delete(0, "end")
        accepted = 0
        for item in self.store.items:
            status = self.store.load(item)["review"]["status"]
            accepted += status == "accepted"
            self.cases.insert("end", f"{item['id']}  ·  {STATUS[status]}")
        self.cases.selection_set(self.index)
        self.cases.see(self.index)
        self.progress.config(text=f"Принято {accepted} из {len(self.store.items)}")
        self.overall_progress.configure(value=100*accepted/max(1,len(self.store.items)))
        self.loading = False

    def collect(self):
        self.document["review"].update(reviewer=self.reviewer.get().strip(),
            note=self.note.get("1.0", "end-1c").strip(), no_signal=self.no_signal.get())

    def changed(self):
        if self.loading or self.document is None:
            return
        self.dirty = True
        self.document["review"]["status"] = "pending"
        self.current_status.config(text="Ожидает · есть изменения")
        self.feedback.config(text="Правки сохранятся при переходе или Ctrl+S")
        self.current_status.configure(style='Pending.TLabel')

    def note_modified(self, event=None):
        if self.note.edit_modified():
            self.changed()
            self.note.edit_modified(False)

    def snapshot(self, changes_document=True):
        self.undo_stack.append({"shapes": copy.deepcopy(self.document["shapes"]),
            "no_signal": self.no_signal.get(),
            "cluster_result": copy.deepcopy(self.cluster_result),
            "changes_document": changes_document,
            "auto_proposals": copy.deepcopy(self.document.get("auto_proposals"))})
        self.undo_stack = self.undo_stack[-40:]

    def undo_shortcut(self, event):
        if isinstance(event.widget, (tk.Text, tk.Entry, ttk.Entry)):
            return  # Text editing must never also undo a mask.
        self.undo()
        return "break"

    def save(self):
        if self.vertices:
            messagebox.showinfo("Незавершённый полигон", "Замкните полигон или нажмите Esc")
            return False
        try:
            self.collect()
            self.document = self.store.save(self.item, self.document)
            self.save_settings()
            self.dirty = False
            self.current_status.config(text=STATUS[self.document["review"]["status"]])
            self.refresh_cases()
            self.feedback.config(text="Сохранено на диск")
            return True
        except Exception as exc:
            messagebox.showerror("Не удалось сохранить", str(exc))
            return False

    def load(self, index):
        if self.document is not None and (self.dirty or self.vertices) and not self.save():
            return False
        item = self.store.items[index]
        try:
            image_path = safe_child(self.store.root, item["image"])
            if digest(image_path) != item["image_sha256"]:
                raise ValueError("Контрольная сумма изображения не совпадает")
            image = Image.open(image_path).convert("RGB")
            doc = self.store.load(item)
            db = freq = ranges = None
            if item.get("axes"):
                self.store.check_axes(item)
                with np.load(safe_child(self.store.root, item["axes"]), allow_pickle=False) as data:
                    db = data["db"].copy()
                    freq = data["freq_mhz"].copy()
                    ranges = data["range_km"].copy()
                if db.shape != (item["height"], item["width"]) or len(freq) != item["width"] or len(ranges) != item["height"]:
                    raise ValueError("Оси не совпадают с матрицей")
        except Exception as exc:
            messagebox.showerror("Не удалось открыть", str(exc))
            return False
        self.loading = True
        self.index, self.item, self.document = index, item, doc
        self.source_path.set(str(Path(item["source"]).resolve()))
        self.image_path.set(str(safe_child(self.store.root, item["image"])))
        self.result_path.set(str(self.store.path(item)))
        self.original_image, self.db, self.freq, self.ranges = image, db, freq, ranges
        for control in self.range_controls[:-1]:
            control.configure(state="normal" if ranges is not None else "disabled")
        self.range_controls[-1].configure(state="readonly" if ranges is not None else "disabled")
        self.range_caption.configure(text="Дальность, км:" if ranges is not None else "Окно: пиксели")
        if ranges is None:
            self.range_low.set("—")
            self.range_high.set("—")
        self.undo_stack, self.vertices, self.selected = [], [], None
        self.move_drag = None
        self.cluster_generation += 1
        self.clear_clusters()
        self.region_start = self.region_end = self.pan_start = None
        self.selection_box = None
        self.dirty = False
        self.no_signal.set(bool(doc["review"].get("no_signal")))
        self.note.delete("1.0", "end")
        self.note.insert("1.0", doc["review"].get("note", ""))
        self.note.edit_modified(False)
        proposal = doc.get("proposal", {}).get("author", "нет")
        self.case_info.config(text=f"{item['id']} · {item.get('split', 'unassigned')}\n"
            f"{item.get('tx', '')} → {item.get('rx', '')}\n{item.get('when', '')}\n"
            f"{item['width']} × {item['height']} пикселей\nПредразметка: {proposal}" +
            ("\nДальность относительная!" if item.get("range_is_relative") else "") +
            ("\nОсь дальности из настроек приёма" if item.get("range_is_configured") else ""))
        if item.get("source_kind") == "image":
            self.case_info.configure(text=f"{item['id']} · {item.get('split','unassigned')}\n{item.get('original_name', '')}\n"
                f"{item['width']} × {item['height']} пикселей\nЧисловых осей нет")
        self.current_status.config(text=STATUS[doc["review"]["status"]])
        styles={'pending':'Pending.TLabel','accepted':'Accepted.TLabel','changes':'Changes.TLabel','ambiguous':'Ambiguous.TLabel'}
        self.current_status.configure(style=styles[doc['review']['status']])
        self.cluster_button.configure(state='disabled' if self.store.manifest.get('assistance_disabled') else 'normal')
        if self.store.manifest.get('assistance_disabled'):
            self.cluster_summary.configure(text='Независимый тест: без автоматических подсказок')
        self.feedback.config(text="Исходник: " + Path(item["source"]).name)
        self.cases.selection_clear(0, "end")
        self.cases.selection_set(index)
        self.cases.see(index)
        self.loading = False
        self.refresh_objects()
        self.fit()
        return True

    def choose_case(self, event=None):
        if not self.loading and self.cases.curselection():
            self.load(self.cases.curselection()[0])

    def navigate(self, step):
        target = self.index + step
        if 0 <= target < len(self.store.items):
            self.load(target)

    def decide(self, status):
        old_status = self.document["review"]["status"]
        self.document["review"]["status"] = status
        if self.save():
            self.navigate(1)
        else:
            self.document["review"]["status"] = old_status

    def refresh_objects(self):
        self.selection.intersection_update(range(len(self.document["shapes"])))
        if self._selected not in self.selection:
            self._selected = min(self.selection) if self.selection else None
        self.objects.delete(0, "end")
        for i, shape in enumerate(self.document["shapes"]):
            group = shape.get("group_id")
            self.objects.insert("end", f"{i + 1}. {shape['label']} · {len(shape['points'])} вершин" +
                                (f" · гр. {group}" if group is not None else ""))
            self.objects.itemconfig(i, fg={"Signal": "#147353", "1E": "#856100",
                "1F": "#12628c", "2F": "#884385", "3F": "#65539a", "E": "#806519",
                "Es": "#a4551d", "Interference": "#ac3531"}[shape["label"]])
        for index in self.selection:
            self.objects.selection_set(index)
        self.redraw()

    def choose_object(self, event=None):
        self.set_selection(self.objects.curselection(), ())
        if self.selected is not None:
            self.label.set(self.document["shapes"][self.selected]["label"])
        self.redraw()
        self.show_label_menu()

    def relabel(self):
        self.apply_label(self.label.get())

    def set_selection(self, indices, candidates=()):
        self.selection = {int(i) for i in indices if 0 <= i < len(self.document["shapes"])}
        available = len(self.cluster_result.shapes) if self.cluster_result is not None else 0
        self.selected_candidates = {int(i) for i in candidates if 0 <= i < available}
        self._selected = min(self.selection) if self.selection else None

    def hide_label_menu(self):
        if hasattr(self, "label_menu"):
            self.label_menu.place_forget()

    def show_label_menu(self, x=None, y=None):
        count = len(self.selection) + len(self.selected_candidates)
        if not count:
            self.hide_label_menu()
            return
        self.label_menu_title.configure(text=f"Выбрано полигонов: {count}. Назначить метку:")
        self.label_menu.update_idletasks()
        width, height = self.label_menu.winfo_reqwidth(), self.label_menu.winfo_reqheight()
        x = self.canvas.winfo_width()-width-12 if x is None else x+12
        y = 30 if y is None else y+12
        x = max(4, min(x, self.canvas.winfo_width()-width-4))
        y = max(4, min(y, self.canvas.winfo_height()-height-4))
        self.label_menu.place(x=x, y=y)
        self.label_menu.lift()

    def deselect(self):
        self.set_selection((), ())
        self.hide_label_menu()
        self.refresh_objects()

    def select_all(self, event=None):
        self.set_selection(range(len(self.document["shapes"])),
            range(len(self.cluster_result.shapes)) if self.cluster_result else ())
        self.refresh_objects()
        self.show_label_menu()
        return "break"

    def expand_group_selection(self):
        groups = {self.document['shapes'][i].get('group_id') for i in self.selection} - {None}
        self.selection.update(i for i,s in enumerate(self.document['shapes']) if s.get('group_id') in groups)
        if self.cluster_result:
            groups = {self.cluster_result.shapes[i].get('group_id') for i in self.selected_candidates} - {None}
            self.selected_candidates.update(i for i,s in enumerate(self.cluster_result.shapes) if s.get('group_id') in groups)
        self._selected = min(self.selection) if self.selection else None
        self.refresh_objects()
        self.show_label_menu()

    def apply_label(self, label):
        if label not in LABELS or not (self.selection or self.selected_candidates):
            return
        self.snapshot()
        selected = set(self.selection)
        shapes = self.document['shapes']
        candidates = self.selected_candidates.copy()
        existing = {tuple(tuple(p) for p in s['points']):i for i,s in enumerate(shapes)}
        matched = set()
        if candidates and self.cluster_result:
            for index in candidates:
                key = tuple(tuple(p) for p in self.cluster_result.shapes[index]['points'])
                if key in existing:
                    selected.add(existing[key])
                    matched.add(index)
        next_group = max((s.get('group_id') or 0 for s in shapes if isinstance(s.get('group_id'),int)), default=0)+1
        # Assigning only part of a group to another class must not leave one
        # instance with conflicting labels. Split that selected subset out.
        split_groups = {}
        for index in sorted(selected):
            shape = shapes[index]
            group = shape.get('group_id')
            if group is not None and any(i not in selected and s.get('group_id')==group and s['label']!=label
                                         for i,s in enumerate(shapes)):
                if group not in split_groups:
                    split_groups[group] = next_group
                    next_group += 1
                shape['group_id'] = split_groups[group]
            shape['label'] = label
        if candidates and self.cluster_result:
            mapping = {}
            for index in sorted(candidates):
                if index in matched:
                    continue
                shape = copy.deepcopy(self.cluster_result.shapes[index])
                key = (shape['flags'].get('proposal_run'), shape.get('group_id'), label)
                if key not in mapping:
                    mapping[key] = next_group
                    next_group += 1
                shape['group_id'], shape['label'] = mapping[key], label
                selected.add(len(shapes))
                shapes.append(shape)
            self.document.setdefault('auto_proposals',[]).append({
                'method':self.cluster_result.params['method'], 'params':self.cluster_result.params,
                'scope':self.cluster_result.scope, 'added_polygons':len(candidates)-len(matched)})
            self.cluster_result.shapes = [s for i,s in enumerate(self.cluster_result.shapes) if i not in candidates]
            self.update_cluster_summary()
            self.no_signal.set(False)
        self.set_selection(selected, ())
        self.label.set(label)
        self.changed()
        self.hide_label_menu()
        self.refresh_objects()
        self.feedback.configure(text=f"Метка {label} назначена полигонам: {len(selected)}")

    def update_cluster_summary(self):
        if not self.cluster_result or not self.cluster_result.shapes:
            self.cluster_result = None
            self.cluster_summary.configure(text="Кандидатов нет")
            self.add_clusters_button.configure(state='disabled')
            return
        shapes = self.cluster_result.shapes
        count = len({s.get('group_id') for s in shapes})
        self.cluster_result.stats.update(clusters=count, polygons=len(shapes))
        self.cluster_summary.configure(text=f"Кластеров: {count}; полигонов: {len(shapes)}")

    def right_click(self, event):
        if self.vertices:
            self.finish_polygon()
        else:
            if not (self.selection or self.selected_candidates):
                kind, index = self.hit_test(self.to_image(event.x,event.y))
                if kind == 'mask':
                    self.set_selection([index])
                elif kind == 'candidate':
                    self.set_selection((), [index])
                self.refresh_objects()
            self.show_label_menu(event.x,event.y)
        return 'break'

    def group(self):
        if self.selected is None:
            return
        value = simpledialog.askinteger("Части одной моды", "Общий номер группы (0 — убрать):", minvalue=0, parent=self.root)
        if value is not None:
            self.snapshot()
            for index in self.selection:
                self.document["shapes"][index]["group_id"] = value or None
            self.changed()
            self.refresh_objects()

    def delete_shape(self):
        if self.selection or self.selected_candidates:
            modifies = bool(self.selection)
            self.snapshot(changes_document=modifies)
            for index in sorted(self.selection, reverse=True):
                self.document["shapes"].pop(index)
            if self.cluster_result and self.selected_candidates:
                self.cluster_result.shapes = [s for i,s in enumerate(self.cluster_result.shapes)
                                              if i not in self.selected_candidates]
                self.update_cluster_summary()
            self.selected = None
            if modifies:
                self.changed()
            self.refresh_objects()
            self.hide_label_menu()

    def undo(self):
        if self.vertices:
            self.remove_last_point()
            return
        elif self.undo_stack:
            previous = self.undo_stack.pop()
            self.document["shapes"] = previous["shapes"]
            self.no_signal.set(previous["no_signal"])
            self.cluster_result = previous['cluster_result']
            self.update_cluster_summary()
            self.document["review"]["no_signal"] = previous["no_signal"]
            if previous["auto_proposals"] is None:
                self.document.pop("auto_proposals", None)
            else:
                self.document["auto_proposals"] = previous["auto_proposals"]
            self.selected = None
            self.hide_label_menu()
            if previous.get('changes_document',True):
                self.changed()
            self.refresh_objects()
        self.redraw()

    def remove_last_point(self, event=None):
        """Undo only an unfinished polygon's last vertex, never a saved mask."""
        if self.vertices:
            self.vertices.pop()
            self.feedback.config(text=f"Последняя точка убрана. Осталось вершин: {len(self.vertices)}")
            self.redraw()
        self.canvas.focus_set()
        return "break"

    def enter(self, event=None):
        if self.root.focus_get() == self.canvas:
            self.finish_polygon()
            return "break"

    def finish_polygon(self):
        if not self.vertices:
            return
        if len(self.vertices) < 3:
            self.feedback.config(text="Для полигона нужны минимум три вершины")
            return
        from .data import validate_shapes
        shape = {"label": self.label.get(), "points": self.vertices[:], "group_id": None,
                 "shape_type": "polygon", "flags": {"created_by": self.reviewer.get().strip() or "human"}}
        try:
            validate_shapes([shape], self.item["width"], self.item["height"])
        except ValueError as exc:
            self.feedback.config(text=str(exc))
            return
        self.snapshot()
        self.document["shapes"].append(shape)
        self.vertices = []
        self.selected = len(self.document["shapes"]) - 1
        self.changed()
        self.refresh_objects()

    def cancel_polygon(self):
        self.vertices = []
        self.region_start = self.region_end = None
        self.selection_box = None
        self.hide_label_menu()
        self.redraw()

    def rect(self):
        return (64, 24, max(120, self.canvas.winfo_width() - 15), max(120, self.canvas.winfo_height() - 47))

    def to_image(self, x, y):
        l, t, r, b = self.rect()
        x0, y0, x1, y1 = self.view
        return [x0 + (x - l) * (x1 - x0) / (r - l), y0 + (y - t) * (y1 - y0) / (b - t)]

    def to_canvas(self, x, y):
        l, t, r, b = self.rect()
        x0, y0, x1, y1 = self.view
        return [l + (x - x0) * (r - l) / (x1 - x0), t + (y - y0) * (b - t) / (y1 - y0)]

    def inside(self, x, y):
        l, t, r, b = self.rect()
        return l <= x <= r and t <= y <= b

    def click(self, event):
        self.canvas.focus_set()
        self.hide_label_menu()
        if not self.inside(event.x, event.y):
            return
        point = self.to_image(event.x, event.y)
        modifier = bool(getattr(event, 'state', 0) & 0x5)
        self.move_drag = None
        self.drag = None
        if self.tool.get() == "region":
            self.region_start = self.region_end = point
            self.redraw()
            return
        if self.tool.get() == "draw":
            self.vertices.append(point)
            self.redraw()
            return
        kind, index = self.hit_test(point)
        if self.tool.get() == 'multi' or (modifier and index is None):
            self.selection_box = [point, point]
            self.selection_additive = modifier
            self.redraw()
            return
        if modifier:
            target = self.selection if kind == 'mask' else self.selected_candidates
            if index in target:
                target.remove(index)
            elif index is not None:
                target.add(index)
            self._selected = min(self.selection) if self.selection else None
            self.refresh_objects()
            return
        best = None
        if self.selected is not None and len(self.selection)==1 and not self.selected_candidates:
            shape = self.document["shapes"][self.selected]
            for j, p in enumerate(shape["points"]):
                cx, cy = self.to_canvas(*p)
                distance = (cx - event.x) ** 2 + (cy - event.y) ** 2
                if distance < 12 ** 2 and (best is None or distance < best[0]):
                    best = distance, j
        if best:
            self.drag = best[1]
            self.snapshot()
            return
        if kind == 'mask':
            if index not in self.selection:
                self.set_selection([index])
            self._selected = index
            self.label.set(self.document['shapes'][index]['label'])
            indices = set(self.selection)
            if self.move_group.get():
                groups = {self.document['shapes'][i].get('group_id') for i in indices}-{None}
                indices.update(i for i,s in enumerate(self.document['shapes']) if s.get('group_id') in groups)
            self.move_drag = {"start": point,
                "original": {i: copy.deepcopy(self.document["shapes"][i]["points"]) for i in indices},
                "snapshot": False}
        elif kind == 'candidate':
            self.set_selection((), [index])
        else:
            self.set_selection((), ())
        self.refresh_objects()

    def hit_test(self, point):
        for index in reversed(range(len(self.document['shapes']))):
            if contains(self.document['shapes'][index]['points'], point):
                return 'mask', index
        if self.cluster_result:
            for index in reversed(range(len(self.cluster_result.shapes))):
                if contains(self.cluster_result.shapes[index]['points'], point):
                    return 'candidate', index
        return None, None

    def motion(self, event):
        if self.selection_box is not None:
            self.selection_box[1] = self.to_image(*self.bound_canvas_point(event.x,event.y))
            self.redraw()
            return
        if self.region_start is not None:
            self.region_end = self.to_image(*self.bound_canvas_point(event.x, event.y))
            self.redraw()
            return
        if self.move_drag is not None:
            p = np.asarray(self.to_image(event.x, event.y))
            delta = p - self.move_drag["start"]
            originals = self.move_drag["original"]
            all_points = np.asarray([p for points in originals.values() for p in points])
            delta = np.clip(delta, -all_points.min(axis=0),
                            [self.item["width"] - 1, self.item["height"] - 1] - all_points.max(axis=0))
            if not self.move_drag["snapshot"] and np.allclose(delta, 0):
                return
            if not self.move_drag["snapshot"]:
                self.snapshot()
                self.move_drag["snapshot"] = True
            for i, points in originals.items():
                self.document["shapes"][i]["points"] = (np.asarray(points) + delta).tolist()
            self.canvas.configure(cursor="fleur")
            self.changed()
            self.redraw()
            return
        if self.drag is not None and self.selected is not None:
            p = self.to_image(event.x, event.y)
            p[0] = max(0, min(self.item["width"] - 1, p[0]))
            p[1] = max(0, min(self.item["height"] - 1, p[1]))
            self.document["shapes"][self.selected]["points"][self.drag] = p
            self.changed()
            self.redraw()

    def release(self, event=None):
        moved = self.drag is not None or (self.move_drag is not None and self.move_drag['snapshot'])
        self.drag = None
        self.move_drag = None
        self.canvas.configure(cursor="")
        if self.selection_box is not None:
            if event is not None:
                self.selection_box[1] = self.to_image(*self.bound_canvas_point(event.x,event.y))
            a,b = self.selection_box
            self.selection_box = None
            rect = (min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1]))
            masks = {i for i,s in enumerate(self.document['shapes']) if intersects_rect(s['points'],rect)}
            candidates = {i for i,s in enumerate(self.cluster_result.shapes)
                          if intersects_rect(s['points'],rect)} if self.cluster_result else set()
            if self.selection_additive:
                masks.update(self.selection)
                candidates.update(self.selected_candidates)
            self.set_selection(masks,candidates)
            self.refresh_objects()
            self.show_label_menu(getattr(event,'x',None),getattr(event,'y',None))
            return
        if self.region_start is not None:
            if event is not None:
                self.region_end = self.to_image(*self.bound_canvas_point(event.x, event.y))
            start, end = self.region_start, self.region_end
            self.region_start = self.region_end = None
            a, b = self.to_canvas(*start), self.to_canvas(*end)
            if abs(a[0] - b[0]) >= 6 and abs(a[1] - b[1]) >= 6:
                self.view = self.clamp_view((min(start[0], end[0]), min(start[1], end[1]),
                                            max(start[0], end[0]), max(start[1], end[1])))
                self.tool.set("select")
            self.sync_range_fields()
            self.redraw()
            return
        if not moved and self.tool.get() != 'draw':
            self.show_label_menu(getattr(event,'x',None),getattr(event,'y',None))

    def bound_canvas_point(self, x, y):
        l, t, r, b = self.rect()
        return max(l, min(r, x)), max(t, min(b, y))

    def hover(self, event):
        if self.view is None or not self.inside(event.x, event.y):
            return
        x, y = self.to_image(event.x, event.y)
        text = f"x={x:.1f}, y={y:.1f}"
        if self.freq is not None:
            f = np.interp(x, np.arange(len(self.freq)), self.freq)
            r = np.interp(y, np.arange(len(self.ranges)), self.ranges)
            text = f"{f:.3f} МГц · {r:.1f} км"
        self.cursor_text.config(text=text)

    def clamp_view(self, view):
        w, h = self.item["width"] - 1, self.item["height"] - 1
        x0, y0, x1, y1 = view
        dx, dy = min(w, max(2, x1 - x0)), min(h, max(2, y1 - y0))
        x0, y0 = max(0, min(w - dx, x0)), max(0, min(h - dy, y0))
        return x0, y0, x0 + dx, y0 + dy

    def fit(self):
        if self.item:
            self.hide_label_menu()
            self.view = (0, 0, self.item["width"] - 1, self.item["height"] - 1)
            self.sync_range_fields()
            self.schedule_draw()

    def echo_view(self):
        self.set_range(1000, 5000)

    def sync_range_fields(self):
        self.range_preset.set("Свое окно")
        if self.ranges is not None and self.view is not None:
            values = np.interp([self.view[1], self.view[3]], np.arange(len(self.ranges)), self.ranges)
            self.range_low.set(f"{min(values):.1f}")
            self.range_high.set(f"{max(values):.1f}")
        if self.item and self.view == (0, 0, self.item["width"] - 1, self.item["height"] - 1):
            self.range_preset.set("Весь кадр")

    def set_range(self, low, high):
        if self.ranges is None:
            raise ValueError("В этом наборе нет физической оси дальности")
        if not (math.isfinite(low) and math.isfinite(high) and low < high):
            raise ValueError("Нижняя граница должна быть меньше верхней")
        available_low, available_high = float(self.ranges[-1]), float(self.ranges[0])
        low, high = max(low, available_low), min(high, available_high)
        if low >= high:
            raise ValueError(f"Окно вне данных: доступны {available_low:.0f}–{available_high:.0f} км")
        ys = np.interp([high, low], self.ranges[::-1], np.arange(len(self.ranges))[::-1])
        self.view = self.clamp_view((self.view[0], float(ys[0]), self.view[2], float(ys[1])))
        self.hide_label_menu()
        self.sync_range_fields()
        self.redraw()

    def apply_range(self, event=None):
        try:
            low = float(self.range_low.get().strip().replace(",", "."))
            high = float(self.range_high.get().strip().replace(",", "."))
            self.set_range(low, high)
        except ValueError as exc:
            self.feedback.config(text=f"Окно дальности: {exc}")
        return "break"

    def preset_range(self, event=None):
        name = self.range_preset.get()
        low, high = RANGE_PRESETS[name]
        self.range_low.set(str(low))
        self.range_high.set(str(high))
        return self.apply_range()

    def focus_masks(self):
        if self.selection or self.selected_candidates:
            shapes = [self.document['shapes'][i] for i in self.selection]
            if self.cluster_result:
                shapes += [self.cluster_result.shapes[i] for i in self.selected_candidates]
        else:
            shapes = [s for s in self.document["shapes"] if s["label"] != "Interference"]
            if not shapes and self.cluster_result:
                shapes = self.cluster_result.shapes
        if not shapes:
            self.feedback.config(text="Пока нет масок: задайте границы в км или выделите область")
            return
        points = np.asarray([p for s in shapes for p in s["points"]], dtype=float)
        lo, hi = points.min(axis=0), points.max(axis=0)
        pad = np.maximum((hi - lo) * .15, [5, 4])
        self.view = self.clamp_view((lo[0] - pad[0], lo[1] - pad[1], hi[0] + pad[0], hi[1] + pad[1]))
        self.sync_range_fields()
        self.redraw()

    def zoom_center(self, factor):
        x0, y0, x1, y1 = self.view
        self.zoom_at(((x0 + x1) / 2, (y0 + y1) / 2), factor)

    def zoom_at(self, p, factor, range_only=False):
        self.hide_label_menu()
        x0, y0, x1, y1 = self.view
        xfactor = 1 if range_only else factor
        self.view = self.clamp_view((p[0] + (x0 - p[0]) * xfactor,
            p[1] + (y0 - p[1]) * factor, p[0] + (x1 - p[0]) * xfactor,
            p[1] + (y1 - p[1]) * factor))
        self.sync_range_fields()
        self.redraw()

    def zoom(self, event):
        if not self.inside(event.x, event.y) or not event.delta:
            return "break"
        p = self.to_image(event.x, event.y)
        ticks = max(-5, min(5, event.delta / 120))
        self.zoom_at(p, .8 ** ticks, range_only=bool(event.state & 0x1))
        # Consume the event before Tk class/toplevel/all bindings can also
        # scroll the surrounding UI. View changes never alter annotation data.
        return "break"

    def pan_begin(self, event):
        self.hide_label_menu()
        self.pan_start = (event.x, event.y, self.view)

    def pan(self, event):
        if self.pan_start is None:
            return
        x, y, view = self.pan_start
        l, t, r, b = self.rect()
        dx = (event.x - x) * (view[2] - view[0]) / (r - l)
        dy = (event.y - y) * (view[3] - view[1]) / (b - t)
        self.view = self.clamp_view((view[0] - dx, view[1] - dy, view[2] - dx, view[3] - dy))
        self.sync_range_fields()
        self.redraw()

    def schedule_draw(self):
        if self.draw_job is not None:
            self.root.after_cancel(self.draw_job)
        self.draw_job = self.root.after(35, self.redraw)

    def redraw(self):
        self.draw_job = None
        if self.item is None or self.view is None:
            return
        self.undo_point_button.configure(state="normal" if self.vertices else "disabled")
        self.canvas.delete("all")
        l, t, r, b = self.rect()
        x0, y0, x1, y1 = self.view
        size = (int(r - l + 1), int(b - t + 1))
        # Pixel-centre coordinates map exactly to the plotting rectangle's
        # endpoints. The same transform drives image sampling and vertices.
        affine = ((x1 - x0) / max(1, size[0] - 1), 0, x0,
                  0, (y1 - y0) / max(1, size[1] - 1), y0)
        if self.db is not None:
            low, high = self.low.get(), max(self.low.get() + 1, self.high.get())
            rgb = colormaps["turbo"](np.clip((np.nan_to_num(self.db, nan=low) - low) / (high - low), 0, 1), bytes=True)[:, :, :3]
            base = Image.fromarray(rgb)
        else:
            base = self.original_image
        display = base.transform(size, Image.Transform.AFFINE, affine, Image.Resampling.NEAREST).convert("RGBA")
        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        def local(p):
            return ((p[0] - x0) * (size[0] - 1) / (x1 - x0),
                    (p[1] - y0) * (size[1] - 1) / (y1 - y0))
        if self.visible.get():
            for i, shape in enumerate(self.document["shapes"]):
                pts = [local(p) for p in shape["points"]]
                c = tuple(bytes.fromhex(COLORS[shape["label"]][1:]))
                draw.polygon(pts, fill=c + (int(255 * self.opacity.get()),))
                draw.line(pts + [pts[0]], fill=(255,255,255,255) if i in self.selection else c+(255,), width=3 if i in self.selection else 2)
                if i == self.selected and len(self.selection)==1 and not self.selected_candidates:
                    for px, py in pts:
                        draw.ellipse((px - 4, py - 4, px + 4, py + 4), fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))
        if self.vertices:
            pts = [local(p) for p in self.vertices]
            if len(pts) > 1:
                draw.line(pts, fill="white", width=2)
            for px, py in pts:
                draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill="white")
        if self.cluster_result is not None:
            labelled = set()
            for index, shape in enumerate(self.cluster_result.shapes):
                points = [local(p) for p in shape["points"]]
                group = shape['group_id']
                color = CLUSTER_COLORS[(group-1)%len(CLUSTER_COLORS)]
                chosen = index in self.selected_candidates
                draw.polygon(points, fill=color+(65 if chosen else 35,))
                draw.line(points + [points[0]], fill=(255,255,255,255) if chosen else color+(255,), width=3 if chosen else 2)
                if group not in labelled:
                    draw.text(points[0], f"K{group}", fill=color+(255,))
                    labelled.add(group)
        self.photo = ImageTk.PhotoImage(Image.alpha_composite(display, overlay))
        self.canvas.create_image(l, t, anchor="nw", image=self.photo)
        self.canvas.create_rectangle(l, t, r, b, outline="#8b9bad")
        if self.region_start is not None and self.region_end is not None:
            self.canvas.create_rectangle(*self.to_canvas(*self.region_start),
                *self.to_canvas(*self.region_end), outline="white", width=2, dash=(5, 4))
        if self.selection_box is not None:
            self.canvas.create_rectangle(*self.to_canvas(*self.selection_box[0]),
                *self.to_canvas(*self.selection_box[1]), outline='#ffe79b',width=2,dash=(4,3))
        for v in np.linspace(x0, x1, 6):
            cx, _ = self.to_canvas(v, y0)
            text = f"{np.interp(v, np.arange(len(self.freq)), self.freq):.1f}" if self.freq is not None else f"{v:.0f}"
            self.canvas.create_text(cx, b + 13, text=text, fill="#dbe6f1", font=("Segoe UI", 9))
        for v in np.linspace(y0, y1, 6):
            _, cy = self.to_canvas(x0, v)
            text = f"{np.interp(v, np.arange(len(self.ranges)), self.ranges):.0f}" if self.ranges is not None else f"{v:.0f}"
            self.canvas.create_text(l - 8, cy, text=text, fill="#dbe6f1", anchor="e", font=("Segoe UI", 9))
        self.canvas.create_text((l + r) / 2, b + 33, text="Частота, МГц" if self.freq is not None else "x, пиксели", fill="#dbe6f1")
        self.canvas.create_text(l, 10, anchor="w", text="Действующая дальность, км" if self.ranges is not None else "y, пиксели", fill="#dbe6f1")
        if self.db is not None:
            self.canvas.create_text(r, 10, anchor="e", text=f"{self.low.get():.0f}–{max(self.low.get()+1,self.high.get()):.0f} дБ · turbo", fill="#dbe6f1")

    def import_candidate(self):
        if self.store.manifest.get('assistance_disabled'):
            self.feedback.configure(text='Независимая разметка: импорт подсказок отключён')
            return
        if (self.dirty or self.vertices) and not self.save():
            return
        path = filedialog.askopenfilename(title="Кандидат LabelMe для текущего изображения", filetypes=[("LabelMe JSON", "*.json")])
        if not path:
            return
        author = simpledialog.askstring("Происхождение разметки", "Автор / название модели:", parent=self.root)
        if not author:
            return
        try:
            self.store.import_labelme(self.item, path, author)
            self.load(self.index)
            self.refresh_cases()
        except Exception as exc:
            messagebox.showerror("Ошибка импорта", str(exc))

    def export(self):
        if (self.dirty or self.vertices) and not self.save():
            return
        parent = filedialog.askdirectory(title="Папка для нового экспорта")
        if not parent:
            return
        from datetime import datetime
        destination = Path(parent) / ("accepted_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
        try:
            count = self.store.export(destination)
            self.export_path.set(str(destination.resolve()))
            self.save_settings()
            messagebox.showinfo("Экспорт готов", f"Принятых изображений: {count}\n{destination}")
        except Exception as exc:
            messagebox.showerror("Ошибка экспорта", str(exc))

    def close(self):
        if (self.dirty or self.vertices) and not self.save():
            return
        try:
            self.save_settings()
        except OSError:
            pass  # A preferences failure must not prevent closing saved work.
        self.root.destroy()


def run(folder):
    root = tk.Tk()
    try:
        Reviewer(root, folder)
    except Exception as exc:
        messagebox.showerror("ИоноРазметка", str(exc))
        root.destroy()
        raise
    root.mainloop()


def run_library(folder):
    from .library import choose
    root=tk.Tk()
    root.withdraw()
    try:
        selected=choose(root,folder)
        if selected is None:
            root.destroy()
            return
        root.deiconify()
        Reviewer(root,selected)
    except Exception as exc:
        messagebox.showerror('ИоноРазметка',str(exc))
        root.destroy()
        raise
    root.mainloop()
