"""Build a portable image pack through the existing scientific loader."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import warnings

import numpy as np
from PIL import Image
from matplotlib import colormaps

from .data import atomic_json, digest, utcnow

POLICY = (
    "Полигоны охватывают видимую полосу полезного эха, а не всю площадь между ветвями. "
    "Соседние ветви и явно разорванные участки размечаются отдельными полигонами; "
    "для частей одной моды задаётся общий group_id. Сомнительный класс остаётся Signal. "
    "Классы 1E/1F/2F подтверждает эксперт. Помехи можно выделять как Interference. "
    "Не дорисовывать невидимые продолжения. Принятие пустого сигнала требует отметки no_signal."
)


PROJECT = Path(__file__).resolve().parent.parent / "vendor" / "ionograms_handler"
SOUNDINGS = {".h5", ".lfs"}


def measurements(folder):
    return sorted(p for p in Path(folder).rglob("*") if p.is_file() and p.suffix.lower() in SOUNDINGS)


def project_folder(parent, source):
    from .folders import unique_folder
    target = Path(parent) / f"{Path(source).name}_проект"
    return unique_folder(parent, target.name) if target.exists() else target


class PreparationCancelled(Exception):
    pass


def prepare(paths, output, project=None, gate=(0, 8000), progress=None, cancelled=None):
    paths = list(paths)
    if not paths:
        raise ValueError("В папке нет файлов H5 или LFS")
    if not np.isfinite(gate).all() or len(gate) != 2 or gate[0] >= gate[1]:
        raise ValueError("Неверный диапазон дальности")
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Набор уже существует. Выберите новую папку")
    try:
        from muf import loader
    except ImportError:
        sys.path.insert(0, str(Path(project or PROJECT).resolve()))
        from muf import loader

    output.mkdir(parents=True)
    (output / "images").mkdir()
    (output / "arrays").mkdir()
    items, errors, valid_paths = [], [], []
    days = set()
    for path in paths:
        if cancelled and cancelled():
            break
        try:
            days.add(loader.read_header(path).datetime.date().isoformat())
            valid_paths.append(path)
        except Exception as exc:
            errors.append({"source": str(path), "error": str(exc)})
    dates = sorted(days)
    # A day is never split across training, validation and test.
    splits = {day: "train" for day in dates}
    if len(dates) >= 2:
        splits[dates[-1]] = "test"
    if len(dates) >= 3:
        splits[dates[-2]] = "validation"
    for number, path in enumerate(valid_paths, 1):
        if cancelled and cancelled():
            break
        path = Path(path).resolve()
        try:
            with warnings.catch_warnings(record=True) as recorded:
                ion = loader.load(path, gate_km=gate)
            # Matrix pixel centres are the coordinate authority; no plot
            # margins, labels or interpolation baked into annotation images.
            db = np.asarray(ion.db.T, dtype=np.float32)
            freq, ranges = np.asarray(ion.freq), np.asarray(ion.vrange)
            if freq[0] > freq[-1]:
                db, freq = db[:, ::-1], freq[::-1]
            if ranges[0] < ranges[-1]:
                db, ranges = db[::-1], ranges[::-1]
            if not np.all(np.diff(freq) > 0) or not np.all(np.diff(ranges) < 0):
                raise ValueError("Оси не монотонны")
            ident = f"case_{number:03d}"
            image_file = f"images/{ident}.png"
            array_file = f"arrays/{ident}.npz"
            shown = np.clip((np.nan_to_num(db, nan=15.0) - 15) / 45, 0, 1)
            Image.fromarray(colormaps["turbo"](shown, bytes=True)[:, :, :3]).save(output / image_file)
            np.savez_compressed(output / array_file, db=db, freq_mhz=freq, range_km=ranges)
            source_stat = path.stat()
            day = ion.header.datetime.date().isoformat()
            item = {"id": ident, "image": image_file, "axes": array_file,
                    "width": int(db.shape[1]), "height": int(db.shape[0]),
                    "axes_sha256": digest(output / array_file),
                    "image_sha256": digest(output / image_file),
                    "source": str(path), "source_sha256": digest(path),
                    "source_bytes": source_stat.st_size,
                    "source_mtime_ns": source_stat.st_mtime_ns,
                    "when": ion.header.datetime.isoformat(),
                    "tx": ion.header.tx_name, "rx": ion.header.rx_name,
                    "split": splits[day],
                    "range_is_relative": bool(getattr(ion.header, "range_is_relative", False)),
                    "warnings": [str(w.message) for w in recorded],
                    "render": {"colormap": "turbo", "vmin": 15, "vmax": 60,
                               "matrix": "ion.db.T", "filters": "none"}}
            items.append(item)
            print(f"{ident}: {path.name} -> {db.shape[1]}x{db.shape[0]} [{splits[day]}]", flush=True)
        except Exception as exc:
            errors.append({"source": str(path), "error": str(exc)})
            print(f"SKIP {path}: {exc}", flush=True)
        if progress is not None:
            progress(number, len(valid_paths), path.name)
    atomic_json(output / "manifest.json", {"schema": "ionoreview/1", "created_at": utcnow(),
                "loader_project": str(Path(project or PROJECT).resolve()), "items": items,
                "annotation_policy": POLICY, "errors": errors,
                "cancelled": bool(cancelled and cancelled()),
                "sampling": "user-selected source files; splits assigned by whole UTC days"})
    if cancelled and cancelled():
        raise PreparationCancelled(f"Подготовка остановлена. Сохранено изображений: {len(items)}.\nПапка: {output}")
    if not items:
        raise ValueError("Не удалось подготовить ни одного изображения; см. manifest.json")
    return items


def main(argv=None):
    parser = argparse.ArgumentParser(description="Подготовка набора для приёмки")
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parent.parent/'vendor/ionograms_handler')
    parser.add_argument("--gate", nargs=2, type=float, default=(0, 8000))
    args = parser.parse_args(argv)
    prepare(args.files, args.out, args.project, tuple(args.gate))


if __name__ == "__main__":
    main()
