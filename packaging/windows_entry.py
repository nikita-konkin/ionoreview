"""Portable GUI entry point; user datasets always remain outside the bundle."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import traceback

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def application_directory():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def initial_folder(explicit=None):
    """Use the executable location, never PyInstaller's temporary/internal root."""
    return Path(explicit).resolve() if explicit else application_directory() / "datasets"


def _console_fallbacks():
    # PyInstaller --windowed intentionally makes these None. Libraries can
    # still emit warnings or progress output, so give them a valid stream.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        folder = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "IonoReview"
        folder.mkdir(parents=True, exist_ok=True)
        sys.stderr = open(folder / "runtime.log", "a", encoding="utf-8")


def launch(folder):
    import tkinter as tk
    from tkinter import filedialog, messagebox
    from ionoreview.app import Reviewer
    from ionoreview.library import choose
    from ionoreview.folders import resolve_pack_folder, require_image_files, import_image_folder, unique_folder

    root = tk.Tk()
    root.withdraw()
    library_root = initial_folder()

    class PortableReviewer(Reviewer):
        def open_library(self, folder=None):
            destination = Path(folder) if folder else library_root
            if not (destination / "catalog.json").is_file():
                selected = filedialog.askdirectory(parent=self.root, title="Каталог наборов с catalog.json")
                if not selected:
                    return
                destination = Path(selected)
            return super().open_library(destination)

    try:
        destination = Path(folder)
        while True:
            if (destination / "catalog.json").is_file():
                library_root = destination
                destination = choose(root, destination)
                if destination is None:
                    root.destroy()
                    return 0
                break
            if destination.is_dir():
                try:
                    pack = resolve_pack_folder(destination)
                    if pack is not None:
                        destination = pack
                        if (destination.parent / "catalog.json").is_file():
                            library_root = destination.parent
                        break
                    require_image_files(destination)
                    output = filedialog.askdirectory(parent=root, title="Где создать рабочий набор и сохранять разметку?")
                    if output:
                        destination = import_image_folder(destination, unique_folder(output, "images"))
                        break
                except ValueError as exc:
                    messagebox.showinfo("ИоноРазметка", str(exc), parent=root)
            selected = filedialog.askdirectory(parent=root, title="Выберите набор, каталог или папку изображений")
            if not selected:
                root.destroy()
                return 0
            destination = Path(selected)
        root.deiconify()
        PortableReviewer(root, destination)
        root.mainloop()
        return 0
    except Exception:
        root.destroy()
        raise


