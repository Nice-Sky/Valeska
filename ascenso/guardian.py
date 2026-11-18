"""El Guardián: te persigue con alertas encima de todo hasta que completes la misión."""
from __future__ import annotations

import time

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from .exercises import EXERCISES
from .game import fmt
from .ui import theme as T
from .ui.widgets import button, glow

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
        self.setObjectName("nagWindow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QWidget#nagWindow {{ background:{T.BG}; }}")
        geo = screen.geometry()
        if hard:
            self.setGeometry(geo)
        else:
            w, h = 680, 520
            self.setGeometry(geo.x() + (geo.width() - w) // 2, geo.y() + (geo.height() - h) // 3, w, h)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setStyleSheet(f"QFrame#nagFrame {{ border: 3px solid {T.RED}; background: {T.BG}; }}")
        frame.setObjectName("nagFrame")
        outer.addWidget(frame)
        lay = QVBoxLayout(frame)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if primary:
            self._build(lay)
        else:
            t = QLabel("⚠  ALERTA DEL SISTEMA  ⚠\n\nMisión diaria incompleta.")
            t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            t.setStyleSheet(f"color:{T.RED};font-size:40px;font-weight:700;")
            lay.addWidget(t)

    def _build(self, lay):
        game = self.g.game
        big = 46 if self.hard else 26
        box = QWidget()
        box.setMaximumWidth(900)
        bl = QVBoxLayout(box)
        bl.setSpacing(14)
        title = QLabel("⚠  ALERTA DEL SISTEMA  ⚠")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color:{T.RED};font-size:{big}px;font-weight:700;letter-spacing:4px;")
        bl.addWidget(title)
        q = game.quest or {}
        name = game.player["name"] or "Jugador"
        kind = "MISIÓN DE PENALIZACIÓN" if q.get("penalty") else "misión diaria"
        msg = QLabel(f"{name}, tu {kind} sigue incompleta.\n"
                     "Si no la completás antes de medianoche recibirás una penalización.")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setWordWrap(True)
        msg.setStyleSheet(f"color:{T.TEXT};font-size:{18 if self.hard else 15}px;")
        bl.addWidget(msg)
        rem = game.remaining()
        lines = [f"{EXERCISES[k].icon}  {EXERCISES[k].name}: faltan {fmt(v)}{' s' if EXERCISES[k].timed else ''}"
                 for k, v in rem] or ["Abrí el Sistema para recibir la misión de hoy"]
        pend = QLabel("\n".join(lines))
        pend.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pend.setStyleSheet(f"color:{T.GLOW};font-size:{20 if self.hard else 16}px;font-weight:600;padding:10px;")
        bl.addWidget(pend)

        train = button("⚔   ENTRENAR AHORA", "primary", self.g.train_now)
        train.setMinimumHeight(56)
        train.setStyleSheet("font-size:20px;")
        bl.addWidget(train)
        left = game.snoozes_left()
        if left > 0:
            sn = button(f"Posponer 15 minutos  (te quedan {left})", "", self.g.snooze)
            sn.setMinimumHeight(44)
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
        bl.addSpacing(10)
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
        self.win.tray_message("⚠ ALERTA DEL SISTEMA", "Tu misión diaria sigue incompleta.")
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
