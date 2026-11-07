import random
import sys
import types
from datetime import datetime, timedelta, timezone

import numpy as np

from ionoreview.prepare import measurements, prepare, project_folder


def fake_loader(monkeypatch, freq):
    start = datetime(2026, 8, random.randint(1, 20), tzinfo=timezone.utc)
    header = lambda path: types.SimpleNamespace(datetime=start + timedelta(minutes=random.randint(0, 900)),
                                                tx_name='NIC1', rx_name='Yoshkar-Ola')
    load = lambda path, gate_km: types.SimpleNamespace(
        db=np.random.default_rng(7).uniform(10, 60, (len(freq), 9)).astype(np.float32), freq=freq,
        vrange=np.linspace(2500, 3300, 9), header=header(path))
    monkeypatch.setitem(sys.modules, 'muf', types.SimpleNamespace(loader=types.SimpleNamespace(read_header=header, load=load)))


def soundings(folder, count):
    paths = []
    for n in range(count):
        path = folder / f'день-{n % 2}' / f'lfm_ionogram-{random.randint(1000, 9999)}-{n}.h5'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(random.getrandbits(8) for _ in range(32)))
        paths.append(path)
    return paths


def test_measurements_finds_soundings_in_nested_folders(tmp_path):
    expected = soundings(tmp_path, random.randint(2, 6))
    (tmp_path / 'снимок.png').write_bytes(b'\x89PNG')
    assert measurements(tmp_path) == sorted(expected), 'Sounding files in nested folders are not all found'


def test_prepare_reports_progress_for_every_file(tmp_path, monkeypatch):
    fake_loader(monkeypatch, np.linspace(4, 30, 11))
    paths = soundings(tmp_path / 'h5', random.randint(2, 5))
    seen = []
    prepare(paths, tmp_path / 'проект', progress=lambda done, total, name: seen.append(done))
    assert seen == list(range(1, len(paths) + 1)), 'Preparation does not report progress after every file'


def test_prepare_keeps_measured_frequency_axis_in_npz(tmp_path, monkeypatch):
    freq = np.sort(np.random.default_rng(3).uniform(3, 30, 13))
    fake_loader(monkeypatch, freq)
    prepare(soundings(tmp_path / 'h5', 1), tmp_path / 'проект')
    with np.load(tmp_path / 'проект' / 'arrays' / 'case_001.npz') as z:
        assert np.allclose(z['freq_mhz'], freq), 'Prepared NPZ does not keep the measured frequency axis'


def test_project_folder_is_named_after_its_source(tmp_path):
    source = tmp_path / f'ионограммы-{random.randint(1, 99)}'
    assert project_folder(tmp_path, source).name == f'{source.name}_проект', 'Project folder is not named after its source folder'


def test_project_folder_dont_reuse_existing_folder(tmp_path):
    source = tmp_path / 'ионограммы'
    (tmp_path / 'ионограммы_проект').mkdir()
    assert not project_folder(tmp_path, source).exists(), 'Project folder reuses a folder that already exists'


def test_invalid_h5_is_logged_and_other_files_survive(tmp_path, monkeypatch):
    from ionoreview.data import read_json
    fake_loader(monkeypatch, np.linspace(4, 30, 11))
    paths = soundings(tmp_path/'input', 2)
    loader = sys.modules['muf'].loader
    original = loader.read_header
    def header(path):
        if path == paths[0]:
            raise ValueError('not an ionogram')
        return original(path)
    loader.read_header = header
    out = tmp_path/'project'
    assert len(prepare(paths, out)) == 1
    assert read_json(out/'manifest.json')['errors'][0]['error'] == 'not an ionogram'


def test_cancel_keeps_completed_images_and_manifest(tmp_path, monkeypatch):
    import pytest
    from ionoreview.prepare import PreparationCancelled
    from ionoreview.data import read_json
    fake_loader(monkeypatch, np.linspace(4, 30, 11))
    stopped = []
    out = tmp_path/'project'
    with pytest.raises(PreparationCancelled):
        prepare(soundings(tmp_path/'input',3), out, progress=lambda *args: stopped.append(True), cancelled=lambda: bool(stopped))
    manifest = read_json(out/'manifest.json')
    assert manifest['cancelled'] and len(manifest['items']) == 1
    assert (out/manifest['items'][0]['axes']).is_file()


def test_project_dialog_creates_and_opens_readable_pack(tmp_path, monkeypatch):
    import tkinter as tk
    from ionoreview import project_dialog
    from ionoreview.data import ReviewStore
    fake_loader(monkeypatch, np.linspace(4,30,11))
    source=tmp_path/'input';soundings(source,2)
    monkeypatch.setattr(project_dialog.filedialog,'askdirectory',lambda **kw: str(tmp_path))
    errors=[]
    monkeypatch.setattr(project_dialog.messagebox,'showerror',lambda *a,**kw: errors.append(a))
    root=tk.Tk();root.withdraw()
    timer=root.after(15000,root.destroy)
    try:
        destination=project_dialog.create_project(root,source)
        assert not errors and destination
        store=ReviewStore(destination)
        assert len(store.items)==2 and (destination/'images/case_001.png').exists()
        from ionoreview.app import Reviewer
        app=Reviewer(root,destination)
        root.update_idletasks()
        assert app.db.shape==(9,11)
        assert app.store.root==destination.resolve()
    finally:
        if root.winfo_exists():
            root.after_cancel(timer);root.destroy()
