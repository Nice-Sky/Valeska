"""Dibujo "holográfico": neón, marcos biselados, barras de luz y fondo del Sistema."""
from __future__ import annotations

import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient)
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from . import icons
from . import theme as T

PALETTES = {
    "": (T.GLOW, T.CORE),
    "blue": (T.GLOW, T.CORE),
    "red": (T.RED, "#ffe3e8"),
    "gold": (T.GOLD, "#fff6dc"),
}


def palette(tone: str):
    return PALETTES.get(tone or "", PALETTES[""])


def qc(color: str, alpha: int = 255) -> QColor:
    c = QColor(color)
    c.setAlpha(alpha)
    return c


# ------------------------------------------------------------------ primitivas
def neon_path(p: QPainter, path: QPainterPath, color: str, core: str = T.CORE, width: float = 1.4,
              halo: int = 4, spread: float = 2.6, alpha: int = 34):
    """Dibuja un trazo tipo tubo de neón: halo de color + núcleo casi blanco."""
    p.setBrush(Qt.BrushStyle.NoBrush)
    for i in range(halo, 0, -1):
        pen = QPen(qc(color, alpha), width + i * spread)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        p.drawPath(path)
    pen = QPen(qc(color, 235), width + 0.8)
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    p.setPen(pen)
    p.drawPath(path)
    pen = QPen(qc(core, 255), max(0.8, width * 0.55))
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    p.setPen(pen)
    p.drawPath(path)


def neon_line(p, x1, y1, x2, y2, color, core=T.CORE, width=1.4, halo=4, spread=2.6, alpha=34):
    path = QPainterPath(QPointF(x1, y1))
    path.lineTo(QPointF(x2, y2))
    neon_path(p, path, color, core, width, halo, spread, alpha)


def chamfer(r: QRectF, cut: float = 10) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(r.left() + cut, r.top())
    path.lineTo(r.right() - cut, r.top())
    path.lineTo(r.right(), r.top() + cut)
    path.lineTo(r.right(), r.bottom() - cut)
    path.lineTo(r.right() - cut, r.bottom())
    path.lineTo(r.left() + cut, r.bottom())
    path.lineTo(r.left(), r.bottom() - cut)
    path.lineTo(r.left(), r.top() + cut)
    path.closeSubpath()
    return path