def self_test(report_path):
    """Exercise frozen imports, native libraries, Tk, arrays and annotation IO."""
    import tempfile
    import tkinter as tk
    import numpy as np
    import cv2
    import scipy
    import sklearn
    from PIL import Image
    from matplotlib import colormaps
    from ionoreview.app import Reviewer
    from ionoreview.clustering import ClusterParams, cluster_ionogram
    from ionoreview.data import ReviewStore, atomic_json, digest
    from ionoreview.folders import resolve_pack_folder, copy_pack
    from ionoreview import __version__

    with tempfile.TemporaryDirectory(prefix="ionoreview-selftest-") as temp:
        # Windows CI can supply TEMP through an 8.3 alias or a junction.
        # Pack resolution returns canonical paths, so compare canonical roots.
        temporary_root = Path(temp).resolve()
        pack = temporary_root / "pack"
        (pack / "images").mkdir(parents=True)
        (pack / "arrays").mkdir()
        db = np.full((80, 100), 20, dtype=np.float32)
        db[25:30, 10:40] = 55
        db[55:60, 60:90] = 55
        rgb = colormaps["turbo"](np.clip((db - 15) / 45, 0, 1), bytes=True)[:, :, :3]
        Image.fromarray(rgb).save(pack / "images/synthetic.png")
        freq = np.linspace(5, 25, 100)
        ranges = np.linspace(4000, 1000, 80)
        import zipfile
        with zipfile.ZipFile(pack / "arrays/synthetic.npz", "w", compression=zipfile.ZIP_LZMA) as archive:
            for name, value in {"db": db, "freq_mhz": freq, "range_km": ranges}.items():
                with archive.open(name + ".npy", "w") as stream:
                    np.lib.format.write_array(stream, value, allow_pickle=False)
        item = {"id": "synthetic", "image": "images/synthetic.png", "axes": "arrays/synthetic.npz",
                "width": 100, "height": 80, "source": "synthetic self-test",
                "image_sha256": digest(pack / "images/synthetic.png"),
                "axes_sha256": digest(pack / "arrays/synthetic.npz"), "split": "train"}
        atomic_json(pack / "manifest.json", {"schema": "ionoreview/1", "items": [item]})
        cluster_counts = {}
        for method in ("DBSCAN", "K-means"):
            result = cluster_ionogram(db, freq, ranges, (0, 0, 99, 79),
                ClusterParams(method=method, n_clusters=2, frequency_gap_mhz=.5,
                              range_gap_km=50, min_span_mhz=.1))
            assert result.stats["clusters"] == 2, result.stats
            assert result.shapes
            cluster_counts[method] = result.stats["clusters"]
        store = ReviewStore(pack)
        doc = store.blank(item)
        doc["shapes"] = [{"label": "Signal", "points": [[10, 25], [40, 25], [40, 30], [10, 30]],
                          "shape_type": "polygon", "group_id": None, "flags": {}}]
        doc["review"].update(status="accepted", reviewer="synthetic self-test")
        store.save(item, doc)
        assert store.export(Path(temp) / "export") == 1
        annotation_hash = digest(store.path(item))
        for part in ('images', 'arrays', 'annotations'):
            assert resolve_pack_folder(pack / part) == pack
        wrapper = temporary_root / 'delivery'
        other_pack = copy_pack(pack, wrapper / 'dataset')
        assert resolve_pack_folder(wrapper) == other_pack
        root = tk.Tk()
        root.withdraw()
        try:
            reviewer = Reviewer(root, pack)
            root.update_idletasks()
            assert reviewer.item["id"] == "synthetic"
            assert reviewer.original_image.size == (100, 80)
            assert reviewer.db.shape == (80, 100)
            assert reviewer.switch_pack(other_pack)
            root.update_idletasks()
            assert reviewer.store.root == other_pack
            assert reviewer.document['shapes'][0]['label'] == 'Signal'
            assert digest(store.path(item)) == annotation_hash
            assert digest(ReviewStore(other_pack).path(item)) == annotation_hash
        finally:
            root.destroy()
        report = {"ok": True, "frozen": bool(getattr(sys, "frozen", False)), "application_version": __version__,
                  "application_directory": str(application_directory()), "clusters": cluster_counts,
                  "versions": {"numpy": np.__version__, "opencv": cv2.__version__,
                               "scipy": scipy.__version__, "sklearn": sklearn.__version__},
                  "checks": ["native imports", "PNG/NPZ", "DBSCAN", "K-means", "annotation IO", "Tk startup",
                             "pack subfolders", "delivery wrapper", "pack switching", "annotations preserved"]}
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    return 0


def main(argv=None):
    _console_fallbacks()
    parser = argparse.ArgumentParser(description="ИоноРазметка — portable Windows GUI")
    parser.add_argument("--data-root", type=Path, help="External dataset library, pack, or image folder")
    parser.add_argument("--self-test", type=Path, metavar="REPORT_JSON", help="Run a noninteractive build self-test and exit")
    args = parser.parse_args(argv)
    try:
        return self_test(args.self_test) if args.self_test else launch(initial_folder(args.data_root))
    except Exception as exc:
        if args.self_test:
            args.self_test.parent.mkdir(parents=True, exist_ok=True)
            args.self_test.write_text(json.dumps({"ok": False, "error": str(exc), "traceback": traceback.format_exc()},
                                                ensure_ascii=True, indent=2), encoding="utf-8")
        else:
            from tkinter import messagebox
            location = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "IonoReview" / "last-error.log"
            location.parent.mkdir(parents=True, exist_ok=True)
            location.write_text(traceback.format_exc(), encoding="utf-8")
            messagebox.showerror("ИоноРазметка", f"Не удалось открыть редактор.\n{exc}\nПодробности: {location}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
