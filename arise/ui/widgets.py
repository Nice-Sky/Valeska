"""Componentes reutilizables: paneles holográficos, insignia de rango, ventanas del Sistema, avisos."""
from __future__ import annotations

from collections import deque
from typing import Callable, Optional

from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRect, QRectF, Qt, QTimer, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (QDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLayout, QLineEdit, QPushButton,
                               QVBoxLayout, QWidget)

from . import fx, holo, icons
from . import theme as T


class HoloButton(QPushButton, holo.Surface):
    """Botón holográfico: vidrio + borde de neón con bloom; los principales tienen relleno azul."""

    sweep = False
    M = 7

    def __init__(self, text: str, kind: str = "", icon: str = ""):
        QPushButton.__init__(self, text)
        self.kind = kind
        self.icon_name = icon
        self.hover = False
        self.setProperty("kind", kind)
        self.setStyleSheet("QPushButton { background: transparent; border: none; padding: 16px 28px; }")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.surface_init()

    def setIcon(self, ic):  # compatibilidad: se usa set_icon_name
        pass

    def set_icon_name(self, name: str):
        self.icon_name = name
        self.update()

    def setProperty(self, name, value):
        if name == "kind":
            self.kind = value or ""
            self.update()
        return super().setProperty(name, value)

    def sizeHint(self):
        f = QFont(T.FONT, 11)
        f.setWeight(QFont.Weight.DemiBold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.6)
        from PySide6.QtGui import QFontMetricsF
        w = QFontMetricsF(f).horizontalAdvance(self.text()) + 52 + (26 if self.icon_name else 0)
        return QSize(int(max(w, 90)), 50)

    def minimumSizeHint(self):
        return QSize(min(self.sizeHint().width(), 140), 50)

    def enterEvent(self, e):
        self.hover = True
        self.update()

    def leaveEvent(self, e):
        self.hover = False
        self.update()

    def mousePressEvent(self, e):
        from .. import voice as _v
        if _v.SOUNDS_REF and self.isEnabled():
            _v.SOUNDS_REF.play("click")
        super().mousePressEvent(e)

    def surface_spec(self):
        tone = "red" if self.kind == "danger" else ""
        fill = None
        if self.kind == "primary":
            fill = "#2f86ff" if not self.hover else "#4aa0ff"
        elif self.kind == "danger" and self.hover:
            fill = T.RED
        elif self.hover:
            fill = "#1d4fa8"
        return holo.SurfaceSpec(QRectF(self.rect()).adjusted(self.M, self.M, -self.M, -self.M), tone, cut=5,
                                brackets=False, strong=True, seed=3, glass_alpha=225, density=0.25, small=True,
                                fill=fill)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.35)
        self.paint_surface(p)
        color, core = holo.palette("red" if self.kind == "danger" else "")
        f = QFont(T.FONT, 11)
        f.setWeight(QFont.Weight.DemiBold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.6)
        from PySide6.QtGui import QFontMetricsF
        fm = QFontMetricsF(f)
        tw = fm.horizontalAdvance(self.text())
        iw = 26 if self.icon_name else 0
        x = (self.width() - tw - iw) / 2
        if self.icon_name:
            icons.paint(p, self.icon_name, QRectF(x, (self.height() - 18) / 2, 18, 18), core, 1.9)
        p.setFont(f)
        p.setPen(QColor("white" if self.kind in ("primary",) or self.hover else core))
        p.drawText(QRectF(x + iw, 0, tw + 4, self.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   self.text())


def button(text: str, kind: str = "", slot: Optional[Callable] = None, icon: str = "") -> QPushButton:
    if kind == "ghost":
        b = QPushButton(text)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setProperty("kind", kind)
    else:
        b = HoloButton(text.strip(), kind, icon)
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


class Panel(QFrame, holo.Surface):
    """Ventana holográfica con borde de neón, bloom y encabezado [ícono][TÍTULO]."""

    _seed = 1
    INSET = 16

    def __init__(self, title: str = "", icon: str = "circle-alert", parent=None, compact: bool = False):
        QFrame.__init__(self, parent)
        Panel._seed += 1
        self.seed = Panel._seed
        self.tone = ""
        self.compact = compact
        self.sweep = not compact
        self.surface_init()
        self.lay = QVBoxLayout(self)
        m = self.INSET + (12 if compact else 24)
        self.lay.setContentsMargins(m + 4, m - (2 if title else 0), m + 4, m)
        self.lay.setSpacing(10)
        self.title = None
        if title:
            self.title = holo.TitleBar(title, icon)
            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(self.title)
            row.addStretch()
            self.lay.addLayout(row)
            self.lay.addSpacing(4)

    def surface_spec(self):
        r = QRectF(self.rect()).adjusted(self.INSET, self.INSET, -self.INSET, -self.INSET)
        return holo.SurfaceSpec(r, self.tone, cut=8 if self.compact else 14, brackets=not self.compact,
                                seed=self.seed, density=0.6 if self.compact else 1.0, glass_alpha=165)

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
        self.paint_surface(p)


class RankBadge(QWidget):
    COLORS = {"S": T.GOLD, "A": T.PURPLE}

    def __init__(self, size: int = 96, parent=None):
        super().__init__(parent)
        self.rank = "E"
        self.setFixedSize(size, size)
        self._key = None
        self._img = None
        self._glow = None
    def set_rank(self, r: str):
        self.rank = r
        self.update()

    def _build(self):
        w, h = self.width(), self.height()
        dpr = self.devicePixelRatioF()
        m = 16
        poly = QPolygonF([QPointF(w / 2, m), QPointF(w - m, h * .29), QPointF(w - m, h * .71),
                          QPointF(w / 2, h - m), QPointF(m, h * .71), QPointF(m, h * .29)])
        path = QPainterPath()
        path.addPolygon(poly)
        path.closeSubpath()
        col = self.COLORS.get(self.rank, T.GLOW)
        base = fx.new_image(w, h, dpr)
        neon = fx.new_image(w, h, dpr)
        pb = QPainter(base)
        pb.setRenderHint(QPainter.RenderHint.Antialiasing)
        holo.glass(pb, path, col, seed=4, strong=True, density=0.5)
        pn = QPainter(neon)
        pn.setRenderHint(QPainter.RenderHint.Antialiasing)
        holo._stroke(pn, path, col, T.CORE, 2.4, 1.1)
        inner = QPolygonF([QPointF(w / 2 + (pt.x() - w / 2) * 0.82, h / 2 + (pt.y() - h / 2) * 0.82) for pt in poly])
        ip = QPainterPath()
        ip.addPolygon(inner)
        ip.closeSubpath()
        pn.setPen(QPen(holo.qc(col, 110), 1))
        pn.drawPath(ip)
        pn.end()
        pb.drawImage(0, 0, neon)
        pb.end()
        self._img, self._glow = base, fx.edge_fade(fx.bloom(neon, ((3, 1.2), (7, 1.0), (12, 0.7))), 14)

    def paintEvent(self, e):
        key = (self.width(), self.rank, self.devicePixelRatioF())
        if key != self._key:
            self._build()
            self._key = key
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.drawImage(0, 0, self._img)
        k = fx.Clock.get().pulse(5.0, 0.85, 1.0)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.setOpacity(k)
        p.drawImage(0, 0, self._glow)
        p.setOpacity(1)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        col = self.COLORS.get(self.rank, T.GLOW)
        f = QFont(T.FONT, int(self.height() * 0.3))
        f.setWeight(QFont.Weight.Bold)
        fx.draw_glow_text(p, QRectF(self.rect()).adjusted(0, -2, 0, 0), self.rank, f, col, T.CORE, glow=1.3, intensity=k)


class _HoloBody(QWidget, holo.Surface):
    MX, MY = 136, 92

    def __init__(self, tone, parent=None):
        QWidget.__init__(self, parent)
        self.tone = tone
        self.surface_init()

    def surface_spec(self):
        r = QRectF(self.rect()).adjusted(self.MX, self.MY, -self.MX, -self.MY)
        return holo.SurfaceSpec(r, self.tone, cut=4, beams=True, brackets=False, strong=True, seed=11,
                                glass_alpha=215)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.paint_surface(p)


class _Reveal(QWidget):
    """Capa encima del diálogo que anima su "materialización": línea de luz -> despliegue vertical -> parpadeo."""

    def __init__(self, dlg):
        super().__init__(dlg)
        self.dlg = dlg
        self.k = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, e):
        k = self.k
        if k >= 1:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        cy = r.center().y()
        ease = lambda x: 1 - (1 - max(0.0, min(1.0, x))) ** 3
        tone = self.dlg.tone
        color, core = holo.palette(tone)
        if k < 0.22:  # solo una línea de luz que se estira desde el centro
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            p.fillRect(r, Qt.GlobalColor.transparent)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            w = (r.width() - 120) * ease(k / 0.22)
            holo.neon_line(p, r.center().x() - w / 2, cy, r.center().x() + w / 2, cy, color, core, 2.4, 6, 3, 40)
            return
        if k < 0.55:  # se despliega hacia arriba y abajo
            half = (r.height() / 2) * ease((k - 0.22) / 0.33)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            p.fillRect(QRectF(r.left(), r.top(), r.width(), cy - half - r.top()), Qt.GlobalColor.transparent)
            p.fillRect(QRectF(r.left(), cy + half, r.width(), r.bottom() - cy - half), Qt.GlobalColor.transparent)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            for y in (cy - half, cy + half):
                holo.neon_line(p, r.left() + 60, y, r.right() - 60, y, color, core, 1.6, 4, 2.4, 34)
            return
        # parpadeo holográfico
        import math as _m
        jitter = 0.5 * (1 - (k - 0.55) / 0.45) * abs(_m.sin(k * 90))
        if jitter > 0.02:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
            p.fillRect(r, QColor(0, 0, 0, int(255 * jitter)))


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
        outer.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        body_w = _HoloBody(tone)
        outer.addWidget(body_w)
        lay = QVBoxLayout(body_w)
        lay.setContentsMargins(_HoloBody.MX + 34, _HoloBody.MY + 30, _HoloBody.MX + 34, _HoloBody.MY + 30)
        lay.setSpacing(20)
        row = QHBoxLayout()
        row.addStretch()
        self.title_bar = holo.TitleBar(title, icon, tone, 17)
        row.addWidget(self.title_bar)
        row.addStretch()
        lay.addLayout(row)
        self.tone = tone
        self.body_w = body_w
        b = QLabel(body)
        b.setObjectName("sysBody")
        b.setWordWrap(True)
        b.setTextFormat(Qt.TextFormat.RichText)
        b.setAlignment(Qt.AlignmentFlag.AlignCenter)
        b.setFixedWidth(500)
        b.ensurePolished()
        b.setMinimumHeight(b.heightForWidth(500) + 8)
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
        from PySide6.QtCore import QVariantAnimation
        self._reveal = _Reveal(self)
        self._reveal.setGeometry(self.rect())
        self._reveal.raise_()
        self.title_bar.box.reveal = 0.0
        fx.Clock.get().tick.connect(self.update)
        self.open()
        self._reveal.setGeometry(self.rect())
        a = QVariantAnimation(self)
        a.setDuration(760)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.valueChanged.connect(self._on_k)
        a.start()
        self._anim = a

    def _on_k(self, k):
        self._reveal.k = k
        self.title_bar.box.reveal = max(0.0, min(1.0, (k - 0.5) / 0.4))
        self.update()

    def _choose(self, i):
        if getattr(self, "_closing", False):
            return
        self._closing = True
        self.result_index = i
        from PySide6.QtCore import QVariantAnimation
        a = QVariantAnimation(self)
        a.setDuration(240)
        a.setStartValue(0.54)
        a.setEndValue(0.0)
        a.valueChanged.connect(lambda k: (setattr(self._reveal, "k", k), self.update()) if hasattr(self, "_reveal") else None)
        a.finished.connect(self._finish_close)
        a.start()
        self._anim = a
        from .. import voice as _v
        if _v.SOUNDS_REF:
            _v.SOUNDS_REF.play("close")

    def _finish_close(self):
        try:
            fx.Clock.get().tick.disconnect(self.update)
        except (RuntimeError, TypeError):
            pass
        self.accept()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            return  # hay que elegir una opción
        super().keyPressEvent(e)

    def value(self) -> str:
        return self.input.text() if self.input else ""


