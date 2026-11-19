"""Superficies holográficas: vidrio texturizado, neón con bloom real, tubos de luz y fondo."""
from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen,
                           QRadialGradient)
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from . import fx, icons
from . import theme as T

PALETTES = {
    "": (T.GLOW, T.CORE),
    "blue": (T.GLOW, T.CORE),
    "red": (T.RED, "#ffe6ea"),
    "gold": (T.GOLD, "#fff7e0"),
}


def palette(tone: str):
    return PALETTES.get(tone or "", PALETTES[""])


def qc(color: str, alpha: int = 255) -> QColor:
    c = QColor(color)
    c.setAlpha(max(0, min(255, alpha)))
    return c


# ================================================================== primitivas (dibujo directo)
def chamfer(r: QRectF, cut: float = 10) -> QPainterPath:
    path = QPainterPath()
    if cut <= 0:
        path.addRect(r)
        return path
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


def neon_path(p: QPainter, path: QPainterPath, color: str, core: str = T.CORE, width: float = 1.4,
              halo: int = 4, spread: float = 2.6, alpha: int = 34):
    """Neón sin bloom real (para cosas que se redibujan en cada cuadro, como el HUD de la cámara)."""
    p.setBrush(Qt.BrushStyle.NoBrush)
    for i in range(halo, 0, -1):
        pen = QPen(qc(color, alpha), width + i * spread)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        p.setPen(pen)
        p.drawPath(path)
    p.setPen(QPen(qc(color, 235), width + 0.8))
    p.drawPath(path)
    p.setPen(QPen(qc(core, 255), max(0.8, width * 0.55)))
    p.drawPath(path)


def neon_line(p, x1, y1, x2, y2, color, core=T.CORE, width=1.4, halo=4, spread=2.6, alpha=34):
    path = QPainterPath(QPointF(x1, y1))
    path.lineTo(QPointF(x2, y2))
    neon_path(p, path, color, core, width, halo, spread, alpha)


