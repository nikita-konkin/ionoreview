"""Create self-contained review packs from ordinary image folders."""
from datetime import datetime
from pathlib import Path
import shutil

from PIL import Image, ImageOps

from .data import ReviewStore, atomic_json, digest, utcnow

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


def import_image_folder(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    files = sorted(p for p in source.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)
    if not files:
        raise ValueError("В папке нет PNG, JPEG, BMP или TIFF")
    if len(files) > 1000:
        raise ValueError("Больше 1000 изображений. Выберите папку с меньшей партией")
    if destination.exists():
        raise ValueError("Рабочая папка уже существует")
    destination.mkdir(parents=True)
    (destination / "images").mkdir()
    (destination / "annotations").mkdir()
    items, errors = [], []
    for index, path in enumerate(files, 1):
        try:
            with Image.open(path) as opened:
                if opened.width * opened.height > 30_000_000:
                    raise ValueError("Изображение больше 30 миллионов пикселей")
                # Apply EXIF orientation once; annotation/export use this PNG.
                image = ImageOps.exif_transpose(opened).convert("RGB")
            ident = f"image_{index:04d}"
            relative = f"images/{ident}.png"
            image.save(destination / relative)
            items.append({"id": ident, "image": relative, "width": image.width,
                "height": image.height, "image_sha256": digest(destination / relative),
                "source": str(path), "source_sha256": digest(path),
                "source_bytes": path.stat().st_size, "axes": None,
                "when": "", "tx": "", "rx": "", "split": "unassigned",
                "source_kind": "image", "original_name": path.name})
        except Exception as exc:
            errors.append({"source": str(path), "error": str(exc)})
    atomic_json(destination / "manifest.json", {"schema": "ionoreview/1", "created_at": utcnow(),
        "source_folder": str(source), "items": items, "errors": errors,
        "annotation_policy": "Размечайте видимую полосу сигнала. Нет числовых осей: координаты только в пикселях. "
                             "Кластеры требуют ручной проверки и назначения классов. "
                             "Все изображения пока unassigned; назначьте независимый тест до обучения."})
    if not items:
        raise ValueError("Нет читаемых изображений; ошибки записаны в manifest.json")
    store = ReviewStore(destination)
    for item in items:
        sidecar = Path(item["source"]).with_suffix(".json")
        if sidecar.is_file():
            try:
                store.import_labelme(item, sidecar, "LabelMe (import)")
            except Exception as exc:
                errors.append({"source": str(sidecar), "error": str(exc)})
    store.manifest["errors"] = errors
    atomic_json(destination / "manifest.json", store.manifest)
    return destination


def copy_pack(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination == source or source in destination.parents:
        raise ValueError("Новая рабочая папка должна быть вне текущего набора")
    if destination.exists():
        raise ValueError("Выберите новую папку; существующие наборы не перезаписываются")
    shutil.copytree(source, destination)
    return destination


def unique_folder(parent, stem):
    return Path(parent) / ("ionoreview_" + stem + "_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
