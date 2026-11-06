import json
import re
import copy
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk

import numpy as np
from PIL import Image
import pytest

from ionoreview.data import ReviewStore, atomic_json, digest, validate_shapes


def test_atomic_json_retries_windows_reader_lock_without_losing_old_file(tmp_path,monkeypatch):
    import ionoreview.data as data
    path=tmp_path/'progress.json';atomic_json(path,{'step':1})
    replace=data.os.replace;attempts=[]
    def blocked_then_replace(source,target):
        attempts.append(1)
        assert data.read_json(path)=={'step':1}
        if len(attempts)<3:
            exc=PermissionError('Windows reader has the destination open');exc.winerror=5
            raise exc
        return replace(source,target)
    monkeypatch.setattr(data.os,'replace',blocked_then_replace)
    monkeypatch.setattr(data.time,'sleep',lambda _:None)
    atomic_json(path,{'step':2})
    assert data.read_json(path)=={'step':2} and len(attempts)==3
    assert not list(tmp_path.glob('*.tmp'))


def test_atomic_json_permanent_denial_keeps_previous_file_and_reports_failure(tmp_path,monkeypatch):
    import ionoreview.data as data
    path=tmp_path/'progress.json';atomic_json(path,{'step':1})
    def denied(*args):
        exc=PermissionError('Permanent denial');exc.winerror=5
        raise exc
    monkeypatch.setattr(data.os,'replace',denied)
    monkeypatch.setattr(data.time,'sleep',lambda _:None)
    with pytest.raises(PermissionError):atomic_json(path,{'step':2})
    assert data.read_json(path)=={'step':1}
    assert not list(tmp_path.glob('*.tmp'))


@pytest.fixture
def pack(tmp_path):
    root = tmp_path / "pack"
    (root / "images").mkdir(parents=True)
    (root / "arrays").mkdir()
    Image.new("RGB", (100, 80), "navy").save(root / "images/case_001.png")
    np.savez_compressed(root / "arrays/case_001.npz", db=np.ones((80, 100)) * 30,
                        freq_mhz=np.linspace(5, 25, 100), range_km=np.linspace(4000, 1000, 80))
    item = {"id": "case_001", "image": "images/case_001.png", "axes": "arrays/case_001.npz",
            "width": 100, "height": 80, "image_sha256": digest(root / "images/case_001.png"),
            "source": "original.h5", "when": "2026-10-17T00:00:00Z", "split": "train"}
    atomic_json(root / "manifest.json", {"schema": "ionoreview/1", "items": [item]})
    return ReviewStore(root)


def polygon():
    return {"label": "Signal", "points": [[10, 10], [40, 10], [35, 30], [10, 25]],
            "shape_type": "polygon", "flags": {}}


def test_acceptance_is_explicit_and_negative_signal_must_be_marked(pack):
    item = pack.items[0]
    doc = pack.load(item)
    doc["review"]["status"] = "accepted"
    with pytest.raises(ValueError, match="эксперта"):
        pack.save(item, doc)
    doc["review"]["reviewer"] = "Эксперт"
    with pytest.raises(ValueError, match="Пустой"):
        pack.save(item, doc)
    doc["review"]["no_signal"] = True
    saved = pack.save(item, doc)
    assert saved["review"]["revision"] == 1
    saved["shapes"] = [polygon()]
    with pytest.raises(ValueError, match="противоречит"):
        pack.save(item, saved)


def test_history_and_revision_prevent_silent_overwrite(pack):
    item = pack.items[0]
    first = pack.load(item)
    first["shapes"] = [polygon()]
    saved = pack.save(item, first)
    saved["review"]["note"] = "Исправлена вершина"
    pack.save(item, saved)
    assert len(list((pack.root / "history/case_001").glob("*.json"))) == 1
    with pytest.raises(ValueError, match="другим процессом"):
        pack.save(item, first)


@pytest.mark.parametrize("bad", [
    {"label": "1X", "points": [[0, 0], [20, 0], [20, 10]]},
    {"label": "Signal", "points": [[0, 0], [100, 0], [20, 10]]},
    {"label": "Signal", "points": [[0, 0], [20, 0], [float('nan'), 10]]},
    {"label": "Signal", "points": [[0, 0], [20, 0], [40, 0]]},
])
def test_invalid_annotations_are_rejected(bad):
    with pytest.raises(ValueError):
        validate_shapes([bad], 100, 80)


