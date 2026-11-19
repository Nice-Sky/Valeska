"""Las traducciones tienen que estar completas: todo texto visible pasa por t() y existe en inglés y portugués."""
import importlib
import re

import pytest

import tools.i18n_scan as scan
from arise import i18n

PH = re.compile(r"\{(\w*)\}")


def test_no_visible_text_without_translation_call():
    untranslated, _ = scan.scan()
    assert untranslated == [], "\n".join(f"{w} {t!r}" for w, t in untranslated)


@pytest.mark.parametrize("lang", ["en", "pt"])
def test_every_key_is_translated(lang):
    assert scan.missing(lang) == []


@pytest.mark.parametrize("lang", ["en", "pt"])
def test_placeholders_match(lang):
    table = importlib.import_module(f"arise.locales.{lang}").TEXT
    bad = [k for k, v in table.items() if sorted(PH.findall(k)) != sorted(PH.findall(v))]
    assert bad == []


def test_switching_language():
    try:
        i18n.set_lang("en")
        assert i18n.t("Serie lista") == "Set done"
        assert i18n.t("Serie {n}", n=2) == "Set 2"
        assert i18n.plural(1, "{n} día", "{n} días") == "1 day"
        i18n.set_lang("pt")
        assert i18n.t("Flexiones") == "Flexões"
    finally:
        i18n.set_lang("es")
    assert i18n.t("Serie lista") == "Serie lista"