def _cracks(p: QPainter, r: QRectF, color: str, rnd: random.Random, count: int, alpha=(14, 40)):
    """Líneas finas tipo vidrio rayado / grietas holográficas."""
    p.setBrush(Qt.BrushStyle.NoBrush)
    for _ in range(count):
        x = r.left() + rnd.random() * r.width()
        y = r.top() + rnd.random() * r.height()
        ang = math.radians(-28 + rnd.uniform(-35, 35))
        path = QPainterPath(QPointF(x, y))
        for _ in range(rnd.randint(3, 8)):
            ln = rnd.uniform(10, 55)
            ang += math.radians(rnd.uniform(-35, 35))
            x += math.cos(ang) * ln
            y += math.sin(ang) * ln
            path.lineTo(QPointF(x, y))
            if rnd.random() < 0.25:  # ramita
                b = QPainterPath(QPointF(x, y))
                ba = ang + math.radians(rnd.choice((-1, 1)) * rnd.uniform(30, 70))
                b.lineTo(QPointF(x + math.cos(ba) * rnd.uniform(8, 25), y + math.sin(ba) * rnd.uniform(8, 25)))
                p.setPen(QPen(qc(color, rnd.randint(*alpha) // 2), 0.8))
                p.drawPath(b)
        p.setPen(QPen(qc(color, rnd.randint(*alpha)), rnd.choice((0.7, 0.9, 1.1))))
        p.drawPath(path)


def glass(p: QPainter, path: QPainterPath, color: str, seed: int = 1, strong: bool = False, density: float = 1.0,
          alpha: int = 225):
    """Vidrio oscuro con gradiente, grietas finas, grano y líneas de escaneo."""
    r = path.boundingRect()
    g = QLinearGradient(r.topLeft(), r.bottomRight())
    g.setColorAt(0, QColor(9, 24, 56, alpha))
    g.setColorAt(0.5, QColor(3, 9, 24, alpha))
    g.setColorAt(1, QColor(7, 18, 44, alpha))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawPath(path)
    p.save()
    p.setClipPath(path)
    rad = QRadialGradient(QPointF(r.center().x(), r.top() + r.height() * 0.35), max(r.width(), r.height()) * 0.75)
    rad.setColorAt(0, qc(color, 40 if strong else 26))
    rad.setColorAt(1, qc(color, 0))
    p.fillRect(r, rad)
    rnd = random.Random(seed)
    area = r.width() * r.height()
    _cracks(p, r, color, rnd, int(max(6, area / 6500) * density), (18, 52))
    p.fillRect(r, QBrush(fx.noise_tile()))
    p.setPen(QPen(QColor(120, 190, 255, 7), 1))
    y = r.top()
    while y < r.bottom():
        p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        y += 3
    p.restore()


def holo_frame(p: QPainter, rect: QRectF, tone: str = "", seed: int = 1, cut: float = 10, beams: bool = False,
               strong: bool = False, brackets: bool = True):
    """Versión liviana (sin bloom) para elementos que se repintan constantemente."""
    color, core = palette(tone)
    path = chamfer(rect, cut)
    glass(p, path, color, seed, strong=strong, density=0.5)
    neon_path(p, path, color, core, width=1.1, halo=4, spread=2.4, alpha=30)


# ================================================================== piezas de neón (se dibujan en la capa que recibe bloom)
def _stroke(p: QPainter, path: QPainterPath, color: str, core: str, width: float = 1.6, core_w: float = 0.9,
            color_alpha: int = 255):
    p.setBrush(Qt.BrushStyle.NoBrush)
    pen = QPen(qc(color, color_alpha), width)
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    pen.setCapStyle(Qt.PenCapStyle.SquareCap)
    p.setPen(pen)
    p.drawPath(path)
    pen = QPen(qc(core, 255), core_w)
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    p.setPen(pen)
    p.drawPath(path)


def _line(p, x1, y1, x2, y2, color, core, width=1.4, core_w=0.8, alpha=255):
    path = QPainterPath(QPointF(x1, y1))
    path.lineTo(QPointF(x2, y2))
    _stroke(p, path, color, core, width, core_w, alpha)


def _tube(p: QPainter, x1: float, x2: float, y: float, h: float, color: str, core: str):
    """Tubo de luz con volumen (gradiente a lo alto: borde oscuro → color → núcleo blanco)."""
    r = QRectF(x1, y - h / 2, x2 - x1, h)
    g = QLinearGradient(r.topLeft(), r.bottomLeft())
    g.setColorAt(0.0, qc(color, 90))
    g.setColorAt(0.28, qc(color, 255))
    g.setColorAt(0.5, qc(core, 255))
    g.setColorAt(0.72, qc(color, 255))
    g.setColorAt(1.0, qc(color, 90))
    path = QPainterPath()
    path.addRoundedRect(r, h / 2, h / 2)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawPath(path)


def _beam(p: QPainter, x1: float, x2: float, y: float, color: str, core: str, rnd: random.Random, inward: int):
    """Barra de luz con detalles de circuito. `inward` = +1 si el interior está hacia abajo."""
    d = inward
    _tube(p, x1 + 6, x2 - 6, y, 11, color, core)
    _tube(p, x1 + 70, x2 - 70, y - inward * 15, 2.5, color, core)
    # carril fino exterior
    _line(p, x1 + 40, y - d * 9, x2 - 40, y - d * 9, color, core, 1.0, 0.5, 170)
    # trazas de circuito hacia adentro
    x = x1 + 24
    while x < x2 - 30:
        seg = rnd.uniform(18, 80)
        end = min(x + seg, x2 - 24)
        if rnd.random() > 0.25:
            off = rnd.choice((8, 12, 16))
            _line(p, x, y + d * off, end, y + d * off, color, core, 1.2, 0.6, 210)
            if rnd.random() < 0.4:  # baja en escalón
                _line(p, end, y + d * off, end + 6, y + d * (off + 6), color, core, 1.0, 0.5, 190)
            if rnd.random() < 0.35:
                p.fillRect(QRectF(x - 1.5, y + d * off - 1.5, 3, 3), qc(core, 255))
        x = end + rnd.uniform(6, 22)
    # remates en las puntas
    for sx, sg in ((x1, 1), (x2, -1)):
        path = QPainterPath(QPointF(sx + sg * 2, y - d * 14))
        path.lineTo(QPointF(sx + sg * 2, y + d * 6))
        path.lineTo(QPointF(sx + sg * 34, y + d * 6))
        _stroke(p, path, color, core, 2.2, 1.0)
        p.fillRect(QRectF(sx + sg * 40 - (8 if sg < 0 else 0), y + d * 4 - 2, 8, 4), qc(core, 255))


def _brackets(p: QPainter, r: QRectF, cut: float, color: str, core: str, size: float = 22):
    for (x, y, dx, dy) in ((r.left(), r.top(), 1, 1), (r.right(), r.bottom(), -1, -1),
                           (r.right(), r.top(), -1, 1), (r.left(), r.bottom(), 1, -1)):
        big = (dx == dy)
        s = size if big else size * 0.45
        path = QPainterPath(QPointF(x, y + dy * (cut + s)))
        path.lineTo(QPointF(x, y + dy * cut))
        path.lineTo(QPointF(x + dx * cut, y))
        path.lineTo(QPointF(x + dx * (cut + s), y))
        _stroke(p, path, color, core, 3.0 if big else 2.0, 1.2)


# ================================================================== superficie con caché + bloom
class SurfaceSpec:
    __slots__ = ("rect", "tone", "cut", "beams", "brackets", "strong", "seed", "glass_alpha", "frame", "density",
                 "small", "fill", "quiet")

    def __init__(self, rect: QRectF, tone="", cut=12.0, beams=False, brackets=True, strong=False, seed=1,
                 glass_alpha=235, frame=True, density=1.0, small=False, fill=None, quiet=False):
        self.rect, self.tone, self.cut, self.beams, self.brackets = rect, tone, cut, beams, brackets
        self.strong, self.seed, self.glass_alpha, self.frame, self.density = strong, seed, glass_alpha, frame, density
        self.small, self.fill, self.quiet = small, fill, quiet

    def key(self):
        r = self.rect
        return (round(r.x()), round(r.y()), round(r.width()), round(r.height()), self.tone, self.cut, self.beams,
                self.brackets, self.strong, self.seed, self.glass_alpha, self.frame, self.density, self.small, self.fill,
                self.quiet)


def build_surface(w: int, h: int, dpr: float, spec: SurfaceSpec):
    color, core = palette(spec.tone)
    r = spec.rect
    rnd = random.Random(spec.seed)
    base = fx.new_image(w, h, dpr)
    neon = fx.new_image(w, h, dpr)
    pb = QPainter(base)
    pb.setRenderHint(QPainter.RenderHint.Antialiasing)
    pn = QPainter(neon)
    pn.setRenderHint(QPainter.RenderHint.Antialiasing)

    if spec.beams:
        # placa trasera más grande, entre las barras
        back = QRectF(r.left() - 70, r.top() - 34, r.width() + 140, r.height() + 68)
        bp = QPainterPath()
        bp.addRect(back)
        glass(pb, bp, color, spec.seed + 3, density=1.6, alpha=120)
        # rieles laterales
        for x in (back.left() + 8, back.right() - 8):
            _line(pn, x, back.top() + 14, x, back.bottom() - 14, color, core, 1.6, 0.7, 200)
            for yy in (back.top() + back.height() * 0.3, back.top() + back.height() * 0.7):
                pn.fillRect(QRectF(x - 3, yy - 10, 6, 20), qc(color, 200))
                pn.fillRect(QRectF(x - 1, yy - 8, 2, 16), qc(core, 255))
        _beam(pn, back.left() - 24, back.right() + 24, back.top() - 6, color, core, rnd, +1)
        _beam(pn, back.left() - 24, back.right() + 24, back.bottom() + 6, color, core, rnd, -1)

    path = chamfer(r, spec.cut)
    glass(pb, path, color, spec.seed, strong=spec.strong, density=spec.density, alpha=spec.glass_alpha)
    if spec.frame and spec.quiet:  # versión sobria: línea fina, poco brillo
        _stroke(pn, path, color, core, 1.2, 0.5, 150)
    elif spec.frame:
        _stroke(pn, path, color, core, 1.8, 0.9, 235)
        # brillo interior pegado al borde
        inner = chamfer(r.adjusted(4, 4, -4, -4), max(0, spec.cut - 3))
        pn.setPen(QPen(qc(color, 60), 1))
        pn.setBrush(Qt.BrushStyle.NoBrush)
        pn.drawPath(inner)
    if spec.brackets:
        _brackets(pn, r, spec.cut, color, core)
    pn.end()

    if spec.fill:  # relleno de color (botones principales)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, qc(spec.fill, 150))
        g.setColorAt(0.5, qc(spec.fill, 95))
        g.setColorAt(1, qc(spec.fill, 160))
        pb.setPen(Qt.PenStyle.NoPen)
        pb.setBrush(g)
        pb.drawPath(path)
    passes = ((1.5, 1.2), (4, 1.0), (7, 0.6)) if spec.small else ((2.5, 1.3), (7, 1.1), (16, 0.9))
    glow = fx.bloom(neon, passes, gain=0.45 if spec.quiet else 1.0)
    margin = min(r.left(), r.top(), w - r.right(), h - r.bottom())
    if spec.beams:  # las barras sobresalen ~94 px a los lados y ~46 px arriba/abajo
        margin = min(r.left() - 94, w - r.right() - 94, r.top() - 46, h - r.bottom() - 46)
    fx.edge_fade(glow, max(2.0, margin))
    pb.drawImage(0, 0, neon)
    pb.end()
    return base, glow


class Surface:
    """Mezcla para widgets: cachea el vidrio + neón y le suma el bloom animado en cada pintado."""

    animated = True
    sweep = True

    def surface_spec(self) -> SurfaceSpec:  # pragma: no cover - lo implementa cada widget
        raise NotImplementedError

    def surface_init(self):
        self._skey = None
        self._sbase = self._sglow = None
        self._phase = random.random() * 10
        # el repintado lo dispara la atmósfera de la ventana (un solo update por cuadro)

    def _on_tick(self):
        if self.isVisible():
            self.update()

    def surface_images(self, spec: SurfaceSpec):
        """Vidrio+neón y bloom precalculados. Guarda varias versiones (ej. normal y hover) para no recalcular."""
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), round(dpr, 2), spec.key())
        cache = self.__dict__.setdefault("_scache", {})
        hit = cache.get(key)
        if hit is None:
            if len(cache) >= 4:
                cache.pop(next(iter(cache)))
            hit = cache[key] = build_surface(self.width(), self.height(), dpr, spec)
        return hit

    def paint_surface(self, p: QPainter, spec: SurfaceSpec | None = None, opacity: float = 1.0,
                      sweep: bool | None = None):
        spec = spec or self.surface_spec()
        base, glow = self.surface_images(spec)
        base_op = p.opacity() * opacity
        if base_op <= 0.003:
            return
        p.setOpacity(base_op)
        p.drawImage(0, 0, base)
        clock = fx.Clock.get()
        inten = clock.pulse(5.0, 0.86, 1.0, self._phase) if self.animated else 0.95
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.setOpacity(inten * base_op)
        p.drawImage(0, 0, glow)
        p.setOpacity(base_op)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        if self.animated and (self.sweep if sweep is None else sweep):
            self._paint_sweep(p, spec, clock.now() + self._phase)
        p.setOpacity(base_op / opacity if opacity else 1.0)

    def _paint_sweep(self, p: QPainter, spec: SurfaceSpec, t: float):
        period, active = 11.0, 1.6
        k = (t % period) / active
        if k > 1:
            return
        r = spec.rect
        x = r.left() - r.height() + (r.width() + r.height() * 2) * k
        g = QLinearGradient(QPointF(x - 80, r.top()), QPointF(x + 80, r.top() + 60))
        color = palette(spec.tone)[0]
        g.setColorAt(0, qc(color, 0))
        g.setColorAt(0.5, qc(color, 18))
        g.setColorAt(1, qc(color, 0))
        p.save()
        p.setClipPath(chamfer(r, spec.cut))
        p.fillRect(r, g)
        p.restore()


class HoverFade:
    """Mezcla para animar suavemente un valor 0..1 al pasar el mouse (sin recalcular el brillo)."""

    def hover_init(self, ms: int = 180):
        from PySide6.QtCore import QVariantAnimation
        self.hover_k = 0.0
        self._hanim = QVariantAnimation(self)
        self._hanim.setDuration(ms)
        self._hanim.valueChanged.connect(self._hover_val)

    def _hover_val(self, v):
        self.hover_k = float(v)
        self.update()

    def hover_to(self, target: float):
        self._hanim.stop()
        self._hanim.setStartValue(self.hover_k)
        self._hanim.setEndValue(float(target))
        self._hanim.start()


# ================================================================== fondo
class Backdrop(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._key = None
        self._img = None

    def paintEvent(self, e):
        p = QPainter(self)
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), dpr)
        if key != self._key:
            self._img = render_backdrop(self.width(), self.height(), dpr)
            self._key = key
        p.drawImage(0, 0, self._img)