class _Dimmer(QWidget):
    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 3, 12, 185))


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
            d.layout().activate()
            d.adjustSize()
            g = self.parent.frameGeometry()
            d.move(g.center() - d.rect().center())
        d.open_animated()

    @property
    def busy(self) -> bool:
        return self.current is not None or bool(self.queue)


class _Toast(QWidget, holo.Surface):
    sweep = False

    def __init__(self, parent, text, icon_name, gold):
        QWidget.__init__(self, parent)
        self.gold = gold
        self.text_, self.icon_name = text, icon_name
        self.fade = 1.0
        self.surface_init()
        self.font_ = QFont(T.FONT, 10)
        self.font_.setWeight(QFont.Weight.DemiBold)
        from PySide6.QtGui import QFontMetricsF
        w = QFontMetricsF(self.font_).horizontalAdvance(text)
        self.setFixedSize(int(w + 100), 66)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def surface_spec(self):
        return holo.SurfaceSpec(QRectF(self.rect()).adjusted(14, 14, -14, -14), "gold" if self.gold else "", cut=6,
                                brackets=False, strong=True, seed=5, glass_alpha=240, density=0.3, small=True)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self.fade)
        self.paint_surface(p)
        p.setOpacity(self.fade)
        col = T.GOLD if self.gold else T.CORE
        icons.paint(p, self.icon_name, QRectF(34, (self.height() - 18) / 2, 18, 18), col, 1.9)
        p.setFont(self.font_)
        p.setPen(QColor(col))
        p.drawText(QRectF(62, 0, self.width() - 70, self.height()), Qt.AlignmentFlag.AlignVCenter, self.text_)


