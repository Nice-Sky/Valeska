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
from ..game import ACHIEVEMENTS, DIFF_ORDER, DIFFICULTY, STATS, fmt, rank_of, xp_needed
from . import theme as T
from . import holo, icons
from .video import VideoView
from .widgets import Panel, RankBadge, button, icon_label, label, restyle


def scroll_page(*widgets) -> QScrollArea:
    inner = QWidget()
    inner.setObjectName("page")
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(4, 4, 14, 20)
    lay.setSpacing(16)
    for w in widgets:
        lay.addWidget(w)
    lay.addStretch()
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setWidget(inner)
    return sa


def clear_layout(lay):
    while lay.count():
        it = lay.takeAt(0)
        if it.widget():
            it.widget().deleteLater()
        elif it.layout():
            clear_layout(it.layout())


class QuestList(QWidget):
    """Lista de objetivos de la misión con barras de progreso."""

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
            bar = QProgressBar()
            bar.setObjectName("thin")
            bar.setFixedHeight(6)
            bar.setTextVisible(False)
            bar.setRange(0, t)
            bar.setValue(int(v))
            bar.setProperty("done", done)
            self.lay.addWidget(bar)
            self.lay.addSpacing(6)


class ExCard(QPushButton):
    """Tarjeta de ejercicio holográfica con ícono grande."""

    def __init__(self, icon_name, title, sub, done=False):
        super().__init__()
        self.icon_name, self.title_text, self.sub, self.done = icon_name, title, sub, done
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(140)
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self.hover = False

    def enterEvent(self, e):
        self.hover = True
        self.update()

    def leaveEvent(self, e):
        self.hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        tone = "gold" if self.done else ""
        holo.holo_frame(p, QRectF(self.rect()).adjusted(4, 4, -4, -4), tone, sum(map(ord, self.title_text)), cut=8,
                        strong=self.hover, brackets=self.hover)
        color, core = holo.palette(tone)
        s = 38
        r = QRectF((self.width() - s) / 2, 22, s, s)
        p.setOpacity(0.5 if self.hover else 0.3)
        icons.paint(p, self.icon_name, r, color, 4.5)
        p.setOpacity(1)
        icons.paint(p, self.icon_name, r, core, 1.6)
        f = QFont(T.FONT, 13)
        f.setBold(True)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        p.setFont(f)
        p.setPen(QColor(core))
        p.drawText(QRectF(0, 68, self.width(), 26), Qt.AlignmentFlag.AlignCenter, self.title_text.upper())
        p.setFont(QFont(T.FONT, 10))
        p.setPen(QColor(T.GOLD if self.done else T.MUTED))
        p.drawText(QRectF(0, 96, self.width(), 22), Qt.AlignmentFlag.AlignCenter, self.sub)


