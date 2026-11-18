"""Gráfico de líneas holográfico: área con degradé, línea con resplandor, cruz que sigue al mouse y tooltip.

Reglas aplicadas: un solo eje Y (nunca dos escalas), grilla tenue, valores redondos en el eje,
etiqueta directa del último valor, leyenda si hay 2+ series, tooltip con todas las series en esa fecha.
Colores de serie validados contra el fondo oscuro (separación para daltonismo y contraste).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import holo
from . import theme as T

SERIES_BLUE = "#3a8de8"    # validados: banda de luminosidad, ΔE daltonismo 27, contraste ≥ 3:1 sobre #061230
SERIES_AMBER = "#c4861c"
MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


@dataclass
class Series:
    name: str
    color: str
    points: list            # [(date, valor)]
    kind: str = "line"      # line | dots
    area: bool = False
    glow: bool = True


def nice_ticks(lo: float, hi: float, n: int = 4):
    span = max(hi - lo, 1e-6)
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    start = math.floor(lo / step) * step
    ticks = []
    v = start
    while v <= hi + step * 0.5:
        ticks.append(round(v, 6))
        v += step
    return ticks, step


def fmt_num(v: float, decimals: int = 1) -> str:
    return f"{v:.{decimals}f}".replace(".", ",")


class LineChart(QWidget):
    def __init__(self, unit: str = "", decimals: int = 1, height: int = 260, empty: str = "Sin datos todavía."):
        super().__init__()
        self.setFixedHeight(height)
        self.setMouseTracking(True)
        self.unit, self.decimals, self.empty = unit, decimals, empty
        self.series: list[Series] = []
        self.hover_x: float | None = None
        self.d0 = self.d1 = None
        self.pad_y = 0.0

    def set_series(self, series: list[Series], d0: date | None = None, d1: date | None = None, pad_y: float = 0.0):
        self.series = [s for s in series if s.points]
        dates = [d for s in self.series for d, _ in s.points]
        self.d0 = d0 or (min(dates) if dates else None)
        self.d1 = d1 or (max(dates) if dates else None)
        self.pad_y = pad_y
        self.update()

    # ------------------------------------------------------------ geometría
    def _frame(self):
        W, H = self.width(), self.height()
        legend = 26 if len(self.series) > 1 else 6
        return QRectF(54, 10 + legend, W - 54 - 70, H - 10 - legend - 30)

    def _scales(self, plot: QRectF):
        vals = [v for s in self.series for _, v in s.points]
        lo, hi = min(vals), max(vals)
        pad = max(self.pad_y, (hi - lo) * 0.12, 10 ** -self.decimals)
        ticks, step = nice_ticks(lo - pad, hi + pad)
        lo, hi = ticks[0], ticks[-1]
        span = max(1, (self.d1 - self.d0).days)
        X = lambda d: plot.left() + plot.width() * (d - self.d0).days / span
        Y = lambda v: plot.bottom() - plot.height() * (v - lo) / (hi - lo)
        return X, Y, ticks

    # ------------------------------------------------------------ dibujo
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        small = QFont(T.FONT, 8)
        p.setFont(small)
        if not self.series or self.d0 is None:
            p.setPen(QColor(T.MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.empty)
            return
        plot = self._frame()
        X, Y, ticks = self._scales(plot)

        # grilla y eje Y (tenues)
        for v in ticks:
            y = Y(v)
            p.setPen(QPen(QColor(120, 170, 255, 26), 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(T.MUTED))
            p.drawText(QRectF(0, y - 8, plot.left() - 10, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       fmt_num(v, self.decimals if (ticks[1] - ticks[0]) < 1 else 0))
        # eje X: marcas por semana (o por mes si el rango es largo)
        span = (self.d1 - self.d0).days
        step = 7 if span <= 70 else 14 if span <= 140 else 30
        d = self.d0 + timedelta(days=(7 - self.d0.weekday()) % 7) if step < 30 else self.d0.replace(day=1)
        while d <= self.d1:
            if d >= self.d0:
                x = X(d)
                p.setPen(QPen(QColor(120, 170, 255, 16), 1))
                p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
                p.setPen(QColor(T.MUTED))
                p.drawText(QRectF(x - 40, plot.bottom() + 6, 80, 16), Qt.AlignmentFlag.AlignCenter,
                           f"{d.day} {MONTHS[d.month - 1]}")
            d = d + timedelta(days=step) if step < 30 else (d.replace(day=28) + timedelta(days=5)).replace(day=1)
        p.setPen(QPen(QColor(120, 170, 255, 60), 1))
        p.drawLine(QPointF(plot.left(), plot.bottom()), QPointF(plot.right(), plot.bottom()))

        # series
        p.save()
        p.setClipRect(plot.adjusted(-8, -8, 8, 8))
        for s in self.series:
            pts = [QPointF(X(d), Y(v)) for d, v in s.points]
            if s.kind == "line" and len(pts) > 1:
                path = QPainterPath(pts[0])
                for a, b in zip(pts, pts[1:]):  # curva suave (Catmull-Rom simplificado)
                    mx = (a.x() + b.x()) / 2
                    path.cubicTo(QPointF(mx, a.y()), QPointF(mx, b.y()), b)
                if s.area:
                    area = QPainterPath(path)
                    area.lineTo(QPointF(pts[-1].x(), plot.bottom()))
                    area.lineTo(QPointF(pts[0].x(), plot.bottom()))
                    area.closeSubpath()
                    g = QLinearGradient(QPointF(0, plot.top()), QPointF(0, plot.bottom()))
                    g.setColorAt(0, holo.qc(s.color, 90))
                    g.setColorAt(1, holo.qc(s.color, 0))
                    p.fillPath(area, g)
                if s.glow:
                    for w, a in ((10, 18), (6, 34), (3.5, 70)):
                        pen = QPen(holo.qc(s.color, a), w)
                        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                        p.setPen(pen)
                        p.drawPath(path)
                pen = QPen(QColor(s.color), 2.2)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawPath(path)
                p.setPen(QPen(holo.qc(T.CORE, 150), 0.8))
                p.drawPath(path)
            if s.kind == "dots" or len(pts) == 1 or (s.kind == "line" and len(pts) <= 16):
                r = 4.0 if s.kind == "dots" else 3.5
                for pt in pts:
                    p.setPen(QPen(QColor("#061230"), 2))  # anillo del color del fondo
                    p.setBrush(QColor(s.color))
                    p.drawEllipse(pt, r, r)
        p.restore()

        # etiqueta directa del último valor de la primera serie
        main = self.series[0]
        ld, lv = main.points[-1]
        lx, ly = X(ld), Y(lv)
        f = QFont(T.FONT, 10)
        f.setWeight(QFont.Weight.Bold)
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(QRectF(lx + 8, ly - 10, 70, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{fmt_num(lv, self.decimals)}{self.unit}")

        # leyenda (2+ series): clave con la forma de la marca
        if len(self.series) > 1:
            p.setFont(small)
            x = plot.left()
            for s in self.series:
                if s.kind == "line":
                    p.setPen(QPen(QColor(s.color), 2.4))
                    p.drawLine(QPointF(x, 14), QPointF(x + 18, 14))
                else:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(s.color))
                    p.drawEllipse(QPointF(x + 9, 14), 4, 4)
                p.setPen(QColor(T.TEXT))
                tw = QFontMetricsF(small).horizontalAdvance(s.name)
                p.drawText(QRectF(x + 24, 6, tw + 4, 16), Qt.AlignmentFlag.AlignVCenter, s.name)
                x += tw + 50

        if self.hover_x is not None:
            self._hover(p, plot, X, Y)

    def _hover(self, p, plot, X, Y):
        if not plot.adjusted(-10, 0, 10, 0).contains(QPointF(self.hover_x, plot.center().y())):
            return
        dates = sorted({d for s in self.series for d, _ in s.points})
        d = min(dates, key=lambda dd: abs(X(dd) - self.hover_x))
        x = X(d)
        p.setPen(QPen(holo.qc(T.CORE, 120), 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
        rows = []
        for s in self.series:
            v = dict(s.points).get(d)
            if v is not None:
                rows.append((s, v))
                p.setPen(QPen(QColor("white"), 2))
                p.setBrush(QColor(s.color))
                p.drawEllipse(QPointF(x, Y(v)), 5.5, 5.5)
        if not rows:
            return
        fb = QFont(T.FONT, 10)
        fb.setWeight(QFont.Weight.Bold)
        fs = QFont(T.FONT, 8)
        w, h = 220, 30 + 20 * len(rows)
        bx = x + 14 if x + 14 + w < self.width() else x - 14 - w
        box = QRectF(bx, plot.top() + 4, w, h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(4, 12, 32, 240))
        p.drawPath(holo.chamfer(box, 5))
        holo.neon_path(p, holo.chamfer(box, 5), T.GLOW, T.CORE, 0.8, 2, 2, 30)
        p.setFont(fs)
        p.setPen(QColor(T.MUTED))
        dias = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
        p.drawText(box.adjusted(12, 6, -8, 0), Qt.AlignmentFlag.AlignTop,
                   f"{dias[d.weekday()]} {d.day} {MONTHS[d.month - 1]} {d.year}")
        y = box.top() + 26
        for s, v in rows:
            p.setPen(QPen(QColor(s.color), 2.4))
            p.drawLine(QPointF(box.left() + 12, y + 8), QPointF(box.left() + 26, y + 8))
            p.setFont(fb)
            p.setPen(QColor("white"))
            val = f"{fmt_num(v, self.decimals)}{self.unit}"
            p.drawText(QRectF(box.left() + 34, y, 70, 18), Qt.AlignmentFlag.AlignVCenter, val)
            p.setFont(fs)
            p.setPen(QColor(T.MUTED))
            p.drawText(QRectF(box.left() + 100, y, w - 104, 18), Qt.AlignmentFlag.AlignVCenter, s.name)
            y += 20

    def mouseMoveEvent(self, e):
        self.hover_x = e.position().x()
        self.update()

    def leaveEvent(self, e):
        self.hover_x = None
        self.update()


def moving_average(points, days: int = 7):
    out = []
    for d, _ in points:
        w = [v for dd, v in points if 0 <= (d - dd).days < days]
        out.append((d, sum(w) / len(w)))
    return out


def weekly_trend(points) -> float | None:
    """Pendiente (kg por semana) por mínimos cuadrados."""
    if len(points) < 3:
        return None
    xs = [(d - points[0][0]).days for d, _ in points]
    if xs[-1] - xs[0] < 4:
        return None
    ys = [v for _, v in points]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if not den:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den * 7
