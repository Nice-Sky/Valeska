"""Componentes reutilizables: paneles holográficos, insignia de rango, ventanas del Sistema, avisos."""
from __future__ import annotations

from collections import deque
from typing import Callable, Optional

from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRect, QRectF, Qt, QTimer, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPolygonF
from PySide6.QtWidgets import (QDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout, QWidget)

from . import holo, icons
from . import theme as T


def button(text: str, kind: str = "", slot: Optional[Callable] = None, icon: str = "") -> QPushButton:
    b = QPushButton(("  " + text) if icon and text else text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if kind:
        b.setProperty("kind", kind)
    if icon:
        b.setIcon(icons.icon(icon, 18))
        b.setIconSize(QSize(18, 18))
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


def icon_label(name: str, size: int = 20, color: str = icons.WHITE) -> QLabel:
    l = QLabel()
    l.setPixmap(icons.pixmap(name, size, color))
    l.setFixedSize(size + 2, size + 2)
    return l


def glow(widget, color=None, radius=None):  # compatibilidad: el brillo ahora se dibuja a mano
    return None


def restyle(w: QWidget):
    w.style().unpolish(w)
    w.style().polish(w)
    for c in w.findChildren(QWidget):
        c.style().unpolish(c)
        c.style().polish(c)


class Panel(QFrame):
    """Ventana holográfica con borde de neón y encabezado [ícono][TÍTULO]."""

    _seed = 1

    def __init__(self, title: str = "", icon: str = "circle-alert", parent=None, compact: bool = False):
        super().__init__(parent)
        Panel._seed += 1
        self.seed = Panel._seed
        self.tone = ""
        self.compact = compact
        self.lay = QVBoxLayout(self)
        m = 14 if compact else 26
        self.lay.setContentsMargins(m + 4, m, m + 4, m)
        self.lay.setSpacing(10)
        self.title = None
        if title:
            self.title = holo.TitleBar(title, icon)
            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(self.title)
            row.addStretch()
            self.lay.addLayout(row)
            self.lay.addSpacing(6)

    def set_title(self, text: str):
        if self.title:
            self.title.set_text(text)

    def set_tone(self, tone: str = ""):
        self.tone = tone
        if self.title:
            self.title.set_tone(tone)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        holo.holo_frame(p, QRectF(self.rect()).adjusted(6, 6, -6, -6), self.tone, self.seed,
                        cut=8 if self.compact else 12, brackets=not self.compact)


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
        m = 10
        poly = QPolygonF([QPointF(w / 2, m), QPointF(w - m, h * .27), QPointF(w - m, h * .73),
                          QPointF(w / 2, h - m), QPointF(m, h * .73), QPointF(m, h * .27)])
        path = QPainterPath()
        path.addPolygon(poly)
        path.closeSubpath()
        col = self.COLORS.get(self.rank, T.GLOW)
        holo.glass(p, path, col, seed=4, scratches=8)
        holo.neon_path(p, path, col, T.CORE, width=1.6, halo=5, alpha=34)
        f = QFont(T.FONT, int(h * 0.36))
        f.setBold(True)
        p.setFont(f)
        p.setPen(holo.qc(col, 70))
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-3, -3), (3, 3)):
            p.drawText(QRectF(dx, dy, w, h), Qt.AlignmentFlag.AlignCenter, self.rank)
        p.setPen(QColor(T.CORE if self.rank not in self.COLORS else col))
        p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, self.rank)


class _HoloBody(QWidget):
    def __init__(self, tone, parent=None):
        super().__init__(parent)
        self.tone = tone

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        holo.holo_frame(p, QRectF(self.rect()).adjusted(44, 40, -44, -40), self.tone, seed=11, cut=6,
                        beams=True, strong=True, brackets=False)


