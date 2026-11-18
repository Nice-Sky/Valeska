"""Ventana principal, bandeja del sistema y arranque."""
from __future__ import annotations

import sys

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QButtonGroup, QHBoxLayout, QMainWindow, QMenu, QPushButton,
                               QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

from . import storage
from .game import PLAN_ORDER, PLANS, Game, rank_of
from .guardian import Guardian
from .ui import theme as T
from .ui.body_page import CuerpoPage
from .ui.pages import AjustesPage, EntrenarPage, EstadoPage, MisionPage, RegistroPage
from .ui import icons
from .ui.holo import Backdrop
from .ui.widgets import Dialogs, GlowLabel, Toaster, label
from .voice import Sounds, Voice

PAGES = [("estado", "ESTADO", "user-round"), ("mision", "HOY", "target"), ("entrenar", "ENTRENAR", "dumbbell"),
         ("registro", "PROGRESO", "chart-column"), ("cuerpo", "CUERPO", "scan-line"), ("ajustes", "AJUSTES", "settings")]
INSTANCE_KEY = "arise-trainer-instance"


def app_icon() -> QIcon:
    ico = storage.resource("icon.ico")
    if ico.exists():
        return QIcon(str(ico))
    pm = QPixmap(64, 64)
    pm.fill(QColor(T.BG))
    p = QPainter(pm)
    p.setPen(QColor(T.GLOW))
    f = QFont(T.FONT, 36)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "A")
    p.end()
    return QIcon(pm)


