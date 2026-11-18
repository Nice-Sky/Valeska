"""Efectos tipo shader: bloom (desenfoque gaussiano aditivo), ruido, texto con resplandor y reloj de animación."""
from __future__ import annotations

import math
import time
from functools import lru_cache

import numpy as np
from PySide6.QtCore import QObject, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

FMT = QImage.Format.Format_ARGB32_Premultiplied


# ------------------------------------------------------------------ imágenes <-> numpy
def _view(img: QImage) -> np.ndarray:
    ptr = img.bits()
    return np.frombuffer(ptr, np.uint8, img.sizeInBytes()).reshape(img.height(), img.bytesPerLine() // 4, 4)[:, :img.width()]


def new_image(w: int, h: int, dpr: float = 1.0) -> QImage:
    img = QImage(max(1, int(w * dpr)), max(1, int(h * dpr)), FMT)
    img.fill(Qt.GlobalColor.transparent)
    img.setDevicePixelRatio(dpr)
    return img


def bloom(src: QImage, passes=((4, 1.1), (12, 1.0), (30, 0.8)), gain: float = 1.0) -> QImage:
    """Devuelve el resplandor de `src`: suma de desenfoques gaussianos (como un shader de bloom)."""
    if cv2 is None:
        return src
    a = _view(src).astype(np.float32)
    h, w = a.shape[:2]
    acc = np.zeros_like(a)
    for sigma, k in passes:
        sigma = sigma * src.devicePixelRatio()
        scale = 0.5 if sigma > 8 else 1.0
        if scale < 1:
            small = cv2.resize(a, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
            b = cv2.GaussianBlur(small, (0, 0), sigma * scale)
            b = cv2.resize(b, (w, h), interpolation=cv2.INTER_LINEAR)
        else:
            b = cv2.GaussianBlur(a, (0, 0), sigma)
        acc += b * k
    acc *= gain
    out = QImage(w, h, FMT)
    _view(out)[:] = np.clip(acc, 0, 255).astype(np.uint8)
    out.setDevicePixelRatio(src.devicePixelRatio())
    return out


@lru_cache(maxsize=8)
def noise_tile(size: int = 192, alpha: int = 18) -> QImage:
    """Grano fino para dar textura de vidrio/holograma."""
    rng = np.random.default_rng(7)
    v = rng.integers(0, 255, (size, size), dtype=np.uint8)
    img = QImage(size, size, FMT)
    arr = _view(img)
    a = (v.astype(np.float32) / 255 * alpha).astype(np.uint8)
    arr[..., 0] = (a * 0.95).astype(np.uint8)
    arr[..., 1] = (a * 0.85).astype(np.uint8)
    arr[..., 2] = (a * 0.6).astype(np.uint8)
    arr[..., 3] = a
    return img


# ------------------------------------------------------------------ texto con resplandor
_text_cache: dict = {}


def glow_text_image(text: str, font: QFont, color: str, core: str, dpr: float, glow: float = 1.0,
                    spacing: float = 0.0) -> tuple[QImage, QImage, QSize]:
    key = (text, font.toString(), color, core, round(dpr, 2), glow, spacing)
    hit = _text_cache.get(key)
    if hit:
        return hit
    f = QFont(font)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    fm = QFontMetricsF(f)
    pad = int(14 + 18 * glow)
    w = int(fm.horizontalAdvance(text) + pad * 2 + spacing)
    h = int(fm.height() + pad * 2)
    sharp = new_image(w, h, dpr)
    p = QPainter(sharp)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setFont(f)
    path = QPainterPath()
    path.addText(QPointF(pad, pad + fm.ascent()), f, text)
    p.fillPath(path, QColor(core))
    p.end()
    src = new_image(w, h, dpr)
    p = QPainter(src)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = QColor(color)
    p.fillPath(path, c)
    p.setPen(QPen(c, 1.2))
    p.drawPath(path)
    p.end()
    halo = bloom(src, ((2, 1.0), (6, 0.9), (16, 0.7)), gain=glow)
    res = (sharp, halo, QSize(w, h))
    if len(_text_cache) > 400:
        _text_cache.clear()
    _text_cache[key] = res
    return res


def draw_glow_text(p: QPainter, rect: QRectF, text: str, font: QFont, color: str, core: str,
                   align=Qt.AlignmentFlag.AlignCenter, glow: float = 1.0, spacing: float = 0.0, intensity: float = 1.0):
    dpr = p.device().devicePixelRatioF() if p.device() else 1.0
    sharp, halo, sz = glow_text_image(text, font, color, core, dpr, glow, spacing)
    w, h = sz.width(), sz.height()
    if align & Qt.AlignmentFlag.AlignLeft:
        x = rect.left() - (14 + 18 * glow)
    elif align & Qt.AlignmentFlag.AlignRight:
        x = rect.right() - w + (14 + 18 * glow)
    else:
        x = rect.center().x() - w / 2
    y = rect.center().y() - h / 2
    mode = p.compositionMode()
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    p.setOpacity(intensity)
    p.drawImage(QPointF(x, y), halo)
    p.setOpacity(1.0)
    p.setCompositionMode(mode)
    p.drawImage(QPointF(x, y), sharp)


# ------------------------------------------------------------------ reloj de animación
class Clock(QObject):
    tick = Signal()
    _inst = None

    def __init__(self):
        super().__init__()
        self.t0 = time.monotonic()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick.emit)
        self.timer.start(50)

    @classmethod
    def get(cls) -> "Clock":
        if cls._inst is None:
            cls._inst = Clock()
        return cls._inst

    def now(self) -> float:
        return time.monotonic() - self.t0

    def pulse(self, period: float = 3.6, lo: float = 0.78, hi: float = 1.0, offset: float = 0.0) -> float:
        x = (math.sin((self.now() + offset) * 2 * math.pi / period) + 1) / 2
        return lo + (hi - lo) * x


def edge_fade(img: QImage, margin: float) -> QImage:
    """Atenúa el resplandor hacia los bordes del widget para que no se vea el corte rectangular."""
    m = max(1.0, margin * img.devicePixelRatio())
    a = _view(img)
    h, w = a.shape[:2]
    ys = np.minimum(np.arange(h), np.arange(h)[::-1]).astype(np.float32)
    xs = np.minimum(np.arange(w), np.arange(w)[::-1]).astype(np.float32)
    fy = np.clip(ys / m, 0, 1)
    fx_ = np.clip(xs / m, 0, 1)
    f = np.minimum(fy[:, None], fx_[None, :])
    f = f * f * (3 - 2 * f)  # smoothstep
    a[:] = (a.astype(np.float32) * f[..., None]).astype(np.uint8)
    return img
