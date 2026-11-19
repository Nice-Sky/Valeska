"""Busca textos visibles en español dentro del código.

Uso:
  python tools/i18n_scan.py            # lista textos que NO pasan por t() (deberían envolverse)
  python tools/i18n_scan.py --keys     # lista las claves usadas con t()/plural() que faltan en en/pt
Lo usa también tests/test_i18n.py para garantizar que la traducción esté completa.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "arise"
SKIP_FILES = {"locales", "_version.py", "i18n.py"}

# textos que no se traducen (marcas, siglas, formatos)
NOT_TEXT = re.compile(r"^(#[0-9a-fA-F]{3,8}|[A-Z]{2,4}|[a-z_][a-z0-9_.-]*|[\w./\\-]+\.(svg|wav|png|jpg|json|task|ttf|exe|ico|txt|py))$")
CSSISH = re.compile(r"(font-size|font-weight|color:|background|border|padding|QPushButton|QLabel|rgba\(|qlineargradient|"
                    r"letter-spacing|margin|text-align|selection-|::|stop:)")
WORD = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ¿¡]{3,}")
EXEMPT = {"Arise Trainer", "ARISE", "T R A I N E R", "Montserrat", "Segoe UI", "AriseTrainer", "Español", "English",
          "Português", "IDIOMA · LANGUAGE", "Elegí el idioma · Choose your language · Escolha o idioma",
          "Nice-Sky/Valeska", "arise.trainer", "AriseTrainerAppMutex", "arise-trainer-instance", "XP", "OK",
          "Jumping Jacks", "HH:mm", "kg", "ml", "MJPG"}
TRANSLATORS = {"t", "plural"}
DATA_TABLES = {"PLANS", "STATS", "ACHIEVEMENTS", "WEEKDAYS", "GROUPS", "EQUIPMENT", "VIEW_NAMES", "RPE", "READINESS",
               "VIEW_HINT", "LANGS", "SOUNDS", "PAGES", "READINESS_ICON", "VIEWS", "MODES"}
# argumentos que no se muestran (claves internas)
INTERNAL_CALLS = {"setObjectName", "setProperty", "getattr", "setattr", "hasattr", "get", "setdefault", "pop", "startswith",
                  "endswith", "split", "replace", "join", "format", "strftime", "strptime", "fromisoformat", "fromString",
                  "toString", "resource", "connect", "play", "img", "icon", "pixmap", "paint", "icon_label",
                  "set_icon_name", "set_icon", "Signal", "print", "log_debug", "QColor", "qc", "palette", "warn",
                  "open", "glob", "Path", "update", "index", "count", "encode", "decode", "QUrl", "QFont", "addItem_internal",
                  "isoformat", "contains", "removeServer", "connectToServer", "listen", "CreateMutexW", "SetCurrentProcessExplicitAppUserModelID",
                  "environ", "getenv", "OpenKey", "SetValueEx", "DeleteValue", "QueryValueEx", "exec", "write_text", "read_text",
                  "VideoWriter_fourcc", "dump", "load", "loads", "dumps", "re", "compile", "match", "search", "sub", "fullmatch"}


def is_text(s: str) -> bool:
    s2 = s.strip()
    if not s2 or s2 in EXEMPT or NOT_TEXT.match(s2) or CSSISH.search(s2):
        return False
    if s2.startswith(("<", "{", "%", "http", "--", "/", "\\", "$")) and not WORD.search(re.sub(r"<[^>]+>|\{[^}]*\}", "", s2)):
        return False
    plain = re.sub(r"<[^>]+>|\{[^}]*\}|&nbsp;", " ", s2)
    return bool(WORD.search(plain)) and (" " in plain.strip() or plain.strip()[:1].isupper() or "¿" in plain or "¡" in plain)


def _call_name(node) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


class Scan(ast.NodeVisitor):
    def __init__(self, path):
        self.path = path
        self.untranslated = []
        self.keys = []
        self.stack = []
        self.ignored = {i + 1 for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines()) if "# i18n: no" in ln}

    def visit_Call(self, node):
        name = _call_name(node)
        if name == "modal" and node.args and isinstance(node.args[0], ast.Constant):
            self.keys.append((node.args[0].value, node.lineno))
            for a in node.args[1:]:
                self.visit(a)
            return
        if name in TRANSLATORS:
            for a in node.args[: (1 if name == "t" else 3)]:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    self.keys.append((a.value, node.lineno))
            for a in node.args[(1 if name == "t" else 3):]:
                self.visit(a)
            for k in node.keywords:
                self.visit(k.value)
            return
        if name in INTERNAL_CALLS:
            return
        self.generic_visit(node)

    def visit_Subscript(self, node):  # d["clave"]
        self.visit(node.value)

    def visit_Compare(self, node):  # x == "texto" (comparaciones internas)
        return

    def visit_Dict(self, node):
        for v in node.values:
            if v is not None:
                self.visit(v)

    def visit_JoinedStr(self, node):
        if node.lineno in self.ignored:
            return
        txt = "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
        if is_text(txt):
            self.untranslated.append((txt, node.lineno))
        for v in node.values:
            if isinstance(v, ast.FormattedValue):
                self.visit(v.value)

    def visit_Constant(self, node):
        if getattr(node, "lineno", 0) in self.ignored:
            return
        if isinstance(node.value, str) and is_text(node.value):
            self.untranslated.append((node.value, node.lineno))

    def visit_Expr(self, node):  # docstrings y expresiones sueltas
        if isinstance(node.value, ast.Constant):
            return
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:]
        for d in node.decorator_list:
            self.visit(d)
        for b in body:
            self.visit(b)
        self.visit(node.args)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assign(self, node):  # tablas de datos: se traducen al mostrarse (data_keys)
        names = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if names & DATA_TABLES:
            return
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:]
        for b in body:
            self.visit(b)


def files():
    for p in sorted(SRC.rglob("*.py")):
        rel = p.relative_to(SRC)
        if rel.parts[0] in SKIP_FILES or p.name in SKIP_FILES:
            continue
        yield p


EXTRA_KEYS_ATTRS = ("name", "tip", "partial_msg", "return_msg", "label", "desc")


def data_keys() -> set[str]:
    """Textos que viven en datos (ejercicios, planes, logros...) y se traducen al mostrarse."""
    from arise import coach, exercises, game
    keys = set()
    for e in exercises.EXERCISES.values():
        for a in ("name", "tip", "partial_msg", "return_msg"):
            v = getattr(e, a)
            if v:
                keys.add(v)
    keys |= set(exercises.GROUPS.values()) | set(exercises.EQUIPMENT.values()) | set(exercises.VIEW_NAMES.values())
    for p in game.PLANS.values():
        keys |= {p["label"], p["desc"]}
    for k, (name, desc, _) in game.STATS.items():
        keys |= {name, desc}
    for a in game.ACHIEVEMENTS:
        keys |= {a[1], a[2]}
    keys |= set(coach.RPE.values()) | set(coach.READINESS.values())
    keys |= set(game.WEEKDAYS)
    from arise.app import PAGES
    keys |= {p[1] for p in PAGES}
    from arise.ui.body_page import VIEWS, PhotoCompare
    keys |= {v[1] for v in VIEWS} | {v[2] for v in VIEWS} | set(PhotoCompare.MODES)
    from arise.ui.train_page import VIEW_HINT
    keys |= set(VIEW_HINT.values())
    return keys


def module_messages() -> set[str]:
    """Mensajes de las mediciones (exercises.py devuelve texto en español que se traduce al mostrar)."""
    out = set()
    for name in ("exercises.py", "coach.py"):
        tree = ast.parse((SRC / name).read_text(encoding="utf-8"))
        docs = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs \
                    and is_text(node.value):
                out.add(node.value)
    return out


def scan():
    untranslated, keys = [], set()
    for p in files():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        s = Scan(p)
        s.visit(tree)
        rel = p.relative_to(ROOT)
        if p.name not in ("exercises.py", "coach.py"):
            untranslated += [(f"{rel}:{ln}", txt) for txt, ln in s.untranslated]
        keys |= {k for k, _ in s.keys}
    return untranslated, keys


def all_keys() -> set[str]:
    _, keys = scan()
    return keys | data_keys() | module_messages()


def missing(lang: str) -> list[str]:
    import importlib
    table = importlib.import_module(f"arise.locales.{lang}").TEXT
    return sorted(k for k in all_keys() if k not in table)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    if "--keys" in sys.argv:
        for lang in ("en", "pt"):
            m = missing(lang)
            print(f"== {lang}: faltan {len(m)}")
            for k in m:
                print(repr(k))
    else:
        u, _ = scan()
        for where, txt in u:
            print(where, repr(txt))
        print(len(u), "textos sin t()")
