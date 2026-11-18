"""Pantalla CUERPO: control semanal con fotos (frente / perfil izq. / perfil der.), peso y composición estimada."""
from __future__ import annotations

import time
from datetime import date, timedelta
from html import escape

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QGridLayout, QHBoxLayout, QSlider, QStackedWidget,
                               QVBoxLayout, QWidget)

from .. import body, storage
from ..camera import CameraWorker
from ..game import WEEKDAYS
from . import holo, icons
from . import theme as T
from .pages import clear_layout, scroll_page
from .video import VideoView
from .charts import SERIES_AMBER, SERIES_BLUE, LineChart, Series, moving_average, weekly_trend
from .widgets import Panel, button, icon_label, label, restyle

VIEWS = [
    ("front", "FRENTE", "Parate de frente, cuerpo entero en la imagen, brazos un poco separados del cuerpo.", "user-round"),
    ("left", "PERFIL IZQUIERDO", "Girá para que tu lado izquierdo mire a la cámara. Brazos cruzados sobre el pecho.", "arrow-left"),
    ("right", "PERFIL DERECHO", "Ahora el lado derecho hacia la cámara. Brazos cruzados sobre el pecho.", "arrow-right"),
]
VIEW_NAMES = {k: n for k, n, *_ in VIEWS}


def photos_dir():
    d = storage.data_dir() / "fotos"
    d.mkdir(exist_ok=True)
    return d


def load_qimage(name: str | None) -> QImage | None:
    if not name:
        return None
    p = photos_dir() / name
    if not p.exists():
        return None
    img = QImage(str(p))
    return None if img.isNull() else img


def stat_box(value: str, name: str, delta: str = "", good: bool | None = None) -> QWidget:
    col = {True: T.GREEN, False: T.RED}.get(good, T.MUTED)
    d = f"<br><span style='color:{col};font-size:12px'>{delta}</span>" if delta else ""
    box = label(f"<span style='font-size:22px;font-weight:700;color:white'>{value}</span><br>"
                f"<span style='color:{T.MUTED}'>{name}</span>{d}", align=Qt.AlignmentFlag.AlignCenter)
    box.setTextFormat(Qt.TextFormat.RichText)
    box.setStyleSheet("border:1px solid #1c3a70;padding:10px;")
    return box


# =================================================================== comparador de fotos
def _read_rgb(name):
    import cv2
    if not name:
        return None
    img = cv2.imread(str(photos_dir() / name))
    return None if img is None else cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def _read_mask(name):
    import cv2
    if not name:
        return None
    m = cv2.imread(str(photos_dir() / name.replace(".jpg", "_mask.png")), cv2.IMREAD_GRAYSCALE)
    return None if m is None else (m > 127).astype(np.float32)


def _qimg(rgb: np.ndarray) -> QImage:
    rgb = np.ascontiguousarray(rgb)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


def _contour_path(mask, x0, y0) -> QPainterPath:
    import cv2
    path = QPainterPath()
    if mask is None:
        return path
    cs, _ = cv2.findContours((body.largest_component(mask) * 255).astype(np.uint8), cv2.RETR_EXTERNAL,
                             cv2.CHAIN_APPROX_SIMPLE)
    for c in cs:
        pts = c[:, 0, :]
        if len(pts) < 3:
            continue
        path.moveTo(QPointF(pts[0][0] - x0, pts[0][1] - y0))
        for x, y in pts[1:]:
            path.lineTo(QPointF(x - x0, y - y0))
        path.closeSubpath()
    return path