# =================================================================== ESTADO
class EstadoPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("page")
        status = Panel("ESTADO", "user-round")
        head = QHBoxLayout()
        self.badge = RankBadge(104)
        head.addWidget(self.badge)
        head.addSpacing(14)
        info = QFormLayout()
        info.setHorizontalSpacing(30)
        info.setVerticalSpacing(8)
        self.name, self.level, self.title, self.streak = (label() for _ in range(4))
        self.level.setObjectName("big")
        for txt, w in (("NOMBRE", self.name), ("NIVEL", self.level), ("TÍTULO", self.title), ("RACHA", self.streak)):
            info.addRow(label(txt, "lbl"), w)
        head.addLayout(info, 1)
        status.lay.addLayout(head)
        self.xp = QProgressBar()
        self.xp.setMinimumHeight(24)
        status.lay.addWidget(self.xp)
        self.stats = QGridLayout()
        self.stats.setSpacing(10)
        status.lay.addLayout(self.stats)
        self.points = label("", "gold", align=Qt.AlignmentFlag.AlignCenter)
        status.lay.addWidget(self.points)

        quest = Panel("MISIÓN DIARIA", "scroll-text")
        self.quest = QuestList(win, False)
        quest.lay.addWidget(self.quest)
        quest.lay.addWidget(button("Ver misión", "primary", lambda: win.go("mision"), icon="scroll-text"))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll_page(status, quest))

    def refresh(self):
        g = self.win.game
        p = g.player
        self.badge.set_rank(rank_of(p["level"]))
        self.name.setText(p["name"])
        self.level.setText(str(p["level"]))
        self.title.setText(g.current_title())
        self.streak.setText(f"{g.s['streak']} día{'s' if g.s['streak'] != 1 else ''}  (máx {g.s['bestStreak']})")
        need = xp_needed(p["level"])
        self.xp.setRange(0, need)
        self.xp.setValue(int(p["xp"]))
        self.xp.setFormat(f"XP  {fmt(p['xp'])} / {fmt(need)}")
        clear_layout(self.stats)
        for i, (k, (name, _)) in enumerate(STATS.items()):
            card = Panel(compact=True)
            row = QHBoxLayout()
            col = QVBoxLayout()
            t = label(k)
            t.setStyleSheet(f"color:{T.GLOW};font-size:15px;font-weight:700;")
            col.addWidget(t)
            col.addWidget(label(name, "lbl"))
            row.addLayout(col)
            row.addStretch()
            v = label(str(g.stat_value(k)))
            v.setStyleSheet("font-size:26px;font-weight:700;color:white;")
            row.addWidget(v)
            if p["freePoints"] > 0:
                b = button("+", "primary", lambda _=False, k=k: self.win.game.allocate(k))
                b.setFixedSize(34, 34)
                row.addWidget(b)
            card.lay.addLayout(row)
            self.stats.addWidget(card, i // 2, i % 2)
        self.points.setText(f"Puntos disponibles: {p['freePoints']}" if p["freePoints"] else "")
        self.quest.refresh()


# =================================================================== MISIÓN
class MisionPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("page")
        self.panel = Panel("MISIÓN DIARIA", "scroll-text")
        self.sub = label("", "muted", align=Qt.AlignmentFlag.AlignCenter)
        self.panel.lay.addWidget(self.sub)
        self.list = QuestList(win, True)
        self.panel.lay.addWidget(self.list)
        self.warning = label("", "warn", wrap=True, align=Qt.AlignmentFlag.AlignCenter)
        self.warning.setTextFormat(Qt.TextFormat.RichText)
        self.panel.lay.addWidget(self.warning)
        self.count = label("", "countdown", align=Qt.AlignmentFlag.AlignCenter)
        self.panel.lay.addWidget(self.count)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll_page(self.panel))
        t = QTimer(self)
        t.timeout.connect(self.tick)
        t.start(1000)

    def refresh(self):
        q = self.win.game.quest
        if not q:
            return
        self.panel.set_title("MISIÓN DE PENALIZACIÓN" if q["penalty"] else "MISIÓN DIARIA")
        self.panel.title.set_icon("skull" if q["penalty"] else "scroll-text")
        self.panel.set_tone("red" if q["penalty"] else "")
        diff = DIFFICULTY.get(q["difficulty"], DIFFICULTY["facil"])["label"]
        self.sub.setText(f"Dificultad: {diff}" + ("  ·  +50% por fallar" if q["penalty"] else ""))
        self.list.refresh()
        if q["completed"]:
            self.warning.setObjectName("ok")
            self.warning.setText(icons.img("circle-check", 18, T.GREEN) + "&nbsp; MISIÓN COMPLETADA. Descansá, cazador.")
        else:
            self.warning.setObjectName("warn")
            self.warning.setText(icons.img("triangle-alert", 18, T.RED) + "&nbsp; ADVERTENCIA: si no completás la misión antes de medianoche recibirás una penalización.")
        restyle(self.warning)
        self.tick()

    def tick(self):
        q = self.win.game.quest
        if not q or q["completed"]:
            self.count.setText("")
            return
        now = datetime.now()
        end = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
        s = int((end - now).total_seconds())
        self.count.setText(f"TIEMPO RESTANTE  {s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}")


