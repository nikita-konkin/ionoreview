import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont

from ionoreview.palette import ModePalette, TurboPalette


def painted(palette, label, chosen=False):
    image = Image.new("RGBA", (64, 44), (0, 0, 0, 0))
    palette.paint(ImageDraw.Draw(image), [(11, 9), (53, 9), (49, 33), (13, 31)], label, 0.23, chosen)
    return image


def test_mode_palette_gives_every_e_family_label_one_colour():
    colours = {painted(ModePalette(ImageFont.load_default(12)), label).getpixel((31, 9)) for label in ("1E", "E", "Es")}
    assert len(colours) == 1, f"E-family labels dont share one outline colour: {colours}"


def test_mode_palette_keeps_1f_apart_from_2f():
    palette = ModePalette(ImageFont.load_default(12))
    assert painted(palette, "1F").getpixel((31, 9)) != painted(palette, "2F").getpixel((31, 9)), "1F and 2F outlines cannot be told apart"


def test_mode_palette_outlines_labels_outside_the_modes_with_dashes():
    image = painted(ModePalette(ImageFont.load_default(12)), "Interference")
    assert len({image.getpixel((x, 9))[:3] for x in range(13, 52)}) > 1, "Interference outline is solid instead of dashed"


def test_mode_palette_leaves_labels_outside_the_modes_unfilled():
    assert painted(ModePalette(ImageFont.load_default(12)), "Signal").getpixel((31, 21))[3] == 0, "Signal polygon is filled although it is not a mode"


def test_mode_palette_marks_chosen_mask_with_its_ink():
    palette = ModePalette(ImageFont.load_default(12))
    assert painted(palette, "2F", chosen=True).getpixel((31, 9))[:3] == ImageColor.getrgb(palette.ink()), "Chosen mask is not outlined with the palette ink"


def test_mode_palette_draws_stronger_echo_darker():
    picture = ModePalette(ImageFont.load_default(12)).background(np.array([[27.5, 51.0]]), 25, 60)
    assert int(picture[0, 1].sum()) < int(picture[0, 0].sum()), "Stronger echo is not drawn darker than weaker echo"


def test_mode_palette_writes_label_left_of_mask():
    image = Image.new("RGBA", (130, 44), (0, 0, 0, 0))
    ModePalette(ImageFont.load_default(12)).caption(ImageDraw.Draw(image), [(71, 12), (117, 10), (112, 33), (74, 29)], "1F")
    assert image.crop((0, 0, 69, 44)).getbbox() is not None, "No caption appears left of the mask"


def test_turbo_palette_keeps_former_1f_colour():
    assert painted(TurboPalette(), "1F").getpixel((31, 9))[:3] == (0x55, 0xc7, 0xff), "Turbo palette lost the familiar 1F colour"


def test_turbo_palette_adds_no_caption():
    image = Image.new("RGBA", (130, 44), (0, 0, 0, 0))
    TurboPalette().caption(ImageDraw.Draw(image), [(71, 12), (117, 10), (112, 33), (74, 29)], "1F")
    assert image.getbbox() is None, "Turbo palette draws captions it never drew before"
