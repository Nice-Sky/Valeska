"""Atmósfera de la ventana principal, como una gran ventana del Sistema:

- placa de vidrio oscuro casi negro con rayones y grietas finas,
- vetas de "humo" azul oscuro que se mueven lento dentro de la placa,
- barras de luz gruesas arriba y abajo (de todo el ancho) con trazas de circuito y pilares a los costados,
- luz azul que se filtra desde las barras hacia adentro, pulsos de energía que recorren las barras.

Todo lo fijo (placa, grietas, barras, bloom) se renderiza una sola vez por tamaño de ventana; en cada cuadro solo se
dibuja el humo (a media resolución) y los brillos animados, así que se mantiene fluido.
"""
from __future__ import annotations

import math
import random
from functools import lru_cache

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

from . import fx, holo
from . import theme as T

QUALITY_FPS = {"alto": 40, "medio": 24, "bajo": 10}
BEAM_TOP = 28      # posición de las barras respecto del borde de la ventana
BEAM_BOTTOM = 24
PILLAR = 20


def _fft_noise(size: int, beta: float, seed: int) -> np.ndarray:
    """Ruido 1/f^beta periódico (se repite sin costura), normalizado 0..1."""
    rng = np.random.default_rng(seed)
    f = np.fft.fft2(rng.standard_normal((size, size)))
    ky = np.fft.fftfreq(size)[:, None]
    kx = np.fft.fftfreq(size)[None, :]
    k = np.sqrt(kx * kx + ky * ky)
    k[0, 0] = 1.0
    f *= 1.0 / k ** beta
    f[0, 0] = 0
    n = np.real(np.fft.ifft2(f))
    n -= n.min()
    return n / max(1e-9, n.max())


@lru_cache(maxsize=8)
def smoke_texture(size: int, beta: float, seed: int, color: str, alpha: float, lo: float = 0.45,
                  gamma: float = 1.8) -> QPixmap:
    n = _fft_noise(size, beta, seed)
    v = np.clip((n - lo) / (1 - lo), 0, 1) ** gamma
    c = QColor(color)
    a = (v * 255 * alpha).astype(np.float32)
    img = QImage(size, size, fx.FMT)
    arr = fx._view(img)
    arr[..., 0] = (a * c.blueF()).astype(np.uint8)
    arr[..., 1] = (a * c.greenF()).astype(np.uint8)
    arr[..., 2] = (a * c.redF()).astype(np.uint8)
    arr[..., 3] = a.astype(np.uint8)
    return QPixmap.fromImage(img)


@lru_cache(maxsize=4)
def spark_sprite(r: int = 9, color: str = T.CYAN) -> QPixmap:
    s = r * 2
    img = QImage(s, s, fx.FMT)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    g = QRadialGradient(QPointF(r, r), r)
    g.setColorAt(0, QColor(255, 255, 255, 230))
    c = QColor(color)
    c.setAlpha(120)
    g.setColorAt(0.3, c)
    c.setAlpha(0)
    g.setColorAt(1, c)
    p.fillRect(img.rect(), g)
    p.end()
    return QPixmap.fromImage(img)


@lru_cache(maxsize=2)
def pulse_sprite(w: int = 220, h: int = 30) -> QPixmap:
    """Destello alargado que recorre las barras de luz."""
    img = QImage(w, h, fx.FMT)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    g = QRadialGradient(QPointF(w / 2, w / 2), w / 2)
    g.setColorAt(0, QColor(255, 255, 255, 255))
    g.setColorAt(0.15, QColor(150, 220, 255, 200))
    g.setColorAt(0.5, QColor(60, 140, 255, 60))
    g.setColorAt(1, QColor(60, 140, 255, 0))
    p.scale(1, h / w)
    p.fillRect(QRectF(0, 0, w, w), g)
    p.end()
    return QPixmap.fromImage(img)


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max", "size")

    def __init__(self, area: QRectF, rnd: random.Random, fresh=False):
        self.x = rnd.uniform(area.left(), area.right())
        self.y = rnd.uniform(area.top(), area.bottom()) if fresh else area.bottom() - rnd.uniform(0, 30)
        self.vx = rnd.uniform(-5, 5)
        self.vy = -rnd.uniform(6, 18)
        self.max = rnd.uniform(5, 11)
        self.life = rnd.uniform(0, self.max) if fresh else 0.0
        self.size = rnd.uniform(0.3, 0.8)


