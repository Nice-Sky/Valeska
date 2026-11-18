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
from .ui import holo, icons
from .ui.widgets import button

SURRENDER_PHRASE = "ME RINDO"
CHECK_MS = 10_000


class NagWindow(QWidget):
    """Ventana de alerta. En modo hardcore hay una por pantalla, a pantalla completa."""

    def __init__(self, guardian: "Guardian", screen, hard: bool, primary: bool):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        super().__init__(None, flags)
        self.g = guardian
        self.hard = hard
        self.allow_close = False
        self.setWindowTitle("ALERTA DEL SISTEMA")
        if not hard:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        geo = screen.geometry()
        if hard:
            self.setGeometry(geo)
        else:
            w, h = 820, 640
            self.setGeometry(geo.x() + (geo.width() - w) // 2, geo.y() + (geo.height() - h) // 3, w, h)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(90, 80, 90, 80)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if primary:
            self._build(lay)
        else:
            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(holo.TitleBar("ALERTA DEL SISTEMA", "triangle-alert", "red", 28))
            row.addStretch()
            lay.addLayout(row)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        if self.hard:
            holo.backdrop(p, r, 21)
            p.fillRect(r, QColor(60, 0, 12, 60))
            w, h = min(980, r.width() - 160), min(700, r.height() - 160)
            box = QRectF((r.width() - w) / 2, (r.height() - h) / 2, w, h)
        else:
            box = r.adjusted(44, 40, -44, -40)
        holo.holo_frame(p, box, "red", 31, cut=8, beams=True, strong=True, brackets=False)

    def _build(self, lay):
        game = self.g.game
        size = 22 if self.hard else 17
        box = QWidget()
        box.setMaximumWidth(760)
        bl = QVBoxLayout(box)
        bl.setSpacing(14)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(holo.TitleBar("ALERTA DEL SISTEMA", "triangle-alert", "red", size))
        row.addStretch()
        bl.addLayout(row)
        q = game.quest or {}
        name = escape(game.player["name"] or "Jugador")
        kind = "<b>MISIÓN DE PENALIZACIÓN</b>" if q.get("penalty") else "misión diaria"
        msg = QLabel(f"{name}, tu {kind} sigue incompleta.<br>"
                     "Si no la completás antes de medianoche recibirás una <b style='color:#ff3b5c'>penalización</b>.")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setWordWrap(True)
        msg.setStyleSheet(f"color:{T.CORE};font-size:{18 if self.hard else 15}px;")
        bl.addWidget(msg)
        rem = game.remaining()
        fs = 19 if self.hard else 15
        lines = [f"{icons.img(EXERCISES[k].icon, fs + 2, T.GLOW)}&nbsp;&nbsp;{EXERCISES[k].name}: faltan <b>{fmt(v)}</b>"
                 f"{' s' if EXERCISES[k].timed else ''}" for k, v in rem] or ["Abrí el Sistema para recibir la misión de hoy"]
        pend = QLabel("<br>".join(lines))
        pend.setTextFormat(Qt.TextFormat.RichText)
        pend.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pend.setStyleSheet(f"color:{T.GLOW};font-size:{fs}px;padding:8px;line-height:150%;")
        bl.addWidget(pend)

        train = button("ENTRENAR AHORA", "primary", self.g.train_now, icon="swords")
        train.setMinimumHeight(54)
        train.setStyleSheet("font-size:19px;letter-spacing:4px;")
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
        surr_btn = button("Me rindo por hoy… (igual te comés la penalización)", "ghost",
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
                self.show()
        except Exception as e:  # el guardián nunca debe romper la app
            print("Guardián:", e)

    def show(self, test: bool = False):
        self.close()
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
        self.win.voice.say("Alerta del Sistema. Misión diaria incompleta.", True)
        self.win.tray_message("ALERTA DEL SISTEMA", "Tu misión diaria sigue incompleta.")
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
        self.next_nag = time.time() + self.interval * 60
        self.close()
        self.win.show_page("mision")

    def snooze(self):
        self.game.snooze()
        self.next_nag = time.time() + 15 * 60
        self.close()

    def dismiss(self):
        self.next_nag = time.time() + self.interval * 60
        self.close()

    def surrender(self):
        self.game.surrender()
        self.close()
        self.win.refresh()
