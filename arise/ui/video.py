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
        self.world = None
        self.skeleton = T.GLOW
        self.count = "0"
        self.target = ""
        self.feedback = "Encendé la cámara para empezar"
        self.tone = ""
        self.progress = 0.0
        self.center = ""
        self.center_small = ""
        self.pop = 0
        self.ghost: QImage | None = None   # foto anterior superpuesta (control semanal)
        self.ghost_opacity = 0.35
        self.flash = 0

    def set_frame(self, img: QImage, lm, color: str, world=None):
        self.image, self.landmarks, self.skeleton = img, lm, color
        self.world = world
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
            # líneas de escaneo sobre la imagen
            p.setPen(QPen(QColor(120, 190, 255, 14), 1))
            y = area.top()
            while y < area.bottom():
                p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
                y += 3
            if self.ghost is not None and not self.ghost.isNull():
                p.setOpacity(self.ghost_opacity)
                p.drawImage(area, self.ghost)
                p.setOpacity(1.0)
            if self.flash:
                p.fillRect(area, QColor(255, 255, 255, int(255 * self.flash / 6)))
                self.flash -= 1
            if self.landmarks is not None:
                self._skeleton(p, area)
            self._tracking_badge(p, area)
        p.setPen(QPen(QColor(T.LINE), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
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

    # ------------------------------------------------------------------ rig holográfico
    BONES = [  # (a, b, grosor relativo)
        (11, 13, 1.0), (13, 15, 0.75), (12, 14, 1.0), (14, 16, 0.75),       # brazos
        (23, 25, 1.35), (25, 27, 1.05), (24, 26, 1.35), (26, 28, 1.05),     # piernas
        (27, 31, 0.5), (28, 32, 0.5), (15, 19, 0.4), (16, 20, 0.4),          # pies y manos
        (11, 12, 0.7), (23, 24, 0.9), (11, 23, 0.55), (12, 24, 0.55),        # torso
    ]
    ANGLES = [(11, 13, 15), (12, 14, 16), (23, 25, 27), (24, 26, 28)]  # codos y rodillas

    def _skeleton(self, p: QPainter, area: QRectF):
        import math
        from PySide6.QtGui import QPainterPath, QPolygonF
        from . import fx
        lm = self.landmarks
        W = area.width()
        pt = lambda i: QPointF(area.x() + lm[i].x * area.width(), area.y() + lm[i].y * area.height())
        vis = lambda i: (lm[i].visibility or 0) >= 0.45
        col = QColor(self.skeleton)
        core = QColor(T.CORE)
        t = fx.Clock.get().now()
        base_w = max(6.0, W / 72)
        zs = [lm[i].z for i in (11, 12, 23, 24)]
        zmid = sum(zs) / len(zs)

        def width_for(i, k):  # más cerca de la cámara (z menor) = más grueso
            depth = max(0.6, min(1.5, 1 - (lm[i].z - zmid) * 1.6))
            return base_w * k * depth

        def capsule(a: QPointF, b: QPointF, wa: float, wb: float) -> QPainterPath:
            dx, dy = b.x() - a.x(), b.y() - a.y()
            ln = math.hypot(dx, dy) or 1
            nx, ny = -dy / ln, dx / ln
            poly = QPolygonF([QPointF(a.x() + nx * wa / 2, a.y() + ny * wa / 2), QPointF(b.x() + nx * wb / 2, b.y() + ny * wb / 2),
                              QPointF(b.x() - nx * wb / 2, b.y() - ny * wb / 2), QPointF(a.x() - nx * wa / 2, a.y() - ny * wa / 2)])
            path = QPainterPath()
            path.addPolygon(poly)
            path.addEllipse(a, wa / 2, wa / 2)
            path.addEllipse(b, wb / 2, wb / 2)
            return path.simplified()

        def a_(c, alpha):
            c = QColor(c)
            c.setAlpha(alpha)
            return c

        bones = [(a, b, k) for a, b, k in self.BONES if vis(a) and vis(b)]
        # columna: de los hombros a la pelvis
        spine = None
        if all(vis(i) for i in (11, 12, 23, 24)):
            neck = (pt(11) + pt(12)) / 2
            pelvis = (pt(23) + pt(24)) / 2
            spine = (neck, pelvis)

        # 1) halo exterior (resplandor)
        p.setPen(Qt.PenStyle.NoPen)
        for grow, alpha in ((3.2, 26), (2.2, 40), (1.5, 60)):
            p.setBrush(a_(col, alpha))
            for a, b, k in bones:
                p.drawPath(capsule(pt(a), pt(b), width_for(a, k) * grow, width_for(b, k) * grow))
            if spine:
                p.drawPath(capsule(spine[0], spine[1], base_w * 1.1 * grow, base_w * 1.1 * grow))
        # 2) cuerpo del hueso: vidrio translúcido del color de estado
        from PySide6.QtGui import QLinearGradient
        for a, b, k in bones:
            pa, pb = pt(a), pt(b)
            g = QLinearGradient(pa, pb)
            g.setColorAt(0, a_(col, 150))
            g.setColorAt(0.5, a_(col, 95))
            g.setColorAt(1, a_(col, 150))
            p.setBrush(g)
            p.setPen(QPen(a_(core, 200), 1.1))
            p.drawPath(capsule(pa, pb, width_for(a, k), width_for(b, k)))
        # 3) columna con vértebras
        if spine:
            n0, p0 = spine
            p.setPen(QPen(a_(core, 230), max(2.0, base_w * 0.3)))
            p.drawLine(n0, p0)
            for j in range(1, 8):
                q = n0 + (p0 - n0) * (j / 8)
                dx, dy = p0.x() - n0.x(), p0.y() - n0.y()
                ln = math.hypot(dx, dy) or 1
                nx, ny = -dy / ln * base_w * 0.55, dx / ln * base_w * 0.55
                p.setPen(QPen(a_(col, 220), max(1.5, base_w * 0.22)))
                p.drawLine(q + QPointF(nx, ny), q - QPointF(nx, ny))
            # cuello -> cabeza
            if vis(0):
                p.setPen(QPen(a_(core, 200), max(1.6, base_w * 0.25)))
                p.drawLine(n0, pt(0))
        # 4) venas de energía: líneas finas a los costados de cada hueso con pulsos que viajan
        for a, b, k in bones + ([(None, None, 1.1)] if spine else []):
            pa, pb = (pt(a), pt(b)) if a is not None else spine
            dx, dy = pb.x() - pa.x(), pb.y() - pa.y()
            ln = math.hypot(dx, dy) or 1
            nx, ny = -dy / ln, dx / ln
            wv = base_w * k * 0.32
            for side, ph in ((1, 0.0), (-1, 0.5)):
                path = QPainterPath(pa)
                c1 = pa + QPointF(dx * 0.33 + nx * wv * side * 1.4, dy * 0.33 + ny * wv * side * 1.4)
                c2 = pa + QPointF(dx * 0.66 - nx * wv * side * 0.6, dy * 0.66 - ny * wv * side * 0.6)
                path.cubicTo(c1, c2, pb)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(a_(core, 120), 1.0))
                p.drawPath(path)
                # pulso que recorre la vena
                u = (t * 0.9 + ph + (a or 0) * 0.13) % 1.0
                q = path.pointAtPercent(u)
                rg = max(3.0, base_w * 0.55)
                from PySide6.QtGui import QRadialGradient
                gr = QRadialGradient(q, rg * 2.2)
                gr.setColorAt(0, QColor(255, 255, 255, 230))
                gr.setColorAt(0.4, a_(col, 150))
                gr.setColorAt(1, a_(col, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(gr)
                p.drawEllipse(q, rg * 2.2, rg * 2.2)
        # 5) articulaciones: anillos dobles con marcas tipo mira
        for i in (11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28):
            if not vis(i):
                continue
            c = pt(i)
            r = width_for(i, 0.75)
            p.setBrush(a_(QColor("#02060f"), 200))
            p.setPen(QPen(a_(core, 240), 1.6))
            p.drawEllipse(c, r, r)
            p.setBrush(QColor(T.CORE))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(c, r * 0.35, r * 0.35)
            p.setPen(QPen(a_(col, 200), 1.2))
            rr = r * 1.7
            rot = t * 40 + i * 20
            p.setBrush(Qt.BrushStyle.NoBrush)
            for ang in (0, 90, 180, 270):
                p.drawArc(QRectF(c.x() - rr, c.y() - rr, rr * 2, rr * 2), int((rot + ang) * 16), int(45 * 16))
        # 6) cabeza
        if vis(0) and vis(7) and vis(8):
            hc = (pt(7) + pt(8)) / 2
            hr = max(base_w * 1.6, math.hypot(pt(7).x() - pt(8).x(), pt(7).y() - pt(8).y()) * 0.85)
            p.setBrush(a_(col, 40))
            p.setPen(QPen(a_(core, 200), 1.4))
            p.drawEllipse(hc, hr, hr * 1.15)
            p.setPen(QPen(a_(col, 160), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(hc, hr * 1.35, hr * 1.5)
        # 7) ángulos de codos y rodillas
        from ..exercises import angle3
        if self.world is not None:
            f = QFont(T.FONT, max(8, int(W / 110)))
            f.setWeight(QFont.Weight.Bold)
            p.setFont(f)
            for a, b, c in self.ANGLES:
                if not (vis(a) and vis(b) and vis(c)):
                    continue
                ang = angle3(self.world[a], self.world[b], self.world[c])
                pb = pt(b)
                v1 = math.degrees(math.atan2(-(pt(a).y() - pb.y()), pt(a).x() - pb.x()))
                v2 = math.degrees(math.atan2(-(pt(c).y() - pb.y()), pt(c).x() - pb.x()))
                span = (v2 - v1 + 540) % 360 - 180
                rr = base_w * 3.2
                p.setPen(QPen(a_(core, 170), 1.4))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawArc(QRectF(pb.x() - rr, pb.y() - rr, rr * 2, rr * 2), int(v1 * 16), int(span * 16))
                mid = math.radians(v1 + span / 2)
                tp = QPointF(pb.x() + math.cos(mid) * rr * 1.7, pb.y() - math.sin(mid) * rr * 1.7)
                txt = f"{ang:.0f}°"
                p.setPen(QColor(0, 0, 0, 170))
                p.drawText(QRectF(tp.x() - 29, tp.y() - 11, 60, 22), Qt.AlignmentFlag.AlignCenter, txt)
                p.setPen(QColor("white"))
                p.drawText(QRectF(tp.x() - 30, tp.y() - 12, 60, 22), Qt.AlignmentFlag.AlignCenter, txt)

    def _tracking_badge(self, p: QPainter, area: QRectF):
        """Etiqueta grande con el estado de detección (para saber de un vistazo si te está viendo)."""
        lm = self.landmarks
        f = QFont(T.FONT, 10)
        f.setWeight(QFont.Weight.Bold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        p.setFont(f)
        if lm is None:
            txt, col = "SIN DETECCIÓN", QColor(T.RED)
        else:
            keys = (0, 11, 12, 23, 24, 25, 26, 27, 28)
            conf = sum((lm[i].visibility or 0) for i in keys) / len(keys)
            txt = f"SEGUIMIENTO {int(conf * 100)}%"
            col = QColor(T.GREEN if conf > 0.7 else T.GOLD if conf > 0.45 else T.RED)
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(txt) + 34
        r = QRectF(self.width() - w - 50, 14, w, 28)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(2, 6, 16, 210))
        p.drawRect(r)
        p.setPen(QPen(col, 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)
        p.setBrush(col)
        p.setPen(Qt.PenStyle.NoPen)
        from . import fx
        blink = 0.5 + 0.5 * abs(__import__("math").sin(fx.Clock.get().now() * 3))
        c2 = QColor(col)
        c2.setAlphaF(blink)
        p.setBrush(c2)
        p.drawEllipse(QPointF(r.left() + 14, r.center().y()), 4.5, 4.5)
        p.setPen(QColor("white"))
        p.drawText(r.adjusted(24, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, txt)
        p.setBrush(Qt.BrushStyle.NoBrush)
