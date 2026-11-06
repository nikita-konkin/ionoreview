"""Draws the application icon: an oblique ionogram ladder of E, 1F and 2F traces on a dark rounded tile."""
import sys
from pathlib import Path

from PIL import Image, ImageDraw


def mode(size, nose, reach, rise, top):
    return [(size * (nose[0] - reach * t * t), size * (nose[1] + rise * t)) for t in [k / 40 for k in range(int(-40 * top), 41)]]


def tile(size=1024):
    shade = Image.new('RGBA', (size, size))
    paint = ImageDraw.Draw(shade)
    for y in range(size):
        t = y / size
        paint.line((0, y, size, y), fill=(int(14 + 16 * t), int(32 + 44 * t), int(70 + 112 * t), 255))
    for k in range(1, 5):
        x = size * k // 5
        paint.line((x, 0, x, size), fill=(62, 94, 150, 255), width=size // 200)
        paint.line((0, x, size, x), fill=(62, 94, 150, 255), width=size // 200)
    width = size // 17
    paint.line((size * .14, size * .80, size * .86, size * .80), fill='#f2874a', width=width)
    for colour, points in [('#4f9dff', mode(size, (.84, .56), .70, .14, .6)), ('#2fd393', mode(size, (.64, .33), .50, .11, .6))]:
        paint.line(points, fill=colour, width=width, joint='curve')
        for x, y in points:
            paint.ellipse((x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=colour)
    paint.ellipse((size * .14 - width / 2, size * .80 - width / 2, size * .14 + width / 2, size * .80 + width / 2), fill='#f2874a')
    paint.ellipse((size * .86 - width / 2, size * .80 - width / 2, size * .86 + width / 2, size * .80 + width / 2), fill='#f2874a')
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), size // 5, fill=255)
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    image.paste(shade, (0, 0), mask)
    return image


def main(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    image = tile()
    image.resize((256, 256), Image.LANCZOS).save(folder / 'ionoreview.png')
    image.save(folder / 'ionoreview.ico', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == '__main__':
    main(sys.argv[1])
