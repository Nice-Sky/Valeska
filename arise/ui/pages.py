"""Pantallas de la app."""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from html import escape

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLabel,
                               QListWidget, QProgressBar, QPushButton, QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from .. import storage
from ..camera import CameraWorker, list_cameras
from ..exercises import EXERCISE_ORDER, EXERCISES, RepCounter
from ..i18n import plural, t
from ..game import ACHIEVEMENTS, PLAN_ORDER, PLANS, STATS, WEEKDAYS, fmt, next_rank, rank_of, xp_needed
from . import theme as T
from . import holo, icons
from .video import VideoView
from .widgets import GlowLabel, NeonBar, Panel, RankBadge, button, icon_label, label, restyle


def scroll_page(*widgets) -> QScrollArea:
    inner = QWidget()
    inner.setObjectName("page")
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(6, 14, 16, 26)
    lay.setSpacing(14)
    for w in widgets:
        lay.addWidget(w)
    lay.addStretch()
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    sa.setWidget(inner)
    return sa


def clear_layout(lay):
    while lay.count():
        it = lay.takeAt(0)
        if it.widget():
            it.widget().hide()
            it.widget().deleteLater()
        elif it.layout():
            clear_layout(it.layout())


class QuestList(QWidget):
    """Lista de objetivos del día con barras de progreso."""

    def __init__(self, win, with_buttons: bool):
        super().__init__()
        self.win = win
        self.with_buttons = with_buttons
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(4)

    def refresh(self):
        clear_layout(self.lay)
        q = self.win.game.quest
        if not q:
            return
        if q.get("rest"):
            r = QHBoxLayout()
            r.addWidget(icon_label("moon", 20, T.GLOW))
            r.addWidget(label("Día de descanso. Recuperar también es parte del plan. Si querés, podés entrenar igual.", "muted", wrap=True), 1)
            self.lay.addLayout(r)
            return
        for k, t in q["targets"].items():
            ex = EXERCISES[k]
            v = min(q["progress"].get(k, 0), t)
            done = v >= t
            row = QHBoxLayout()
            row.addWidget(icon_label(ex.icon, 20, T.GREEN if done else icons.WHITE))
            name = label(ex.name)
            name.setStyleSheet("font-size:17px;font-weight:600;")
            row.addWidget(name)
            row.addStretch()
            num = label(f"[{fmt(v)}/{t}]{' s' if ex.timed else ''}")
            num.setStyleSheet(f"font-size:16px;color:{T.GREEN if done else 'white'};")
            row.addWidget(num)
            if self.with_buttons and not done:
                row.addWidget(button("Entrenar", "", lambda _=False, k=k: self.win.open_training(k), icon="swords"))
            self.lay.addLayout(row)
            self.lay.addWidget(ThinBar(v / t if t else 0, done))
            self.lay.addSpacing(6)


class ThinBar(QWidget):
    """Barra fina de progreso con tubo de luz."""

    def __init__(self, k: float, done: bool):
        super().__init__()
        self.k, self.done = max(0.0, min(1.0, k)), done
        self.setFixedHeight(12)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 4, -1, -4)
        p.fillRect(r, QColor(2, 8, 22, 200))
        p.setPen(QColor(45, 110, 220, 90))
        p.drawRect(r)
        if self.k > 0:
            col = T.GREEN if self.done else T.GLOW
            fr = QRectF(r.left(), r.top(), r.width() * self.k, r.height())
            for i, a in ((3, 30), (2, 55), (1, 90)):
                c = QColor(col)
                c.setAlpha(a)
                p.fillRect(fr.adjusted(0, -i, 0, i), c)
            p.fillRect(fr, QColor(col))
            p.fillRect(QRectF(fr.left(), fr.center().y() - 0.5, fr.width(), 1), QColor(T.CORE))


class ExCard(QPushButton, holo.Surface, holo.HoverFade):
    """Tarjeta de ejercicio holográfica con ícono grande; se ilumina y "levanta" suave al pasar el mouse."""

    PAD = 18

    def __init__(self, icon_name, title, sub, done=False):
        QPushButton.__init__(self)
        self.icon_name, self.title_text, self.sub, self.done = icon_name, title, sub, done
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(176)
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self.sweep = False
        self.surface_init()
        self.hover_init(220)

    def _spec(self, hovered: bool):
        return holo.SurfaceSpec(QRectF(self.rect()).adjusted(self.PAD, self.PAD, -self.PAD, -self.PAD),
                                "gold" if self.done else "", cut=10, brackets=hovered, strong=hovered,
                                seed=sum(map(ord, self.title_text)), density=0.7, quiet=not hovered)

    def surface_spec(self):
        return self._spec(self.hover_k > 0.5)

    def enterEvent(self, e):
        self.hover_to(1.0)
        from .. import voice as _v
        if _v.SOUNDS_REF:
            _v.SOUNDS_REF.play("hover")

    def leaveEvent(self, e):
        self.hover_to(0.0)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        k = self.hover_k
        p.translate(0, -4 * k)  # se "levanta"
        if k < 0.999:
            self.paint_surface(p, self._spec(False))
        if k > 0.001:
            self.paint_surface(p, self._spec(True), opacity=k)
        color, core = holo.palette("gold" if self.done else "")
        s = 40 + 4 * k
        r = QRectF((self.width() - s) / 2, 40 - 2 * k, s, s)
        p.setOpacity(0.35 + 0.3 * k)
        icons.paint(p, self.icon_name, r, color, 5.0)
        p.setOpacity(1)
        icons.paint(p, self.icon_name, r, core, 1.7)
        f = QFont(T.FONT, 13)
        f.setWeight(QFont.Weight.DemiBold)
        from . import fx
        fx.draw_glow_text(p, QRectF(0, 90, self.width(), 26), self.title_text.upper(), f, color, core,
                          glow=0.45, spacing=2.5, intensity=0.6 + 0.4 * k)
        sf = QFont(T.FONT, 10)
        p.setFont(sf)
        p.setPen(QColor(T.GOLD if self.done else T.MUTED))
        p.drawText(QRectF(0, 118, self.width(), 22), Qt.AlignmentFlag.AlignCenter, self.sub)