# =================================================================== ENTRENAR
class EntrenarPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("page")
        self.worker: CameraWorker | None = None
        self.ex = None
        self.counter = None
        self.state = "idle"
        self.good = 0
        self.bad = 0
        self.xp = 0.0
        self.visible_since = None
        self.countdown_end = 0.0
        self.last_center = ""

        self.stack = QStackedWidget()
        # --- selector
        picker = Panel("ELEGÍ EL EJERCICIO", "dumbbell")
        self.grid = QGridLayout()
        self.grid.setSpacing(12)
        picker.lay.addLayout(self.grid)
        picker.lay.addWidget(label("Consejo: para que la IA te vea bien, dejá todo tu cuerpo dentro de la imagen y buena luz.",
                                   "muted", wrap=True, align=Qt.AlignmentFlag.AlignCenter))
        self.stack.addWidget(scroll_page(picker))

        # --- entrenamiento
        train = Panel("ENTRENAMIENTO", "dumbbell")
        self.train_panel = train
        self.tip = label("", "muted", wrap=True, align=Qt.AlignmentFlag.AlignCenter)
        train.lay.addWidget(self.tip)
        self.video = VideoView()
        train.lay.addWidget(self.video, 1)
        ctr = QHBoxLayout()
        self.cam_combo = QComboBox()
        self.cam_combo.setMinimumWidth(220)
        ctr.addWidget(self.cam_combo, 1)
        self.btn_cam = button("Encender cámara", "primary", self.toggle_camera, icon="camera")
        ctr.addWidget(self.btn_cam)
        train.lay.addLayout(ctr)
        man = QHBoxLayout()
        man.addStretch()
        man.addWidget(label("Sin cámara (modo honor, 70% XP):", "lbl"))
        self.manual_btns = []
        for n in (1, 5, 10):
            b = button(f"+{n}", "", lambda _=False, n=n: self.manual(n))
            self.manual_btns.append(b)
            man.addWidget(b)
        man.addStretch()
        train.lay.addLayout(man)
        stats = QHBoxLayout()
        self.lbl_good, self.lbl_bad, self.lbl_xp = label(), label(), label()
        for w in (self.lbl_good, self.lbl_bad, self.lbl_xp):
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            w.setTextFormat(Qt.TextFormat.RichText)
            stats.addWidget(w, 1)
        train.lay.addLayout(stats)
        train.lay.addWidget(button("Terminar serie", "danger", self.finish, icon="flag"))
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(4, 4, 14, 8)
        wl.addWidget(train)
        self.stack.addWidget(wrap)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stack)

    # ---------------------------------------------------------------- vistas
    def refresh(self):
        if self.ex is not None:
            self.update_stats()
            return
        clear_layout(self.grid)
        q = self.win.game.quest
        for i, k in enumerate(EXERCISE_ORDER):
            ex = EXERCISES[k]
            if q and k in q["targets"]:
                t = q["targets"][k]
                sub = f"Misión {min(q['progress'].get(k, 0), t):g}/{t}"
            else:
                sub = "Libre"
            b = ExCard(ex.icon, ex.name, f"{sub}  ·  {ex.stat}", done=bool(q and k in q["targets"] and q["progress"].get(k, 0) >= q["targets"][k]))
            b.clicked.connect(lambda _=False, k=k: self.open(k))
            self.grid.addWidget(b, i // 3, i % 3)

    def open(self, k: str):
        self.ex = EXERCISES[k]
        self.counter = RepCounter(self.ex)
        self.good = self.bad = 0
        self.xp = 0.0
        self.train_panel.set_title(self.ex.name.upper())
        self.train_panel.title.set_icon(self.ex.icon)
        self.tip.setText(self.ex.tip)
        for b, n in zip(self.manual_btns, (1, 5, 10)):
            b.setText(f"+{n}{' s' if self.ex.timed else ''}")
        self.video.count = "0"
        self.video.progress = 0
        self.cam_combo.clear()
        self.cam_combo.addItems(list_cameras())
        idx = self.win.game.s["settings"].get("camera", 0)
        if idx < self.cam_combo.count():
            self.cam_combo.setCurrentIndex(idx)
        self.stack.setCurrentIndex(1)
        self.update_stats()
        if self.worker:
            self.wait_for_body()
        else:
            self.video.set_feedback("Encendé la cámara para empezar")

    def update_stats(self):
        if not self.ex:
            return
        q = self.win.game.quest
        t = q["targets"].get(self.ex.id) if q else None
        self.video.target = f"misión {min(q['progress'].get(self.ex.id, 0), t):g}/{t}" if t else ""
        big = "font-size:22px;font-weight:700;color:white;"
        self.lbl_good.setText(f"<span style='{big}'>{fmt(self.good)}</span><br><span style='color:{T.MUTED}'>{'segundos' if self.ex.timed else 'buenas'}</span>")
        self.lbl_bad.setText(f"<span style='{big}'>{self.bad}</span><br><span style='color:{T.MUTED}'>mal hechas</span>")
        self.lbl_xp.setText(f"<span style='{big}'>{fmt(self.xp)}</span><br><span style='color:{T.MUTED}'>XP ganada</span>")
        self.video.update()

    # ---------------------------------------------------------------- cámara
    @property
    def training(self) -> bool:
        return self.worker is not None and self.state in ("countdown", "running")

    def toggle_camera(self):
        if self.worker:
            self.stop_camera()
            return
        idx = max(0, self.cam_combo.currentIndex())
        self.win.game.s["settings"]["camera"] = idx
        self.btn_cam.setEnabled(False)
        self.btn_cam.setText("Cargando IA…")
        self.video.center_small = "Iniciando cámara y modelo de visión…"
        self.video.update()
        self.worker = CameraWorker(idx, self.win.game.s["settings"].get("mirror", True), self)
        self.worker.ready.connect(self.on_ready)
        self.worker.failed.connect(self.on_failed)
        self.worker.frame.connect(self.on_frame)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def on_ready(self):
        self.btn_cam.setEnabled(True)
        self.btn_cam.setText("Apagar cámara")
        self.btn_cam.setIcon(icons.icon("camera-off", 18))
        self.btn_cam.setProperty("kind", "")
        restyle(self.btn_cam)
        self.video.center_small = ""
        self.wait_for_body()

    def on_failed(self, msg: str):
        self.win.dialogs.show("ERROR", f"No pude iniciar la cámara.<br><small>{escape(msg)}</small><br><br>"
                                       "Probá con otra cámara de la lista, o usá los botones +1 / +5 / +10.", tone="red")

    def on_worker_finished(self):
        self.worker = None
        self.state = "idle"
        self.btn_cam.setEnabled(True)
        self.btn_cam.setText("Encender cámara")
        self.btn_cam.setIcon(icons.icon("camera", 18))
        self.btn_cam.setProperty("kind", "primary")
        restyle(self.btn_cam)
        self.video.center = self.video.center_small = ""
        self.video.clear()
        self.video.set_feedback("Cámara apagada")

    def stop_camera(self):
        if self.worker:
            self.worker.stop()

    def wait_for_body(self):
        self.state = "waiting"
        self.visible_since = None
        self.video.set_feedback("Ponete en posición")

    def on_frame(self, img, lm, world, aspect, t):
        color = T.GLOW
        if self.ex is None:
            self.video.set_frame(img, lm, color)
            return
        v = self.video
        if lm is None:
            if self.state in ("waiting", "countdown"):
                self.state = "waiting"
                self.visible_since = None
                v.center, v.center_small = "", "Buscando tu cuerpo…"
            v.set_feedback("No te detecto. Alejate y que se vea todo tu cuerpo", "bad")
            v.set_frame(img, None, color)
            return

        if self.state == "waiting":
            self.visible_since = self.visible_since or t
            v.center_small = "Te veo. Quedate en posición…"
            if t - self.visible_since > 0.8:
                self.state = "countdown"
                self.countdown_end = t + 3
                v.center_small = ""
        elif self.state == "countdown":
            left = int(self.countdown_end - t) + 1
            txt = str(left) if self.countdown_end - t > 0 else "¡YA!"
            if txt != self.last_center:
                self.last_center = txt
                v.center = txt
                self.win.sounds.play("go" if txt == "¡YA!" else "tick")
            if t >= self.countdown_end:
                self.state = "running"
                self.win.voice.say("Empezá", True)
                QTimer.singleShot(600, lambda: setattr(self.video, "center", ""))
        elif self.state == "running":
            color = self.process(lm, world, aspect, t)
        v.set_frame(img, lm, color)

    def process(self, lm, world, aspect, t) -> str:
        r = self.counter.update(lm, world, aspect, t)
        ex, v, g = self.ex, self.video, self.win.game
        if ex.timed:
            if r.event == "second":
                self.good += r.count
                v.count = str(int(self.counter.seconds))
                self.xp += g.add_reps(ex.id, r.count)
                s = int(self.counter.seconds)
                if s % 10 == 0:
                    self.win.voice.say(f"{s} segundos")
                self.update_stats()
            ok = r.status == "ok"
            v.progress = 1.0 if ok else 0.0
            v.set_feedback(r.msg or "", "good" if ok else "bad")
            if not ok and r.msg:
                self.win.voice.say(r.msg)
            return T.GREEN if ok else T.RED

        if r.progress is not None:
            v.progress = r.progress
        if r.event == "rep":
            self.good += 1
            v.count = str(self.counter.reps)
            v.bump()
            self.win.sounds.play("rep")
            self.win.voice.say(str(self.counter.reps), True)
            self.xp += g.add_reps(ex.id, 1)
            v.set_feedback(r.msg, "good")
            self.update_stats()
        elif r.event in ("bad", "partial"):
            if r.event == "bad":
                self.bad += 1
            self.win.sounds.play("bad")
            self.win.voice.say(r.msg.replace(" (no cuenta)", ""))
            v.set_feedback(r.msg, "bad")
            self.update_stats()
        elif r.msg and r.status != "ok":
            v.set_feedback(r.msg, "warn" if r.status == "warn" else "bad")
        elif r.status == "ok" and v.tone == "bad":
            v.set_feedback("Seguí así", "")
        return {"warn": T.GOLD, "ok": T.GLOW}.get(r.status, T.RED)

    def manual(self, n: int):
        if not self.ex:
            return
        self.good += n
        self.video.count = str(self.good)
        self.video.bump()
        self.xp += self.win.game.add_reps(self.ex.id, n, manual=True)
        self.update_stats()

    def finish(self):
        ex = self.ex
        g = self.win.game
        if ex and (self.good or self.bad):
            g.log_set(ex.id, self.good, self.bad, self.xp)
            rem = g.remaining()
            falta = ""
            if rem and not g.quest["completed"]:
                falta = "<br><small>Te falta: " + ", ".join(f"{EXERCISES[k].name} {fmt(v)}" for k, v in rem) + "</small>"
            res = (f"Tiempo válido: <b style='color:{T.GLOW}'>{fmt(self.good)} s</b>" if ex.timed else
                   f"Repeticiones válidas: <b style='color:{T.GLOW}'>{self.good}</b><br>Mal hechas: {self.bad}")
            self.win.dialogs.show("SERIE TERMINADA",
                                  f"{icons.img(ex.icon, 20)}&nbsp; <b>{ex.name}</b><br><br>{res}<br>"
                                  f"<span style='font-size:22px;color:{T.GOLD}'><b>+{fmt(self.xp)} XP</b></span>{falta}")
        self.ex = None
        self.counter = None
        self.state = "waiting" if self.worker else "idle"
        self.video.center = self.video.center_small = ""
        self.stop_camera()
        self.stack.setCurrentIndex(0)
        self.refresh()


# =================================================================== REGISTRO
class RegistroPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("page")
        heat = Panel("ÚLTIMOS 28 DÍAS", "calendar-days")
        self.heat = QGridLayout()
        self.heat.setSpacing(6)
        heat.lay.addLayout(self.heat)
        tot = Panel("TOTALES", "activity")
        self.totals = QGridLayout()
        self.totals.setSpacing(8)
        tot.lay.addLayout(self.totals)
        ach = Panel("LOGROS", "trophy")
        self.ach = QGridLayout()
        self.ach.setSpacing(8)
        ach.lay.addLayout(self.ach)
        log = Panel("MENSAJES DEL SISTEMA", "terminal")
        self.log = QListWidget()
        self.log.setMinimumHeight(240)
        log.lay.addWidget(self.log)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll_page(heat, tot, ach, log))

    def refresh(self):
        g = self.win.game
        s = g.s
        clear_layout(self.heat)
        today = g.today()
        for i in range(28):
            d = (date.fromisoformat(today) - timedelta(days=27 - i))
            k = d.isoformat()
            h = {"completed": g.quest and g.quest["completed"]} if k == today else s["history"].get(k)
            c = label(str(d.day), align=Qt.AlignmentFlag.AlignCenter)
            c.setMinimumHeight(40)
            if h and h.get("completed"):
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

        jug = Panel("JUGADOR", "user-round")
        f = QFormLayout()
        f.setVerticalSpacing(12)
        f.setHorizontalSpacing(24)
        from PySide6.QtWidgets import QLineEdit
        self.name = QLineEdit()
        self.name.setMaxLength(24)
        self.name.editingFinished.connect(self.save_name)
        f.addRow("Nombre", self.name)
        self.diff = QComboBox()
        self.diff.addItems(["Fácil — empezando", "Normal", "Difícil", "Extremo — 100/100/100"])
        self.diff.currentIndexChanged.connect(lambda i: not self._loading and self.win.game.set_difficulty(DIFF_ORDER[i]))
        f.addRow("Dificultad", self.diff)
        jug.lay.addLayout(f)
        jug.lay.addWidget(label("La dificultad nueva se aplica desde mañana (o ya, si todavía no empezaste la misión de hoy).", "muted", wrap=True))
        self.voice = QCheckBox("Voz que cuenta las repeticiones y te corrige")
        self.sound = QCheckBox("Efectos de sonido")
        self.mirror = QCheckBox("Cámara en modo espejo")
        for cb, key in ((self.voice, "voice"), (self.sound, "sound"), (self.mirror, "mirror")):
            cb.toggled.connect(lambda on, key=key: self.set_setting(key, on))
            jug.lay.addWidget(cb)

        guard = Panel("EL GUARDIÁN", "shield")
        guard.lay.addWidget(label("Mientras ASCENSO esté abierto (aunque sea en la bandeja, al lado del reloj), "
                                  "te va a perseguir con alertas encima de todo hasta que completes la misión.",
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
        self.hard = QCheckBox("Modo hardcore: pantalla completa que no se puede cerrar")
        self.hard.toggled.connect(self.toggle_hard)
        guard.lay.addWidget(self.hard)
        self.auto = QCheckBox("Arrancar ASCENSO automáticamente al prender la compu")
        self.auto.toggled.connect(self.toggle_auto)
        guard.lay.addWidget(self.auto)
        guard.lay.addWidget(button("Probar alerta ahora", "", lambda: self.win.guardian.show(test=True), icon="bell-ring"))

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
        lay.addWidget(scroll_page(jug, guard, datos))

    def refresh(self):
        self._loading = True
        s = self.win.game.s
        st = s["settings"]
        self.name.setText(s["player"]["name"])
        self.diff.setCurrentIndex(DIFF_ORDER.index(st["difficulty"]) if st["difficulty"] in DIFF_ORDER else 0)
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
                              "En modo hardcore la alerta cubre <b>todas tus pantallas</b> y no se puede cerrar "
                              "hasta que vayas a entrenar, uses una posposición o escribas la frase de rendición.<br><br>¿Aceptás?",
                              (("Acepto", "danger"), ("Mejor no", "")), tone="red", callback=answer)

    def toggle_auto(self, on):
        if not self._loading and not storage.set_autostart(on):
            self.win.toaster.show("No pude cambiar el inicio automático")

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar progreso", f"ascenso-{date.today()}.json", "JSON (*.json)")
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