def test_catalog_search_opens_correct_pack(tmp_path, tk_root):
    from tkinter import ttk
    from ionoreview.library import choose
    for folder in ['first','second']:
        atomic_json(tmp_path/folder/'manifest.json',{})
    atomic_json(tmp_path/'catalog.json',{'schema':'ionoreview-library/1','datasets':[
        {'path':'first','title':'First','count':3,'stations':['NIC1']},
        {'path':'second','title':'Second','count':7,'stations':['NIC2']}]})
    def select():
        window=next(w for w in tk_root.winfo_children() if isinstance(w,tk.Toplevel) and w.title()=='Каталог ионограмм')
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        widgets=list(descendants(window))
        entry=next(w for w in widgets if isinstance(w,ttk.Entry))
        entry.insert(0,'NIC2')
        next(w for w in widgets if isinstance(w,ttk.Button) and w.cget('text')=='Открыть набор').invoke()
    tk_root.after(50,select)
    assert choose(tk_root,tmp_path)==(tmp_path/'second').resolve()


def test_import_is_pending_and_does_not_accept_model_output(pack, tmp_path):
    item = pack.items[0]
    candidate = tmp_path / "candidate.json"
    atomic_json(candidate, {"imagePath": "case_001.png", "imageWidth": 100,
                           "imageHeight": 80, "shapes": [polygon()]})
    result = pack.import_labelme(item, candidate, "local-vlm")
    assert result["review"]["status"] == "pending"
    assert result["proposal"]["author"] == "local-vlm"
    assert result["shapes"][0]["flags"]["proposal_author"] == "local-vlm"
    invalid = json.loads(candidate.read_text(encoding="utf-8"))
    invalid["imagePath"] = "other.png"
    atomic_json(candidate, invalid)
    with pytest.raises(ValueError, match="другому изображению"):
        pack.import_labelme(item, candidate, "local-vlm")


def test_export_only_expert_accepted_preserves_coordinates_and_axes(pack, tmp_path):
    item = pack.items[0]
    doc = pack.load(item)
    doc["shapes"] = [polygon()]
    doc = pack.save(item, doc)
    with pytest.raises(ValueError, match="нет принятых"):
        pack.export(tmp_path / "not_ready")
    doc["review"].update(status="accepted", reviewer="Эксперт")
    pack.save(item, doc)
    dest = tmp_path / "accepted"
    assert pack.export(dest) == 1
    exported = json.loads((dest / "train/case_001.json").read_text(encoding="utf-8"))
    assert exported["shapes"][0]["points"] == polygon()["points"]
    assert exported["imagePath"] == "case_001.png"
    assert (dest / "train/case_001.npz").exists()
    with pytest.raises(ValueError, match="новую папку"):
        pack.export(dest)


def test_changed_image_is_not_silently_accepted(pack):
    item = pack.items[0]
    doc = pack.load(item)
    Image.new("RGB", (100, 80), "red").save(pack.root / item["image"])
    with pytest.raises(ValueError, match="Изображение изменилось"):
        pack.save(item, doc)