class PhotoCompare(QWidget):
    """Foto actual vs. anterior, con la anterior alineada automáticamente sobre el cuerpo actual."""

    MODES = ["Superponer", "Deslizar (antes / después)", "Lado a lado", "Siluetas"]

    def __init__(self):
        super().__init__()
        self.setFixedHeight(520)
        self.setMouseTracking(True)
        self.mode = 0
        self.value = 0.45          # opacidad (superponer) o posición del corte (deslizar)
        self.cur = self.prev = None
        self.cur_path = self.prev_path = QPainterPath()
        self.cur_label = self.prev_label = ""
        self.aligned = False
        self._key = None

    def set_pair(self, cur: dict | None, prev: dict | None, view: str):
        key = (cur and cur["date"], prev and prev["date"], view)
        if key == self._key:
            self.update()
            return
        self._key = key
        self.cur = self.prev = None
        self.cur_path = self.prev_path = QPainterPath()
        lab = lambda c: f"{c['date']}  ·  {c['weight']:.1f} kg" if c else ""
        self.cur_label, self.prev_label = lab(cur), lab(prev)
        if not cur:
            self.update()
            return
        cname = cur["photos"].get(view)
        crgb, cmask = _read_rgb(cname), _read_mask(cname)
        if crgb is None:
            self.update()
            return
        h, w = crgb.shape[:2]
        prgb = pmask = None
        self.aligned = False
        if prev:
            pname = prev["photos"].get(view)
            prgb, pmask = _read_rgb(pname), _read_mask(pname)
            if prgb is not None:
                ph, pw = prgb.shape[:2]
                M = body.alignment_matrix((pw, ph), (w, h),
                                          (prev.get("landmarks") or {}).get(view), (cur.get("landmarks") or {}).get(view),
                                          pmask, cmask)
                prgb = body.warp(prgb, M, (w, h))
                pmask = body.warp(pmask, M, (w, h)) if pmask is not None else None
                self.aligned = True
        crop = body.body_crop(*(m for m in (cmask, pmask) if m is not None)) if cmask is not None else None
        x0, y0, cw, ch = crop or (0, 0, w, h)
        self.cur = _qimg(crgb[y0:y0 + ch, x0:x0 + cw])
        self.cur_path = _contour_path(cmask, 0, 0).translated(-x0, -y0) if cmask is not None else QPainterPath()
        if prgb is not None:
            self.prev = _qimg(prgb[y0:y0 + ch, x0:x0 + cw])
            self.prev_path = _contour_path(pmask, 0, 0).translated(-x0, -y0) if pmask is not None else QPainterPath()
        self.update()

    def _fit(self, img: QImage, r: QRectF) -> QRectF:
        s = min(r.width() / img.width(), r.height() / img.height())
        return QRectF(r.center().x() - img.width() * s / 2, r.center().y() - img.height() * s / 2,
                      img.width() * s, img.height() * s)

    def _caption(self, p, r: QRectF, text: str, color: str):
        f = QFont(T.FONT, 9)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(text) + 22
        box = QRectF(r.center().x() - w / 2, r.top() + 8, w, 24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(4, 12, 32, 220))
        p.drawPath(holo.chamfer(box, 4))
        p.setPen(QPen(QColor(color), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(holo.chamfer(box, 4))
        p.setPen(QColor("white"))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        p.fillRect(r, QColor(1, 4, 12, 230))
        if self.cur is None:
            p.setPen(QColor(T.MUTED))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "Todavía no hay fotos. Hacé tu primer control semanal.")
            holo.neon_path(p, holo.chamfer(r.adjusted(1, 1, -1, -1), 6), T.GLOW, T.CORE, 1.0, 3, 2, 22)
            return
        inner = r.adjusted(10, 40, -10, -10)
        mode = self.mode if self.prev is not None else 0
        if mode == 2:  # lado a lado
            half = inner.width() / 2
            for img, lab, col, rr in ((self.prev, self.prev_label, T.GLOW, QRectF(inner.left(), inner.top(), half - 6, inner.height())),
                                      (self.cur, self.cur_label, T.GOLD, QRectF(inner.left() + half + 6, inner.top(), half - 6, inner.height()))):
                p.drawImage(self._fit(img, rr), img)
                self._caption(p, QRectF(rr.left(), r.top(), rr.width(), 30), ("ANTES  " if img is self.prev else "AHORA  ") + lab, col)
        else:
            area = self._fit(self.cur, inner)
            sx = area.width() / self.cur.width()
            if mode == 3:  # siluetas sobre la foto actual atenuada
                p.setOpacity(0.35)
                p.drawImage(area, self.cur)
                p.setOpacity(1)
                p.save()
                p.translate(area.topLeft())
                p.scale(sx, sx)
                for path, col in ((self.prev_path, SERIES_BLUE), (self.cur_path, SERIES_AMBER)):
                    if path.isEmpty():
                        continue
                    for w_, a in ((7, 40), (4, 80)):
                        p.setPen(QPen(holo.qc(col, a), w_ / sx))
                        p.drawPath(path)
                    p.setPen(QPen(QColor(col), 2 / sx))
                    p.drawPath(path)
                p.restore()
                self._legend(p, r)
            elif mode == 1:  # deslizar
                cut = area.left() + area.width() * self.value
                p.drawImage(area, self.cur)
                p.save()
                p.setClipRect(QRectF(area.left(), area.top(), cut - area.left(), area.height()))
                p.drawImage(area, self.prev)
                p.restore()
                holo.neon_line(p, cut, area.top(), cut, area.bottom(), T.GLOW, T.CORE, 1.5, 4, 2.2, 40)
                p.setBrush(QColor(4, 12, 32, 230))
                p.setPen(QPen(QColor(T.CORE), 1.5))
                p.drawEllipse(QPointF(cut, area.center().y()), 14, 14)
                icons_y = area.center().y()
                p.drawText(QRectF(cut - 14, icons_y - 14, 28, 28), Qt.AlignmentFlag.AlignCenter, "⇆")
                self._caption(p, QRectF(r.left() + 10, r.top(), r.width() / 2 - 20, 30), "◀ ANTES  " + self.prev_label, T.GLOW)
                self._caption(p, QRectF(r.center().x() + 10, r.top(), r.width() / 2 - 20, 30), "AHORA  " + self.cur_label + " ▶", T.GOLD)
            else:  # superponer
                p.drawImage(area, self.cur)
                if self.prev is not None:
                    p.setOpacity(self.value)
                    p.drawImage(area, self.prev)
                    p.setOpacity(1)
                txt = self.cur_label + (f"   +   {self.prev_label} al {int(self.value * 100)}%" if self.prev is not None else "")
                self._caption(p, QRectF(r.left(), r.top(), r.width(), 30), txt, T.GLOW)
        if self.prev is not None and self.aligned:
            p.setFont(QFont(T.FONT, 8))
            p.setPen(QColor(T.MUTED))
            p.drawText(r.adjusted(12, 0, -12, -8), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight,
                       "Alineadas automáticamente por la posición del cuerpo")
        holo.neon_path(p, holo.chamfer(r.adjusted(1, 1, -1, -1), 6), T.GLOW, T.CORE, 1.0, 3, 2, 22)

    def _legend(self, p, r):
        f = QFont(T.FONT, 9)
        p.setFont(f)
        x = r.left() + 16
        for name, col in (("Antes  " + self.prev_label, SERIES_BLUE), ("Ahora  " + self.cur_label, SERIES_AMBER)):
            p.setPen(QPen(QColor(col), 3))
            p.drawLine(QPointF(x, r.top() + 20), QPointF(x + 20, r.top() + 20))
            p.setPen(QColor(T.TEXT))
            tw = p.fontMetrics().horizontalAdvance(name)
            p.drawText(QRectF(x + 26, r.top() + 11, tw + 4, 18), Qt.AlignmentFlag.AlignVCenter, name)
            x += tw + 60

    def mousePressEvent(self, e):
        self._drag(e)

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._drag(e)

    def _drag(self, e):
        if self.mode == 1 and self.cur is not None:
            area = self._fit(self.cur, QRectF(self.rect()).adjusted(10, 40, -10, -10))
            self.value = max(0.0, min(1.0, (e.position().x() - area.left()) / max(1, area.width())))
            self.changed_by_drag(self.value)
            self.update()

    def changed_by_drag(self, v):  # lo reemplaza la página para mover el slider
        pass


# =================================================================== página
class CuerpoPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("page")
        self.stack = QStackedWidget()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stack)

        # ---------------- resumen
        self.ctrl = Panel("CONTROL SEMANAL", "scan-line")
        self.ctrl_txt = label("", "muted", wrap=True, align=Qt.AlignmentFlag.AlignCenter)
        self.ctrl_txt.setTextFormat(Qt.TextFormat.RichText)
        self.ctrl.lay.addWidget(self.ctrl_txt)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("Hacer control ahora", "primary", self.start_checkin, icon="camera"))
        row.addStretch()
        self.ctrl.lay.addLayout(row)

        peso = Panel("PESO", "scale")
        prow = QHBoxLayout()
        prow.addWidget(label("Peso de hoy (kg):", "lbl"))
        self.weight_in = QDoubleSpinBox()
        self.weight_in.setRange(20, 350)
        self.weight_in.setDecimals(1)
        self.weight_in.setSingleStep(0.1)
        self.weight_in.setValue(75.0)
        prow.addWidget(self.weight_in)
        prow.addWidget(button("Guardar", "", self.save_weight, icon="check"))
        prow.addStretch()
        peso.lay.addLayout(prow)
        peso.lay.addWidget(label("Consejo: pesate a la misma hora (en ayunas, después del baño). El promedio de 7 días "
                                 "es más confiable que el número de un solo día.", "muted", wrap=True))
        self.wstats = QGridLayout()
        self.wstats.setSpacing(8)
        peso.lay.addLayout(self.wstats)
        rrow = QHBoxLayout()
        self.range_btns = {}
        for days, txt in ((30, "30 días"), (90, "90 días"), (0, "Todo")):
            b = button(txt, "", lambda _=False, d=days: self.set_range(d))
            self.range_btns[days] = b
            rrow.addWidget(b)
        rrow.addStretch()
        self.trend_lbl = label("", align=Qt.AlignmentFlag.AlignRight)
        self.trend_lbl.setTextFormat(Qt.TextFormat.RichText)
        rrow.addWidget(self.trend_lbl)
        peso.lay.addLayout(rrow)
        self.range_days = 30
        self.wchart = LineChart(" kg", 1, 300, "Registrá tu peso al menos 2 días para ver la curva.")
        peso.lay.addWidget(self.wchart)

        comp = Panel("COMPOSICIÓN ESTIMADA", "activity")
        self.cgrid = QGridLayout()
        self.cgrid.setSpacing(8)
        comp.lay.addLayout(self.cgrid)
        mrow = QHBoxLayout()
        mcol1, mcol2 = QVBoxLayout(), QVBoxLayout()
        self.waist_chart = LineChart(" cm", 1, 210, "Con 2 controles vas a ver la evolución.")
        self.bf_chart = LineChart("%", 1, 210, "Con 2 controles vas a ver la evolución.")
        mcol1.addWidget(label("CINTURA (cm)", "lbl"))
        mcol1.addWidget(self.waist_chart)
        mcol2.addWidget(label("% DE GRASA ESTIMADO", "lbl"))
        mcol2.addWidget(self.bf_chart)
        mrow.addLayout(mcol1, 1)
        mrow.addSpacing(16)
        mrow.addLayout(mcol2, 1)
        comp.lay.addLayout(mrow)
        self.findings = label("", wrap=True)
        self.findings.setTextFormat(Qt.TextFormat.RichText)
        comp.lay.addWidget(self.findings)
        comp.lay.addWidget(label(
            "Cómo se calcula: con la foto de frente se mide el ancho y con las de perfil la profundidad de cuello, "
            "cintura y cadera; con eso se estiman los contornos y el % de grasa con el método de la Marina de EE.UU. "
            "Usa medidas y altura, no el peso, así que ganar músculo no cuenta como grasa (a diferencia del IMC). "
            "Es una estimación con un margen de ±3-4%: lo que importa es la tendencia con fotos en las mismas condiciones.",
            "muted", wrap=True))

        fotos = Panel("FOTOS", "images")
        frow = QGridLayout()
        frow.setHorizontalSpacing(10)
        frow.setVerticalSpacing(8)
        self.view_sel = QComboBox()
        for k, n, *_ in VIEWS:
            self.view_sel.addItem(n.capitalize(), k)
        self.cur_sel = QComboBox()
        self.prev_sel = QComboBox()
        self.mode_sel = QComboBox()
        self.mode_sel.addItems(PhotoCompare.MODES)
        for i, (w, t) in enumerate(((self.view_sel, "Vista"), (self.mode_sel, "Modo"), (self.cur_sel, "Fecha"),
                                    (self.prev_sel, "Comparar con"))):
            w.setMinimumContentsLength(10)
            w.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            frow.addWidget(label(t, "lbl"), i // 2, (i % 2) * 2)
            frow.addWidget(w, i // 2, (i % 2) * 2 + 1)
            w.currentIndexChanged.connect(self.update_compare)
        frow.setColumnStretch(1, 1)
        frow.setColumnStretch(3, 1)
        fotos.lay.addLayout(frow)
        orow = QHBoxLayout()
        self.op_lbl = label("Opacidad de la foto anterior", "lbl")
        orow.addWidget(self.op_lbl)
        self.op = QSlider(Qt.Orientation.Horizontal)
        self.op.setRange(0, 100)
        self.op.setValue(45)
        self.op.valueChanged.connect(self.update_compare)
        orow.addWidget(self.op, 1)
        fotos.lay.addLayout(orow)
        self.compare = PhotoCompare()
        self.compare.changed_by_drag = lambda v: (self.op.blockSignals(True), self.op.setValue(int(v * 100)),
                                                  self.op.blockSignals(False))
        fotos.lay.addWidget(self.compare)

        self.stack.addWidget(scroll_page(self.ctrl, peso, comp, fotos))

        # ---------------- captura
        cap = Panel("CONTROL SEMANAL", "scan-line")
        self.cap_panel = cap
        self.cap_tip = label("", wrap=True, align=Qt.AlignmentFlag.AlignCenter)
        self.cap_tip.setStyleSheet(f"font-size:16px;color:{T.CORE};")
        cap.lay.addWidget(self.cap_tip)
        self.video = VideoView()
        cap.lay.addWidget(self.video, 1)
        crow = QHBoxLayout()
        crow.addWidget(button("Cancelar", "danger", self.cancel_checkin, icon="x"))
        crow.addStretch()
        self.ghost_slider = QSlider(Qt.Orientation.Horizontal)
        self.ghost_slider.setRange(0, 80)
        self.ghost_slider.setValue(35)
        self.ghost_slider.setFixedWidth(180)
        self.ghost_slider.valueChanged.connect(lambda v: setattr(self.video, "ghost_opacity", v / 100))
        crow.addWidget(label("Foto anterior", "lbl"))
        crow.addWidget(self.ghost_slider)
        crow.addStretch()
        crow.addWidget(button("Sacar foto ya", "primary", lambda: self.capture(force=True), icon="camera"))
        cap.lay.addLayout(crow)
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(4, 4, 14, 8)
        wl.addWidget(cap)
        self.stack.addWidget(wrap)

        self.worker: CameraWorker | None = None
        self.step = 0
        self.shots: dict = {}
        self.weight_today = 0.0
        self.stable_since = None
        self.countdown_end = None
        self.last_center = ""

    # ------------------------------------------------------------ resumen
    def refresh(self):
        g = self.win.game
        due = g.checkin_due()
        last = g.last_checkin()
        day = WEEKDAYS[g.settings.get("checkinDay", 0)].lower()
        if due:
            self.ctrl.set_tone("gold")
            txt = (f"{icons.img('scan-line', 18, T.GOLD)}&nbsp; <b style='color:{T.GOLD}'>Te toca el control de esta semana.</b><br>"
                   "Son 3 fotos (frente, perfil izquierdo y derecho) y tu peso. Tarda 2 minutos.")
        else:
            self.ctrl.set_tone("")
            txt = f"Próximo control: <b style='color:white'>{g.next_checkin()}</b> (día elegido: {day})."
        if last:
            txt += f"<br>Último control: {last['date']} · {last['weight']:.1f} kg"
        self.ctrl_txt.setText(txt)

        st = g.weight_stats()
        clear_layout(self.wstats)
        f = lambda v: "—" if v is None else f"{v:.1f} kg"
        if st["count"]:
            wc = st["week_change"]
            items = [(f(st["last"]), "Último"), (f(st["avg7"]), "Promedio 7 días"), (f(st["avg30"]), "Promedio 30 días"),
                     (f(st["avg_all"]), f"Promedio total ({st['count']} registros)"),
                     ("—" if wc is None else f"{wc:+.1f} kg", "Cambio semanal (prom. 7 d)")]
            for i, (v, n) in enumerate(items):
                self.wstats.addWidget(stat_box(v, n), 0, i)
            if st["last"]:
                self.weight_in.setValue(st["last"])
        self._refresh_weight_chart()
        cks_ok = [c for c in g.s["checkins"] if (c.get("metrics") or {}).get("reliable")]
        wpts = [(date.fromisoformat(c["date"]), c["metrics"]["waist_cm"]) for c in cks_ok]
        bpts = [(date.fromisoformat(c["date"]), c["metrics"]["body_fat"]) for c in cks_ok if c["metrics"].get("body_fat")]
        self.waist_chart.set_series([Series("Cintura", SERIES_BLUE, wpts, area=True)], pad_y=1.0)
        self.bf_chart.set_series([Series("% de grasa", SERIES_BLUE, bpts, area=True)], pad_y=0.5)

        clear_layout(self.cgrid)
        cks = g.s["checkins"]
        if cks:
            m = cks[-1]["metrics"]
            pm = cks[-2]["metrics"] if len(cks) > 1 else {}
            def delta(k, unit, lower_is_good=True):
                if not pm.get(k) or not m.get(k):
                    return "", None
                d = m[k] - pm[k]
                if abs(d) < 0.05:
                    return "= sin cambios", None
                return f"{d:+.1f}{unit} vs anterior", (d < 0) == lower_is_good
            items = [
                ("—" if m.get("body_fat") is None else f"{m['body_fat']:.1f}%", "% de grasa", *delta("body_fat", "%")),
                ("—" if m.get("lean_kg") is None else f"{m['lean_kg']:.1f} kg", "Masa magra", *delta("lean_kg", " kg", False)),
                ("—" if m.get("fat_kg") is None else f"{m['fat_kg']:.1f} kg", "Masa grasa", *delta("fat_kg", " kg")),
                (f"{m.get('waist_cm', 0):.1f} cm", "Cintura", *delta("waist_cm", " cm")),
                (f"{m.get('neck_cm', 0):.1f} cm", "Cuello", *delta("neck_cm", " cm", False)),
                (f"{m.get('hip_cm', 0):.1f} cm", "Cadera", *delta("hip_cm", " cm")),
                (f"{m.get('shoulder_waist', 0):.2f}", "Hombros / cintura", *delta("shoulder_waist", "", False)),
                (f"{m.get('waist_height', 0):.2f}", "Cintura / altura", *delta("waist_height", "")),
            ]
            for i, (v, n, d, good) in enumerate(items):
                self.cgrid.addWidget(stat_box(v, n, d, good), i // 4, i % 4)
            fl = cks[-1].get("findings") or []
            warns = m.get("warnings") or []
            html = "".join(f"{icons.img('sparkles', 15, T.GOLD)}&nbsp; {escape(x)}<br>" for x in fl)
            html += "".join(f"<span style='color:{T.GOLD}'>{icons.img('triangle-alert', 15, T.GOLD)}&nbsp; {escape(x)}</span><br>" for x in warns)
            self.findings.setText(html or f"<span style='color:{T.MUTED}'>Con el próximo control vas a ver la comparación.</span>")
        else:
            self.cgrid.addWidget(label("Todavía no hiciste ningún control.", "muted"), 0, 0)
            self.findings.setText("")

        dates = [c["date"] for c in reversed(cks)]
        changed = len(dates) != getattr(self, "_ndates", -1)
        self._ndates = len(dates)
        for combo, items in ((self.cur_sel, dates), (self.prev_sel, ["(ninguna)"] + dates)):
            cur = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(items)
            if cur in items and not changed:
                combo.setCurrentText(cur)
            combo.blockSignals(False)
        if changed:  # por defecto: último control vs el anterior
            self.cur_sel.setCurrentIndex(0)
            self.prev_sel.setCurrentIndex(2 if len(dates) > 1 else 0)
        self.update_compare()

    def set_range(self, days: int):
        self.range_days = days
        self._refresh_weight_chart()

    def _refresh_weight_chart(self):
        g = self.win.game
        for d, b in self.range_btns.items():
            b.setProperty("kind", "primary" if d == self.range_days else "")
        pts = sorted((date.fromisoformat(k), v) for k, v in g.s["weights"].items())
        if self.range_days:
            start = g._today() - timedelta(days=self.range_days - 1)
            d0 = start
        else:
            d0 = pts[0][0] if pts else None
        avg = [x for x in moving_average(pts) if d0 is None or x[0] >= d0]
        daily = [x for x in pts if d0 is None or x[0] >= d0]
        if len(daily) < 2:
            self.wchart.set_series([])
            self.trend_lbl.setText("")
            return
        self.wchart.set_series([Series("Promedio 7 días", SERIES_BLUE, avg, area=True),
                                Series("Peso del día", SERIES_AMBER, daily, kind="dots", glow=False)],
                               d0=min(d0 or daily[0][0], daily[0][0]) if self.range_days else None,
                               d1=g._today() if self.range_days else None, pad_y=0.3)
        t = weekly_trend(avg)
        if t is None:
            self.trend_lbl.setText("")
        else:
            col = T.MUTED if abs(t) < 0.1 else T.CORE
            self.trend_lbl.setText(f"<span style='color:{T.MUTED}'>Tendencia del período:</span> "
                                   f"<b style='color:{col}'>{t:+.2f} kg/semana</b>".replace(".", ","))

    def update_compare(self):
        g = self.win.game
        by_date = {c["date"]: c for c in g.s["checkins"]}
        view = self.view_sel.currentData() or "front"
        cur = by_date.get(self.cur_sel.currentText())
        prev = by_date.get(self.prev_sel.currentText())
        self.compare.mode = self.mode_sel.currentIndex()
        self.compare.value = self.op.value() / 100
        self.op_lbl.setText({0: "Opacidad de la foto anterior", 1: "Corte antes / después (también podés arrastrar)"}
                            .get(self.compare.mode, "—"))
        self.op.setEnabled(self.compare.mode in (0, 1))
        self.compare.set_pair(cur, prev, view)

    def save_weight(self):
        try:
            self.win.game.log_weight(self.weight_in.value())
            self.win.toaster.show(f"Peso guardado: {self.weight_in.value():.1f} kg", icon="scale")
        except ValueError as e:
            self.win.toaster.show(str(e))
        self.refresh()

    # ------------------------------------------------------------ flujo del control
    def start_checkin(self):
        g = self.win.game
        d = self.win.dialogs
        prof = g.profile

        def ask_height(*_):
            d.show("TU ALTURA", "Para convertir las fotos a centímetros necesito tu altura (en cm).<br>"
                                "<small>Se pide una sola vez; podés cambiarla en Ajustes.</small>",
                   ("Confirmar",), callback=got_height, with_input=True, placeholder="Ej: 175", icon="ruler")

        def got_height(_, v):
            try:
                h = float(v.replace(",", "."))
                if not 120 <= h <= 230:
                    raise ValueError
            except ValueError:
                ask_height()
                return
            prof["heightCm"] = h
            g.save()
            next_step()

        def ask_sex():
            d.show("FÓRMULA", "La estimación de grasa usa una fórmula distinta para hombres y mujeres.",
                   (("Hombre", "primary"), ("Mujer", "")), callback=lambda i, _: (prof.__setitem__("sex", "m" if i == 0 else "f"),
                                                                                 g.save(), next_step()), icon="user-round")

        def ask_weight():
            st = g.weight_stats()
            ph = f"Ej: {st['last']:.1f}" if st.get("last") else "Ej: 78.5"
            d.show("PESO DE HOY", "Pesate y escribí tu peso en kg.<br><small>Ideal: en ayunas, sin ropa o con poca ropa.</small>",
                   ("Continuar",), callback=got_weight, with_input=True, placeholder=ph, icon="scale")

        def got_weight(_, v):
            try:
                kg = float(v.replace(",", "."))
                if not 20 <= kg <= 350:
                    raise ValueError
            except ValueError:
                ask_weight()
                return
            self.weight_today = kg
            next_step()

        steps = []
        if not prof.get("heightCm"):
            steps.append(ask_height)
        if not prof.get("sex"):
            steps.append(ask_sex)
        steps.append(ask_weight)
        steps.append(self._open_camera)

        def next_step():
            if steps:
                steps.pop(0)()
        next_step()

    def _open_camera(self):
        self.step = 0
        self.shots = {}
        self.stack.setCurrentIndex(1)
        self._prepare_view()
        idx = self.win.game.s["settings"].get("camera", 0)
        self.worker = CameraWorker(idx, self.win.game.s["settings"].get("mirror", True), self, segmentation=True)
        self.worker.frame.connect(self.on_frame)
        self.worker.status.connect(lambda m: (setattr(self.video, "center_small", m), self.video.update()))
        self.worker.failed.connect(lambda m: (self.win.dialogs.show("ERROR", f"No pude iniciar la cámara.<br><small>{escape(m)}</small>",
                                                                    tone="red"), self.cancel_checkin()))
        self.video.center_small = "Iniciando cámara…"
        self.worker.start()

    def _prepare_view(self):
        key, name, tip, ic = VIEWS[self.step]
        self.cap_panel.set_title(f"FOTO {self.step + 1}/3 · {name}")
        self.cap_panel.title.set_icon(ic)
        self.cap_tip.setText(tip)
        last = self.win.game.last_checkin()
        self.video.ghost = load_qimage(last["photos"].get(key)) if last else None
        self.video.count = ""
        self.video.target = ""
        self.stable_since = None
        self.countdown_end = None
        self.win.voice.say(tip.split(".")[0], True)

    def _orientation_ok(self, lm) -> tuple[bool, str]:
        vis = lambda i: (lm[i].visibility or 0) > 0.5
        if not all(vis(i) for i in (0, 11, 12, 23, 24)) or not (vis(27) or vis(28)):
            return False, "Necesito verte de pies a cabeza: alejate un poco"
        if max(lm[27].y, lm[28].y) > 0.99 or lm[0].y < 0.02:
            return False, "Quedaste cortado: alejate o bajá la cámara"
        torso = abs((lm[23].y + lm[24].y) / 2 - (lm[11].y + lm[12].y) / 2) or 0.01
        ratio = abs(lm[11].x - lm[12].x) / torso
        front = VIEWS[self.step][0] == "front"
        if front and ratio < 0.45:
            return False, "Ponete de frente a la cámara"
        if not front and ratio > 0.3:
            return False, "Girá un poco más: de perfil a la cámara"
        return True, "Quedate quieto…"

    def on_frame(self, img, lm, world, aspect, t):
        v = self.video
        if self.stack.currentIndex() != 1:
            return
        v.center_small = ""
        if lm is None:
            v.set_feedback("No te detecto: alejate y que se vea todo tu cuerpo", "bad")
            self.stable_since = self.countdown_end = None
            v.center = ""
            v.set_frame(img, None, T.GLOW)
            return
        ok, msg = self._orientation_ok(lm)
        if not ok:
            v.set_feedback(msg, "warn")
            self.stable_since = self.countdown_end = None
            v.center = ""
            v.set_frame(img, lm, T.GOLD, world)
            return
        v.set_feedback(msg, "good")
        if self.countdown_end is None:
            self.stable_since = self.stable_since or t
            if t - self.stable_since > 1.2:
                self.countdown_end = t + 3
        else:
            left = self.countdown_end - t
            txt = str(int(left) + 1) if left > 0 else ""
            if txt != self.last_center:
                self.last_center = txt
                v.center = txt
                if txt:
                    self.win.sounds.play("tick")
            if left <= 0:
                v.set_frame(img, lm, T.GREEN, world)
                self.capture()
                return
        v.set_frame(img, lm, T.GREEN, world)

    def capture(self, force: bool = False):
        if not self.worker or not self.worker.latest:
            return
        rgb, mask, lm = self.worker.latest
        if mask is None or lm is None:
            if force:
                self.win.toaster.show("No detecto tu cuerpo todavía", icon="circle-alert")
            return
        key = VIEWS[self.step][0]
        self.shots[key] = (rgb.copy(), mask.copy(), lm)
        self.win.sounds.play("go")
        self.video.flash = 6
        self.video.center = ""
        self.countdown_end = self.stable_since = None
        self.step += 1
        if self.step < len(VIEWS):
            QTimer.singleShot(400, self._prepare_view)
        else:
            QTimer.singleShot(300, self.finish_checkin)

    def _stop_camera(self):
        if self.worker:
            self.worker.stop()
            self.worker = None
        self.video.ghost = None
        self.video.clear()

    def cancel_checkin(self):
        self._stop_camera()
        self.stack.setCurrentIndex(0)

    def finish_checkin(self):
        import cv2
        self._stop_camera()
        g = self.win.game
        prof = g.profile
        today = g.today()
        photos, landmarks = {}, {}
        for key, (rgb, mask, lm) in self.shots.items():
            name = f"{today}_{key}.jpg"
            cv2.imwrite(str(photos_dir() / name), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
            cv2.imwrite(str(photos_dir() / f"{today}_{key}_mask.png"), (mask > 0.5).astype(np.uint8) * 255)
            photos[key] = name
            landmarks[key] = body.lm_to_list(lm)
        s = self.shots
        try:
            m = body.analyze(s["front"][1], s["front"][2], s["left"][1], s["left"][2], s["right"][1], s["right"][2],
                             float(prof["heightCm"]), prof.get("sex") or "m", self.weight_today).to_dict()
        except Exception as e:  # nunca perder las fotos por un error de análisis
            m = {"reliable": False, "warnings": [f"No se pudo analizar: {e}"]}
        prev = g.last_checkin()
        findings = body.compare(prev["metrics"], m, prev["weight"], self.weight_today) if prev and prev["date"] != today else []
        g.add_checkin(self.weight_today, photos, m, findings, landmarks)
        self.stack.setCurrentIndex(0)
        self.refresh()
        bf = m.get("body_fat")
        res = (f"Peso: <b>{self.weight_today:.1f} kg</b><br>"
               + (f"Grasa estimada: <b>{bf:.1f}%</b> · Masa magra: <b>{m['lean_kg']:.1f} kg</b><br>"
                  f"Cintura: <b>{m['waist_cm']:.1f} cm</b><br>" if bf is not None else "")
               + ("<br>" + "<br>".join(escape(x) for x in findings) if findings else
                  "<br><small>La semana que viene vas a ver la comparación.</small>")
               + ("".join(f"<br><span style='color:{T.GOLD}'>{escape(w)}</span>" for w in m.get("warnings", []))))
        self.win.dialogs.show("CONTROL REGISTRADO", res, icon="scan-line", tone="gold", sound="level")