def render_backdrop(w: int, h: int, dpr: float, seed: int = 9, tint: str = ""):
    img = fx.new_image(w, h, dpr)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = QRectF(0, 0, w, h)
    g = QLinearGradient(r.topLeft(), r.bottomLeft())
    g.setColorAt(0, QColor("#030a1c"))
    g.setColorAt(1, QColor("#01040c"))
    p.fillRect(r, g)
    for cx, cy, rad, a in ((0.62, 0.05, 0.75, 70), (0.1, 0.9, 0.5, 34), (0.95, 0.7, 0.4, 26)):
        gr = QRadialGradient(QPointF(w * cx, h * cy), max(w, h) * rad)
        col = QColor(T.RED if tint == "red" else "#1f6dff")
        col.setAlpha(a)
        gr.setColorAt(0, col)
        col2 = QColor(col)
        col2.setAlpha(0)
        gr.setColorAt(1, col2)
        p.fillRect(r, gr)
    # trazas de circuito con bloom suave
    lay = fx.new_image(w, h, dpr)
    pl = QPainter(lay)
    pl.setRenderHint(QPainter.RenderHint.Antialiasing)
    rnd = random.Random(seed)
    color = T.RED if tint == "red" else T.GLOW
    for _ in range(int(w * h / 26000)):
        x, y = rnd.random() * w, rnd.random() * h
        path = QPainterPath(QPointF(x, y))
        for _ in range(rnd.randint(2, 4)):
            if rnd.random() > 0.5:
                x += rnd.uniform(-180, 180)
            else:
                y += rnd.uniform(-120, 120)
            path.lineTo(QPointF(x, y))
        pl.setPen(QPen(qc(color, rnd.randint(25, 60)), 1))
        pl.drawPath(path)
        pl.fillRect(QRectF(x - 1.5, y - 1.5, 3, 3), qc(T.CORE, 90))
    pl.end()
    p.drawImage(0, 0, lay)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    p.drawImage(0, 0, fx.bloom(lay, ((4, 0.8), (14, 0.6)), gain=0.9))
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    p.fillRect(r, QBrush(fx.noise_tile(192, 10)))
    vg = QRadialGradient(r.center(), max(w, h) * 0.75)
    vg.setColorAt(0.55, QColor(0, 0, 0, 0))
    vg.setColorAt(1, QColor(0, 0, 0, 170))
    p.fillRect(r, vg)
    p.end()
    return img