class Toaster:
    """Avisos breves: ahora salen como notificaciones de escritorio holográficas (ver notify.py)."""

    def __init__(self, parent: QWidget, notifier=None):
        self.parent = parent
        self.notifier = notifier
        self.items: list[QWidget] = []

    def show(self, text: str, gold: bool = False, icon: str = ""):
        if self.notifier is not None:
            self.notifier.show("SISTEMA" if not gold else "LOGRO", text, icon or ("sparkles" if gold else "bell-ring"),
                               "gold" if gold else "", timeout=4.5, sound="notify")
            return
        self._show_inline(text, gold, icon)

    def _show_inline(self, text: str, gold: bool = False, icon: str = ""):
        t = _Toast(self.parent, text, icon or ("sparkles" if gold else "bell-ring"), gold)
        t.show()
        t.raise_()
        self.items.append(t)
        self._layout()
        from PySide6.QtCore import QVariantAnimation
        anim = QVariantAnimation(t)
        anim.setDuration(600)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.valueChanged.connect(lambda v, t=t: setattr(t, "fade", v))
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
            y += t.height() - 6


class GlowLabel(QWidget):
    """Texto con resplandor real (bloom). Para números grandes y títulos."""

    def __init__(self, text: str = "", size: int = 22, weight=QFont.Weight.Bold, color: str = T.GLOW,
                 core: str = T.CORE, align=Qt.AlignmentFlag.AlignLeft, spacing: float = 0.0, glow: float = 1.0):
        super().__init__()
        self.text_ = text
        self.font_ = QFont(T.FONT, size)
        self.font_.setWeight(weight)
        self.color, self.core, self.align, self.spacing, self.glow = color, core, align, spacing, glow
        self._phase = 0.0
        self._fit()

    def _fit(self):
        f = QFont(self.font_)
        if self.spacing:
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, self.spacing)
        from PySide6.QtGui import QFontMetricsF
        fm = QFontMetricsF(f)
        self.setMinimumSize(int(fm.horizontalAdvance(self.text_) + 8), int(fm.height() + 6))
        self.updateGeometry()

    def setText(self, text: str):
        self.text_ = str(text)
        self._fit()
        self.update()

    def text(self):
        return self.text_

    def set_color(self, color: str):
        self.color = color
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fx.draw_glow_text(p, QRectF(self.rect()), self.text_, self.font_, self.color, self.core, self.align,
                          glow=self.glow, spacing=self.spacing, intensity=fx.Clock.get().pulse(5.0, 0.85, 1.0))


