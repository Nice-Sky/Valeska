"""Notificaciones de escritorio estilo Windows, con estética holográfica.

Aparecen abajo a la derecha de la pantalla (encima de la barra de tareas), entran deslizándose con un parpadeo de
"materialización", se apilan, tienen una barra de tiempo y pueden traer botones. Funcionan aunque la app esté
minimizada en la bandeja.
"""
from __future__ import annotations

import math
from typing import Callable, Optional

from PySide6.QtCore import QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import fx, holo, icons
from . import theme as T

WIDTH = 410
MARGIN = 14


class NotificationCard(QWidget, holo.Surface):
    sweep = True

    def __init__(self, center: "Notifier", title: str, text: str, icon: str, tone: str,  # i18n: no
                 actions: list[tuple[str, Callable]], timeout: float, on_click: Optional[Callable]):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
                 | Qt.WindowType.WindowDoesNotAcceptFocus)
        QWidget.__init__(self, None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.center, self.tone, self.on_click = center, tone, on_click
        self.timeout = timeout
        self.elapsed = 0.0
        self.hovered = False
        self.appear = 0.0       # 0..1 animación de entrada
        self.closing = False
        self.surface_init()

        color, core = holo.palette(tone)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(30, 26, 26, 26)
        lay.setSpacing(14)
        ib = holo.IconBox(icon, tone, 58)
        lay.addWidget(ib, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(4)
        self.title_lbl = QLabel(title)
        f = QFont(T.FONT, 11)
        f.setWeight(QFont.Weight.Bold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.2)
        self.title_lbl.setFont(f)
        self.title_lbl.setStyleSheet(f"color:{core};")
        col.addWidget(self.title_lbl)
        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setStyleSheet(f"color:{T.TEXT};font-size:13px;")
        col.addWidget(body)
        if actions:
            row = QHBoxLayout()
            row.setSpacing(6)
            from .widgets import button
            for i, (label, cb) in enumerate(actions):
                b = button(label, "primary" if i == 0 else "", lambda _=False, cb=cb: (cb(), self.dismiss()))
                b.setFixedHeight(52)
                row.addWidget(b)
            row.addStretch()
            col.addLayout(row)
        lay.addLayout(col, 1)
        self.setFixedWidth(WIDTH)
        self.adjustSize()
        fx.Clock.get().tick.connect(self._tick)

    def surface_spec(self):
        r = QRectF(self.rect()).adjusted(10, 10, -10, -10)
        return holo.SurfaceSpec(r, self.tone, cut=6, brackets=True, strong=True, seed=9, glass_alpha=238,
                                density=0.5, small=True)

    def _tick(self):
        if not self.isVisible():
            return
        now = fx.Clock.get().now()
        dt = min(0.2, now - getattr(self, "_last", now))
        self._last = now
        if not self.hovered and not self.closing and self.timeout > 0:
            self.elapsed += dt
            if self.elapsed >= self.timeout:
                self.dismiss()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # parpadeo de materialización durante la entrada
        a = self.appear
        flick = 1.0 if a >= 1 else (0.35 + 0.65 * a) * (0.6 + 0.4 * abs(math.sin(a * 37)))
        p.setOpacity(flick)
        self.paint_surface(p)
        color, core = holo.palette(self.tone)
        # acento vertical a la izquierda
        r = QRectF(self.rect()).adjusted(10, 10, -10, -10)
        holo.neon_line(p, r.left() + 5, r.top() + 14, r.left() + 5, r.bottom() - 14, color, core, 2.2, 3, 2.2, 40)
        # barra de tiempo restante
        if self.timeout > 0:
            k = max(0.0, 1 - self.elapsed / self.timeout)
            y = r.bottom() - 4
            p.fillRect(QRectF(r.left() + 14, y, (r.width() - 28) * k, 2), holo.qc(color, 200))

    def enterEvent(self, e):
        self.hovered = True

    def leaveEvent(self, e):
        self.hovered = False

    def mousePressEvent(self, e):
        if self.on_click:
            self.on_click()
        self.dismiss()

    def dismiss(self):
        if self.closing:
            return
        self.closing = True
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(260)
        anim.setStartValue(self.pos())
        anim.setEndValue(self.pos() + QPoint(WIDTH + 40, 0))
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(self._gone)
        anim.start()
        self._anim = anim

    def _gone(self):
        try:
            fx.Clock.get().tick.disconnect(self._tick)
        except (RuntimeError, TypeError):
            pass
        self.center._remove(self)
        self.close()


class Notifier:
    """Administra la pila de notificaciones en la esquina inferior derecha."""

    MAX = 4

    def __init__(self, sounds=None):
        self.sounds = sounds
        self.cards: list[NotificationCard] = []

    def show(self, title: str, text: str = "", icon: str = "bell-ring", tone: str = "",
             actions: Optional[list] = None, timeout: float = 6.0, sound: str = "notify",
             on_click: Optional[Callable] = None) -> NotificationCard:
        if len(self.cards) >= self.MAX:
            self.cards[0].dismiss()
        card = NotificationCard(self, title, text, icon, tone, actions or [], timeout, on_click)
        self.cards.append(card)
        geo = QGuiApplication.primaryScreen().availableGeometry()
        target = self._slot_pos(len(self.cards) - 1, card, geo)
        card.move(target + QPoint(WIDTH + 40, 0))
        card.show()
        anim = QPropertyAnimation(card, b"pos", card)
        anim.setDuration(380)
        anim.setStartValue(card.pos())
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        card._in_anim = anim
        appear = QVariantAnimation(card)
        appear.setDuration(520)
        appear.setStartValue(0.0)
        appear.setEndValue(1.0)
        appear.valueChanged.connect(lambda v, c=card: setattr(c, "appear", v))
        appear.start()
        card._appear_anim = appear
        if self.sounds:
            self.sounds.play(sound)
        self._relayout(skip=card)
        return card

    def _slot_pos(self, index: int, card: QWidget, geo) -> QPoint:
        y = geo.bottom() - MARGIN
        for c in reversed(self.cards[index:]):
            y -= c.height() - 8
        return QPoint(geo.right() - WIDTH - MARGIN, y)

    def _relayout(self, skip=None):
        geo = QGuiApplication.primaryScreen().availableGeometry()
        y = geo.bottom() - MARGIN
        for c in reversed(self.cards):
            y -= c.height() - 8
            if c is skip or c.closing:
                continue
            a = QPropertyAnimation(c, b"pos", c)
            a.setDuration(220)
            a.setStartValue(c.pos())
            a.setEndValue(QPoint(geo.right() - WIDTH - MARGIN, y))
            a.setEasingCurve(QEasingCurve.Type.OutCubic)
            a.start()
            c._move_anim = a

    def _remove(self, card):
        if card in self.cards:
            self.cards.remove(card)
            self._relayout()

    def clear(self):
        for c in list(self.cards):
            c.dismiss()