class NavRail(QWidget):
    """Barra lateral: vidrio oscuro con un riel de neón a la derecha."""

    def paintEvent(self, e):
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QLinearGradient
        from .ui import holo
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        g = QLinearGradient(r.topLeft(), r.topRight())
        g.setColorAt(0, QColor(2, 7, 18, 235))
        g.setColorAt(1, QColor(5, 16, 40, 215))
        p.fillRect(r, g)
        x = r.right() - 2
        holo.neon_line(p, x, 18, x, r.bottom() - 18, T.GLOW, T.CORE, 1.0, 5, 2.2, 22)
        for y in (r.height() * 0.22, r.height() * 0.62):
            p.fillRect(QRectF(x - 3, y, 6, 34), QColor(T.GLOW))
            p.fillRect(QRectF(x - 1, y + 3, 2, 28), QColor(T.CORE))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Arise Trainer")
        self.setWindowIcon(app_icon())
        self.resize(1180, 820)
        self.setMinimumSize(900, 640)
        self.quitting = False
        self.tray_hint_shown = False

        self.sounds = Sounds()
        self.voice = Voice()
        self.dialogs = Dialogs(self, self.sounds)
        self.toaster = Toaster(self)
        self.game = Game(on_event=self.on_game_event)
        self.apply_settings()

        root = Backdrop()
        root.setObjectName("root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        nav = NavRail()
        nav.setObjectName("nav")
        nav.setFixedWidth(220)
        nl = QVBoxLayout(nav)
        nl.setContentsMargins(0, 22, 0, 18)
        nl.setSpacing(2)
        brand = GlowLabel("ARISE", 26, QFont.Weight.Bold, align=Qt.AlignmentFlag.AlignCenter, spacing=9, glow=1.2)
        nl.addWidget(brand)
        nl.addWidget(label("T R A I N E R", "brandSub", align=Qt.AlignmentFlag.AlignCenter))
        nl.addSpacing(26)
        self.nav_group = QButtonGroup(self)
        self.nav_buttons = {}
        for key, text, ic in PAGES:
            b = QPushButton("  " + text)
            b.setIcon(icons.icon(ic, 18))
            b.setIconSize(QSize(18, 18))
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.show_page(k))
            self.nav_group.addButton(b)
            self.nav_buttons[key] = b
            nl.addWidget(b)
        nl.addStretch()
        self.nav_player = label("", "navPlayer", align=Qt.AlignmentFlag.AlignCenter)
        nl.addWidget(self.nav_player)
        h.addWidget(nav)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(24, 20, 10, 10)
        self.stack = QStackedWidget()
        cl.addWidget(self.stack)
        h.addWidget(content, 1)

        self.pages = {
            "estado": EstadoPage(self), "mision": MisionPage(self), "entrenar": EntrenarPage(self),
            "registro": RegistroPage(self), "cuerpo": CuerpoPage(self), "ajustes": AjustesPage(self),
        }
        for key, *_ in PAGES:
            self.stack.addWidget(self.pages[key])

        self.guardian = Guardian(self)
        self._setup_tray()

        self.day_timer = QTimer(self)
        self.day_timer.timeout.connect(self.game.rollover)
        self.day_timer.start(60_000)

        self.show_page("estado")

    # ------------------------------------------------------------ eventos del juego
    def on_game_event(self, kind, data):
        if kind == "changed":
            self.refresh()
        elif kind == "toast":
            self.toaster.show(data["text"], data.get("gold", False), data.get("icon", ""))
        elif kind == "say":
            self.voice.say(data["text"], data.get("force", False))
        elif kind == "modal":
            training = self.is_training()
            if training and data["title"] not in ("OBJETIVO CUMPLIDO", "PENALIZACIÓN"):
                self.toaster.show(data["title"], True, "star")
                self.sounds.play(data.get("sound", "open"))
                return
            self.dialogs.show(data["title"], data["body"], tone=data.get("color", ""), sound=data.get("sound", "open"),
                              icon=data.get("icon", ""))

    def is_training(self) -> bool:
        if not hasattr(self, "pages"):
            return False
        return self.pages["entrenar"].training or self.pages["cuerpo"].worker is not None

    def apply_settings(self):
        st = self.game.s["settings"]
        self.voice.enabled = st["voice"]
        self.sounds.enabled = st["sound"]

    def refresh(self):
        if not hasattr(self, "pages"):
            return
        p = self.game.player
        self.nav_player.setText(f"<b style='color:white'>{p['name'] or '—'}</b><br>NV {p['level']} · RANGO {rank_of(p['level'])}")
        current = self.stack.currentWidget()
        for page in self.pages.values():
            if page is current or page in (self.pages["estado"], self.pages["mision"]):
                page.refresh()
        if self.tray:
            q = self.game.quest
            state = ("Día de descanso" if q and q.get("rest") else "Objetivo cumplido" if q and q["completed"] else "Objetivo pendiente")
            self.tray.setToolTip(f"Arise Trainer — {p['name']} · Nivel {p['level']}\n{state}")

    def show_page(self, key: str):
        self.stack.setCurrentWidget(self.pages[key])
        self.nav_buttons[key].setChecked(True)
        self.pages[key].refresh()
        self.bring_to_front()

    def go(self, key):
        self.show_page(key)

    def open_training(self, k: str):
        self.show_page("entrenar")
        self.pages["entrenar"].open(k)

    def bring_to_front(self):
        if not self.isVisible() or self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    # ------------------------------------------------------------ bandeja
    def _setup_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(app_icon(), self)
        menu = QMenu()
        for text, slot in (("Abrir Arise Trainer", lambda: self.show_page("estado")),
                           ("Objetivo de hoy", lambda: self.show_page("mision")),
                           ("Entrenar", lambda: self.show_page("entrenar"))):
            a = QAction(text, menu)
            a.triggered.connect(slot)
            menu.addAction(a)
        menu.addSeparator()
        quit_a = QAction("Salir", menu)
        quit_a.triggered.connect(self.quit_app)
        menu.addAction(quit_a)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: r == QSystemTrayIcon.ActivationReason.Trigger and self.show_page("estado"))
        self.tray.show()
        self._tray_menu = menu

    def tray_message(self, title, text):
        if self.tray:
            self.tray.showMessage(title, text, QSystemTrayIcon.MessageIcon.Warning, 6000)

    def closeEvent(self, e):
        if self.quitting or not self.tray:
            self.pages["entrenar"].stop_camera()
            e.accept()
            return
        e.ignore()
        self.pages["entrenar"].stop_camera()
        self.hide()
        if not self.tray_hint_shown:
            self.tray_hint_shown = True
            self.tray.showMessage("Arise Trainer sigue activo",
                                  "Sigue funcionando acá, al lado del reloj, para recordarte el objetivo del día.",
                                  QSystemTrayIcon.MessageIcon.Information, 5000)

    def quit_app(self):
        q = self.game.quest
        if q and not q["completed"] and self.game.nag_settings()["enabled"] and self.game.registered:
            def answer(i, _):
                if i == 1:
                    self._really_quit()
            self.bring_to_front()
            self.dialogs.show("¿SALIR?", "El objetivo de hoy todavía no está cumplido.<br>Si cerrás la app no vas a recibir "
                                        "recordatorios, pero la penalización a medianoche se aplica igual.",
                              (("Me quedo", "primary"), ("Salir igual", "danger")), tone="red", callback=answer)
        else:
            self._really_quit()

    def _really_quit(self):
        self.quitting = True
        self.guardian.close()
        self.pages["entrenar"].stop_camera()
        self.game.save()
        if self.tray:
            self.tray.hide()
        QApplication.quit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.toaster._layout()
        if self.dialogs.current:
            self.dialogs.dimmer.setGeometry(self.rect())

    # ------------------------------------------------------------ primer inicio
    def start_onboarding(self):
        d = self.dialogs

        def ask_name(*_):
            d.show("REGISTRO", "¿Cómo te llamás?", ("Confirmar",), callback=got_name,
                   with_input=True, placeholder="Tu nombre", icon="user-round")

        def got_name(_, name):
            if not name.strip():
                ask_name()
                return
            self._name = name.strip()
            plans = "<br>".join(f"<b>{p['label']}</b>: <span style='color:#7f95bf'>{p['desc']}</span>" for p in PLANS.values())
            d.show("PLAN", f"Elegí tu punto de partida.<br><br><div style='text-align:left'>{plans}</div><br>"
                           "<small>Los objetivos suben solos un 5% cada 7 días cumplidos. Podés cambiar el plan en Ajustes.</small>",
                   (("Principiante", "primary"), ("Intermedio", ""), ("Avanzado", ""), ("Extremo", "danger")),
                   callback=got_plan, icon="target")

        def got_plan(i, _):
            self.game.register(self._name, PLAN_ORDER[max(0, i)])
            if storage.autostart_supported():
                d.show("RECORDATORIOS", "¿Querés que Arise Trainer arranque solo al prender la compu?<br>"
                                        "<small>Así los recordatorios funcionan aunque te olvides de abrirlo.</small>",
                       (("Sí", "primary"), ("No", "")), icon="bell-ring",
                       callback=lambda i, _: (storage.set_autostart(i == 0), show_quest()))
            else:
                show_quest()

        def show_quest():
            q = self.game.quest
            if q.get("rest"):
                body = "Hoy es tu día de descanso. Tu primer objetivo arranca mañana.<br><small>Los días de descanso se configuran en Ajustes.</small>"
            else:
                body = "Tu objetivo de hoy:<br><br>" + "<br>".join(self._quest_lines())
            d.show("OBJETIVO DIARIO", body, ("Empezar",), icon="target", callback=lambda *_: self.show_page("mision"))

        d.show("NOTIFICACIÓN",
               "Bienvenido a <b style='color:#4fd8ff'>Arise Trainer</b>.<br><br>"
               "Cada día tenés un objetivo de entrenamiento. Cumplirlo suma XP, racha y nivel.<br>"
               "Fallarlo tiene penalización.<br><br>La cámara cuenta tus repeticiones: solo valen las bien hechas.",
               ("Empezar",), callback=ask_name)

    def _quest_lines(self):
        from .exercises import EXERCISES
        q = self.game.quest
        return [f"{EXERCISES[k].name}: <b>{t}</b>{' s' if EXERCISES[k].timed else ''}" for k, t in q["targets"].items()]

    def startup(self, minimized: bool):
        storage.migrate_autostart()
        if not minimized:
            self.show()
        if not self.game.registered:
            self.show()
            QTimer.singleShot(300, self.start_onboarding)
        else:
            self.game.rollover()
            self.game.check_achievements()
            self.refresh()
            if self.game.checkin_due():
                QTimer.singleShot(2500, lambda: self.toaster.show("Hoy te toca el control corporal semanal", True, "scan-line"))
        QTimer.singleShot(5000, self.guardian.check)


