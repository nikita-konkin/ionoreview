from pathlib import Path

from ionoreview.guide import ASSETS, GUIDE, images

REPO = Path(__file__).resolve().parents[1]


def kinds(code):
    return [block[0] for block in GUIDE[code]]


def test_both_languages_have_the_same_block_structure():
    assert kinds("ru") == kinds("en"), "Russian and English guides differ in structure"


def test_both_languages_show_the_same_images_in_the_same_order():
    assert images("ru") == images("en"), "Languages show different example images"


def test_guide_ships_three_to_four_example_images():
    assert 3 <= len(images("ru")) <= 4, "The guide should show 3-4 examples"


def test_every_example_image_exists_and_is_small():
    sizes = [(ASSETS / name).stat().st_size for name in images("ru")]
    assert all(0 < size < 150_000 for size in sizes), f"Example image sizes are wrong: {sizes}"


def lacking(code, facts):
    text = " ".join(block[1] for block in GUIDE[code] if block[0] != "img")
    return [fact for fact in facts if fact not in text]


def test_russian_guide_states_the_core_rules():
    facts = ("2640–2670", "носик", "MUF(1F) > MUF(2F) > MUF(3F)", "2690–2710", "Interference", "Неоднозначно")
    assert not lacking("ru", facts), f"Russian guide lacks: {lacking('ru', facts)}"


def test_english_guide_states_the_core_rules():
    facts = ("2640–2670", "nose", "MUF(1F) > MUF(2F) > MUF(3F)", "2690–2710", "Interference", "Ambiguous")
    assert not lacking("en", facts), f"English guide lacks: {lacking('en', facts)}"


def test_windows_build_bundles_the_guide_images():
    spec = (REPO / "packaging/ionoreview.spec").read_text(encoding="utf-8")
    assert "assets" in spec and "guide" in spec, "PyInstaller spec does not bundle guide images"


def test_bundle_destination_matches_the_runtime_location():
    spec = (REPO / "packaging/ionoreview.spec").read_text(encoding="utf-8")
    assert "'ionoreview/assets/guide'" in spec or '"ionoreview/assets/guide"' in spec, "Bundle folder differs from ionoreview/assets/guide"