def backdrop(p: QPainter, rect: QRectF, seed: int = 9, tint: str = ""):
    dpr = p.device().devicePixelRatioF() if p.device() else 1.0
    p.drawImage(rect.topLeft(), render_backdrop(int(rect.width()), int(rect.height()), dpr, seed, tint))


# ================================================================== encabezado [ícono][TÍTULO]
def title_font(size: int) -> QFont:
    f = QFont(T.FONT, size)
    f.setWeight(QFont.Weight.DemiBold)
    return f


class _Box(QWidget, Surface):
    PAD = 14

    def __init__(self, tone="", parent=None):
        QWidget.__init__(self, parent)
        self.tone = tone
        self.surface_init()

    def surface_spec(self):
        r = QRectF(self.rect()).adjusted(self.PAD, self.PAD, -self.PAD, -self.PAD)
        return SurfaceSpec(r, self.tone, cut=0, beams=False, brackets=False, strong=True, seed=5,
                           glass_alpha=215, density=0.4, small=True)

    sweep = False


class IconBox(_Box):  # noqa: E302
    def __init__(self, icon_name="circle-alert", tone="", size=46, parent=None):
        super().__init__(tone, parent)
        self.icon_name = icon_name
        self.setFixedSize(size, size)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.paint_surface(p)
        color, core = palette(self.tone)
        s = (self.width() - self.PAD * 2) * 0.56
        r = QRectF((self.width() - s) / 2, (self.height() - s) / 2, s, s)
        p.setOpacity(0.55)
        icons.paint(p, self.icon_name, r, color, 4.2)
        p.setOpacity(1.0)
        icons.paint(p, self.icon_name, r, core, 2.0)


