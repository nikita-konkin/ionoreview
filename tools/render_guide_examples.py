"""Render the example images of the labelling guide (ionoreview/assets/guide) from the corrected review pack; usage: python tools/render_guide_examples.py ionoreview/assets/guide"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, r"N:\ionoreview")
from ionoreview.palette import ModePalette

OUT = Path(sys.argv[1])
SCALE = 1.4
font = ImageFont.truetype("segoeuib.ttf", 13)
small = ImageFont.truetype("segoeui.ttf", 11)

def load(pack, case, annotation=None):
    pack = Path(pack)
    with np.load(pack / "arrays" / f"{case}.npz") as z:
        db, freq, rng = z["db"], z["freq_mhz"], z["range_km"]
    doc = json.loads(Path(annotation or pack / "annotations" / f"{case}.json").read_text(encoding="utf-8"))
    return db, freq, rng, doc["shapes"]

def render(db, freq, rng, shapes, title, name, relabel=None):
    palette = ModePalette(font)
    h, w = db.shape
    base = Image.fromarray(palette.background(db, 25, 60)).convert("RGBA")
    big = base.resize((int(w * SCALE), int(h * SCALE)), Image.Resampling.NEAREST)
    over = Image.new("RGBA", big.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    for s in shapes:
        pts = [(x * SCALE, y * SCALE) for x, y in s["points"]]
        label = relabel(s) if relabel else s["label"]
        palette.paint(d, pts, label, 0.28, False)
    for s in shapes:
        pts = [(x * SCALE, y * SCALE) for x, y in s["points"]]
        palette.caption(d, pts, relabel(s) if relabel else s["label"])
    img = Image.alpha_composite(big, over)
    L, T, R, B = 52, 28, 10, 34
    canvas = Image.new("RGB", (img.width + L + R, img.height + T + B), "white")
    canvas.paste(img.convert("RGB"), (L, T))
    cd = ImageDraw.Draw(canvas)
    cd.text((L, 6), title, font=font, fill="#17243b")
    cd.rectangle((L, T, L + img.width, T + img.height), outline="#8b9bad")
    for v in np.linspace(0, w - 1, 6):
        x = L + v * SCALE
        cd.line((x, T + img.height, x, T + img.height + 4), fill="#8b9bad")
        cd.text((x, T + img.height + 6), f"{np.interp(v, np.arange(len(freq)), freq):.0f}", font=small, fill="#17243b", anchor="mt")
    cd.text((L + img.width / 2, T + img.height + 20), "Частота, МГц / Frequency, MHz", font=small, fill="#52514e", anchor="mt")
    for v in np.linspace(0, h - 1, 6):
        y = T + v * SCALE
        cd.line((L - 4, y, L, y), fill="#8b9bad")
        cd.text((L - 6, y), f"{np.interp(v, np.arange(len(rng)), rng):.0f}", font=small, fill="#17243b", anchor="rm")
    cd.text((L - 6, T - 16), "км / km", font=small, fill="#52514e", anchor="rm")
    pal = canvas.quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pal.save(OUT / name, optimize=True)
    print(name, (OUT / name).stat().st_size, canvas.size)

RP = r"N:\ionoreview\experiments\label-correction-v1\review-pack"
SR = r"N:\ionoreview\experiments\boosting-v5-student288\new-student-reference"
db, f, r, sh = load(RP, "Q030"); render(db, f, r, sh, "Q030 · NIC3 — 1E / 1F / 2F", "ladder_correct.png")
hist = next(Path(RP, "history", "Q030").glob("*.json"))
db, f, r, sh = load(RP, "Q030", hist); render(db, f, r, sh, "Q030 · NIC3 — 1F / 2F / 3F (ошибка / wrong)", "ladder_shifted.png")
db, f, r, sh = load(RP, "T031"); render(db, f, r, sh, "T031 · NIC1 — 1E, 1F, Interference", "nose_and_e.png")
db, f, r, sh = load(SR, "S101"); render(db, f, r, sh, "S101 · NIC3 — 1E, 1F, Interference", "reference.png")