def build_frame(w: int, h: int, dpr: float):
    """Placa + grietas + barras + pilares (con bloom). Se calcula una vez por tamaño."""
    color, core = T.GLOW, T.CORE
    rnd = random.Random(12)
    base = fx.new_image(w, h, dpr)
    neon = fx.new_image(w, h, dpr)
    pb = QPainter(base)
    pb.setRenderHint(QPainter.RenderHint.Antialiasing)
    pn = QPainter(neon)
    pn.setRenderHint(QPainter.RenderHint.Antialiasing)

    top, bottom = BEAM_TOP, h - BEAM_BOTTOM
    plate = QRectF(PILLAR + 6, top + 8, w - 2 * PILLAR - 12, bottom - top - 16)
    path = QPainterPath()
    path.addRect(plate)
    # vidrio casi negro
    g = QLinearGradient(plate.topLeft(), plate.bottomLeft())
    # opaca: así el brillo aditivo de los elementos nunca cambia la transparencia (evita "recuadros" raros)
    g.setColorAt(0, QColor(4, 12, 30, 255))
    g.setColorAt(0.5, QColor(1, 4, 12, 255))
    g.setColorAt(1, QColor(4, 12, 30, 255))
    pb.fillPath(path, g)
    pb.save()
    pb.setClipPath(path)
    # rayones / grietas densas (como el vidrio de la referencia)
    holo._cracks(pb, plate, "#3d7dff", rnd, int(plate.width() * plate.height() / 2600), (10, 34))
    holo._cracks(pb, plate, "#9fd4ff", rnd, int(plate.width() * plate.height() / 14000), (18, 46))
    # luz que se filtra desde las barras
    for y0, y1 in ((plate.top(), plate.top() + 140), (plate.bottom(), plate.bottom() - 140)):
        lg = QLinearGradient(QPointF(0, y0), QPointF(0, y1))
        lg.setColorAt(0, QColor(40, 120, 255, 70))
        lg.setColorAt(1, QColor(40, 120, 255, 0))
        pb.fillRect(plate, lg)
    pb.fillRect(plate, fx.noise_tile(192, 14))
    pb.restore()

    # pilares laterales
    for x in (PILLAR, w - PILLAR):
        inner = x + (6 if x < w / 2 else -6)
        holo._line(pn, x, top + 18, x, bottom - 18, color, core, 1.8, 0.8, 210)
        holo._line(pn, inner, top + 40, inner, bottom - 40, color, core, 0.8, 0.4, 120)
        for yy in (top + (bottom - top) * f for f in (0.28, 0.5, 0.72)):
            pn.fillRect(QRectF(x - 3.5, yy - 14, 7, 28), holo.qc(color, 210))
            pn.fillRect(QRectF(x - 1, yy - 11, 2, 22), holo.qc(core, 255))
    # barras de luz con circuito
    holo._beam(pn, 4, w - 4, top, color, core, rnd, +1)
    holo._beam(pn, 4, w - 4, bottom, color, core, rnd, -1)
    # borde fino de la placa
    pn.setPen(QPen(holo.qc(color, 90), 1))
    pn.setBrush(Qt.BrushStyle.NoBrush)
    pn.drawRect(plate)
    pn.end()

    glow = fx.bloom(neon, ((2.5, 1.4), (8, 1.15), (16, 0.9)), gain=1.0)
    # el resplandor no se derrama sobre el escritorio: se apaga antes del borde de la ventana
    fx.edge_fade(glow, 12)
    pb.drawImage(0, 0, neon)
    pb.end()
    return QPixmap.fromImage(base), QPixmap.fromImage(glow), plate