def glass(p: QPainter, path: QPainterPath, color: str, seed: int = 1, scratches: int = 26, strong: bool = False):
    """Relleno de vidrio oscuro con líneas finas diagonales (textura holográfica)."""
    r = path.boundingRect()
    g = QLinearGradient(r.topLeft(), r.bottomLeft())
    g.setColorAt(0, QColor(8, 22, 50, 235 if strong else 215))
    g.setColorAt(0.5, QColor(4, 12, 30, 235 if strong else 210))
    g.setColorAt(1, QColor(6, 18, 42, 240 if strong else 220))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawPath(path)
    p.save()
    p.setClipPath(path)
    rad = QRadialGradient(r.center(), max(r.width(), r.height()) * 0.7)
    rad.setColorAt(0, qc(color, 26))
    rad.setColorAt(1, qc(color, 0))
    p.fillRect(r, rad)
    rnd = random.Random(seed)
    for _ in range(scratches):
        x = r.left() + rnd.random() * r.width()
        y = r.top() + rnd.random() * r.height()
        ln = 30 + rnd.random() * r.width() * 0.35
        p.setPen(QPen(qc(color, rnd.randint(10, 26)), 1))
        p.drawLine(QPointF(x, y), QPointF(x + ln, y - ln * 0.45))
    # brillo interno pegado al borde
    for i in range(1, 9):
        p.setPen(QPen(qc(color, int(42 * (1 - i / 9))), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(chamfer(r.adjusted(i, i, -i, -i), 10))
    p.restore()


def beam(p: QPainter, x1: float, x2: float, y: float, color: str, core: str = T.CORE, seed: int = 3, up: bool = True):
    """Barra de luz horizontal con detalles de circuito (arriba/abajo de las ventanas del Sistema)."""
    rnd = random.Random(seed)
    d = -1 if up else 1
    # tubo principal
    neon_line(p, x1, y, x2, y, color, core, width=3.2, halo=6, spread=3.2, alpha=30)
    # rieles finos paralelos con cortes
    for off in (6, 11):
        x = x1 + 18
        while x < x2 - 18:
            seg = 20 + rnd.random() * 90
            if rnd.random() > 0.3:
                neon_line(p, x, y + d * off, min(x + seg, x2 - 18), y + d * off, color, core,
                          width=0.9, halo=2, spread=2, alpha=40)
            x += seg + 6 + rnd.random() * 26
    # remates en las puntas (escalones)
    for sx, sgn in ((x1, 1), (x2, -1)):
        path = QPainterPath(QPointF(sx, y))
        path.lineTo(QPointF(sx, y - d * 12))
        path.lineTo(QPointF(sx + sgn * 26, y - d * 12))
        neon_path(p, path, color, core, width=1.6, halo=3)
        p.fillRect(QRectF(sx + sgn * 30 - (6 if sgn < 0 else 0), y - d * 14 - 2, 6, 4), qc(core, 230))


def holo_frame(p: QPainter, rect: QRectF, tone: str = "", seed: int = 1, cut: float = 10, beams: bool = False,
               strong: bool = False, brackets: bool = True):
    color, core = palette(tone)
    path = chamfer(rect, cut)
    glass(p, path, color, seed, strong=strong)
    neon_path(p, path, color, core, width=1.1, halo=4, spread=2.4, alpha=30)
    if brackets:  # esquinas reforzadas
        s = 18
        for (x, y, dx, dy) in ((rect.left(), rect.top(), 1, 1), (rect.right(), rect.bottom(), -1, -1)):
            path2 = QPainterPath(QPointF(x + dx * cut, y + dy * -0))
            path2.moveTo(QPointF(x, y + dy * (cut + s)))
            path2.lineTo(QPointF(x, y + dy * cut))
            path2.lineTo(QPointF(x + dx * cut, y))
            path2.lineTo(QPointF(x + dx * (cut + s), y))
            neon_path(p, path2, color, core, width=2.6, halo=3, alpha=40)
    if beams:
        beam(p, rect.left() - 30, rect.right() + 30, rect.top() - 16, color, core, seed, up=True)
        beam(p, rect.left() - 30, rect.right() + 30, rect.bottom() + 16, color, core, seed + 7, up=False)


def backdrop(p: QPainter, rect: QRectF, seed: int = 9):
    """Fondo general: negro azulado con resplandor, grilla tenue y trazos de circuito."""
    p.fillRect(rect, QColor(T.BG))
    rad = QRadialGradient(QPointF(rect.width() * 0.55, rect.height() * 0.15), max(rect.width(), rect.height()) * 0.8)
    rad.setColorAt(0, QColor(20, 70, 170, 70))
    rad.setColorAt(0.5, QColor(10, 35, 90, 30))
    rad.setColorAt(1, QColor(0, 0, 0, 0))
    p.fillRect(rect, rad)
    p.setPen(QPen(QColor(60, 150, 255, 12), 1))
    step = 46
    x = 0.0
    while x < rect.width():
        p.drawLine(QPointF(x, 0), QPointF(x, rect.height()))
        x += step
    y = 0.0
    while y < rect.height():
        p.drawLine(QPointF(0, y), QPointF(rect.width(), y))
        y += step
    rnd = random.Random(seed)
    for _ in range(18):
        x = rnd.random() * rect.width()
        y = rnd.random() * rect.height()
        path = QPainterPath(QPointF(x, y))
        for _ in range(3):
            if rnd.random() > 0.5:
                x += (rnd.random() - 0.3) * 160
            else:
                y += (rnd.random() - 0.5) * 120
            path.lineTo(QPointF(x, y))
        p.setPen(QPen(QColor(77, 200, 255, 18), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.fillRect(QRectF(x - 1.5, y - 1.5, 3, 3), QColor(120, 220, 255, 40))


# ------------------------------------------------------------------ widgets
class Backdrop(QWidget):
    def paintEvent(self, e):
        p = QPainter(self)
        backdrop(p, QRectF(self.rect()))


class NeonBox(QWidget):
    """Caja con borde de neón (para el ícono y el título del encabezado)."""

    def __init__(self, tone="", parent=None):
        super().__init__(parent)
        self.tone = tone

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color, core = palette(self.tone)
        r = QRectF(self.rect()).adjusted(7, 7, -7, -7)
        p.fillRect(r, QColor(5, 14, 34, 200))
        path = QPainterPath()
        path.addRect(r)
        neon_path(p, path, color, core, width=1.1, halo=3, spread=2.2, alpha=36)


class IconBox(NeonBox):
    def __init__(self, icon_name="circle-alert", tone="", size=46, parent=None):
        super().__init__(tone, parent)
        self.icon_name = icon_name
        self.setFixedSize(size, size)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color, core = palette(self.tone)
        s = self.width() * 0.46
        r = QRectF((self.width() - s) / 2, (self.height() - s) / 2, s, s)
        p.setOpacity(0.45)
        icons.paint(p, self.icon_name, r, color, 4.0)
        p.setOpacity(1.0)
        icons.paint(p, self.icon_name, r, core, 2.0)


class TitleBar(QWidget):
    """[ (!) ] [  TÍTULO  ]  como en las ventanas del Sistema."""

    def __init__(self, text: str, icon_name: str = "circle-alert", tone: str = "", size: int = 15, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        h = int(size * 2.9) + 14
        self.icon = IconBox(icon_name, tone, h)
        lay.addWidget(self.icon)
        self.box = NeonBox(tone)
        bl = QHBoxLayout(self.box)
        bl.setContentsMargins(26, 0, 26, 0)
        self.label = QLabel(text)
        f = QFont(T.FONT, size)
        f.setBold(True)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, size * 0.28)
        self.label.setFont(f)
        self.label.setStyleSheet(f"color:{palette(tone)[1]}; background: transparent;")
        bl.addWidget(self.label)
        self.box.setFixedHeight(h)
        lay.addWidget(self.box)

    def set_text(self, text: str):
        self.label.setText(text)
        self.adjustSize()

    def set_icon(self, name: str):
        self.icon.icon_name = name
        self.icon.update()

    def set_tone(self, tone: str):
        self.icon.tone = self.box.tone = tone
        self.label.setStyleSheet(f"color:{palette(tone)[1]}; background: transparent;")
        self.update()
        self.icon.update()
        self.box.update()