def test_changed_physical_axes_are_not_exported(pack, tmp_path):
    item = pack.items[0]
    item["axes_sha256"] = digest(pack.root / item["axes"])
    doc = pack.load(item)
    doc["shapes"] = [polygon()]
    doc["review"].update(status="accepted", reviewer="Эксперт")
    pack.save(item, doc)
    with open(pack.root / item["axes"], "ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="числовые"):
        pack.export(tmp_path / "bad_axes")


def test_malicious_manifest_does_not_escape_pack(pack):
    data = pack.manifest
    data["items"][0]["image"] = "../../outside.png"
    atomic_json(pack.root / "manifest.json", data)
    with pytest.raises(ValueError, match="пределы"):
        ReviewStore(pack.root)


@pytest.fixture(scope="session")
def tk_root():
    # One Tcl interpreter per process, as in the real application. Repeatedly
    # creating/destroying interpreters on Windows can fail inside init.tcl.
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


def destroy_test_window(root):
    for callback in root.tk.call('after', 'info'):
        root.after_cancel(callback)
    root.destroy()


def test_desktop_roundtrip_and_edit_invalidates_acceptance(pack, monkeypatch, tk_root):
    from ionoreview.app import Reviewer
    root = tk.Toplevel(tk_root)
    monkeypatch.setattr("ionoreview.app.messagebox.showerror", lambda *a: pytest.fail(str(a)))
    try:
        app = Reviewer(root, pack.root)
        root.update()
        app.reviewer.set("Проверка UI")
        app.document["shapes"] = [polygon()]
        app.changed()
        app.document["review"]["status"] = "accepted"
        assert app.save()
        assert pack.load(pack.items[0])["review"]["status"] == "accepted"
        app.selected = 0
        app.label.set("1F")
        app.relabel()
        assert app.document["review"]["status"] == "pending"
        assert app.save()
        app.load(0)
        assert app.document["shapes"][0]["label"] == "1F"
        for p in ((0, 0), (99, 79), (33.4, 41.7)):
            np.testing.assert_allclose(app.to_image(*app.to_canvas(*p)), p, atol=1e-8)
        app.echo_view()
        root.update()
        assert app.photo is not None
        root.geometry("1020x700")
        root.update()
        # Footer and fixed acceptance buttons must remain reachable at the
        # smallest supported size; long form fields are scrollable.
        assert app.feedback.winfo_rooty() < root.winfo_rooty() + root.winfo_height()
        assert app.left_canvas.winfo_height() > 150
    finally:
        destroy_test_window(root)


@pytest.fixture
def reviewer(pack, tk_root):
    from ionoreview.app import Reviewer
    root = tk.Toplevel(tk_root)
    app = Reviewer(root, pack.root)
    root.update()
    try:
        yield app
    finally:
        destroy_test_window(root)


def test_wheel_changes_only_plot_not_sidebar_layout_or_annotations(reviewer):
    app = reviewer
    # Reproduce a scrollable sidebar and the actual Tk event propagation:
    # the previous startswith test also matched its right-hand sibling.
    app.left_canvas.configure(scrollregion=(0, 0, 300, 2000))
    app.left_canvas.yview_moveto(.2)
    app.root.update()
    sidebar = app.left_canvas.yview()
    geometry = app.root.geometry()
    bounds = (app.canvas.winfo_width(), app.canvas.winfo_height(),
              app.left_shell.winfo_width(), app.help_text.winfo_y())
    document = copy.deepcopy(app.document)
    before = tuple(app.view)
    l, t, r, b = app.rect()
    x, y = int((l + r) / 2), int((t + b) / 2)
    anchor = app.to_image(x, y)
    app.canvas.event_generate("<MouseWheel>", x=x, y=y, delta=120)
    app.root.update()
    assert app.view[2] - app.view[0] < before[2] - before[0]
    assert app.left_canvas.yview() == sidebar
    assert app.root.geometry() == geometry
    assert (app.canvas.winfo_width(), app.canvas.winfo_height(),
            app.left_shell.winfo_width(), app.help_text.winfo_y()) == bounds
    assert app.document == document
    assert not app.dirty
    np.testing.assert_allclose(app.to_image(x, y), anchor)
    # Axis margins also consume the event, so they cannot scroll the form.
    app.canvas.event_generate("<MouseWheel>", x=10, y=10, delta=-120)
    app.root.update()
    assert app.left_canvas.yview() == sidebar


def test_shift_wheel_magnifies_range_without_losing_frequency(reviewer):
    app = reviewer
    before = tuple(app.view)
    l, t, r, b = app.rect()
    app.canvas.event_generate("<Shift-MouseWheel>", x=int((l+r)/2), y=int((t+b)/2), delta=120)
    app.root.update()
    assert (app.view[0], app.view[2]) == (before[0], before[2])
    assert app.view[3] - app.view[1] < before[3] - before[1]


def test_narrow_and_custom_ranges_use_physical_axis(reviewer):
    app = reviewer
    app.set_range(2700, 2800)
    actual = np.interp([app.view[1], app.view[3]], np.arange(len(app.ranges)), app.ranges)
    np.testing.assert_allclose(actual, [2800, 2700])
    assert app.range_low.get() == "2700.0"
    assert app.range_high.get() == "2800.0"
    assert app.range_preset.get() == "Свое окно"
    app.range_preset.set("1500–2000")
    app.preset_range()
    actual = np.interp([app.view[1], app.view[3]], np.arange(len(app.ranges)), app.ranges)
    np.testing.assert_allclose(actual, [2000, 1500])
    before = tuple(app.view)
    with pytest.raises(ValueError):
        app.set_range(4000, 1000)
    with pytest.raises(ValueError):
        app.set_range(float('nan'), 1000)
    with pytest.raises(ValueError):
        app.set_range(8000, 9000)
    assert app.view == before
    app.fit()
    assert app.range_preset.get() == "Весь кадр"


def test_blind_pack_blocks_all_automatic_annotation_entry_points(reviewer, monkeypatch):
    app = reviewer
    app.store.manifest['assistance_disabled'] = True
    before = copy.deepcopy(app.document)
    monkeypatch.setattr('ionoreview.app.filedialog.askopenfilename', lambda **kw: pytest.fail('Import opened'))
    app.open_cluster_dialog()
    app.import_candidate()
    app.add_clusters()
    assert app.cluster_window is None
    assert app.document == before


def test_region_zoom_preserves_polygons_and_can_be_cancelled(reviewer):
    app = reviewer
    app.document["shapes"] = [polygon()]
    document = copy.deepcopy(app.document)
    app.vertices = [[5, 5]]  # zooming does not discard a partially drawn shape
    app.tool.set("region")
    start = app.to_canvas(20, 20)
    end = app.to_canvas(60, 50)
    app.click(SimpleNamespace(x=start[0], y=start[1]))
    app.motion(SimpleNamespace(x=end[0], y=end[1]))
    app.release(SimpleNamespace(x=end[0], y=end[1]))
    np.testing.assert_allclose(app.view, (20, 20, 60, 50))
    assert app.tool.get() == "select"
    assert app.document == document
    assert app.vertices == [[5, 5]]
    assert not app.dirty
    before = tuple(app.view)
    app.tool.set("region")
    app.click(SimpleNamespace(x=start[0], y=start[1]))
    app.cancel_polygon()
    assert app.region_start is None
    assert app.view == before


def test_focus_selected_mask_and_transform_at_deep_zoom(reviewer):
    app = reviewer
    app.document["shapes"] = [polygon()]
    app.selected = 0
    app.focus_masks()
    assert app.view[2] - app.view[0] < 50
    assert app.view[3] - app.view[1] < 40
    for point in polygon()["points"]:
        np.testing.assert_allclose(app.to_image(*app.to_canvas(*point)), point, atol=1e-8)
    app.zoom_center(.8)
    assert not app.dirty


def test_remove_last_point_button_and_backspace_preserve_existing_masks(reviewer):
    app = reviewer
    app.document["shapes"] = [polygon()]
    doc = copy.deepcopy(app.document)
    app.vertices = [[10, 10], [20, 10], [25, 15]]
    app.redraw()
    assert str(app.undo_point_button.cget("state")) == "normal"
    app.undo_point_button.invoke()
    assert app.vertices == [[10, 10], [20, 10]]
    app.canvas.focus_force()
    app.root.update()
    app.canvas.event_generate("<BackSpace>")
    app.root.update()
    assert app.vertices == [[10, 10]]
    app.undo()  # Ctrl+Z uses the same last-point behavior while drawing.
    assert app.vertices == []
    assert str(app.undo_point_button.cget("state")) == "disabled"
    app.remove_last_point()
    assert app.document == doc
    assert not app.dirty


def test_paths_follow_current_image_and_help_lists_controls(reviewer):
    from ionoreview.help import HELP_TEXT
    app = reviewer
    assert app.source_path.get().endswith("original.h5")
    assert app.image_path.get() == str(app.store.root / "images/case_001.png")
    assert app.result_path.get() == str(app.store.path(app.item))
    def buttons(widget):
        for child in widget.winfo_children():
            if child.winfo_class() == "TButton":
                yield child.cget("text")
            yield from buttons(child)
    for label in buttons(app.root):
        title = label.split("   ")[0]
        assert title in HELP_TEXT, f"Missing help for button {title}"
    app.policy()
    app.root.update()
    assert app.help_window.winfo_exists()
    first = app.help_window
    app.policy()
    assert app.help_window is first
    app.help_window.destroy()


def test_last_export_path_survives_settings_save(reviewer):
    app = reviewer
    app.export_path.set(str(app.store.root / "accepted_round_1"))
    app.save_settings()
    saved = json.loads((app.store.root / "settings.json").read_text(encoding="utf-8"))
    assert saved["last_export"] == app.export_path.get()


def test_move_whole_polygon_and_group_is_rigid_bounded_and_undoable(reviewer):
    app = reviewer
    first, second = polygon(), polygon()
    first['group_id'] = second['group_id'] = 5
    second['points'] = [[x+30, y+30] for x,y in second['points']]
    app.document['shapes'] = [first, second]
    original = copy.deepcopy(app.document['shapes'])
    app.document['review']['status'] = 'accepted'
    # First click selects; motion moves the entire polygon, not one vertex.
    start = app.to_canvas(20, 20)
    end = app.to_canvas(25, 27)
    app.click(SimpleNamespace(x=start[0], y=start[1]))
    assert not app.dirty
    app.motion(SimpleNamespace(x=end[0], y=end[1]))
    app.release()
    np.testing.assert_allclose(app.document['shapes'][0]['points'],np.asarray(original[0]['points'])+[5,7])
    assert app.document['shapes'][1] == original[1]
    assert app.document['review']['status'] == 'pending'
    assert len(app.undo_stack) == 1
    app.undo()
    assert app.document['shapes'] == original
    app.move_group.set(True)
    app.selected = None
    app.click(SimpleNamespace(x=start[0], y=start[1]))
    far = app.to_canvas(500, 500)
    app.motion(SimpleNamespace(x=far[0], y=far[1]))
    app.release()
    deltas = []
    for before, after in zip(original, app.document['shapes']):
        delta = np.asarray(after['points'])-before['points']
        np.testing.assert_allclose(delta, np.broadcast_to(delta[0], delta.shape))
        deltas.append(delta[0])
        assert np.asarray(after['points']).max(axis=0)[0] <= 99
        assert np.asarray(after['points']).max(axis=0)[1] <= 79
    np.testing.assert_allclose(deltas[0], deltas[1])


def test_cluster_preview_does_not_modify_accepted_then_add_is_reversible(reviewer):
    from ionoreview.clustering import ClusterResult
    app = reviewer
    app.document['shapes'] = [polygon()]
    app.document['review']['status'] = 'accepted'
    before = copy.deepcopy(app.document)
    candidate = polygon()
    candidate['points'] = [[x+40,y+30] for x,y in candidate['points']]
    candidate['group_id'] = 1
    candidate['flags']['proposal_author'] = 'DBSCAN'
    result = ClusterResult([candidate], {'clusters':1,'points':20,'noise_points':2}, {'method':'DBSCAN'}, [0,0,99,79])
    app.show_clusters(result)
    assert app.document == before
    assert not app.dirty
    app.add_clusters()
    assert app.document['shapes'][0] == before['shapes'][0]
    assert len(app.document['shapes']) == 2
    assert app.document['review']['status'] == 'pending'
    assert app.cluster_result is None
    app.label.set('1F')
    app.relabel()
    assert app.document['shapes'][1]['label'] == '1F'
    app.undo()
    app.undo()
    assert app.document['shapes'] == before['shapes']


def test_open_image_folder_switches_pack_and_disables_km_fields(reviewer, tmp_path, monkeypatch):
    app = reviewer
    source = tmp_path/'ordinary_images'
    source.mkdir()
    Image.new('RGB',(100,80),'navy').save(source/'one.jpg')
    parent = tmp_path/'work'
    parent.mkdir()
    answers = iter([str(source),str(parent)])
    monkeypatch.setattr('ionoreview.app.filedialog.askdirectory',lambda **kwargs:next(answers))
    monkeypatch.setattr('ionoreview.app.messagebox.showerror',lambda *a:pytest.fail(str(a)))
    app.open_folder()
    app.root.update()
    assert app.db is None
    assert app.item['original_name']=='one.jpg'
    assert app.store.root.parent==parent
    assert app.source_path.get()==str(source/'one.jpg')
    assert all(str(w.cget('state'))=='disabled' for w in app.range_controls)
    assert app.store.path(app.item).parent.name=='annotations'


def test_open_annotations_subfolder_keeps_images_axes_and_existing_labels(reviewer, pack, tmp_path, monkeypatch):
    from ionoreview.folders import copy_pack
    destination = copy_pack(pack.root, tmp_path/'student_return')
    store = ReviewStore(destination)
    item = store.items[0]
    document = store.blank(item)
    document['shapes'] = [dict(polygon(), label='1F')]
    document['review'].update(status='accepted', reviewer='Student')
    store.save(item, document)
    before = digest(store.path(item))
    selections = []
    def choose(**kwargs):
        selections.append(kwargs)
        return str(destination/'annotations')
    monkeypatch.setattr('ionoreview.app.filedialog.askdirectory', choose)
    monkeypatch.setattr('ionoreview.app.messagebox.showerror', lambda *a,**kw: pytest.fail(str(a)))
    reviewer.open_folder()
    reviewer.root.update()
    assert len(selections) == 1
    assert reviewer.store.root == destination
    assert reviewer.document['shapes'][0]['label'] == '1F'
    assert reviewer.db is not None
    assert digest(store.path(item)) == before


def test_folder_wrapper_resolves_dataset_but_rejects_ambiguous_splits(pack, tmp_path):
    from ionoreview.folders import copy_pack, resolve_pack_folder
    wrapper = tmp_path/'delivery'
    destination = copy_pack(pack.root, wrapper/'dataset')
    assert resolve_pack_folder(wrapper) == destination
    assert resolve_pack_folder(destination/'arrays') == destination
    other = tmp_path/'multiple'
    copy_pack(pack.root, other/'train')
    copy_pack(pack.root, other/'test')
    with pytest.raises(ValueError, match='несколько наборов'):
        resolve_pack_folder(other)


def test_catalog_can_open_returned_student_folder_outside_catalog(pack, tmp_path, tk_root, monkeypatch):
    from tkinter import ttk
    from ionoreview.library import choose
    atomic_json(tmp_path/'catalog.json', {'schema':'ionoreview-library/1','datasets':[]})
    monkeypatch.setattr('ionoreview.library.filedialog.askdirectory', lambda **kw: str(pack.root/'arrays'))
    monkeypatch.setattr('ionoreview.library.messagebox.showerror', lambda *a,**kw: pytest.fail(str(a)))
    def select_other():
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        window = next(w for w in tk_root.winfo_children() if isinstance(w,tk.Toplevel))
        next(w for w in descendants(window) if isinstance(w,ttk.Button) and w.cget('text')=='Открыть другую папку…').invoke()
    tk_root.after(50, select_other)
    assert choose(tk_root,tmp_path) == pack.root


def test_clustering_worker_returns_pixel_candidates_without_touching_annotations(reviewer, tmp_path):
    import time
    from ionoreview.folders import import_image_folder
    from ionoreview.clustering import ClusterParams
    app = reviewer
    source = tmp_path/'images'
    source.mkdir()
    from PIL import ImageDraw
    image=Image.new('RGB',(100,80),'blue')
    draw=ImageDraw.Draw(image)
    draw.rectangle((10,15,80,18),fill='yellow')
    draw.rectangle((10,55,80,58),fill='yellow')
    image.save(source/'signal.png')
    app.switch_pack(import_image_folder(source,tmp_path/'pack_png'))
    before=copy.deepcopy(app.document)
    params=ClusterParams(threshold_db=100,frequency_gap_mhz=3,range_gap_km=3,
                         min_span_mhz=5,coordinate_units='pixels')
    app.start_clustering(params)
    deadline=time.monotonic()+15
    while app.cluster_busy and time.monotonic()<deadline:
        app.root.update()
        time.sleep(.01)
    assert not app.cluster_busy
    assert app.cluster_result.stats['clusters']==2
    assert app.document==before
    assert not app.dirty
    assert not app.store.path(app.item).exists()


def three_polygons():
    first,second,third=polygon(),polygon(),polygon()
    second['points']=[[x+30,y+30] for x,y in second['points']]
    third['points']=[[85,65],[98,65],[98,78],[85,78]]
    return [first,second,third]


def box_select(app, a=(5,5), b=(75,62), state=0):
    app.tool.set('multi')
    start,end=app.to_canvas(*a),app.to_canvas(*b)
    app.click(SimpleNamespace(x=start[0],y=start[1],state=state))
    app.motion(SimpleNamespace(x=end[0],y=end[1]))
    app.release(SimpleNamespace(x=end[0],y=end[1]))
    app.root.update()


def test_box_selection_shows_inline_menu_and_bulk_label_is_one_undo(reviewer):
    app=reviewer
    app.document['shapes']=three_polygons()
    before=copy.deepcopy(app.document['shapes'])
    box_select(app)
    assert app.selection=={0,1}
    assert app.label_menu.winfo_ismapped()
    assert not app.dirty
    app.apply_label('2F')
    assert [s['label'] for s in app.document['shapes']]==['2F','2F','Signal']
    assert len(app.undo_stack)==1
    assert not app.label_menu.winfo_ismapped()
    app.undo()
    assert app.document['shapes']==before


def test_ctrl_click_and_list_multi_selection(reviewer):
    app=reviewer
    app.document['shapes']=three_polygons()
    app.refresh_objects()
    app.tool.set('select')
    for point,state in (((20,20),0),((50,50),4)):
        x,y=app.to_canvas(*point)
        app.click(SimpleNamespace(x=x,y=y,state=state))
        app.release(SimpleNamespace(x=x,y=y))
    assert app.selection=={0,1}
    x,y=app.to_canvas(20,20)
    app.click(SimpleNamespace(x=x,y=y,state=4))
    app.release()
    assert app.selection=={1}
    app.objects.selection_clear(0,'end')
    app.objects.selection_set(0)
    app.objects.selection_set(2)
    app.choose_object()
    assert app.selection=={0,2}


def candidate_result():
    from ionoreview.clustering import ClusterResult
    shapes=three_polygons()
    for i,s in enumerate(shapes):
        s['group_id']=i+1
        s['flags']['proposal_author']='K-means'
    return ClusterResult(shapes,{'clusters':3,'points':90,'noise_points':0},
                         {'method':'K-means'},[0,0,99,79])


def test_label_selected_candidates_materializes_only_selection_and_undo_restores_preview(reviewer):
    app=reviewer
    app.show_clusters(candidate_result())
    before=copy.deepcopy(app.document)
    box_select(app)
    assert app.selected_candidates=={0,1}
    assert app.document==before
    app.apply_label('1F')
    assert len(app.document['shapes'])==2
    assert all(s['label']=='1F' for s in app.document['shapes'])
    assert len(app.cluster_result.shapes)==1
    assert app.document['review']['status']=='pending'
    assert not app.store.path(app.item).exists()
    app.undo()
    assert app.document['shapes']==before['shapes']
    assert len(app.cluster_result.shapes)==3


def test_partial_group_label_detaches_selected_parts_and_group_button_expands(reviewer):
    app=reviewer
    app.document['shapes']=three_polygons()
    for i,s in enumerate(app.document['shapes']):
        s['group_id']=9 if i<2 else 10
    app.set_selection([0])
    app.apply_label('E')
    assert app.document['shapes'][0]['group_id']!=9
    assert app.document['shapes'][1]['label']=='Signal'
    app.undo()
    app.set_selection([0])
    app.expand_group_selection()
    assert app.selection=={0,1}
    app.apply_label('2F')
    assert all(s['label']=='2F' for s in app.document['shapes'][:2])
    assert app.document['shapes'][2]['label']=='Signal'


def test_reject_preview_and_undo_do_not_dirty_document(reviewer):
    app=reviewer
    app.show_clusters(candidate_result())
    before=copy.deepcopy(app.document)
    app.set_selection((),[0,1])
    app.delete_shape()
    assert len(app.cluster_result.shapes)==1
    assert not app.dirty
    app.undo()
    assert len(app.cluster_result.shapes)==3
    assert app.document==before
    assert not app.dirty


def test_labelling_repeated_candidate_reuses_existing_mask(reviewer):
    app=reviewer
    result=candidate_result()
    app.document['shapes']=[copy.deepcopy(result.shapes[0])]
    app.show_clusters(result)
    app.set_selection((),[0])
    app.apply_label('1F')
    assert len(app.document['shapes'])==1
    assert app.document['shapes'][0]['label']=='1F'
    assert len(app.cluster_result.shapes)==2
    app.undo()
    assert len(app.cluster_result.shapes)==3
    assert len(app.document['shapes'])==1
    assert app.document['shapes'][0]['label']=='Signal'


def test_reviewer_paints_ionogram_in_greys_by_default(reviewer):
    from PIL import ImageTk
    reviewer.redraw()
    image = ImageTk.getimage(reviewer.photo).convert("RGB")
    red, green, blue = image.getpixel((image.width * 3 // 4, image.height * 3 // 4))
    assert red == green == blue, "Default reviewer view is not a grey ionogram"


def test_reviewer_paints_ionogram_in_turbo_when_chosen(reviewer):
    from PIL import ImageTk
    reviewer.palette_name.set("Turbo")
    reviewer.redraw()
    image = ImageTk.getimage(reviewer.photo).convert("RGB")
    red, green, blue = image.getpixel((image.width * 3 // 4, image.height * 3 // 4))
    assert not red == green == blue, "Turbo choice still leaves the ionogram grey"


CYRILLIC = re.compile("[А-Яа-яЁё]")
OWN_LANGUAGE_NAMES = {"Русский"}


def visible_texts(app):
    def walk(widget):
        if isinstance(widget, tk.Menu):
            last = widget.index("end")
            for position in range(0 if last is not None else 1, (last or -1) + 1):
                if widget.type(position) not in ("separator", "tearoff"):
                    yield widget.entrycget(position, "label")
        elif "text" in widget.keys():
            yield str(widget.cget("text"))
        if isinstance(widget, tk.Listbox):
            yield from widget.get(0, "end")
        for child in widget.winfo_children():
            if not isinstance(child, tk.Toplevel):
                yield from walk(child)
    yield app.root.title()
    yield app.range_preset.get()
    yield from walk(app.root)


def leftovers(app):
    return sorted({t for t in visible_texts(app) if CYRILLIC.search(t) and t not in OWN_LANGUAGE_NAMES})


def test_interface_starts_in_russian(reviewer):
    assert reviewer.language.get() == "ru", "Default interface language is not Russian"


def test_english_choice_translates_every_visible_text(reviewer):
    reviewer.set_language("en")
    reviewer.root.update()
    assert not leftovers(reviewer), f"Cyrillic left in the English interface: {leftovers(reviewer)}"


def test_english_choice_keeps_widgets_working(reviewer):
    reviewer.set_language("en")
    reviewer.document["shapes"] = [polygon()]
    reviewer.refresh_objects()
    reviewer.set_selection([0])
    reviewer.apply_label("1F")
    assert reviewer.feedback.cget("text") == "Label 1F assigned to polygons: 1", "Feedback is not English after applying a label"


def test_english_status_texts_cover_every_review_status(reviewer):
    from ionoreview.app import STATUS
    reviewer.set_language("en")
    assert not any(CYRILLIC.search(reviewer.t(text)) for text in STATUS.values()), "A review status stays Russian in English"


def test_english_messages_after_actions_are_free_of_cyrillic(reviewer):
    reviewer.set_language("en")
    reviewer.focus_masks()
    reviewer.document["shapes"] = [polygon()]
    reviewer.refresh_objects()
    reviewer.changed()
    reviewer.set_range(1500, 2500)
    reviewer.root.update()
    assert not leftovers(reviewer), f"Cyrillic appeared after actions: {leftovers(reviewer)}"


def test_returning_to_russian_restores_every_text(reviewer):
    before = list(visible_texts(reviewer))
    reviewer.set_language("en")
    reviewer.set_language("ru")
    assert list(visible_texts(reviewer)) == before, "Russian texts differ after a round trip"


def test_unknown_language_choice_is_rejected(reviewer):
    with pytest.raises(ValueError, match="de"):
        reviewer.set_language("de")


def test_language_choice_survives_a_new_session(reviewer, pack, tk_root):
    from ionoreview.app import Reviewer
    reviewer.set_language("en")
    reviewer.save_settings()
    root = tk.Toplevel(tk_root)
    try:
        assert Reviewer(root, pack.root).language.get() == "en", "Saved English choice was forgotten"
    finally:
        destroy_test_window(root)


def test_language_choice_is_written_to_settings(reviewer):
    reviewer.set_language("en")
    saved = json.loads((reviewer.store.root / "settings.json").read_text(encoding="utf-8"))
    assert saved["language"] == "en", "Settings do not record the language"


def test_language_menu_offers_both_languages(reviewer):
    menu = reviewer.language_menu
    assert [menu.entrycget(i, "label") for i in range(menu.index("end") + 1)] == ["Русский", "English"], "Language menu entries are wrong"


def test_every_button_is_described_in_the_english_help(reviewer):
    from ionoreview.help import HELP_TEXT_EN
    reviewer.set_language("en")
    def buttons(widget):
        for child in widget.winfo_children():
            if child.winfo_class() == "TButton":
                yield child.cget("text")
            yield from buttons(child)
    missing = [t.split("   ")[0] for t in buttons(reviewer.root) if t.split("   ")[0] not in HELP_TEXT_EN]
    assert not missing, f"English help lacks buttons: {missing}"


def test_help_window_follows_the_chosen_language(reviewer):
    reviewer.set_language("en")
    reviewer.policy()
    reviewer.root.update()
    shown = reviewer.help_window.winfo_children()
    text = next(w for w in shown if isinstance(w, tk.Text)).get("1.0", "end")
    reviewer.help_window.destroy()
    assert "REVIEWING IONOGRAMS" in text, "Help window ignored the English choice"


def test_open_help_window_is_retranslated_on_language_change(reviewer):
    reviewer.policy()
    reviewer.set_language("en")
    reviewer.root.update()
    text = next(w for w in reviewer.help_window.winfo_children() if isinstance(w, tk.Text)).get("1.0", "end")
    reviewer.help_window.destroy()
    assert "REVIEWING IONOGRAMS" in text, "Open help window stayed Russian"


def test_english_help_is_free_of_cyrillic_except_manifest_policy():
    from ionoreview.help import HELP_TEXT_EN
    assert not CYRILLIC.search(HELP_TEXT_EN), "English help contains Cyrillic text"


def test_guide_button_and_menu_open_one_scrollable_window(reviewer):
    reviewer.show_guide()
    reviewer.root.update()
    first = reviewer.guide.window
    reviewer.show_guide()
    assert reviewer.guide.window is first, "Second request opened another guide window"
    first.destroy()


def test_guide_window_embeds_every_example_image(reviewer):
    from ionoreview.guide import images
    reviewer.show_guide()
    reviewer.root.update()
    count = len(reviewer.guide.text.image_names())
    reviewer.guide.window.destroy()
    assert count == len(images("ru")), "Guide window lacks some example images"


def test_guide_window_scrolls(reviewer):
    reviewer.show_guide()
    reviewer.root.update()
    scrolled = reviewer.guide.text.cget("yscrollcommand")
    reviewer.guide.window.destroy()
    assert scrolled, "Guide text is not tied to a scrollbar"


def test_guide_window_follows_language_change(reviewer):
    reviewer.show_guide()
    reviewer.set_language("en")
    reviewer.root.update()
    text = reviewer.guide.text.get("1.0", "end")
    reviewer.guide.window.destroy()
    assert "nose" in text and "носик" not in text, "Open guide did not switch to English"


def test_guide_is_reachable_from_a_button(reviewer):
    def buttons(widget):
        for child in widget.winfo_children():
            if child.winfo_class() == "TButton":
                yield child.cget("text")
            yield from buttons(child)
    assert "Правила разметки" in list(buttons(reviewer.root)), "No guide button in the top bar"


def test_every_guide_button_is_described_in_the_russian_help():
    from ionoreview.help import HELP_TEXT
    assert "Правила разметки" in HELP_TEXT and "Язык" in HELP_TEXT, "Russian help does not mention the guide and language menu"