def main():
    if sys.platform == "win32":
        try:  # ícono propio en la barra de tareas
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("arise.trainer")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("Arise Trainer")
    app.setQuitOnLastWindowClosed(False)
    from PySide6.QtGui import QFontDatabase
    for f in sorted(storage.resource("fonts").glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(f))
    app.setStyleSheet(T.QSS)
    app.setFont(QFont(T.FONT, 10))

    # instancia única: si ya está abierto, lo traemos al frente
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_KEY)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        return 0
    QLocalServer.removeServer(INSTANCE_KEY)
    server = QLocalServer()
    server.listen(INSTANCE_KEY)

    win = MainWindow()
    server.newConnection.connect(lambda: (server.nextPendingConnection(), win.show_page("estado")))
    win.startup(minimized="--minimizado" in sys.argv)
    if "--autotest" in sys.argv:
        QTimer.singleShot(4000, lambda: _autotest(app))
    return app.exec()


def _autotest(app):
    """Verifica que el programa compilado funcione (lo usa la compilación automática)."""
    out = storage.data_dir() / "autotest.txt"
    try:
        import numpy as np
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
        from .camera import MODEL
        opts = vision.PoseLandmarkerOptions(base_options=BaseOptions(model_asset_buffer=MODEL.read_bytes()),
                                            running_mode=vision.RunningMode.VIDEO, num_poses=1,
                                            output_segmentation_masks=True)
        with vision.PoseLandmarker.create_from_options(opts) as lm:
            img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.zeros((360, 640, 3), np.uint8))
            lm.detect_for_video(img, 1)
        out.write_text("OK", encoding="utf-8")
    except Exception as e:
        out.write_text(f"ERROR {type(e).__name__}: {e}", encoding="utf-8")
    app.exit(0)