class Atmosphere(QWidget):
    """Fondo de la ventana principal. También maneja el reloj de animación de toda la interfaz."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.quality = "alto"
        self.rnd = random.Random(4)
        self.particles: list[Particle] = []
        self._key = None
        self._base = self._glow = None
        self._plate = QRectF()
        self._buf = None
        self.paused = False  # durante la cámara el fondo se congela para no competir con la IA
        clock = fx.Clock.get()
        clock.tick.connect(self._tick)
        self._last = clock.now()

    def set_quality(self, q: str):
        self.quality = q if q in QUALITY_FPS else "alto"
        fx.Clock.get().set_fps(QUALITY_FPS[self.quality])
        self.update()

    def _tick(self):
        if not self.isVisible() or self.quality == "bajo" or self.paused:
            return
        now = fx.Clock.get().now()
        dt = min(0.1, now - self._last)
        self._last = now
        area = self._plate
        target = 26 if self.quality == "alto" else 12
        while len(self.particles) < target and not area.isEmpty():
            self.particles.append(Particle(area, self.rnd, fresh=True))
        for i, pt in enumerate(self.particles):
            pt.x += pt.vx * dt
            pt.y += pt.vy * dt
            pt.life += dt
            if pt.life >= pt.max or pt.y < area.top():
                self.particles[i] = Particle(area, self.rnd)
        self.window().update()

    def _ensure(self):
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), round(dpr, 2))
        if key != self._key:
            self._key = key
            self._base, self._glow, self._plate = build_frame(self.width(), self.height(), dpr)
            self.particles = []

    def _smoke(self, t: float) -> QPixmap:
        """Vetas de humo azul oscuro dentro de la placa, a media resolución."""
        pl = self._plate
        w, h = max(2, int(pl.width() / 2)), max(2, int(pl.height() / 2))
        if self._buf is None or self._buf.width() != w or self._buf.height() != h:
            self._buf = QPixmap(w, h)
        self._buf.fill(Qt.GlobalColor.transparent)
        p = QPainter(self._buf)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        layers = ((smoke_texture(512, 2.5, 1, "#1544b8", 0.85, 0.40, 1.5), 2.8, (7, -3), 0.95),
                  (smoke_texture(512, 2.1, 7, "#2a72f0", 0.65, 0.48, 1.8), 1.9, (-11, -5), 0.8),
                  (smoke_texture(512, 1.8, 3, "#6ab4ff", 0.45, 0.56, 2.2), 1.3, (16, -8), 0.6))
        for tex, scale, (vx, vy), op in layers:
            if self.quality == "medio" and scale < 1.5:
                continue
            p.save()
            p.setOpacity(op * (0.82 + 0.18 * math.sin(t * 0.3 + scale * 2)))
            s = scale / 2
            p.scale(s, s)
            p.drawTiledPixmap(QRectF(0, 0, w / s + 1, h / s + 1), tex,
                              QPointF((t * vx) % tex.width(), (t * vy) % tex.height()))
            p.restore()
        p.end()
        return self._buf

    def paintEvent(self, e):
        self._ensure()
        p = QPainter(self)
        t = fx.Clock.get().now() if self.quality != "bajo" else 0.0
        if self.paused:
            t = getattr(self, "_frozen_t", t)
        else:
            self._frozen_t = t
        p.fillRect(self.rect(), QColor(0, 0, 0, 1))  # alfa mínimo invisible: la ventana recibe clics en todo su área
        p.drawPixmap(0, 0, self._base)
        pl = self._plate
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.drawPixmap(pl, self._smoke(t), QRectF(self._buf.rect()))
        # bloom de barras y pilares, con un pulso lento
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.setOpacity(0.82 + 0.18 * math.sin(t * 1.1))
        p.drawPixmap(0, 0, self._glow)
        p.setOpacity(1)
        if self.quality != "bajo":
            # pulsos de energía recorriendo las barras de luz
            ps = pulse_sprite()
            w = self.width()
            for y, speed, off in ((BEAM_TOP, 0.13, 0.0), (self.height() - BEAM_BOTTOM, 0.09, 0.55)):
                k = (t * speed + off) % 1.4
                if k <= 1.0:
                    x = -ps.width() / 2 + (w + ps.width()) * k
                    p.setOpacity(math.sin(math.pi * k))
                    p.drawPixmap(QPointF(x - ps.width() / 2, y - ps.height() / 2), ps)
            sp = spark_sprite()
            for pt in self.particles:
                k = pt.life / pt.max
                p.setOpacity(math.sin(math.pi * min(1.0, k)) * 0.55)
                s = sp.width() * pt.size
                p.drawPixmap(QRectF(pt.x - s / 2, pt.y - s / 2, s, s), sp, QRectF(sp.rect()))
            p.setOpacity(1)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