class SystemDialog(QDialog):
    """Ventana de notificación del Sistema: barras de luz arriba/abajo, [!][TÍTULO] y texto centrado."""

    def __init__(self, parent, title, body, buttons, tone="", with_input=False, placeholder="", icon="circle-alert"):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.result_index = -1
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        body_w = _HoloBody(tone)
        outer.addWidget(body_w)
        lay = QVBoxLayout(body_w)
        lay.setContentsMargins(84, 70, 84, 70)
        lay.setSpacing(18)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(holo.TitleBar(title, icon, tone, 16))
        row.addStretch()
        lay.addLayout(row)
        b = QLabel(body)
        b.setObjectName("sysBody")
        b.setWordWrap(True)
        b.setTextFormat(Qt.TextFormat.RichText)
        b.setAlignment(Qt.AlignmentFlag.AlignCenter)
        b.setMinimumWidth(420)
        b.setMaximumWidth(560)
        lay.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)
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
            btn.setMinimumWidth(120)
            btn.clicked.connect(lambda _=False, i=i: self._choose(i))
            brow.addWidget(btn)
        brow.addStretch()
        lay.addLayout(brow)
        if self.input:
            self.input.returnPressed.connect(lambda: self._choose(0))
            QTimer.singleShot(50, self.input.setFocus)

    def open_animated(self):
        self.adjustSize()
        final = self.geometry()
        self.open()
        start = QRect(final.x(), final.center().y() - 2, final.width(), 4)
        self.setGeometry(start)
        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setDuration(260)
        self._anim.setStartValue(start)
        self._anim.setEndValue(final)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._anim.start()

    def _choose(self, i):
        self.result_index = i
        self.accept()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            return  # hay que elegir una opción
        super().keyPressEvent(e)

    def value(self) -> str:
        return self.input.text() if self.input else ""


class _Dimmer(QWidget):
    def paintEvent(self, e):
        QPainter(self).fillRect(self.rect(), QColor(0, 3, 12, 170))


class Dialogs:
    """Cola de ventanas del Sistema: se muestran de a una, sin bloquear la cámara."""

    ICONS = {"red": "triangle-alert", "gold": "sparkles"}

    def __init__(self, parent: QWidget, sounds=None):
        self.parent = parent
        self.sounds = sounds
        self.queue: deque = deque()
        self.current: Optional[SystemDialog] = None
        self.dimmer = _Dimmer(parent)
        self.dimmer.hide()

    def show(self, title, body, buttons=("Aceptar",), tone="", sound="open",
             callback: Optional[Callable[[int, str], None]] = None, with_input=False, placeholder="", icon=""):
        self.queue.append((title, body, buttons, tone, sound, callback, with_input, placeholder, icon))
        if self.current is None:
            QTimer.singleShot(0, self._next)

    def _next(self):
        if self.current is not None or not self.queue:
            if self.current is None:
                self.dimmer.hide()
            return
        title, body, buttons, tone, sound, cb, with_input, ph, icon = self.queue.popleft()
        d = SystemDialog(self.parent, title, body, list(buttons), tone, with_input, ph,
                         icon or self.ICONS.get(tone, "circle-alert"))
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
            self.dimmer.setGeometry(self.parent.rect())
            self.dimmer.show()
            self.dimmer.raise_()
            d.adjustSize()
            g = self.parent.frameGeometry()
            d.move(g.center() - d.rect().center())
        d.open_animated()

    @property
    def busy(self) -> bool:
        return self.current is not None or bool(self.queue)


class _Toast(QWidget):
    def __init__(self, parent, text, icon_name, gold):
        super().__init__(parent)
        self.gold = gold
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 12, 22, 12)
        lay.setSpacing(10)
        col = T.GOLD if gold else T.CORE
        lay.addWidget(icon_label(icon_name, 18, col))
        l = QLabel(text)
        l.setStyleSheet(f"color:{col};font-weight:600;font-size:14px;")
        lay.addWidget(l)
        self.adjustSize()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        holo.holo_frame(p, QRectF(self.rect()).adjusted(4, 4, -4, -4), "gold" if self.gold else "", 5, cut=6,
                        strong=True, brackets=False)


class Toaster:
    def __init__(self, parent: QWidget):
        self.parent = parent
        self.items: list[QWidget] = []

    def show(self, text: str, gold: bool = False, icon: str = ""):
        t = _Toast(self.parent, text, icon or ("sparkles" if gold else "bell-ring"), gold)
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
        y = 12
        for t in self.items:
            t.move(self.parent.width() - t.width() - 16, y)
            y += t.height() + 4
