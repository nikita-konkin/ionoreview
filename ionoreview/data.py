"""Review storage and LabelMe interchange. No network or source-file writes."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import time
import uuid
from datetime import datetime, timezone

LABELS = ("Signal", "1E", "1F", "2F", "3F", "E", "Es", "Interference")
STATUSES = {"pending", "accepted", "changes", "ambiguous"}
DRAFT_NOTE = (
    "Черновик ассистента. Проверить границы полос, пропущенные слабые участки "
    "и объединение ветвей в группы. Классы мод не установлены; "
    "до проверки не использовать как эталон."
)


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with open(temp, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        # Windows readers/antivirus can briefly deny replacement of an open file.
        # Retain atomic replacement and the previous valid document while retrying.
        for attempt in range(12):
            try:
                os.replace(temp, path)
                break
            except PermissionError as exc:
                if getattr(exc, 'winerror', None) not in {5, 32, 33} or attempt == 11:
                    raise
                time.sleep(min(0.01 * 2 ** attempt, 0.25))
    finally:
        temp.unlink(missing_ok=True)


def read_json(path):
    with open(path, encoding="utf-8-sig") as stream:
        return json.load(stream)


def safe_child(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if path == root or root not in path.parents:
        raise ValueError("Путь выходит за пределы набора")
    return path


def validate_shapes(shapes, width, height):
    if not isinstance(shapes, list):
        raise ValueError("shapes должен быть списком")
    result = copy.deepcopy(shapes)
    for shape in result:
        if shape.get("label") not in LABELS:
            raise ValueError(f"Неизвестный класс: {shape.get('label')}")
        if shape.get("shape_type", "polygon") != "polygon":
            raise ValueError("Поддерживаются только полигоны LabelMe")
        points = shape.get("points", [])
        if len(points) < 3:
            raise ValueError("В полигоне должно быть не менее трёх вершин")
        for point in points:
            if len(point) != 2 or any(
                isinstance(v, bool) or not isinstance(v, (int, float))
                or not math.isfinite(v) for v in point
            ):
                raise ValueError("Координаты должны быть конечными числами")
            if not (0 <= point[0] <= width - 1 and 0 <= point[1] <= height - 1):
                raise ValueError("Вершина выходит за размеры изображения")
        area = abs(sum(
            points[i][0] * points[(i + 1) % len(points)][1]
            - points[(i + 1) % len(points)][0] * points[i][1]
            for i in range(len(points))
        )) / 2
        if area < 0.5:
            raise ValueError("Полигон имеет нулевую или слишком малую площадь")
        shape.setdefault("flags", {})
        shape.setdefault("group_id", None)
        shape["shape_type"] = "polygon"
    return result


class ReviewStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.manifest = read_json(self.root / "manifest.json")
        if self.manifest.get("schema") != "ionoreview/1":
            raise ValueError("Неподдерживаемый формат manifest.json")
        self.items = self.manifest["items"]
        ids = [item["id"] for item in self.items]
        if len(ids) != len(set(ids)) or not ids:
            raise ValueError("Набор пуст или содержит повторяющиеся id")
        for item in self.items:
            if not item["id"] or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in item["id"]):
                raise ValueError("Некорректный id")
            safe_child(self.root, item["image"])
            if item.get("axes"):
                safe_child(self.root, item["axes"])

    def path(self, item):
        return self.root / "annotations" / (item["id"] + ".json")

    def blank(self, item):
        return {
            "version": "5.5.0", "flags": {}, "shapes": [],
            "imagePath": "../" + item["image"], "imageData": None,
            "imageWidth": item["width"], "imageHeight": item["height"],
            "review": {"status": "pending", "reviewer": "", "note": "",
                       "no_signal": False, "revision": 0},
            "provenance": {"source": item["source"],
                           "image_sha256": item["image_sha256"],
                           "coordinate_system": "image pixels; origin top-left; x=frequency, y=range"},
        }

    def load(self, item):
        path = self.path(item)
        value = read_json(path) if path.exists() else self.blank(item)
        self.validate(item, value)
        return value

    def validate(self, item, value):
        if (value.get("imageWidth"), value.get("imageHeight")) != (item["width"], item["height"]):
            raise ValueError("Размеры аннотации не совпадают с изображением")
        validate_shapes(value.get("shapes"), item["width"], item["height"])
        review = value.get("review", {})
        status = review.get("status")
        if status not in STATUSES:
            raise ValueError("Неизвестный статус")
        signals = [s for s in value["shapes"] if s["label"] != "Interference"]
        if review.get("no_signal") and signals:
            raise ValueError("Отметка «нет сигнала» противоречит полигонам сигнала")
        if status == "accepted":
            if not str(review.get("reviewer", "")).strip():
                raise ValueError("Для приёмки укажите имя эксперта")
            if not signals and not review.get("no_signal"):
                raise ValueError("Пустой результат требует явной отметки «нет сигнала»")
        if status in {"changes", "ambiguous"} and not str(review.get("note", "")).strip():
            raise ValueError("Для исправления или неоднозначного случая нужен комментарий")

    def save(self, item, value):
        self.validate(item, value)
        if digest(safe_child(self.root, item["image"])) != item["image_sha256"]:
            raise ValueError("Изображение изменилось после подготовки набора")
        self.check_axes(item)
        path = self.path(item)
        # Exclusive per-record writer lock and revision check prevent a second
        # editor from silently replacing the first expert's decision.
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = path.with_suffix(".lock")
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise ValueError("Запись занята другим процессом; повторите сохранение") from exc
        try:
            os.close(fd)
            previous = read_json(path) if path.exists() else self.blank(item)
            if previous["review"]["revision"] != value["review"]["revision"]:
                raise ValueError("Аннотация изменена другим процессом. Переоткройте набор")
            saved = copy.deepcopy(value)
            saved["review"]["revision"] += 1
            saved["review"]["updated_at"] = utcnow()
            if path.exists():
                history = self.root / "history" / item["id"] / f"{previous['review']['revision']:05d}_{uuid.uuid4().hex}.json"
                atomic_json(history, previous)
            atomic_json(path, saved)
            return saved
        finally:
            lock.unlink(missing_ok=True)

    def import_labelme(self, item, path, author):
        if not author.strip():
            raise ValueError("Укажите автора предварительной разметки")
        candidate = read_json(path)
        if Path(candidate.get("imagePath", "")).name not in {Path(item["image"]).name, Path(item["source"]).name}:
            raise ValueError("imagePath кандидата относится к другому изображению")
        if (candidate.get("imageWidth"), candidate.get("imageHeight")) != (item["width"], item["height"]):
            raise ValueError("Размеры кандидата не совпадают с изображением")
        shapes = validate_shapes(candidate.get("shapes"), item["width"], item["height"])
        value = self.load(item)
        value["shapes"] = shapes
        for shape in value["shapes"]:
            shape["flags"]["proposal_author"] = author
        value["review"].update(status="pending", no_signal=False, note="", reviewer="")
        value["proposal"] = {"author": author, "imported_at": utcnow(),
                             "file_sha256": digest(path)}
        return self.save(item, value)

    def check_axes(self, item):
        if item.get("axes_sha256") and digest(safe_child(self.root, item["axes"])) != item["axes_sha256"]:
            raise ValueError("Изменились числовые данные или оси ионограммы")

    def export(self, destination):
        """Export a fresh snapshot; accepted expert-reviewed records only."""
        destination = Path(destination).resolve()
        if destination.exists():
            raise ValueError("Для экспорта выберите новую папку")
        if self.root == destination or destination in self.root.parents:
            raise ValueError("Нельзя экспортировать поверх набора")
        selected = []
        for item in self.items:
            value = self.load(item)
            if value["review"]["status"] != "accepted":
                continue
            if digest(safe_child(self.root, item["image"])) != item["image_sha256"]:
                raise ValueError(f"Изменилось изображение {item['id']}")
            self.check_axes(item)
            split = item.get("split", "unassigned")
            if split not in {"train", "validation", "test", "unassigned"}:
                raise ValueError("Некорректная часть выборки")
            selected.append((item, value, split))
        if not selected:
            raise ValueError("Пока нет принятых экспертом изображений")
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.with_name(destination.name + ".tmp_" + uuid.uuid4().hex)
        staging.mkdir()
        try:
            records = []
            for item, value, split in selected:
                folder = staging / split
                folder.mkdir(exist_ok=True)
                image_name = item["id"] + ".png"
                shutil.copyfile(safe_child(self.root, item["image"]), folder / image_name)
                value["imagePath"] = image_name
                if item.get("axes"):
                    axes_name = item["id"] + ".npz"
                    shutil.copyfile(safe_child(self.root, item["axes"]), folder / axes_name)
                    value["provenance"]["axes_file"] = axes_name
                atomic_json(folder / (item["id"] + ".json"), value)
                records.append({"id": item["id"], "split": split,
                                "source": item["source"], "image": f"{split}/{image_name}"})
            atomic_json(staging / "manifest.json", {"schema": "ionoreview-export/1",
                        "created_at": utcnow(), "items": records,
                        "annotation_policy": self.manifest.get("annotation_policy", "")})
            staging.rename(destination)
        except Exception:
            # Preserve a partial export for diagnosis; it is never reported as
            # complete and never overwrites an earlier accepted snapshot.
            raise
        return len(selected)
