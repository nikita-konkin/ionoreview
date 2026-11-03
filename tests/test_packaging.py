"""The portable launcher must never store annotations inside the frozen bundle."""
import importlib.util
from pathlib import Path
import sys


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