class NeonBar(QWidget):
    """Barra de progreso con tubo de luz (para XP)."""

    def __init__(self, height: int = 30):
        super().__init__()
        self.value, self.maximum, self.text_ = 0, 100, ""
        self.setFixedHeight(height)

    def setRange(self, a, b):
        self.maximum = max(1, b)
        self.update()

    def setValue(self, v):
        self.value = v
        self.update()

    def setFormat(self, t):
        self.text_ = t
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(6, 7, -6, -7)
        path = holo.chamfer(r, 4)
        p.fillPath(path, QColor(2, 8, 22, 230))
        k = max(0.0, min(1.0, self.value / self.maximum))
        if k > 0:
            fr = QRectF(r.left() + 2, r.top() + 2, (r.width() - 4) * k, r.height() - 4)
            from PySide6.QtGui import QLinearGradient
            g = QLinearGradient(fr.topLeft(), fr.bottomLeft())
            g.setColorAt(0, QColor(T.GLOW))
            g.setColorAt(0.45, QColor(T.CORE))
            g.setColorAt(1, QColor("#1d5fd8"))
            pulse = fx.Clock.get().pulse(3.0, 0.6, 1.0)
            for i in range(5, 0, -1):
                c = QColor(T.GLOW)
                c.setAlpha(int(22 * pulse))
                p.fillRect(fr.adjusted(-i * 1.5, -i * 1.2, i * 1.5, i * 1.2), c)
            p.fillRect(fr, g)
        holo.neon_path(p, path, T.GLOW, T.CORE, 1.0, 3, 2.0, 26)
        f = QFont(T.FONT, 9)
        f.setWeight(QFont.Weight.DemiBold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
        p.setFont(f)
        p.setPen(QColor(0, 0, 0, 150))
        p.drawText(r.translated(1, 1), Qt.AlignmentFlag.AlignCenter, self.text_)
        p.setPen(QColor("white"))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.text_)
