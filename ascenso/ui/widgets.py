"""Componentes reutilizables: paneles, insignia de rango, ventanas del Sistema, avisos."""
from __future__ import annotations

from collections import deque
from typing import Callable, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QPropertyAnimation
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QDialog, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget)

from . import theme as T


def button(text: str, kind: str = "", slot: Optional[Callable] = None) -> QPushButton:
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if kind:
        b.setProperty("kind", kind)
    if slot:
        b.clicked.connect(slot)
    return b


def label(text: str = "", name: str = "", wrap: bool = False, align=None) -> QLabel:
    l = QLabel(text)
    if name:
        l.setObjectName(name)
    l.setWordWrap(wrap)
    if align is not None:
        l.setAlignment(align)
    return l


def glow(widget: QWidget, color: str = T.LINE, radius: int = 26):
    eff = QGraphicsDropShadowEffect(widget)
    c = QColor(color)
    c.setAlpha(150)
    eff.setColor(c)
    eff.setBlurRadius(radius)
    eff.setOffset(0, 0)
    widget.setGraphicsEffect(eff)


def restyle(w: QWidget):
    w.style().unpolish(w)
    w.style().polish(w)
    for c in w.findChildren(QWidget):
        c.style().unpolish(c)
        c.style().polish(c)


class Panel(QFrame):
    """Panel con borde brillante, esquinas marcadas y título centrado."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(20, 18, 20, 18)
        self.lay.setSpacing(10)
        self.title = None
        if title:
            self.title = QLabel(title)
            self.title.setObjectName("panelTitle")
            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(self.title)
            row.addStretch()
            self.lay.addLayout(row)
            self.lay.addSpacing(4)
        glow(self)

    def set_tone(self, tone: str = ""):
        self.setProperty("tone", tone)
        restyle(self)
        glow(self, {"red": T.RED, "gold": T.GOLD}.get(tone, T.LINE))

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        tone = self.property("tone")
        p.setPen(QPen(QColor({"red": T.RED, "gold": T.GOLD}.get(tone, T.GLOW)), 3))
        w, h, s = self.width() - 2, self.height() - 2, 14
        p.drawLine(1, 1, s, 1)
        p.drawLine(1, 1, 1, s)
        p.drawLine(w, h, w - s, h)
        p.drawLine(w, h, w, h - s)


class RankBadge(QWidget):
    COLORS = {"S": T.GOLD, "A": T.PURPLE}

    def __init__(self, size: int = 96, parent=None):
        super().__init__(parent)
        self.rank = "E"
        self.setFixedSize(size, size)

    def set_rank(self, r: str):
        self.rank = r
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        poly = QPolygonF([QPointF(w / 2, 3), QPointF(w - 3, h * .25), QPointF(w - 3, h * .75),
                          QPointF(w / 2, h - 3), QPointF(3, h * .75), QPointF(3, h * .25)])
        col = QColor(self.COLORS.get(self.rank, T.GLOW))
        fill = QColor(T.LINE)
        fill.setAlpha(70)
        p.setBrush(fill)
        p.setPen(QPen(col, 2.5))
        p.drawPolygon(poly)
        f = QFont(T.FONT, int(h * 0.42))
        f.setBold(True)
        p.setFont(f)
        glowc = QColor(col)
        glowc.setAlpha(90)
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            p.setPen(glowc)
            p.drawText(QRectF(dx, dy, w, h), Qt.AlignmentFlag.AlignCenter, self.rank)
        p.setPen(QColor("white") if self.rank not in self.COLORS else col)
        p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, self.rank)


class SystemDialog(QDialog):
    """Ventana de notificación del Sistema."""

    def __init__(self, parent, title, body, buttons, tone="", with_input=False, placeholder=""):
        super().__init__(parent)
        self.setObjectName("sysDialog")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.result_index = -1
        outer = QVBoxLayout(self)
        outer.setContentsMargins(30, 30, 30, 30)
        box = QFrame()
        box.setObjectName("sysBox")
        box.setProperty("tone", tone)
        glow(box, {"red": T.RED, "gold": T.GOLD}.get(tone, T.GLOW), 40)
        outer.addWidget(box)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(26, 22, 26, 22)
        lay.setSpacing(14)
        t = QLabel(f"(!)  {title}")
        t.setObjectName("sysTitle")
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(t)
        row.addStretch()
        lay.addLayout(row)
        b = QLabel(body)
        b.setObjectName("sysBody")
        b.setWordWrap(True)
        b.setTextFormat(Qt.TextFormat.RichText)
        b.setAlignment(Qt.AlignmentFlag.AlignCenter)
        b.setMinimumWidth(380)
        lay.addWidget(b)
        self.input = None
        if with_input:
            self.input = QLineEdit()
            self.input.setPlaceholderText(placeholder)
            self.input.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.input.setMaxLength(24)
            lay.addWidget(self.input)
        brow = QHBoxLayout()
        brow.addStretch()
        for i, spec in enumerate(buttons):
            text, kind = spec if isinstance(spec, tuple) else (spec, "primary" if i == 0 else "")
            btn = button(text, kind)
            btn.clicked.connect(lambda _=False, i=i: self._choose(i))
            brow.addWidget(btn)
        brow.addStretch()
        lay.addLayout(brow)
        if self.input:
            self.input.returnPressed.connect(lambda: self._choose(0))
            QTimer.singleShot(50, self.input.setFocus)

    def _choose(self, i):
        self.result_index = i
        self.accept()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            return  # hay que elegir una opción
        super().keyPressEvent(e)

    def value(self) -> str:
        return self.input.text() if self.input else ""


class Dialogs:
    """Cola de ventanas del Sistema: se muestran de a una, sin bloquear la cámara."""

    def __init__(self, parent: QWidget, sounds=None):
        self.parent = parent
        self.sounds = sounds
        self.queue: deque = deque()
        self.current: Optional[SystemDialog] = None

    def show(self, title, body, buttons=("Aceptar",), tone="", sound="open",
             callback: Optional[Callable[[int, str], None]] = None, with_input=False, placeholder=""):
        self.queue.append((title, body, buttons, tone, sound, callback, with_input, placeholder))
        if self.current is None:
            QTimer.singleShot(0, self._next)

    def _next(self):
        if self.current is not None or not self.queue:
            return
        title, body, buttons, tone, sound, cb, with_input, ph = self.queue.popleft()
        d = SystemDialog(self.parent, title, body, list(buttons), tone, with_input, ph)
        self.current = d

        def done(_):
            self.current = None
            if cb:
                cb(d.result_index, d.value())
            d.deleteLater()
            QTimer.singleShot(120, self._next)

        d.finished.connect(done)
        if self.sounds:
            self.sounds.play(sound)
        if self.parent.isVisible():
            d.adjustSize()
            g = self.parent.frameGeometry()
            d.move(g.center() - d.rect().center())
        d.open()

    @property
    def busy(self) -> bool:
        return self.current is not None or bool(self.queue)


class Toaster:
    def __init__(self, parent: QWidget):
        self.parent = parent
        self.items: list[QLabel] = []

    def show(self, text: str, gold: bool = False):
        t = QLabel(text, self.parent)
        t.setObjectName("toast")
        t.setProperty("gold", gold)
        t.adjustSize()
        t.show()
        t.raise_()
        self.items.append(t)
        self._layout()
        eff = QGraphicsOpacityEffect(t)
        t.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", t)
        anim.setDuration(600)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        QTimer.singleShot(2800, anim.start)
        anim.finished.connect(lambda: self._remove(t))

    def _remove(self, t):
        if t in self.items:
            self.items.remove(t)
        t.deleteLater()
        self._layout()

    def _layout(self):
        y = 16
        for t in self.items:
            t.move(self.parent.width() - t.width() - 20, y)
            y += t.height() + 8
