"""Colour schemes for the ionogram canvas: the familiar turbo view and a mode view that sets E, 1F and 2F apart."""
from __future__ import annotations

import math
from typing import Protocol, final

import numpy as np
from matplotlib import colormaps
from PIL import ImageColor


class Palette(Protocol):
    def background(self, db, low, high): ...

    def paint(self, draw, points, label, opacity, chosen): ...

    def caption(self, draw, points, label): ...

    def ink(self): ...

    def marquee(self): ...

    def title(self): ...


@final
class TurboPalette:
    """Turbo power scale with one bright colour per label, exactly as the reviewer always showed it."""

    def __init__(self):
        self.colours = {"Signal": "#47e1ae", "1E": "#ffd166", "1F": "#55c7ff", "2F": "#f5a1fa", "3F": "#b9a4ff",
                        "E": "#ffeaa0", "Es": "#ffa965", "Interference": "#ff807c"}

    def background(self, db, low, high):
        return colormaps["turbo"](np.clip((np.nan_to_num(db, nan=low) - low) / (high - low), 0, 1), bytes=True)[:, :, :3]

    def paint(self, draw, points, label, opacity, chosen):
        colour = ImageColor.getrgb(self.colours[label])
        draw.polygon(points, fill=colour + (int(255 * opacity),))
        draw.line(points + [points[0]], fill=(255, 255, 255, 255) if chosen else colour + (255,), width=3 if chosen else 2)

    def caption(self, draw, points, label):
        pass

    def ink(self):
        return "#ffffff"

    def marquee(self):
        return "#ffe79b"

    def title(self):
        return "turbo"


@final
class ModePalette:
    """Grey power scale on which each propagation mode family keeps its own colour and caption, while other labels stay neutral dashes."""

    def __init__(self, font):
        self.font = font
        self.families = {"1E": "#eb6834", "E": "#eb6834", "Es": "#eb6834", "1F": "#2a78d6", "2F": "#1baf7a"}

    def background(self, db, low, high):
        return colormaps["Greys"](np.clip((np.nan_to_num(db, nan=low) - low) / (high - low), 0, 1), bytes=True)[:, :, :3]

    def paint(self, draw, points, label, opacity, chosen):
        ring = list(points) + [points[0]]
        if chosen:
            draw.line(ring, fill=(255, 255, 255, 255), width=5, joint="curve")
        if label in self.families:
            colour = ImageColor.getrgb(self.families[label])
            draw.polygon(points, fill=colour + (int(255 * opacity),))
            draw.line(ring, fill=ImageColor.getrgb(self.ink() if chosen else self.families[label]) + (255,),
                      width=3 if chosen else 2, joint="curve")
            return
        draw.line(ring, fill=(255, 255, 255, 255), width=4, joint="curve")
        for piece in self._dashes(ring):
            draw.line(piece, fill=ImageColor.getrgb(self.ink() if chosen else "#52514e") + (255,), width=3 if chosen else 2)

    def caption(self, draw, points, label):
        draw.text((min(p[0] for p in points) - 4, float(np.median([p[1] for p in points]))), label, font=self.font,
                  anchor="rm", fill=ImageColor.getrgb(self.families.get(label, "#52514e")) + (255,),
                  stroke_width=2, stroke_fill=(255, 255, 255, 255))

    def ink(self):
        return "#d6336c"

    def marquee(self):
        return "#d6336c"

    def title(self):
        return "моды"

    def _dashes(self, ring):
        pieces = []
        travelled = 0.0
        for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
            length = math.hypot(x1 - x0, y1 - y0)
            done = 0.0
            while done < length:
                phase = travelled % 10.0
                step = min(6.0 - phase if phase < 6.0 else 10.0 - phase, length - done)
                if phase < 6.0:
                    pieces.append([(x0 + (x1 - x0) * done / length, y0 + (y1 - y0) * done / length),
                                   (x0 + (x1 - x0) * (done + step) / length, y0 + (y1 - y0) * (done + step) / length)])
                done += step
                travelled += step
        return pieces
