"""Traducciones. El texto fuente está en español; `t()` devuelve la versión del idioma elegido.

Uso: t("Serie {n} terminada", n=3). Las tablas viven en arise/locales/<idioma>.py (dict TEXT).
El idioma se elige al arrancar (ajuste "lang"); cambiarlo pide reiniciar la app.
"""
from __future__ import annotations

import importlib
import locale

LANGS = {"es": "Español", "en": "English", "pt": "Português"}
_lang = "es"
_table: dict = {}


def system_lang() -> str:
    try:
        code = (locale.getlocale()[0] or "").lower()
    except Exception:
        code = ""
    if code.startswith(("en", "english")):
        return "en"
    if code.startswith(("pt", "portuguese")):
        return "pt"
    return "es"


def set_lang(code: str):
    global _lang, _table
    _lang = code if code in LANGS else "es"
    if _lang == "es":
        _table = {}
        return
    try:
        _table = importlib.import_module(f"arise.locales.{_lang}").TEXT
    except Exception:
        _table = {}


def lang() -> str:
    return _lang


def t(s: str, **kw) -> str:
    out = _table.get(s, s) if s else s
    if kw:
        try:
            return out.format(**kw)
        except (KeyError, IndexError, ValueError):
            return s.format(**kw)
    return out


def plural(n, one: str, many: str, **kw) -> str:
    """t() con singular/plural: plural(3, "{n} serie", "{n} series")."""
    return t(one if n == 1 else many, n=n, **kw)
