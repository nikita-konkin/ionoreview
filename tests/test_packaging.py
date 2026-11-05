"""The portable launcher must never store annotations inside the frozen bundle."""
import importlib.util
from pathlib import Path
import sys
import pytest


def launcher():
    path=Path(__file__).resolve().parents[1]/'packaging/windows_entry.py'
    spec=importlib.util.spec_from_file_location('ionoreview_windows_entry',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_default_uses_executable_not_internal_directory(monkeypatch,tmp_path):
    module=launcher()
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'executable',str(tmp_path/'portable/IonoReview.exe'))
    monkeypatch.setattr(sys,'_MEIPASS',str(tmp_path/'temporary-internal'),raising=False)
    assert module.initial_folder()==(tmp_path/'portable/datasets').resolve()


def test_explicit_dataset_folder_is_independent_of_executable(monkeypatch,tmp_path):
    module=launcher()
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'executable',str(tmp_path/'app/IonoReview.exe'))
    target=tmp_path/'external data'
    assert module.initial_folder(target)==target.resolve()


@pytest.mark.parametrize('selection', ['annotations', 'images', 'delivery'])
def test_portable_startup_opens_pack_subfolder_without_another_picker(monkeypatch,tmp_path,selection):
    import tkinter as tk
    import tkinter.filedialog
    import ionoreview.app
    module = launcher()
    wrapper = tmp_path/'delivery'
    pack = wrapper/'dataset'
    (pack/'annotations').mkdir(parents=True)
    (pack/'images').mkdir()
    (pack/'manifest.json').write_text('{}',encoding='utf-8')
    opened = []
    class Root:
        def withdraw(self): pass
        def deiconify(self): pass
        def mainloop(self): pass
        def destroy(self): pass
    class Reviewer:
        def __init__(self,root,folder): opened.append(folder)
    monkeypatch.setattr(tk,'Tk',Root)
    monkeypatch.setattr(ionoreview.app,'Reviewer',Reviewer)
    monkeypatch.setattr(tkinter.filedialog,'askdirectory',lambda **kw:pytest.fail('A valid pack must open immediately'))
    target = wrapper if selection=='delivery' else pack/selection
    assert module.launch(target)==0
    assert opened==[pack]
