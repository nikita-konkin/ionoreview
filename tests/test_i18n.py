import re

import pytest

from ionoreview.i18n import EN, LANGUAGES, translate


def test_russian_text_passes_through_unchanged():
    assert translate("Файл", "ru") == "Файл", "Russian text was altered"


def test_english_text_replaces_known_russian_key():
    assert translate("Файл", "en") == "File", "Known key was not translated"


def test_fields_fill_placeholders_in_both_languages():
    assert translate("Принято {done} из {total}", "en", done=3, total=7) == "Accepted 3 of 7", "Placeholders were not filled"


def test_unknown_language_is_rejected():
    with pytest.raises(ValueError, match="fr"):
        translate("Файл", "fr")


def test_every_english_text_is_free_of_cyrillic():
    leftovers = [value for value in EN.values() if re.search("[А-Яа-яЁё]", value)]
    assert not leftovers, f"English texts keep Cyrillic letters: {leftovers}"


def test_every_english_text_keeps_the_placeholders_of_its_source():
    broken = [key for key, value in EN.items()
              if sorted(re.findall(r"\{\w+\}", key)) != sorted(re.findall(r"\{\w+\}", value))]
    assert not broken, f"Placeholders differ between languages: {broken}"


def test_language_names_are_written_in_their_own_language():
    assert LANGUAGES == {"ru": "Русский", "en": "English"}, "Language menu names changed"
