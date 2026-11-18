"""El Guardián: te persigue con alertas encima de todo hasta que completes la misión."""
from __future__ import annotations

import time

from html import escape

from PySide6.QtCore import QObject, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from .exercises import EXERCISES
from .game import fmt
from .ui import theme as T
from .ui import fx, holo, icons
from .ui.widgets import button

SURRENDER_PHRASE = "ME RINDO"
CHECK_MS = 10_000


class NagWindow(QWidget, holo.Surface):
    """Ventana de alerta. En modo hardcore hay una por pantalla, a pantalla completa."""

    def __init__(self, guardian: "Guardian", screen, hard: bool, primary: bool):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        QWidget.__init__(self, None, flags)
        self.surface_init()
        fx.Clock.get().tick.connect(self.update)
        self._bg_key = None
        self._bg = None
        self.g = guardian
        self.hard = hard
        self.allow_close = False
        self.setWindowTitle("Arise Trainer: objetivo pendiente")
        if not hard:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        geo = screen.geometry()
        if hard:
            self.setGeometry(geo)
        else:
            w, h = 1010, 800
            self.setGeometry(geo.x() + (geo.width() - w) // 2, geo.y() + (geo.height() - h) // 3, w, h)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(176, 128, 176, 128)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if primary:
            self._build(lay)
        else:
            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(holo.TitleBar("OBJETIVO PENDIENTE", "triangle-alert", "red", 28))
            row.addStretch()
            lay.addLayout(row)

    def surface_spec(self):
        r = QRectF(self.rect())
        if self.hard:
            w, h = min(900, r.width() - 300), min(640, r.height() - 200)
            box = QRectF((r.width() - w) / 2, (r.height() - h) / 2, w, h)
        else:
            box = r.adjusted(136, 92, -136, -92)
        return holo.SurfaceSpec(box, "red", cut=4, beams=True, brackets=False, strong=True, seed=31, glass_alpha=225)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.hard:
            key = (self.width(), self.height(), self.devicePixelRatioF())
            if key != self._bg_key:
                self._bg = holo.render_backdrop(self.width(), self.height(), self.devicePixelRatioF(), 21, "red")
                self._bg_key = key
            p.drawImage(0, 0, self._bg)
        self.paint_surface(p)

    def _build(self, lay):
        game = self.g.game
        size = 22 if self.hard else 17
        box = QWidget()
        box.setMaximumWidth(760)
        bl = QVBoxLayout(box)
        bl.setSpacing(14)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(holo.TitleBar("OBJETIVO PENDIENTE", "triangle-alert", "red", size))
        row.addStretch()
        bl.addLayout(row)
        q = game.quest or {}
        name = escape(game.player["name"] or "")
        kind = "objetivo de penalización (+30%)" if q.get("penalty") else "objetivo de hoy"
        msg = QLabel(f"{name}, tu {kind} sigue pendiente.<br>"
                     "Si no lo cumplís antes de medianoche: <b style='color:#ff3b5c'>-XP, racha a cero y mañana +30%</b>.")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setWordWrap(True)
        msg.setStyleSheet(f"color:{T.CORE};font-size:{18 if self.hard else 15}px;")
        bl.addWidget(msg)
        rem = game.remaining()
        fs = 19 if self.hard else 15
        lines = [f"{icons.img(EXERCISES[k].icon, fs + 2, T.GLOW)}&nbsp;&nbsp;{EXERCISES[k].name}: faltan <b>{fmt(v)}</b>"
                 f"{' s' if EXERCISES[k].timed else ''}" for k, v in rem] or ["Abrí Arise Trainer para ver el objetivo de hoy"]
        pend = QLabel("<br>".join(lines))
        pend.setTextFormat(Qt.TextFormat.RichText)
        pend.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pend.setStyleSheet(f"color:{T.GLOW};font-size:{fs}px;padding:8px;line-height:150%;")
        bl.addWidget(pend)

        train = button("ENTRENAR AHORA", "primary", self.g.train_now, icon="swords")
        train.setMinimumHeight(54)
        bl.addWidget(train)
        left = game.snoozes_left()
        if left > 0:
            sn = button(f"Posponer 15 minutos  (te quedan {left})", "", self.g.snooze, icon="hourglass")
            sn.setMinimumHeight(42)
            bl.addWidget(sn)
        if not self.hard:
            bl.addWidget(button("Cerrar (vuelvo en un rato)", "ghost", self.g.dismiss))

        self.surr_box = QWidget()
        sl = QHBoxLayout(self.surr_box)
        sl.setContentsMargins(0, 0, 0, 0)
        self.surr = QLineEdit()
        self.surr.setPlaceholderText(f'Escribí "{SURRENDER_PHRASE}"')
        self.surr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.surr.returnPressed.connect(self._surrender)
        sl.addWidget(self.surr, 1)
        sl.addWidget(button("Confirmar", "danger", self._surrender))
        self.surr_box.hide()
        surr_btn = button("Saltear hoy… (la penalización se aplica igual)", "ghost",
                          lambda: (self.surr_box.show(), self.surr.setFocus()))
        bl.addWidget(surr_btn)
        bl.addWidget(self.surr_box)
        lay.addWidget(box, 0, Qt.AlignmentFlag.AlignCenter)

    def _surrender(self):
        if self.surr.text().strip().upper() == SURRENDER_PHRASE:
            self.g.surrender()
        else:
            self.surr.clear()
            self.surr.setPlaceholderText("Frase incorrecta")

    def closeEvent(self, e):
        if self.allow_close:
            e.accept()
        else:
            e.ignore()
            if not self.hard:
                self.g.dismiss()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            if not self.hard:
                self.g.dismiss()
            return
        super().keyPressEvent(e)


class Guardian(QObject):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.game = win.game
        self.windows: list[NagWindow] = []
        self.next_nag = 0.0
        self.soft_sent = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check)
        self.timer.start(CHECK_MS)
        self.raise_timer = QTimer(self)
        self.raise_timer.timeout.connect(self._keep_on_top)

    @property
    def interval(self) -> int:
        return max(5, int(self.game.nag_settings()["intervalMin"]))

    def check(self):
        try:
            if self.windows:
                if self.game.quest and self.game.quest["completed"]:
                    self.close()
                return
            if self.win.is_training() or self.win.dialogs.busy:
                return
            if time.time() < self.next_nag:
                return
            if self.game.should_nag():
                # 1º aviso: notificación con botones; si se ignora, a los 3 minutos la alerta grande
                if not self.game.nag_settings()["hard"] and not self.soft_sent:
                    self.soft_notice()
                else:
                    self.show()
        except Exception as e:  # el guardián nunca debe romper la app
            print("Guardián:", e)

    def soft_notice(self):
        self.soft_sent = True
        self.next_nag = time.time() + 180
        rem = self.game.remaining()
        txt = "Todavía no cumpliste el entrenamiento de hoy."
        if rem:
            txt += "<br><span style='color:#7f95bf'>" + " · ".join(
                f"{EXERCISES[k].name} {fmt(v)}" for k, v in rem[:3]) + "</span>"
        self.win.notifier.show("OBJETIVO PENDIENTE", txt, "triangle-alert", "red",
                               actions=[("Entrenar", self.train_now), ("15 min", self.snooze)],
                               timeout=25, sound="alarm", on_click=self.train_now)
        self.win.voice.say("Objetivo del día pendiente.", True)

    def show(self, test: bool = False):
        self.close()
        self.soft_sent = False
        hard = bool(self.game.nag_settings()["hard"])
        app = QGuiApplication.instance()
        primary = QGuiApplication.primaryScreen()
        screens = app.screens() if hard else [primary]
        for sc in screens:
            w = NagWindow(self, sc, hard, sc is primary)
            self.windows.append(w)
            w.show()
            w.raise_()
            w.activateWindow()
        self.win.sounds.play("alarm")
        self.win.voice.say("Objetivo del día pendiente.", True)
        self.raise_timer.start(1500)

    def _keep_on_top(self):
        for w in self.windows:
            w.raise_()
            if w.hard and hasattr(w, "surr_box") and not w.surr.hasFocus():
                w.activateWindow()

    def close(self):
        self.raise_timer.stop()
        for w in self.windows:
            w.allow_close = True
            w.close()
            w.deleteLater()
        self.windows = []

    # ---- acciones
    def train_now(self):
        self.soft_sent = False
        self.next_nag = time.time() + self.interval * 60
        self.close()
        self.win.show_page("mision")

    def snooze(self):
        self.soft_sent = False
        self.game.snooze()
        self.next_nag = time.time() + 15 * 60
        self.close()

    def dismiss(self):
        self.soft_sent = False
        self.next_nag = time.time() + self.interval * 60
        self.close()

    def surrender(self):
        self.game.surrender()
        self.close()
        self.win.refresh()