# =================================================================== ESTADO
class EstadoPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("page")
        status = Panel("ESTADO", "user-round")
        head = QHBoxLayout()
        self.badge = RankBadge(110)
        head.addWidget(self.badge)
        head.addSpacing(14)
        info = QFormLayout()
        info.setHorizontalSpacing(30)
        info.setVerticalSpacing(8)
        self.name, self.level, self.rank_next, self.streak, self.adh, self.title = (label() for _ in range(6))
        self.level = GlowLabel("1", 26, spacing=1)
        for txt, w in (("NOMBRE", self.name), ("NIVEL", self.level), ("PRÓXIMO RANGO", self.rank_next),
                       ("RACHA", self.streak), ("CONSTANCIA (30 DÍAS)", self.adh), ("ÚLTIMO LOGRO", self.title)):
            info.addRow(label(txt, "lbl"), w)
        head.addLayout(info, 1)
        status.lay.addLayout(head)
        self.xp = NeonBar(32)
        status.lay.addWidget(self.xp)
        self.stats = QGridLayout()
        self.stats.setSpacing(10)
        status.lay.addLayout(self.stats)

        quest = Panel("OBJETIVO DE HOY", "target")
        self.quest = QuestList(win, False)
        quest.lay.addWidget(self.quest)
        quest.lay.addWidget(button("Ir al objetivo", "primary", lambda: win.go("mision"), icon="target"))

        rec = Panel("RÉCORDS PERSONALES", "trophy")
        self.records = QGridLayout()
        self.records.setSpacing(8)
        rec.lay.addWidget(label("Mejor serie de cada ejercicio (repeticiones seguidas o segundos de plancha).", "muted", wrap=True))
        rec.lay.addLayout(self.records)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll_page(status, quest, rec))

    def refresh(self):
        g = self.win.game
        p = g.player
        lvl = p["level"]
        self.badge.set_rank(rank_of(lvl))
        self.name.setText(p["name"])
        self.level.setText(str(lvl))
        nr = next_rank(lvl)
        self.rank_next.setText(f"{nr[1]} en el nivel {nr[0]} (faltan {nr[0] - lvl})" if nr else "Rango máximo")
        self.streak.setText(f"{g.s['streak']} día{'s' if g.s['streak'] != 1 else ''}  (mejor: {g.s['bestStreak']})")
        adh = g.adherence()
        self.adh.setText("—" if adh is None else f"{adh}%")
        self.adh.setStyleSheet(f"color:{T.GREEN if (adh or 0) >= 80 else T.GOLD if (adh or 0) >= 50 else T.RED if adh is not None else T.TEXT};font-weight:700;")
        self.title.setText(g.last_achievement())
        need = xp_needed(lvl)
        self.xp.setRange(0, need)
        self.xp.setValue(int(p["xp"]))
        self.xp.setFormat(f"XP  {fmt(p['xp'])} / {fmt(need)}")
        clear_layout(self.stats)
        cards = [(k, name, tip, str(g.stat_value(k))) for k, (name, tip, _) in STATS.items()]
        cards.append(("DIS", "Disciplina", "Porcentaje de días cumplidos en los últimos 30 (sin contar descansos)",
                      "—" if adh is None else f"{adh}%"))
        for i, (k, name, tip, val) in enumerate(cards):
            card = Panel(compact=True)
            card.setToolTip(tip)
            row = QHBoxLayout()
            col = QVBoxLayout()
            t = label(k)
            t.setStyleSheet(f"color:{T.GLOW};font-size:15px;font-weight:700;")
            col.addWidget(t)
            col.addWidget(label(name, "lbl"))
            row.addLayout(col)
            row.addStretch()
            v = GlowLabel(val, 24, align=Qt.AlignmentFlag.AlignRight)
            row.addWidget(v)
            card.lay.addLayout(row)
            self.stats.addWidget(card, i // 2, i % 2)
        clear_layout(self.records)
        for i, e in enumerate(EXERCISE_ORDER):
            ex = EXERCISES[e]
            r = g.s["records"].get(e, 0)
            box = label(f"<span style='font-size:22px;font-weight:700;color:white'>{fmt(r) if r else '—'}</span>"
                        f"<span style='color:{T.MUTED}'>{' s' if ex.timed and r else ''}</span><br>"
                        f"{icons.img(ex.icon, 15, T.GLOW)}&nbsp; {ex.name}", align=Qt.AlignmentFlag.AlignCenter)
            box.setTextFormat(Qt.TextFormat.RichText)
            box.setStyleSheet("border:1px solid #1c3a70;padding:8px;")
            self.records.addWidget(box, i // 3, i % 3)
        self.quest.refresh()


# =================================================================== MISIÓN
class MisionPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("page")
        self.panel = Panel("OBJETIVO DE HOY", "target")
        self.sub = label("", "muted", align=Qt.AlignmentFlag.AlignCenter)
        self.panel.lay.addWidget(self.sub)
        self.list = QuestList(win, True)
        self.panel.lay.addWidget(self.list)
        self.warning = label("", "warn", wrap=True, align=Qt.AlignmentFlag.AlignCenter)
        self.warning.setTextFormat(Qt.TextFormat.RichText)
        self.panel.lay.addWidget(self.warning)
        self.count = label("", "countdown", align=Qt.AlignmentFlag.AlignCenter)
        self.panel.lay.addWidget(self.count)
        self.water = WaterCard(win)
        self.sleep = SleepCard(win)
        well = QWidget()
        wl = QHBoxLayout(well)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(4)
        wl.addWidget(self.water, 1)
        wl.addWidget(self.sleep, 1)
        self.checkin = Panel("CONTROL SEMANAL", "scan-line")
        self.checkin.set_tone("gold")
        self.checkin.lay.addWidget(label("Hoy te toca: 3 fotos (frente, perfil izquierdo y derecho) y tu peso.",
                                         "muted", wrap=True, align=Qt.AlignmentFlag.AlignCenter))
        crow = QHBoxLayout()
        crow.addStretch()
        crow.addWidget(button("Hacer control", "primary", lambda: (win.show_page("cuerpo"), win.pages["cuerpo"].start_checkin()),
                              icon="camera"))
        crow.addStretch()
        self.checkin.lay.addLayout(crow)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll_page(self.panel, well, self.checkin))
        t = QTimer(self)
        t.timeout.connect(self.tick)
        t.start(1000)

    def refresh(self):
        q = self.win.game.quest
        if not q:
            return
        g = self.win.game
        self.checkin.setVisible(g.checkin_due())
        rest = q.get("rest")
        self.panel.set_title("DÍA DE DESCANSO" if rest else "PENALIZACIÓN: OBJETIVO +30%" if q["penalty"] else "OBJETIVO DE HOY")
        self.panel.title.set_icon("moon" if rest else "triangle-alert" if q["penalty"] else "target")
        self.panel.set_tone("red" if q["penalty"] else "")
        plan = PLANS.get(q.get("plan"), PLANS["principiante"])["label"]
        fat = g.s.get("fatigue", 0.0)
        ftxt = t("bajo") if fat < 0.35 else t("medio") if fat < 0.65 else t("alto")
        self.sub.setText(t("Plan {plan}  ·  Sesión {n}  ·  Cansancio acumulado: {f}", plan=t(plan),
                           n=g.s.get("sessionsDone", 0) + (0 if q["completed"] else 1), f=ftxt))
        self.list.refresh()
        self.water.refresh()
        self.sleep.refresh()
        if rest:
            self.warning.setObjectName("ok")
            self.warning.setText("")
        elif q["completed"]:
            self.warning.setObjectName("ok")
            self.warning.setText(icons.img("circle-check", 18, T.GREEN) + "&nbsp; Objetivo cumplido. Mañana, de nuevo.")
        else:
            self.warning.setObjectName("warn")
            self.warning.setText(icons.img("triangle-alert", 18, T.RED) + "&nbsp; Si no lo cumplís antes de medianoche: pérdida de XP, racha a cero y mañana +30%.")
        restyle(self.warning)
        self.tick()

    def tick(self):
        q = self.win.game.quest
        if not q or q["completed"] or q.get("rest"):
            self.count.setText("")
            return
        now = datetime.now()
        end = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
        s = int((end - now).total_seconds())
        self.count.setText(f"TIEMPO RESTANTE  {s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}")


class WaterCard(Panel):
    """Agua de hoy: progreso hacia la meta y botones rápidos."""

    def __init__(self, win):
        super().__init__(t("AGUA"), "droplet", compact=True)
        self.win = win
        self.big = label("", wrap=True, align=Qt.AlignmentFlag.AlignCenter)
        self.big.setTextFormat(Qt.TextFormat.RichText)
        self.lay.addWidget(self.big)
        self.bar = ThinBar(0, False)
        self.lay.addWidget(self.bar)
        self.sub = label("", "muted", wrap=True, align=Qt.AlignmentFlag.AlignCenter)
        self.lay.addWidget(self.sub)
        row = QHBoxLayout()
        self.b_glass = button("", "primary", lambda: self._add(1), icon="glass-water")
        row.addWidget(self.b_glass, 2)
        row.addWidget(button("−", "", lambda: self._add(-1)), 0)
        self.lay.addLayout(row)

    def _add(self, n):
        ml = int(self.win.game.settings["water"].get("glassMl", 250)) * n
        if n > 0:
            self.win.wellness.drink(ml)
        else:
            self.win.game.add_water(ml)

    def refresh(self):
        g = self.win.game
        goal, have = g.water_goal(), g.water_today()
        k = have / goal if goal else 0
        col = T.GREEN if k >= 1 else T.CYAN
        self.big.setText(f"<span style='font-size:28px;font-weight:700;color:{col}'>{have / 1000:.1f}</span>"
                         f"<span style='color:{T.MUTED}'> / {goal / 1000:.1f} L</span>")
        self.bar.k, self.bar.done = min(1.0, k), k >= 1
        self.bar.update()
        should, _ = g.water_pace()
        if k >= 1:
            self.sub.setText(t("Meta cumplida. Bien hidratado."))
        elif have < should:
            self.sub.setText(t("Vas {n} ml atrasado para esta hora.", n=should - have))
        else:
            self.sub.setText(t("Al día con tu meta."))
        self.b_glass.setText(t("+1 vaso ({ml} ml)", ml=g.settings["water"].get("glassMl", 250)))


class SleepCard(Panel):
    """Sueño: objetivo, última noche, promedio de la semana y registro rápido."""

    def __init__(self, win):
        super().__init__(t("SUEÑO"), "moon", compact=True)
        self.win = win
        self.big = label("", wrap=True, align=Qt.AlignmentFlag.AlignCenter)
        self.big.setTextFormat(Qt.TextFormat.RichText)
        self.lay.addWidget(self.big)
        self.sub = label("", "muted", wrap=True, align=Qt.AlignmentFlag.AlignCenter)
        self.sub.setTextFormat(Qt.TextFormat.RichText)
        self.lay.addWidget(self.sub)
        row = QHBoxLayout()
        self.b_bed = button(t("Me voy a dormir"), "", self._bed, icon="bed")
        row.addWidget(self.b_bed, 1)
        row.addWidget(button(t("Registrar"), "", self._log, icon="moon"), 1)
        self.lay.addLayout(row)

    def _bed(self):
        self.win.wellness.going_to_sleep()
        self.refresh()

    def _log(self):
        g = self.win.game

        def got(i, v):
            if i != 0:
                return
            try:
                h = float(v.replace(",", "."))
                if not 0 < h <= 16:
                    raise ValueError
            except ValueError:
                self.win.toaster.show(t("Escribí las horas, por ejemplo 7.5"))
                return
            g.log_sleep(h, "")
        self.win.dialogs.show(t("¿CUÁNTO DORMISTE?"), t("Horas de sueño de anoche (por ejemplo 7.5)."),
                              ((t("Guardar"), "primary"), (t("Cancelar"), "")), callback=got, with_input=True,
                              placeholder=f"{g.sleep_target_hours():g}", icon="moon")

    def refresh(self):
        g = self.win.game
        st = g.settings["sleep"]
        target = g.sleep_target_hours()
        last = g.s["sleepLog"].get(g.today())
        stats = g.sleep_stats()
        if last:
            col = T.GREEN if last.get("ok") else T.GOLD
            self.big.setText(f"<span style='font-size:28px;font-weight:700;color:{col}'>{last['h']:g} h</span>"
                             f"<span style='color:{T.MUTED}'> / {target:g} h</span>")
        else:
            self.big.setText(f"<span style='font-size:28px;font-weight:700;color:{T.MUTED}'>— h</span>"
                             f"<span style='color:{T.MUTED}'> / {target:g} h</span>")
        lines = [t("Horario: {bed} → {wake}", bed=st.get("bed", "23:30"), wake=st.get("wake", "07:30"))]
        if stats.get("count"):
            lines.append(t("Promedio 7 días: {h} h", h=f"{stats['avg']:g}"))
        if g.suggested_readiness():
            lines.append(f"<span style='color:{T.GOLD}'>" + t("Dormiste poco: hoy la sesión puede ir más tranqui.")
                         + "</span>")
        if g.s["remind"].get("sleepStart"):
            lines.append(f"<span style='color:{T.CYAN}'>" + t("Durmiendo desde las {h}",
                                                                h=g.s["remind"]["sleepStart"][11:16]) + "</span>")
        self.sub.setText("<br>".join(lines))


# =================================================================== REGISTRO
class VolumeChart(QWidget):
    """Barras de repeticiones por día (últimos 30 días)."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(190)
        self.data: list[tuple[str, float, str]] = []  # (etiqueta, valor, estado)

    def set_data(self, data):
        self.data = data
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        top, bottom, left = 18, 26, 36
        mx = max([v for _, v, _ in self.data] + [10])
        p.setFont(QFont(T.FONT, 8))
        for frac in (0, 0.5, 1):
            y = top + (H - top - bottom) * (1 - frac)
            p.setPen(QColor(79, 216, 255, 30))
            p.drawLine(left, int(y), W, int(y))
            p.setPen(QColor(T.MUTED))
            p.drawText(QRectF(0, y - 8, left - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, fmt(mx * frac))
        n = len(self.data) or 1
        bw = (W - left) / n
        for i, (lab, v, st) in enumerate(self.data):
            h = (H - top - bottom) * (v / mx)
            r = QRectF(left + i * bw + bw * 0.18, H - bottom - h, bw * 0.64, h)
            col = {"ok": T.GREEN, "fail": T.RED, "rest": T.MUTED}.get(st, T.GLOW)
            c = QColor(col)
            c.setAlpha(60)
            p.fillRect(r.adjusted(-2, -2, 2, 0), c)
            c.setAlpha(220)
            p.fillRect(r, c)
            if i % 5 == 4 or i == n - 1:
                p.setPen(QColor(T.MUTED))
                p.drawText(QRectF(left + i * bw - 10, H - bottom + 4, bw + 20, 16), Qt.AlignmentFlag.AlignCenter, lab)


class RegistroPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("page")
        summ = Panel("RESUMEN", "activity")
        self.summary = QGridLayout()
        self.summary.setSpacing(8)
        summ.lay.addLayout(self.summary)
        vol = Panel("VOLUMEN DIARIO · 30 DÍAS", "chart-column")
        self.chart = VolumeChart()
        vol.lay.addWidget(self.chart)
        vol.lay.addWidget(label("Repeticiones totales por día (la plancha cuenta 1 por cada 5 s). "
                                "Verde: objetivo cumplido · Rojo: no cumplido · Gris: descanso.", "muted", wrap=True))
        heat = Panel("ÚLTIMOS 28 DÍAS", "calendar-days")
        self.heat = QGridLayout()
        self.heat.setSpacing(6)
        heat.lay.addLayout(self.heat)
        tot = Panel("TOTALES", "dumbbell")
        self.totals = QGridLayout()
        self.totals.setSpacing(8)
        tot.lay.addLayout(self.totals)
        ach = Panel("LOGROS", "trophy")
        self.ach = QGridLayout()
        self.ach.setSpacing(8)
        ach.lay.addLayout(self.ach)
        log = Panel("HISTORIAL", "terminal")
        self.log = QListWidget()
        self.log.setMinimumHeight(240)
        log.lay.addWidget(self.log)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll_page(summ, vol, heat, tot, ach, log))

    def _day_volume(self, k):
        d = self.win.game.s["daily"].get(k, {})
        return sum(v for e, v in d.items() if e != "plank") + d.get("plank", 0) / 5

    def _day_state(self, k, today):
        g = self.win.game
        h = g.quest if k == today else g.s["history"].get(k)
        if not h:
            return ""
        if h.get("rest"):
            return "rest"
        if h.get("completed"):
            return "ok"
        return "" if k == today else "fail"

    def refresh(self):
        g = self.win.game
        s = g.s
        today = g.today()
        t0 = date.fromisoformat(today)
        days = [(t0 - timedelta(days=29 - i)) for i in range(30)]
        self.chart.set_data([(f"{d.day}/{d.month}", self._day_volume(d.isoformat()), self._day_state(d.isoformat(), today))
                             for d in days])
        week = sum(self._day_volume((t0 - timedelta(days=i)).isoformat()) for i in range(7))
        prev = sum(self._day_volume((t0 - timedelta(days=i)).isoformat()) for i in range(7, 14))
        delta = ("—" if not prev else f"{'+' if week >= prev else ''}{round((week - prev) / prev * 100)}%")
        adh = g.adherence()
        cumplidos = sum(1 for d in days if self._day_state(d.isoformat(), today) == "ok")
        clear_layout(self.summary)
        items = [("Constancia 30 días", "—" if adh is None else f"{adh}%"),
                 ("Días cumplidos (30 d)", str(cumplidos)),
                 ("Volumen últimos 7 días", fmt(week)),
                 ("vs. semana anterior", delta),
                 ("Racha actual", str(s["streak"])),
                 ("Mejor racha", str(s["bestStreak"])),
                 ("Progresión de objetivos", f"+{round((s['progression'] - 1) * 100)}%"),
                 ("Nivel / Rango", f"{s['player']['level']} / {rank_of(s['player']['level'])}")]
        for i, (name, val) in enumerate(items):
            box = label(f"<span style='font-size:22px;font-weight:700;color:white'>{val}</span><br>"
                        f"<span style='color:{T.MUTED}'>{name}</span>", align=Qt.AlignmentFlag.AlignCenter)
            box.setTextFormat(Qt.TextFormat.RichText)
            box.setStyleSheet("border:1px solid #1c3a70;padding:10px;")
            self.summary.addWidget(box, i // 4, i % 4)
        clear_layout(self.heat)
        for i in range(28):
            d = (date.fromisoformat(today) - timedelta(days=27 - i))
            k = d.isoformat()
            h = g.quest if k == today else s["history"].get(k)
            c = label(str(d.day), align=Qt.AlignmentFlag.AlignCenter)
            c.setMinimumHeight(40)
            if h and h.get("rest"):
                st = f"background:rgba(127,149,191,0.12);border:1px solid #33456b;color:{T.MUTED};"
            elif h and h.get("completed"):
                st = f"background:rgba(61,255,168,0.3);border:1px solid {T.GREEN};color:white;"
            elif h and k != today:
                st = f"background:rgba(255,59,92,0.2);border:1px solid {T.RED};color:{T.MUTED};"
            else:
                st = f"border:1px solid #1c3a70;color:{T.MUTED};"
            if k == today:
                st += f"border:2px solid {T.GLOW};"
            c.setStyleSheet(st)
            c.setToolTip(k)
            self.heat.addWidget(c, i // 7, i % 7)

        clear_layout(self.totals)
        items = [(icons.img(EXERCISES[e].icon, 16, T.GLOW) + "&nbsp; " + EXERCISES[e].name + (" (seg)" if EXERCISES[e].timed else ""), s["totals"].get(e, 0))
                 for e in EXERCISE_ORDER] + [(icons.img("trophy", 16, T.GOLD) + "&nbsp; Misiones cumplidas", s["questsDone"])]
        for i, (name, val) in enumerate(items):
            box = label(f"<span style='font-size:24px;font-weight:700;color:white'>{fmt(val)}</span><br>{name}",
                        align=Qt.AlignmentFlag.AlignCenter)
            box.setTextFormat(Qt.TextFormat.RichText)
            box.setStyleSheet("border:1px solid #1c3a70;padding:10px;")
            self.totals.addWidget(box, i // 4, i % 4)

        clear_layout(self.ach)
        for i, (aid, title, desc, _) in enumerate(ACHIEVEMENTS):
            on = aid in s["achievements"]
            box = label(f"{icons.img('award' if on else 'lock', 16, T.GOLD if on else T.MUTED)}&nbsp; <b style='color:{T.GOLD if on else T.MUTED}'>{escape(title)}</b><br>"
                        f"<span style='color:{T.MUTED}'>{escape(desc)}</span>", wrap=True)
            box.setTextFormat(Qt.TextFormat.RichText)
            box.setStyleSheet(f"border:1px solid {T.GOLD if on else '#1c3a70'};padding:8px;")
            self.ach.addWidget(box, i // 3, i % 3)

        self.log.clear()
        for entry in s["log"][:80]:
            t = datetime.fromtimestamp(entry["t"]).strftime("%d/%m %H:%M")
            self.log.addItem(f"{t}   {entry['msg']}")
        if not s["log"]:
            self.log.addItem("Sin mensajes todavía.")


# =================================================================== AJUSTES
class AjustesPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("page")
        self._loading = False

        plan = Panel("PLAN DE ENTRENAMIENTO", "target")
        pf = QFormLayout()
        pf.setVerticalSpacing(12)
        pf.setHorizontalSpacing(24)
        self.plan = QComboBox()
        for k in PLAN_ORDER:
            self.plan.addItem(f"{t(PLANS[k]['label'])} — {t(PLANS[k]['desc'])}")
        self.plan.currentIndexChanged.connect(lambda i: not self._loading and self.win.game.set_plan(PLAN_ORDER[i]))
        pf.addRow(t("Nivel de partida"), self.plan)
        plan.lay.addLayout(pf)
        plan.lay.addWidget(label(t("La progresión es automática: cada ejercicio sube repeticiones, series o peso cuando "
                                   "lo hacés bien y sin demasiado esfuerzo, y baja si venís fallando. Si cambiás el "
                                   "nivel, se recalculan los ejercicios que todavía no hiciste."), "muted", wrap=True))
        plan.lay.addWidget(label(t("Equipamiento que tenés:"), "lbl"))
        eq = QHBoxLayout()
        self.eq_cbs = {}
        for key, txt in (("bar", t("Barra de dominadas")), ("dumbbell", t("Mancuernas"))):
            cb = QCheckBox(txt)
            cb.toggled.connect(lambda _=False: self.save_equipment())
            self.eq_cbs[key] = cb
            eq.addWidget(cb)
        self.adj_kg = QCheckBox(t("Mancuernas ajustables (la progresión puede subir el peso)"))
        self.adj_kg.toggled.connect(lambda on: self.set_setting("adjustableKg", on))
        eq.addWidget(self.adj_kg)
        eq.addStretch()
        plan.lay.addLayout(eq)
        self.prog_lbl = label("", "muted", wrap=True)
        self.prog_lbl.setTextFormat(Qt.TextFormat.RichText)
        plan.lay.addWidget(self.prog_lbl)
        plan.lay.addWidget(label(t("Días de descanso fijos (además, el sistema programa descansos si acumulás cansancio):"),
                                 "lbl", wrap=True))
        rd = QHBoxLayout()
        self.rest_cbs = []
        for i, d in enumerate(WEEKDAYS):
            cb = QCheckBox(d[:3])
            cb.toggled.connect(lambda _=False: self.save_rest())
            self.rest_cbs.append(cb)
            rd.addWidget(cb)
        rd.addStretch()
        plan.lay.addLayout(rd)

        cuerpo = Panel("CONTROL CORPORAL", "scan-line")
        cf = QFormLayout()
        cf.setVerticalSpacing(10)
        self.height_cm = QSpinBox()
        self.height_cm.setRange(0, 230)
        self.height_cm.setSuffix(" cm")
        self.height_cm.setSpecialValueText("sin definir")
        self.height_cm.valueChanged.connect(lambda v: self._set_profile("heightCm", v))
        self.sex = QComboBox()
        self.sex.addItems(["Sin definir", "Hombre", "Mujer"])
        self.sex.currentIndexChanged.connect(lambda i: self._set_profile("sex", ["", "m", "f"][i]))
        self.ck_day = QComboBox()
        self.ck_day.addItems(WEEKDAYS)
        self.ck_day.currentIndexChanged.connect(lambda i: self.set_setting("checkinDay", i))
        cf.addRow("Altura", self.height_cm)
        cf.addRow("Sexo (para la fórmula de grasa)", self.sex)
        cf.addRow("Día del control semanal", self.ck_day)
        cuerpo.lay.addLayout(cf)
        cuerpo.lay.addWidget(label("Las fotos se guardan solo en tu compu, en la carpeta de datos (ver abajo), subcarpeta \"fotos\".",
                                   "muted", wrap=True))
        self.cuerpo_panel = cuerpo

        jug = Panel("PERFIL Y CÁMARA", "user-round")
        f = QFormLayout()
        f.setVerticalSpacing(12)
        f.setHorizontalSpacing(24)
        from PySide6.QtWidgets import QLineEdit
        self.name = QLineEdit()
        self.name.setMaxLength(24)
        self.name.editingFinished.connect(self.save_name)
        f.addRow(t("Nombre"), self.name)
        from ..i18n import LANGS
        self.lang = QComboBox()
        self.lang_keys = list(LANGS)
        self.lang.addItems([LANGS[k] for k in self.lang_keys])
        self.lang.currentIndexChanged.connect(self.set_lang)
        f.addRow(t("Idioma"), self.lang)
        self.camera = QComboBox()
        self.camera.currentIndexChanged.connect(lambda i: i >= 0 and self.set_setting("camera", i))
        f.addRow(t("Cámara"), self.camera)
        jug.lay.addLayout(f)
        self.voice = QCheckBox("Voz que cuenta las repeticiones y te corrige")
        self.sound = QCheckBox("Efectos de sonido")
        self.mirror = QCheckBox("Cámara en modo espejo")
        for cb, key in ((self.voice, "voice"), (self.sound, "sound"), (self.mirror, "mirror")):
            cb.toggled.connect(lambda on, key=key: self.set_setting(key, on))
            jug.lay.addWidget(cb)

        guard = Panel("RECORDATORIOS", "bell-ring")
        guard.lay.addWidget(label("Mientras Arise Trainer esté abierto (aunque sea minimizado al lado del reloj), "
                                  "te muestra una alerta encima de todo hasta que cumplas el objetivo del día.",
                                  "muted", wrap=True))
        self.nag = QCheckBox("Activado")
        self.nag.toggled.connect(lambda on: self.set_nag("enabled", on))
        guard.lay.addWidget(self.nag)
        gf = QFormLayout()
        gf.setVerticalSpacing(10)
        self.hour = QSpinBox()
        self.hour.setRange(0, 23)
        self.hour.setSuffix(" hs")
        self.every = QSpinBox()
        self.every.setRange(5, 120)
        self.every.setSuffix(" min")
        self.snooze = QSpinBox()
        self.snooze.setRange(0, 10)
        for sp, key in ((self.hour, "startHour"), (self.every, "intervalMin"), (self.snooze, "snoozesPerDay")):
            sp.valueChanged.connect(lambda v, key=key: self.set_nag(key, v))
        gf.addRow("Empieza a molestar desde las", self.hour)
        gf.addRow("Repetir cada", self.every)
        gf.addRow("Posposiciones por día", self.snooze)
        guard.lay.addLayout(gf)
        self.hard = QCheckBox("Modo estricto: la alerta cubre todas las pantallas y no se puede cerrar")
        self.hard.toggled.connect(self.toggle_hard)
        guard.lay.addWidget(self.hard)
        self.auto = QCheckBox("Abrir Arise Trainer automáticamente al prender la compu")
        self.auto.toggled.connect(self.toggle_auto)
        guard.lay.addWidget(self.auto)
        guard.lay.addWidget(button("Probar alerta ahora", "", lambda: self.win.guardian.show(test=True), icon="bell-ring"))

        well = Panel(t("AGUA Y SUEÑO"), "droplet")
        well.lay.addWidget(label(t("Te ayudan a sostener el hábito: avisan, pero no te sacan XP ni rachas."), "muted",
                                 wrap=True))
        wf = QFormLayout()
        wf.setVerticalSpacing(10)
        wf.setHorizontalSpacing(24)
        self.w_on = QCheckBox(t("Recordatorios de agua"))
        self.w_on.toggled.connect(lambda on: self.set_sub("water", "enabled", on))
        wf.addRow(self.w_on)
        self.w_goal = QSpinBox()
        self.w_goal.setRange(0, 6000)
        self.w_goal.setSingleStep(250)
        self.w_goal.setSuffix(" ml")
        self.w_goal.setSpecialValueText(t("automática (según tu peso)"))
        self.w_goal.valueChanged.connect(lambda v: self.set_sub("water", "goalMl", v))
        wf.addRow(t("Meta diaria"), self.w_goal)
        self.w_glass = QSpinBox()
        self.w_glass.setRange(100, 1000)
        self.w_glass.setSingleStep(50)
        self.w_glass.setSuffix(" ml")
        self.w_glass.valueChanged.connect(lambda v: self.set_sub("water", "glassMl", v))
        wf.addRow(t("Tamaño del vaso"), self.w_glass)
        self.w_every = QSpinBox()
        self.w_every.setRange(20, 240)
        self.w_every.setSingleStep(10)
        self.w_every.setSuffix(" min")
        self.w_every.valueChanged.connect(lambda v: self.set_sub("water", "everyMin", v))
        wf.addRow(t("Si vas atrasado, avisar cada"), self.w_every)
        hrs = QHBoxLayout()
        self.w_start, self.w_end = QSpinBox(), QSpinBox()
        for sp, key in ((self.w_start, "start"), (self.w_end, "end")):
            sp.setRange(0, 23)
            sp.setSuffix(" hs")
            sp.valueChanged.connect(lambda v, key=key: self.set_sub("water", key, v))
        hrs.addWidget(self.w_start)
        hrs.addWidget(label("→"))
        hrs.addWidget(self.w_end)
        hrs.addStretch()
        wf.addRow(t("Horario de avisos"), hrs)
        self.s_on = QCheckBox(t("Seguimiento del sueño"))
        self.s_on.toggled.connect(lambda on: self.set_sub("sleep", "enabled", on))
        wf.addRow(self.s_on)
        from PySide6.QtWidgets import QTimeEdit
        from PySide6.QtCore import QTime
        self._QTime = QTime
        self.s_bed, self.s_wake = QTimeEdit(), QTimeEdit()
        for te, key in ((self.s_bed, "bed"), (self.s_wake, "wake")):
            te.setDisplayFormat("HH:mm")
            te.timeChanged.connect(lambda v, key=key: self.set_sub("sleep", key, v.toString("HH:mm")))
        wf.addRow(t("Hora de dormir"), self.s_bed)
        wf.addRow(t("Hora de despertar"), self.s_wake)
        self.s_rem = QCheckBox(t("Avisarme antes de la hora de dormir"))
        self.s_rem.toggled.connect(lambda on: self.set_sub("sleep", "remind", on))
        wf.addRow(self.s_rem)
        well.lay.addLayout(wf)

        sist = Panel("SISTEMA", "settings")
        sf = QFormLayout()
        sf.setVerticalSpacing(12)
        sf.setHorizontalSpacing(24)
        self.quality = QComboBox()
        self.quality.addItems(["Alto (todos los efectos, 40 fps)", "Medio (menos humo y partículas)",
                               "Bajo (sin animaciones, para compus lentas)"])
        self.quality.currentIndexChanged.connect(lambda i: self.set_setting("quality", ["alto", "medio", "bajo"][i]))
        sf.addRow("Calidad de efectos", self.quality)
        from PySide6.QtWidgets import QSlider
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.valueChanged.connect(lambda v: self.set_setting("volume", v))
        self.volume.sliderReleased.connect(lambda: self.win.sounds.play("notify"))
        sf.addRow("Volumen de efectos", self.volume)
        sist.lay.addLayout(sf)
        from .._version import VERSION
        self.version_lbl = label(f"Versión instalada: {VERSION}", "muted")
        sist.lay.addWidget(self.version_lbl)
        self.auto_upd = QCheckBox("Actualizar automáticamente en segundo plano (busca cada 3 horas e instala cuando no la usás)")
        self.auto_upd.toggled.connect(lambda on: self.set_setting("autoUpdate", on))
        sist.lay.addWidget(self.auto_upd)
        urow = QHBoxLayout()
        urow.addWidget(button("Buscar actualizaciones", "primary", lambda: self.win.check_updates(True), icon="download"))
        urow.addWidget(button("Probar notificación", "", lambda: self.win.notifier.show(
            "NOTIFICACIÓN", "Así se ven los avisos del Sistema en tu escritorio.", "bell-ring", "",
            actions=[("Genial", lambda: None)]), icon="bell-ring"))
        urow.addStretch()
        sist.lay.addLayout(urow)

        datos = Panel("DATOS", "download")
        row = QHBoxLayout()
        row.addWidget(button("Exportar progreso", "", self.export, icon="download"))
        row.addWidget(button("Importar", "", self.import_, icon="upload"))
        row.addWidget(button("Reiniciar todo", "danger", self.reset, icon="trash-2"))
        datos.lay.addLayout(row)
        self.path = label("", "muted", wrap=True)
        self.path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        datos.lay.addWidget(self.path)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll_page(plan, jug, well, guard, cuerpo, sist, datos))

    def refresh(self):
        self._loading = True
        s = self.win.game.s
        st = s["settings"]
        self.name.setText(s["player"]["name"])
        self.plan.setCurrentIndex(PLAN_ORDER.index(st["plan"]) if st["plan"] in PLAN_ORDER else 0)
        for k, cb in self.eq_cbs.items():
            cb.setChecked(k in st.get("equipment", []))
        self.adj_kg.setChecked(st.get("adjustableKg", True))
        self.adj_kg.setVisible("dumbbell" in st.get("equipment", []))
        done = [(k, p) for k, p in s.get("prog", {}).items() if p.get("hist") and k in EXERCISES]
        if done:
            self.prog_lbl.setText(t("Tu progresión actual") + ":<br>" + "  ·  ".join(
                f"{t(EXERCISES[k].name)} <b style='color:white'>{p['sets']}×{p['reps']}"
                f"{' s' if EXERCISES[k].timed else ''}{(' ' + format(p['kg'], 'g') + ' kg') if p.get('kg') else ''}</b>"
                for k, p in done))
        else:
            self.prog_lbl.setText("")
        from ..i18n import LANGS
        cur = st.get("lang") or "es"
        self.lang.setCurrentIndex(self.lang_keys.index(cur) if cur in self.lang_keys else 0)
        from ..camera import list_cameras
        self.camera.clear()
        self.camera.addItems(list_cameras())
        self.camera.setCurrentIndex(min(st.get("camera", 0), self.camera.count() - 1))
        w, sl = st["water"], st["sleep"]
        self.w_on.setChecked(w.get("enabled", True))
        self.w_goal.setValue(int(w.get("goalMl", 0)))
        self.w_glass.setValue(int(w.get("glassMl", 250)))
        self.w_every.setValue(int(w.get("everyMin", 90)))
        self.w_start.setValue(int(w.get("start", 9)))
        self.w_end.setValue(int(w.get("end", 22)))
        self.s_on.setChecked(sl.get("enabled", True))
        self.s_bed.setTime(self._QTime.fromString(sl.get("bed", "23:30"), "HH:mm"))
        self.s_wake.setTime(self._QTime.fromString(sl.get("wake", "07:30"), "HH:mm"))
        self.s_rem.setChecked(sl.get("remind", True))
        for i, cb in enumerate(self.rest_cbs):
            cb.setChecked(i in st.get("restDays", []))
        prof = s.get("profile", {})
        self.height_cm.setValue(int(prof.get("heightCm") or 0))
        self.sex.setCurrentIndex({"m": 1, "f": 2}.get(prof.get("sex"), 0))
        self.ck_day.setCurrentIndex(st.get("checkinDay", 0))
        self.quality.setCurrentIndex(["alto", "medio", "bajo"].index(st.get("quality", "alto")))
        self.volume.setValue(int(st.get("volume", 70)))
        self.auto_upd.setChecked(st.get("autoUpdate", True))
        self.voice.setChecked(st["voice"])
        self.sound.setChecked(st["sound"])
        self.mirror.setChecked(st.get("mirror", True))
        n = st["nag"]
        self.nag.setChecked(n["enabled"])
        self.hour.setValue(int(n["startHour"]))
        self.every.setValue(int(n["intervalMin"]))
        self.snooze.setValue(int(n["snoozesPerDay"]))
        self.hard.setChecked(bool(n["hard"]))
        self.auto.setEnabled(storage.autostart_supported())
        self.auto.setChecked(storage.autostart_enabled())
        self.path.setText(f"Tus datos se guardan en: {self.win.game.store.path}")
        self._loading = False

    def _set_profile(self, key, val):
        if self._loading:
            return
        self.win.game.s["profile"][key] = val
        self.win.game.save()

    def save_rest(self):
        if self._loading:
            return
        self.win.game.set_rest_days([i for i, cb in enumerate(self.rest_cbs) if cb.isChecked()])

    def save_equipment(self):
        if self._loading:
            return
        g = self.win.game
        g.settings["equipment"] = [k for k, cb in self.eq_cbs.items() if cb.isChecked()]
        self.adj_kg.setVisible("dumbbell" in g.settings["equipment"])
        if g._untouched():  # la sesión de hoy incluye los ejercicios nuevos si todavía no empezaste
            g.new_quest(g.quest["date"], g.quest["penalty"])
        g.save()
        self.win.refresh()

    def set_sub(self, group, key, val):
        if self._loading:
            return
        self.win.game.s["settings"][group][key] = val
        self.win.game.save()
        self.win.refresh()

    def set_lang(self, i):
        if self._loading or i < 0:
            return
        code = self.lang_keys[i]
        self.win.game.s["settings"]["lang"] = code
        self.win.game.save()
        from ..i18n import set_lang
        set_lang(code)
        self.win.dialogs.show(t("IDIOMA"), t("El idioma se aplica al reiniciar Arise Trainer."),
                              ((t("Reiniciar ahora"), "primary"), (t("Después"), "")),
                              callback=lambda j, _: j == 0 and self.win.restart_app())

    def save_name(self):
        if self.name.text().strip():
            self.win.game.player["name"] = self.name.text().strip()
            self.win.game.save()
            self.win.refresh()

    def set_setting(self, key, val):
        if self._loading:
            return
        self.win.game.s["settings"][key] = val
        self.win.apply_settings()
        self.win.game.save()

    def set_nag(self, key, val):
        if self._loading:
            return
        self.win.game.s["settings"]["nag"][key] = val
        self.win.game.save()

    def toggle_hard(self, on):
        if self._loading:
            return
        if not on:
            self.set_nag("hard", False)
            return

        def answer(i, _):
            if i == 0:
                self.set_nag("hard", True)
            else:
                self._loading = True
                self.hard.setChecked(False)
                self._loading = False
        self.win.dialogs.show("CONFIRMAR",
                              "En modo estricto la alerta cubre <b>todas tus pantallas</b> y no se puede cerrar "
                              "hasta que vayas a entrenar, uses una posposición o escribas la frase de rendición.<br><br>¿Aceptás?",
                              (("Acepto", "danger"), ("Mejor no", "")), tone="red", callback=answer)

    def toggle_auto(self, on):
        if not self._loading and not storage.set_autostart(on):
            self.win.toaster.show("No pude cambiar el inicio automático")

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar progreso", f"arise-trainer-{date.today()}.json", "JSON (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.win.game.export(), f, ensure_ascii=False, indent=1)
            self.win.toaster.show("Progreso exportado")

    def import_(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importar progreso", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                self.win.game.import_state(json.load(f))
            self.win.toaster.show("Progreso importado")
            self.refresh()
        except Exception as e:
            self.win.toaster.show(f"No se pudo importar: {e}")

    def reset(self):
        def answer(i, val):
            if i == 0 and val.strip().upper() == "BORRAR":
                self.win.game.reset()
                self.win.start_onboarding()
        self.win.dialogs.show("REINICIAR", "Vas a borrar TODO tu progreso.<br>Escribí <b>BORRAR</b> para confirmar.",
                              (("Borrar todo", "danger"), ("Cancelar", "")), tone="red", callback=answer,
                              with_input=True, placeholder="BORRAR")
