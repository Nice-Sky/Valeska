"""Vista de cámara: imagen + esqueleto + contador y correcciones encima."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import fx, holo
from . import theme as T

CONNECTIONS = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (24, 26), (26, 28), (27, 31), (28, 32), (27, 29), (28, 30),
]
TONES = {"good": T.GREEN, "warn": T.GOLD, "bad": T.RED, "": T.GLOW}


class VideoView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 270)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image: QImage | None = None
        self.landmarks = None
        self.skeleton = T.GLOW
        self.count = "0"
        self.target = ""
        self.feedback = "Encendé la cámara para empezar"
        self.tone = ""
        self.progress = 0.0
        self.center = ""
        self.center_small = ""
        self.pop = 0

    def set_frame(self, img: QImage, lm, color: str):
        self.image, self.landmarks, self.skeleton = img, lm, color
        if self.pop:
            self.pop -= 1
        self.update()

    def clear(self):
        self.image = None
        self.landmarks = None
        self.update()

    def set_feedback(self, text: str, tone: str = ""):
        self.feedback, self.tone = text or "", tone
        self.update()

    def bump(self):
        self.pop = 8

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#000000"))
        W, H = self.width(), self.height()

        area = QRectF(0, 0, W, H)
        if self.image is not None and not self.image.isNull():
            iw, ih = self.image.width(), self.image.height()
            s = min(W / iw, H / ih)
            area = QRectF((W - iw * s) / 2, (H - ih * s) / 2, iw * s, ih * s)
            p.drawImage(area, self.image)
            if self.landmarks is not None:
                self._skeleton(p, area)
        p.setPen(QPen(QColor(T.LINE), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # contador
        size = max(36, int(H * 0.16)) + (6 if self.pop else 0)
        f = QFont(T.FONT, size)
        f.setBold(True)
        p.setFont(f)
        cw = p.fontMetrics().horizontalAdvance(self.count)
        fx.draw_glow_text(p, QRectF(18, 8, cw, size * 1.5), self.count, f, T.GREEN if self.pop else T.GLOW, T.CORE,
                          Qt.AlignmentFlag.AlignLeft, glow=1.2)
        p.setFont(QFont(T.FONT, max(11, size // 4)))
        p.setPen(QColor(T.MUTED))
        p.drawText(QRectF(28 + cw, 8, W, size * 1.4), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, self.target)

        # barra de profundidad
        bx, by, bh = W - 26, 16, H - 90
        p.setPen(QPen(QColor(T.GLOW), 1))
        p.setBrush(QColor(0, 0, 0, 140))
        p.drawRect(QRectF(bx, by, 12, bh))
        fill = bh * max(0.0, min(1.0, self.progress))
        p.fillRect(QRectF(bx + 1, by + bh - fill, 11, fill), QColor(T.GREEN if self.progress >= 0.99 else T.GLOW))

        # feedback
        if self.feedback:
            p.setFont(QFont(T.FONT, max(12, int(H * 0.032)), QFont.Weight.Bold))
            fm = p.fontMetrics()
            tw = min(W - 40, fm.horizontalAdvance(self.feedback) + 36)
            r = QRectF((W - tw) / 2, H - fm.height() - 28, tw, fm.height() + 14)
            col = TONES.get(self.tone, T.GLOW)
            holo.holo_frame(p, r.adjusted(-6, -4, 6, 4), {T.GREEN: "", T.GOLD: "gold", T.RED: "red"}.get(col, ""),
                            7, cut=5, strong=True, brackets=False)
            p.setPen(QColor(col if self.tone else T.CORE))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, fm.elidedText(self.feedback, Qt.TextElideMode.ElideRight, int(tw - 20)))

        # texto central (cuenta regresiva / estado)
        if self.center:
            f = QFont(T.FONT, max(40, int(H * 0.26)))
            f.setBold(True)
            fx.draw_glow_text(p, QRectF(0, 0, W, H), self.center, f, T.GLOW, T.CORE, glow=1.6)
        if self.center_small:
            p.setFont(QFont(T.FONT, max(12, int(H * 0.035))))
            p.setPen(QColor("white"))
            p.drawText(QRectF(20, 0, W - 40, H), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.center_small)

    def _skeleton(self, p: QPainter, area: QRectF):
        lm = self.landmarks
        pt = lambda i: QPointF(area.x() + lm[i].x * area.width(), area.y() + lm[i].y * area.height())
        vis = lambda i: (lm[i].visibility or 0) >= 0.4
        col = QColor(self.skeleton)
        halo = QColor(col)
        halo.setAlpha(80)
        for pen in (QPen(halo, max(8, area.width() / 110)), QPen(col, max(3, area.width() / 300))):
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            for a, b in CONNECTIONS:
                if vis(a) and vis(b):
                    p.drawLine(pt(a), pt(b))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("white"))
        r = max(3.5, area.width() / 220)
        for i in range(11, 33):
            if vis(i):
                p.drawEllipse(pt(i), r, r)
