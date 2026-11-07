"""Create a portable PNG/NPZ project without blocking Tk's event loop."""
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .prepare import measurements, prepare, project_folder, PreparationCancelled
from .data import read_json


def create_project(root, source=None):
    source = source or filedialog.askdirectory(parent=root, title='Папка исходных H5 / LFS (включая подпапки)')
    if not source:
        return None
    parent = filedialog.askdirectory(parent=root, title='Где сохранить проект с PNG, NPZ и разметкой?')
    if not parent:
        return None
    destination = project_folder(parent, source)
    window = tk.Toplevel(root)
    window.title('Создание проекта из H5 / LFS')
    window.geometry('700x310')
    if root.state() != 'withdrawn':
        window.transient(root)
    frame = ttk.Frame(window, padding=20)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Подготовка ионограмм', font=('Segoe UI', 15, 'bold')).pack(anchor='w')
    ttk.Label(frame, text=f'Исходники: {Path(source).resolve()}\nПроект: {destination}\nPNG → images · NPZ → arrays · разметка → annotations', wraplength=650).pack(anchor='w', pady=12)
    status = ttk.Label(frame, text='Поиск файлов и проверка заголовков…', wraplength=650)
    status.pack(anchor='w')
    bar = ttk.Progressbar(frame, mode='indeterminate')
    bar.pack(fill='x', pady=12)
    bar.start()
    cancel = threading.Event()
    events = queue.Queue()
    result = []
    def stop():
        cancel.set()
        status.configure(text='Остановка после текущего файла…')
        button.configure(state='disabled')
    button = ttk.Button(frame, text='Отменить', command=stop)
    button.pack(anchor='e')
    window.protocol('WM_DELETE_WINDOW', stop)
    def worker():
        try:
            files = measurements(source)
            if cancel.is_set():
                raise PreparationCancelled('Подготовка отменена')
            items = prepare(files, destination, progress=lambda d,t,n: events.put(('progress', (d,t,n))), cancelled=cancel.is_set)
            events.put(('done', (len(items), len(read_json(destination/'manifest.json')['errors']))))
        except Exception as exc:
            events.put(('cancelled' if isinstance(exc, PreparationCancelled) else 'error', str(exc)))
    def poll():
        try:
            while True:
                kind, value = events.get_nowait()
                if kind == 'progress':
                    done, total, name = value
                    bar.stop(); bar.configure(mode='determinate', maximum=total, value=done)
                    if not cancel.is_set():
                        status.configure(text=f'Сохранено/обработано: {done} / {total}\n{name}')
                else:
                    window.destroy()
                    if kind == 'done':
                        result.append(destination)
                        count, errors = value
                        if errors:
                            messagebox.showwarning('Проект создан', f'Ионограмм: {count}. Пропущено файлов: {errors}.\nПричины: {destination / "manifest.json"}', parent=root)
                    elif kind == 'cancelled':
                        messagebox.showinfo('Подготовка остановлена', value, parent=root)
                    else:
                        messagebox.showerror('Не удалось создать проект', f'{value}\nПапка результата: {destination}', parent=root)
                    return
        except queue.Empty:
            window.after(100, poll)
    previous_grab = root.grab_current()
    window.grab_set()
    threading.Thread(target=worker, daemon=True).start()
    window.after(100, poll)
    root.wait_window(window)
    if previous_grab is not None and previous_grab.winfo_exists():
        previous_grab.grab_set()
    return result[0] if result else None
