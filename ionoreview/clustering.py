"""Unsupervised proposals from the numerical matrix, never expert labels."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import numpy as np

from .data import validate_shapes


@dataclass(frozen=True)
class ClusterParams:
    threshold_db: float = 43.0
    frequency_gap_mhz: float = .15
    range_gap_km: float = 25.0
    min_samples: int = 4
    min_cluster_points: int = 12
    min_span_mhz: float = .25
    method: str = "DBSCAN"
    n_clusters: int = 2
    coordinate_units: str = "physical"

    def validate(self):
        if self.method not in {"DBSCAN", "K-means"} or self.coordinate_units not in {"physical", "pixels"}:
            raise ValueError("Неизвестный метод или единицы координат")
        pixel = self.coordinate_units == "pixels"
        limits = ((self.threshold_db, 0 if pixel else -50, 255 if pixel else 120),
                  (self.frequency_gap_mhz, 1 if pixel else .01, 1000 if pixel else 1),
                  (self.range_gap_km, 1, 1000 if pixel else 300),
                  (self.min_span_mhz, 0, 10000 if pixel else 10))
        if any(not math.isfinite(v) or not lo <= v <= hi for v, lo, hi in limits):
            raise ValueError("Параметры вне диапазона. Порог: −50…120 дБ или 0…255 для PNG; "
                             "связь: 0.01…1 МГц / 1…300 км или 1…1000 пикселей")
        if (isinstance(self.min_samples, bool) or not isinstance(self.min_samples, int)
                or not 2 <= self.min_samples <= 100):
            raise ValueError("min_samples: целое число от 2 до 100")
        if (isinstance(self.min_cluster_points, bool) or not isinstance(self.min_cluster_points, int)
                or not 3 <= self.min_cluster_points <= 10000):
            raise ValueError("Размер кластера: целое число от 3 до 10000")
        if not isinstance(self.n_clusters, int) or isinstance(self.n_clusters, bool) or not 1 <= self.n_clusters <= 30:
            raise ValueError("Число кластеров должно быть от 1 до 30")


@dataclass
class ClusterResult:
    shapes: list
    stats: dict
    params: dict
    scope: list


def _contours_without_holes(mask, offset_x, offset_y, width, height, min_component_points=1):
    """Split masks at hole interiors instead of filling the space between arms.

    Dilation by one native pixel creates editable positive-area bands even
    for one-bin traces. Separate connected fragments keep one group id.
    """
    import cv2
    padded = np.pad(mask.astype(np.uint8), 2)
    # One-pixel speckles are not editable objects. Close only short native
    # gaps; preserve large empty regions between physically distinct arms.
    padded = cv2.morphologyEx(padded, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    count, components, stats, _ = cv2.connectedComponentsWithStats(padded, connectivity=8)
    keep = np.zeros_like(padded)
    for component in range(1, count):
        if stats[component, cv2.CC_STAT_AREA] >= min_component_points:
            keep[components == component] = 1
    padded = keep
    padded = cv2.dilate(padded, np.ones((3, 3), np.uint8), iterations=1)
    count, components, stats, _ = cv2.connectedComponentsWithStats(1 - padded, connectivity=8)
    for component in range(1, count):
        x, y, w, h, area = stats[component]
        if area <= 16 and x > 0 and y > 0 and x+w < padded.shape[1] and y+h < padded.shape[0]:
            padded[components == component] = 1
    stack = [(padded, offset_x - 2, offset_y - 2)]
    polygons = []
    while stack:
        part, ox, oy = stack.pop()
        contours, hierarchy = cv2.findContours(part, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        holes = [] if hierarchy is None else [i for i, h in enumerate(hierarchy[0]) if h[3] >= 0]
        if holes:
            hx, hy, hw, hh = cv2.boundingRect(contours[holes[0]])
            cut = max(1, min(part.shape[1] - 1, hx + hw // 2))
            stack.append((part[:, :cut].copy(), ox, oy))
            stack.append((part[:, cut:].copy(), ox + cut, oy))
            continue
        for contour in contours:
            if cv2.contourArea(contour) < .5:
                continue
            approx = cv2.approxPolyDP(contour, .45, True)[:, 0, :].astype(float)
            approx += [ox, oy]
            approx[:, 0] = np.clip(approx[:, 0], 0, width - 1)
            approx[:, 1] = np.clip(approx[:, 1], 0, height - 1)
            # Clipping at the image border can create duplicate vertices.
            points = []
            for point in approx.tolist():
                if not points or point != points[-1]:
                    points.append(point)
            if len(points) > 1 and points[0] == points[-1]:
                points.pop()
            try:
                validate_shapes([{"label": "Signal", "points": points}], width, height)
            except ValueError:
                continue
            polygons.append(points)
    return polygons


def cluster_ionogram(db, freq_mhz, range_km, view, params=None):
    from sklearn.cluster import DBSCAN, KMeans

    params = params or ClusterParams()
    params.validate()
    db = np.asarray(db)
    freq_mhz, range_km = np.asarray(freq_mhz), np.asarray(range_km)
    if db.ndim != 2 or db.shape != (len(range_km), len(freq_mhz)):
        raise ValueError("Матрица и оси имеют разные размеры")
    if not (np.all(np.isfinite(freq_mhz)) and np.all(np.isfinite(range_km))
            and np.all(np.diff(freq_mhz) > 0) and np.all(np.diff(range_km) < 0)):
        raise ValueError("Нужны конечные монотонные физические оси")
    height, width = db.shape
    if len(view) != 4 or not all(math.isfinite(v) for v in view):
        raise ValueError("Некорректная область кластеризации")
    x0, y0 = max(0, math.ceil(view[0])), max(0, math.ceil(view[1]))
    x1, y1 = min(width - 1, math.floor(view[2])), min(height - 1, math.floor(view[3]))
    if x0 >= x1 or y0 >= y1:
        raise ValueError("Область должна включать хотя бы два отсчёта каждой оси")
    region = db[y0:y1 + 1, x0:x1 + 1]
    ys, xs = np.nonzero(np.isfinite(region) & (region >= params.threshold_db))
    count = len(xs)
    if count > 20000:
        raise ValueError(f"Слишком много точек ({count} > 20000): повысьте порог или сузьте область")
    stats = {"points": count, "noise_points": count, "clusters": 0, "polygons": 0,
             "discarded_clusters": 0, "outline_padding_pixels": 1}
    if count < params.min_cluster_points:
        return ClusterResult([], stats, asdict(params), [x0, y0, x1, y1])
    xs, ys = xs + x0, ys + y0
    features = np.column_stack((
        (freq_mhz[xs] - freq_mhz[x0]) / params.frequency_gap_mhz,
        (range_km[ys] - range_km[y0]) / params.range_gap_km))
    if params.method == "DBSCAN":
        labels = DBSCAN(eps=1, min_samples=params.min_samples, metric="chebyshev",
                        algorithm="kd_tree", n_jobs=1).fit_predict(features)
    else:
        if count < params.n_clusters:
            raise ValueError("Точек меньше запрошенного числа кластеров")
        # K-means assigns even isolated noise to a centre. Use the same local
        # density criterion as DBSCAN before fitting the requested count.
        dense = DBSCAN(eps=1, min_samples=params.min_samples, metric="chebyshev",
                       algorithm="kd_tree", n_jobs=1).fit_predict(features) >= 0
        if np.count_nonzero(dense) < max(params.n_clusters, params.min_cluster_points):
            return ClusterResult([], stats, asdict(params), [x0,y0,x1,y1])
        labels = np.full(count, -1, dtype=int)
        labels[dense] = KMeans(n_clusters=params.n_clusters, random_state=42, n_init=10).fit_predict(features[dense])
    stats["noise_points"] = int(np.count_nonzero(labels == -1))
    shapes = []
    for label in sorted(set(labels) - {-1}):
        keep = labels == label
        cx, cy = xs[keep], ys[keep]
        if len(cx) < params.min_cluster_points or np.ptp(freq_mhz[cx]) < params.min_span_mhz:
            stats["discarded_clusters"] += 1
            continue
        # A cap also bounds interactive drawing work on pathological images.
        if stats["clusters"] >= 100:
            raise ValueError("Больше 100 кластеров: повысьте порог или минимальный размер")
        ox, oy = int(cx.min()), int(cy.min())
        mask = np.zeros((int(cy.max()) - oy + 1, int(cx.max()) - ox + 1), np.uint8)
        mask[cy - oy, cx - ox] = 1
        polygons = _contours_without_holes(mask, ox, oy, width, height,
                                         min_component_points=max(3, params.min_cluster_points // 2))
        if not polygons:
            stats["discarded_clusters"] += 1
            continue
        stats["clusters"] += 1
        group = stats["clusters"]
        for points in polygons:
            shapes.append({"label": "Signal", "points": points, "group_id": group,
                "shape_type": "polygon", "flags": {"proposal_author": params.method,
                    "cluster_id": group, "draft": True, "threshold_db": params.threshold_db}})
    stats["polygons"] = len(shapes)
    return ClusterResult(validate_shapes(shapes, width, height), stats, asdict(params), [x0, y0, x1, y1])


def image_features(image):
    """Brightness score for PNG/JPEG with no numerical SNR; not measured dB.

    On colour scientific plots, grey/white plot margins are excluded. The
    user should crop the actual graph and adjust the brightness threshold.
    Grey plots use the dominant background to infer dark/light signal polarity.
    """
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    brightness = rgb @ np.asarray([.299, .587, .114], dtype=np.float32)
    colour = np.ptp(rgb, axis=2) > 35
    if colour.mean() > .01:
        brightness = np.where(colour, brightness, 0)
    elif np.median(brightness)>127:
        brightness=255-brightness
    return brightness.astype(np.float32)
