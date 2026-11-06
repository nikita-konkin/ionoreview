import random
import tkinter as tk

from PIL import ImageColor

from ionoreview.theme import apply_theme, face


def test_button_face_draws_its_outline_on_the_edge():
    edge = '#%06x' % random.randint(0, 0xffffff)
    image = face('#ffffff', edge)
    assert image.getpixel((image.width // 2, 0))[:3] == ImageColor.getrgb(edge), 'Button face does not draw its outline on the top edge'


def test_button_face_fills_its_middle():
    fill = '#%06x' % random.randint(0, 0xffffff)
    image = face(fill, '#000000')
    assert image.getpixel((image.width // 2, image.height // 2))[:3] == ImageColor.getrgb(fill), 'Button face does not fill its middle'


def test_button_face_rounds_its_corners():
    image = face('#ffffff', '#000000')
    assert image.getpixel((0, 0))[3] < 10, 'Button face does not leave its corner transparent'


def test_theme_draws_ordinary_buttons_with_outlined_face():
    root = tk.Tk()
    try:
        layout = str(apply_theme(root).layout('TButton'))
    finally:
        root.destroy()
    assert 'Plain.face' in layout, 'Ordinary button layout does not use the outlined face'


def test_theme_survives_second_application_to_one_window():
    root = tk.Tk()
    try:
        apply_theme(root)
        layout = str(apply_theme(root).layout('Primary.TButton'))
    finally:
        root.destroy()
    assert 'Primary.face' in layout, 'Second theme application loses the primary face'


def test_application_icon_holds_small_and_large_sizes():
    from PIL import Image
    from ionoreview.theme import ICON
    sizes = Image.open(ICON.with_suffix('.ico')).ico.sizes()
    assert {(16, 16), (256, 256)} <= sizes, 'Application icon does not hold both the 16 and 256 pixel sizes'


def test_theme_gives_window_application_icon():
    root = tk.Tk()
    try:
        apply_theme(root)
        names = root.tk.call('image', 'names')
    finally:
        root.destroy()
    assert any('icon' in str(n) for n in names), 'Theme does not give the window its application icon'