class TextBox(_Box):
    def __init__(self, text, tone="", size=15, parent=None):
        super().__init__(tone, parent)
        self.reveal = 1.0  # 0..1: el título se escribe letra por letra al abrir
        self.text = text
        self.size = size
        self.font = title_font(size)
        self._fit()

    def _fit(self):
        sp = self.size * 0.3
        f = QFont(self.font)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, sp)
        fm = QFontMetricsF(f)
        self.setFixedSize(int(fm.horizontalAdvance(self.text) + self.size * 3.6 + self.PAD * 2),
                          int(self.size * 2.9 + self.PAD * 2))

    def set_text(self, text):
        self.text = text
        self._fit()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.paint_surface(p)
        color, core = palette(self.tone)
        txt = self.text
        if self.reveal < 1:
            n = int(len(txt) * self.reveal)
            txt = txt[:n] + ("▌" if n < len(txt) else "")
            txt = txt + " " * (len(self.text) - len(txt))
        fx.draw_glow_text(p, QRectF(self.rect()), txt, self.font, color, core,
                          glow=0.9, spacing=self.size * 0.3, intensity=fx.Clock.get().pulse(5.0, 0.85, 1.0, self._phase))


class TitleBar(QWidget):
    """[ (!) ] [  TÍTULO  ]"""

    def __init__(self, text: str, icon_name: str = "circle-alert", tone: str = "", size: int = 15, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(-14)
        self.box = TextBox(text, tone, size)
        self.icon = IconBox(icon_name, tone, self.box.height())
        lay.addWidget(self.icon)
        lay.addWidget(self.box)

    def set_text(self, text: str):
        self.box.set_text(text)
        self.adjustSize()

    def set_icon(self, name: str):
        self.icon.icon_name = name
        self.icon.update()

    def set_tone(self, tone: str):
        self.icon.tone = self.box.tone = tone
        self.icon.update()
        self.box.update()

    @property
    def label(self):  # compatibilidad con pruebas
        class _L:
            def __init__(s, b):
                s.b = b

            def text(s):
                return s.b.text
        return _L(self.box)
