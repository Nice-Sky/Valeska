"""Íconos Lucide (SVG de línea) dibujados del color que haga falta."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ..storage import resource

WHITE = "#f2fbff"


@lru_cache(maxsize=None)
def _svg(name: str) -> str:
    p = resource("icons", f"{name}.svg")
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return resource("icons", "circle-alert.svg").read_text(encoding="utf-8")


@lru_cache(maxsize=512)
def pixmap(name: str, size: int = 20, color: str = WHITE, stroke: float = 1.75, dpr: float = 2.0) -> QPixmap:
    data = _svg(name).replace("currentColor", color).replace('stroke-width="2"', f'stroke-width="{stroke}"')
    r = QSvgRenderer(QByteArray(data.encode("utf-8")))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(p, QRectF(0, 0, size * dpr, size * dpr))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, size: int = 20, color: str = WHITE) -> QIcon:
    ic = QIcon(pixmap(name, size, color))
    ic.addPixmap(pixmap(name, size, color), QIcon.Mode.Disabled)
    return ic


def paint(p: QPainter, name: str, rect: QRectF, color: str = WHITE, stroke: float = 1.75):
    data = _svg(name).replace("currentColor", color).replace('stroke-width="2"', f'stroke-width="{stroke}"')
    QSvgRenderer(QByteArray(data.encode("utf-8"))).render(p, rect)


_TMP = None


def img(name: str, size: int = 18, color: str = WHITE) -> str:
    """Etiqueta <img> para usar un ícono dentro de texto enriquecido (QLabel)."""
    global _TMP
    import tempfile
    from pathlib import Path
    if _TMP is None:
        _TMP = Path(tempfile.gettempdir()) / "arise_icons"
        _TMP.mkdir(exist_ok=True)
    f = _TMP / f"{name}_{size}_{color.strip('#')}.png"  # i18n: no
    if not f.exists():
        pm = pixmap(name, size, color, dpr=2.0)
        pm.save(str(f))
    return f'<img src="{f.as_posix()}" width="{size}" height="{size}" style="vertical-align:middle">'
