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


# =================================================================== gráfico de peso
class WeightChart(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(240)
        self.points: list[tuple[date, float]] = []

    def set_data(self, weights: dict):
        self.points = sorted((date.fromisoformat(k), v) for k, v in weights.items())[-90:]
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        if len(self.points) < 2:
            p.setPen(QColor(T.MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Registrá tu peso al menos 2 días para ver la curva.")
            return
        top, bottom, left, right = 16, 26, 44, 10
        vals = [v for _, v in self.points]
        lo, hi = min(vals) - 0.5, max(vals) + 0.5
        d0, d1 = self.points[0][0], self.points[-1][0]
        span = max(1, (d1 - d0).days)
        X = lambda d: left + (W - left - right) * (d - d0).days / span
        Y = lambda v: top + (H - top - bottom) * (1 - (v - lo) / (hi - lo))
        p.setFont(QFont(T.FONT, 8))
        for k in range(4):
            v = lo + (hi - lo) * k / 3
            y = Y(v)
            p.setPen(QColor(79, 216, 255, 28))
            p.drawLine(QPointF(left, y), QPointF(W - right, y))
            p.setPen(QColor(T.MUTED))
            p.drawText(QRectF(0, y - 8, left - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{v:.1f}")
        p.drawText(QRectF(left, H - bottom + 6, 80, 16), Qt.AlignmentFlag.AlignLeft, f"{d0.day}/{d0.month}")
        p.drawText(QRectF(W - right - 80, H - bottom + 6, 80, 16), Qt.AlignmentFlag.AlignRight, f"{d1.day}/{d1.month}")
        # media móvil de 7 días
        avg = []
        for d, _ in self.points:
            w = [v for dd, v in self.points if 0 <= (d - dd).days < 7]
            avg.append((d, sum(w) / len(w)))
        path = QPainterPath(QPointF(X(avg[0][0]), Y(avg[0][1])))
        for d, v in avg[1:]:
            path.lineTo(QPointF(X(d), Y(v)))
        holo.neon_path(p, path, T.GLOW, T.CORE, 1.8, 5, 2.4, 26)
        p.setPen(Qt.PenStyle.NoPen)
        for d, v in self.points:
            p.setBrush(QColor(T.GOLD))
            p.drawEllipse(QPointF(X(d), Y(v)), 3, 3)
        p.setPen(QColor(T.MUTED))
        p.drawText(QRectF(left, 0, W, 14), Qt.AlignmentFlag.AlignLeft,
                   "●  peso del día      ━  promedio de 7 días")


# =================================================================== comparador de fotos
class PhotoCompare(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(460)
        self.cur: QImage | None = None
        self.prev: QImage | None = None
        self.cur_label = self.prev_label = ""
        self.mode = "overlay"
        self.opacity = 0.45

    def set_images(self, cur, prev, cur_label, prev_label):
        self.cur, self.prev, self.cur_label, self.prev_label = cur, prev, cur_label, prev_label
        self.update()

    def _fit(self, img: QImage, r: QRectF) -> QRectF:
        s = min(r.width() / img.width(), r.height() / img.height())
        return QRectF(r.center().x() - img.width() * s / 2, r.center().y() - img.height() * s / 2,
                      img.width() * s, img.height() * s)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        p.fillRect(r, QColor(0, 0, 0, 160))
        if self.cur is None:
            p.setPen(QColor(T.MUTED))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "Todavía no hay fotos. Hacé tu primer control semanal.")
            return
        f = QFont(T.FONT, 10)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        if self.mode == "side" and self.prev is not None:
            half = r.width() / 2
            for img, lab, rr in ((self.prev, self.prev_label, QRectF(r.left(), r.top(), half - 4, r.height())),
                                 (self.cur, self.cur_label, QRectF(r.left() + half + 4, r.top(), half - 4, r.height()))):
                p.drawImage(self._fit(img, rr), img)
                p.setPen(QColor(T.CORE))
                p.drawText(rr.adjusted(10, 8, -10, -8), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter, lab)
        else:
            area = self._fit(self.cur, r)
            p.drawImage(area, self.cur)
            if self.prev is not None:
                p.setOpacity(self.opacity)
                p.drawImage(area, self.prev)
                p.setOpacity(1)
            p.setPen(QColor(T.CORE))
            txt = self.cur_label + (f"   ·   superpuesta: {self.prev_label} ({int(self.opacity * 100)}%)" if self.prev else "")
            p.drawText(r.adjusted(10, 8, -10, -8), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter, txt)
        holo.neon_path(p, holo.chamfer(r.adjusted(1, 1, -1, -1), 6), T.GLOW, T.CORE, 1.0, 3, 2, 22)


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
        self.wchart = WeightChart()
        peso.lay.addWidget(self.wchart)

        comp = Panel("COMPOSICIÓN ESTIMADA", "activity")
        self.cgrid = QGridLayout()
        self.cgrid.setSpacing(8)
        comp.lay.addLayout(self.cgrid)
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
        frow = QHBoxLayout()
        self.view_sel = QComboBox()
        for k, n, *_ in VIEWS:
            self.view_sel.addItem(n.capitalize(), k)
        self.cur_sel = QComboBox()
        self.prev_sel = QComboBox()
        self.mode_sel = QComboBox()
        self.mode_sel.addItems(["Superponer", "Lado a lado"])
        for w, t in ((self.view_sel, "Vista"), (self.cur_sel, "Fecha"), (self.prev_sel, "Comparar con"), (self.mode_sel, "")):
            if t:
                frow.addWidget(label(t, "lbl"))
            frow.addWidget(w, 1)
            w.currentIndexChanged.connect(self.update_compare)
        fotos.lay.addLayout(frow)
        orow = QHBoxLayout()
        orow.addWidget(label("Opacidad de la foto anterior", "lbl"))
        self.op = QSlider(Qt.Orientation.Horizontal)
        self.op.setRange(0, 100)
        self.op.setValue(45)
        self.op.valueChanged.connect(self.update_compare)
        orow.addWidget(self.op, 1)
        fotos.lay.addLayout(orow)
        self.compare = PhotoCompare()
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
        self.wchart.set_data(g.s["weights"])

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
                (f"{m.get('waist_height', 0):.2f}", "Cintura / altura (ideal < 0,50)", *delta("waist_height", "")),
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

    def update_compare(self):
        g = self.win.game
        by_date = {c["date"]: c for c in g.s["checkins"]}
        view = self.view_sel.currentData() or "front"
        cur = by_date.get(self.cur_sel.currentText())
        prev = by_date.get(self.prev_sel.currentText())
        self.compare.mode = "side" if self.mode_sel.currentIndex() == 1 else "overlay"
        self.compare.opacity = self.op.value() / 100
        lab = lambda c: f"{c['date']} · {c['weight']:.1f} kg" if c else ""
        self.compare.set_images(load_qimage(cur and cur["photos"].get(view)), load_qimage(prev and prev["photos"].get(view)),
                                lab(cur), lab(prev))

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
            v.set_frame(img, lm, T.GOLD)
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
                v.set_frame(img, lm, T.GREEN)
                self.capture()
                return
        v.set_frame(img, lm, T.GREEN)

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
        photos = {}
        for key, (rgb, mask, lm) in self.shots.items():
            name = f"{today}_{key}.jpg"
            cv2.imwrite(str(photos_dir() / name), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
            cv2.imwrite(str(photos_dir() / f"{today}_{key}_mask.png"), (mask > 0.5).astype(np.uint8) * 255)
            photos[key] = name
        s = self.shots
        try:
            m = body.analyze(s["front"][1], s["front"][2], s["left"][1], s["left"][2], s["right"][1], s["right"][2],
                             float(prof["heightCm"]), prof.get("sex") or "m", self.weight_today).to_dict()
        except Exception as e:  # nunca perder las fotos por un error de análisis
            m = {"reliable": False, "warnings": [f"No se pudo analizar: {e}"]}
        prev = g.last_checkin()
        findings = body.compare(prev["metrics"], m, prev["weight"], self.weight_today) if prev and prev["date"] != today else []
        g.add_checkin(self.weight_today, photos, m, findings)
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
