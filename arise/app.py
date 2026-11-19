"""Ventana principal, bandeja del sistema y arranque."""
from __future__ import annotations

import sys

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QLabel, QButtonGroup, QHBoxLayout, QMainWindow, QMenu, QPushButton,
                               QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

from . import storage
from .i18n import lang, plural, t
from .exercises import EXERCISES as EX
from .game import PLAN_ORDER, PLANS, Game, rank_of
from .guardian import Guardian
from .ui import theme as T
from .ui.body_page import CuerpoPage
from .ui.pages import AjustesPage, EstadoPage, MisionPage, RegistroPage
from .ui.train_page import EntrenarPage
from .ui import icons
from .ui.atmosphere import Atmosphere
from .ui.notify import Notifier
from .ui.widgets import Dialogs, GlowLabel, NavIndicator, ScanReveal, Toaster, button, label
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
    """Barra lateral: otra ventana holográfica flotante."""

    def __init__(self):
        super().__init__()
        from .ui import holo
        self._holo = holo
        self._sf = type("NavSurface", (QWidget, holo.Surface), {  # i18n: no
            "surface_spec": lambda w: holo.SurfaceSpec(QRectF(w.rect()).adjusted(18, 18, -18, -18), "", cut=12,
                                                       brackets=True, seed=77, glass_alpha=150, density=0.8),
            "paintEvent": lambda w, e: w.paint_surface(_aa(QPainter(w))),
        })(self)
        self._sf.surface_init()
        self._sf.lower()

    def resizeEvent(self, e):
        self._sf.setGeometry(self.rect())


def _aa(p):
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    return p


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
        import arise.voice as _voice
        _voice.SOUNDS_REF = self.sounds
        self.voice = Voice()
        self.dialogs = Dialogs(self, self.sounds)
        self.notifier = Notifier(self.sounds)
        self.toaster = Toaster(self, self.notifier)
        self.game = Game(on_event=self.on_game_event)
        self.apply_settings()

        # ventana sin marco y translúcida: solo se ven las ventanas holográficas y el humo
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        root = Atmosphere()
        root.setObjectName("root")
        root.setMouseTracking(True)
        self.atmo = root
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(34, 40, 34, 36)
        outer.setSpacing(0)
        outer.addWidget(self._build_titlebar())
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        outer.addLayout(h, 1)

        nav = NavRail()
        nav.setObjectName("nav")
        nav.setFixedWidth(240)
        nl = QVBoxLayout(nav)
        nl.setContentsMargins(22, 34, 22, 32)
        nl.setSpacing(2)
        brand = GlowLabel("ARISE", 26, QFont.Weight.Bold, align=Qt.AlignmentFlag.AlignCenter, spacing=9, glow=1.2)
        nl.addWidget(brand)
        nl.addWidget(label("T R A I N E R", "brandSub", align=Qt.AlignmentFlag.AlignCenter))
        nl.addSpacing(26)
        self.nav_group = QButtonGroup(self)
        self.nav_buttons = {}
        for key, text, ic in PAGES:
            b = QPushButton("  " + t(text))
            b.setIcon(icons.icon(ic, 18))
            b.setIconSize(QSize(18, 18))
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.show_page(k))
            self.nav_group.addButton(b)
            self.nav_buttons[key] = b
            nl.addWidget(b)
        nl.addStretch()
        self.nav_ind = NavIndicator(nav)
        self.nav_ind.lower()
        nav._sf.lower()
        self.nav_player = label("", "navPlayer", align=Qt.AlignmentFlag.AlignCenter)
        nl.addWidget(self.nav_player)
        h.addWidget(nav)

        content = QWidget()
        self.content = content
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
        from .wellness import Wellness
        self.wellness = Wellness(self)
        self._setup_tray()

        self.pending_update = None
        self._downloading = False
        self._ready_notified = False
        self.update_timer = QTimer(self)  # busca actualizaciones cada 30 minutos mientras la app está abierta
        self.update_timer.timeout.connect(lambda: self._auto_update_enabled() and self.check_updates())
        self.install_timer = QTimer(self)
        self.install_timer.setSingleShot(True)
        self.install_timer.timeout.connect(self._maybe_install_update)

        self.day_timer = QTimer(self)
        self.day_timer.timeout.connect(self.game.rollover)
        self.day_timer.start(60_000)

        self.atmo.installEventFilter(self)
        self.show_page("estado")

    # ------------------------------------------------------------ barra superior y bordes
    def _build_titlebar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(50)
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(14, 4, 4, 0)
        hl.setSpacing(4)
        tl = label("ARISE TRAINER  ·  " + t("SISTEMA ACTIVO"), "lbl")  # i18n: no
        tl.setStyleSheet(f"color:{T.GLOW};font-size:11px;letter-spacing:3px;")
        hl.addWidget(tl)
        hl.addStretch()
        for ic, slot, kind in (("minus", self.showMinimized, ""), ("square", self._toggle_max, ""),
                               ("x", self.close, "danger")):
            b = button("", kind, slot, icon=ic)
            b.setFixedSize(58, 48)
            hl.addWidget(b)
        bar.mouseDoubleClickEvent = lambda e: self._toggle_max()
        bar._titlebar = True
        bar.installEventFilter(self)
        return bar

    def _toggle_max(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def _edges(self, pos) -> Qt.Edge:
        m = 8
        r = self.rect()
        e = Qt.Edge(0)
        if pos.x() <= m:
            e |= Qt.Edge.LeftEdge
        if pos.x() >= r.width() - m:
            e |= Qt.Edge.RightEdge
        if pos.y() <= m:
            e |= Qt.Edge.TopEdge
        if pos.y() >= r.height() - m:
            e |= Qt.Edge.BottomEdge
        return e

    def eventFilter(self, obj, ev):
        from PySide6.QtCore import QEvent
        if obj is self.atmo or getattr(obj, "_titlebar", False):
            if ev.type() == QEvent.Type.MouseButtonPress and ev.button() == Qt.MouseButton.LeftButton:
                pos = obj.mapTo(self, ev.position().toPoint())
                edges = self._edges(pos)
                wh = self.windowHandle()
                if wh is not None:
                    if edges and not self.isMaximized():
                        wh.startSystemResize(edges)
                        return True
                    if pos.y() < 48:
                        wh.startSystemMove()
                        return True
            elif ev.type() == QEvent.Type.MouseMove and obj is self.atmo:
                e = self._edges(obj.mapTo(self, ev.position().toPoint()))
                cursors = {Qt.Edge.LeftEdge: Qt.CursorShape.SizeHorCursor, Qt.Edge.RightEdge: Qt.CursorShape.SizeHorCursor,
                           Qt.Edge.TopEdge: Qt.CursorShape.SizeVerCursor, Qt.Edge.BottomEdge: Qt.CursorShape.SizeVerCursor}
                if e in cursors:
                    obj.setCursor(cursors[e])
                elif e:
                    tl_br = (Qt.Edge.TopEdge | Qt.Edge.LeftEdge, Qt.Edge.BottomEdge | Qt.Edge.RightEdge)
                    obj.setCursor(Qt.CursorShape.SizeFDiagCursor if e in tl_br else Qt.CursorShape.SizeBDiagCursor)
                else:
                    obj.unsetCursor()
        return super().eventFilter(obj, ev)

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
            if training and data.get("key") not in ("OBJETIVO CUMPLIDO", "PENALIZACIÓN"):
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
        self.sounds.set_volume(st.get("volume", 70) / 100)
        if hasattr(self, "atmo"):
            self.atmo.set_quality(st.get("quality", "alto"))

    # ------------------------------------------------------------ actualizaciones
    def check_updates(self, manual: bool = False):
        """Consulta GitHub Releases. En automático descarga e instala sola en segundo plano."""
        from . import updater
        import time as _time
        self._last_update_check = _time.monotonic()

        def done(info, err):
            QTimer.singleShot(0, lambda: self._update_result(info, err, manual))
        updater.check_async(done)

    def _auto_update_enabled(self) -> bool:
        import sys as _sys
        return (self.game.s["settings"].get("autoUpdate", True) and _sys.platform == "win32"
                and getattr(_sys, "frozen", False))

    def _update_result(self, info, err, manual):
        from . import updater
        if err or not info:
            if manual:
                self.notifier.show(t("SIN CONEXIÓN"), t("No pude consultar si hay versión nueva. Probá más tarde."),
                                   "circle-alert", "", timeout=6)
            return
        if not updater.is_newer(info["version"]):
            if manual:
                self.notifier.show(t("ESTÁS AL DÍA"), t("Tenés la última versión ({v}).", v=updater.VERSION), "circle-check", "",
                                   timeout=5)
            return
        if self.pending_update and self.pending_update["version"] == info["version"]:
            self._maybe_install_update(manual)
            return
        if self._auto_update_enabled() or manual:
            self._download_update(info, show_progress=manual)
        else:
            self.notifier.show(t("ACTUALIZACIÓN DISPONIBLE"),
                               t("Hay una versión nueva: <b>{new}</b> (tenés {old}).", new=info["version"], old=updater.VERSION),
                               "download", "gold", timeout=30,
                               actions=[(t("Actualizar"), lambda i=info: self._download_update(i, True))])

    def _download_update(self, info, show_progress=False):
        from . import updater
        import sys as _sys
        if not info.get("url") or _sys.platform != "win32" or not getattr(_sys, "frozen", False):
            import webbrowser
            webbrowser.open(updater.RELEASES_PAGE)
            return
        if self._downloading:
            return
        self._downloading = True
        card = body = None
        if show_progress:
            card = self.notifier.show(t("DESCARGANDO ACTUALIZACIÓN"), "0%", "download", "", timeout=0)
            body = card.findChildren(QLabel)[-1]

        def prog(k):
            if body is not None:
                QTimer.singleShot(0, lambda: body.setText(f"{int(k * 100)}%"))

        def done(path, err):
            def ui():
                self._downloading = False
                if card is not None:
                    card.dismiss()
                if err or not path:
                    if show_progress:
                        self.notifier.show(t("ERROR"), t("No se pudo descargar la actualización: {e}", e=err), "circle-alert",
                                           "red", timeout=8)
                    return
                self.pending_update = {"version": info["version"], "path": path}
                self._maybe_install_update(force=show_progress)
            QTimer.singleShot(0, ui)
        updater.download_async(info["url"], prog, done, info.get("sha256"))

    def _app_busy(self) -> bool:
        return (self.is_training() or self.dialogs.busy or bool(self.guardian.windows)
                or self.pages["cuerpo"].stack.currentIndex() == 1)

    def _maybe_install_update(self, force: bool = False):
        """Instala la actualización descargada cuando no estás usando la app (o al toque si lo pediste)."""
        upd = self.pending_update
        if not upd:
            return
        if self._app_busy():
            self.install_timer.start(120_000)  # reintenta en 2 minutos
            return
        idle = not self.isVisible() or self.isMinimized() or not self.isActiveWindow()
        if force or idle:
            self._install_now()
            return
        if not self._ready_notified:
            self._ready_notified = True
            self.notifier.show(t("ACTUALIZACIÓN LISTA"),
                               t("La versión <b>{v}</b> ya está descargada. Se instala sola cuando no estés usando la "
                                 "app (o al cerrarla).", v=upd["version"]), "download", "gold", timeout=12,
                               actions=[(t("Instalar ahora"), self._install_now)])
        self.install_timer.start(120_000)

    def _check_failed_update(self):
        """Si la última instalación automática no se completó, avisa y ofrece instalar con el asistente."""
        from . import updater
        import os as _os
        tried = self.game.s.get("remind", {}).get("updateTried")
        if not tried or not updater.is_newer(tried.get("version", "")):
            return
        path = tried.get("path", "")
        if not _os.path.exists(path):
            return
        QTimer.singleShot(6000, lambda: self.notifier.show(
            t("ACTUALIZACIÓN PENDIENTE"),
            t("La versión <b>{v}</b> no se pudo instalar sola. Tocá «Instalar» para abrir el instalador.", v=tried["version"]),
            "download", "gold", timeout=0,
            actions=[(t("Instalar"), lambda: (updater.run_installer(path, silent=False), self._really_quit()))]))

    def _remember_install(self, upd):
        self.game.s.setdefault("remind", {})["updateTried"] = {"version": upd["version"], "path": upd["path"]}
        self.game.save()

    def _install_now(self):
        from . import updater
        upd = self.pending_update
        if not upd:
            return
        self._remember_install(upd)
        self.install_timer.stop()
        self._installing = True  # evita que _really_quit lo vuelva a lanzar
        self.notifier.show(t("ACTUALIZANDO"), t("Instalando la versión {v}… La app se vuelve a abrir sola.", v=upd["version"]),
                           "download", "gold", timeout=4)
        self.game.save()
        QTimer.singleShot(1200, lambda: (updater.run_installer(upd["path"]), self._really_quit()))

    def refresh(self):
        if not hasattr(self, "pages"):
            return
        p = self.game.player
        self.nav_player.setText(f"<b style='color:white'>{p['name'] or '—'}</b><br>"
                                + t("NV {n} · RANGO {r}", n=p["level"], r=rank_of(p["level"])))
        current = self.stack.currentWidget()
        for page in self.pages.values():
            if page is current or page in (self.pages["estado"], self.pages["mision"]):
                page.refresh()
        if self.tray:
            q = self.game.quest
            state = (t("Día de descanso") if q and q.get("rest") else t("Objetivo cumplido") if q and q["completed"]
                     else t("Objetivo pendiente"))
            self.tray.setToolTip(t("Arise Trainer — {name} · Nivel {n}", name=p["name"], n=p["level"]) + f"\n{state}")

    def _maybe_check_on_open(self):
        """Al abrir la ventana, busca actualizaciones si pasaron más de 15 minutos desde la última vez."""
        import time as _time
        if self._auto_update_enabled() and _time.monotonic() - getattr(self, "_last_update_check", 0) > 15 * 60:
            self.check_updates()

    def show_page(self, key: str):
        self._maybe_check_on_open()
        changed = self.stack.currentWidget() is not self.pages[key]
        self.stack.setCurrentWidget(self.pages[key])
        self.nav_buttons[key].setChecked(True)
        self.pages[key].refresh()
        b = self.nav_buttons[key]
        QTimer.singleShot(0, lambda b=b: self.nav_ind.move_to(b.geometry(), True))
        if changed and self.isVisible():
            if not hasattr(self, "_reveal"):
                self._reveal = ScanReveal(self.content)
            self._reveal.play(self.pages[key])
            self.sounds.play("hover")
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
        for text, slot in ((t("Abrir Arise Trainer"), lambda: self.show_page("estado")),
                           (t("Objetivo de hoy"), lambda: self.show_page("mision")),
                           (t("Entrenar"), lambda: self.show_page("entrenar"))):
            a = QAction(text, menu)
            a.triggered.connect(slot)
            menu.addAction(a)
        menu.addSeparator()
        quit_a = QAction(t("Salir"), menu)
        quit_a.triggered.connect(self.quit_app)
        menu.addAction(quit_a)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: r == QSystemTrayIcon.ActivationReason.Trigger and self.show_page("estado"))
        self.tray.show()
        self._tray_menu = menu

    def tray_message(self, title, text, tone="red", icon="triangle-alert"):
        self.notifier.show(title.upper(), text, icon, tone, timeout=8, sound="alarm" if tone == "red" else "notify")

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
            self.notifier.show(t("SIGO ACTIVO"), t("Arise Trainer queda funcionando al lado del reloj para recordarte "
                                                   "el objetivo del día."), "eye", "", timeout=6)

    def quit_app(self):
        q = self.game.quest
        if q and not q["completed"] and self.game.nag_settings()["enabled"] and self.game.registered:
            def answer(i, _):
                if i == 1:
                    self._really_quit()
            self.bring_to_front()
            self.dialogs.show(t("¿SALIR?"), t("El objetivo de hoy todavía no está cumplido.<br>Si cerrás la app no vas a "
                                              "recibir recordatorios, pero la penalización a medianoche se aplica igual."),
                              ((t("Me quedo"), "primary"), (t("Salir igual"), "danger")), tone="red", callback=answer)
        else:
            self._really_quit()

    def restart_app(self):
        """Reinicia la app (por ejemplo, al cambiar el idioma)."""
        from PySide6.QtCore import QProcess
        srv = getattr(QApplication.instance(), "arise_server", None)
        if srv:
            srv.close()
        args = sys.argv[1:] if getattr(sys, "frozen", False) else [sys.argv[0]] + sys.argv[1:]
        args = [a for a in args if a not in ("--minimizado", "--actualizado")]
        self.game.save()
        QProcess.startDetached(sys.executable, args)
        self._really_quit()

    def _really_quit(self):
        from . import updater
        if self.pending_update and not getattr(self, "_installing", False):
            self._installing = True
            self._remember_install(self.pending_update)
            updater.run_installer(self.pending_update["path"], relaunch=False)
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
            d.show(t("REGISTRO"), t("¿Cómo te llamás?"), (t("Confirmar"),), callback=got_name,
                   with_input=True, placeholder=t("Tu nombre"), icon="user-round")

        def got_name(_, name):
            if not name.strip():
                ask_name()
                return
            self._name = name.strip()
            plans = "<br>".join(f"<b>{t(p['label'])}</b>: <span style='color:#7f95bf'>{t(p['desc'])}</span>"
                                for p in PLANS.values())
            d.show(t("PLAN"), t("Elegí tu punto de partida.") + f"<br><br><div style='text-align:left'>{plans}</div><br><small>"
                   + t("La progresión es automática: cada ejercicio sube cuando lo hacés bien y sin demasiado esfuerzo. "
                       "Podés cambiar el nivel en Ajustes.") + "</small>",
                   ((t("Principiante"), "primary"), (t("Intermedio"), ""), (t("Avanzado"), ""), (t("Extremo"), "danger")),
                   callback=got_plan, icon="target")

        def got_plan(i, _):
            self.game.register(self._name, PLAN_ORDER[max(0, i)])
            self.game.settings["lang"] = lang()
            d.show(t("EQUIPAMIENTO"), t("¿Qué tenés para entrenar en casa?<br><small>Suma ejercicios con barra y "
                                        "mancuernas a tu rotación. Se cambia en Ajustes.</small>"),
                   ((t("Nada"), ""), (t("Barra"), ""), (t("Mancuernas"), ""), (t("Las dos"), "primary")),
                   callback=got_equipment, icon="dumbbell")

        def got_equipment(i, _):
            self.game.settings["equipment"] = [[], ["bar"], ["dumbbell"], ["bar", "dumbbell"]][max(0, i)]
            self.game.new_quest(self.game.today(), False)
            self.game.save()
            self.refresh()
            if storage.autostart_supported():
                d.show(t("RECORDATORIOS"), t("¿Querés que Arise Trainer arranque solo al prender la compu?<br>"
                                             "<small>Así los recordatorios funcionan aunque te olvides de abrirlo.</small>"),
                       ((t("Sí"), "primary"), (t("No"), "")), icon="bell-ring",
                       callback=lambda i, _: (storage.set_autostart(i == 0), show_quest()))
            else:
                show_quest()

        def show_quest():
            q = self.game.quest
            if q.get("rest"):
                body = t("Hoy es tu día de descanso. Tu primer objetivo arranca mañana.<br><small>Los días de descanso "
                         "se configuran en Ajustes.</small>")
            else:
                body = t("Tu sesión de hoy:") + "<br><br>" + "<br>".join(self._quest_lines())
            d.show(t("OBJETIVO DIARIO"), body, (t("Empezar"),), icon="target",
                   callback=lambda *_: self.show_page("entrenar"))

        def intro():
            self._intro_dialog(ask_name)

        def pick_lang(i, _):
            code = ["es", "en", "pt"][max(0, i)]
            if code != lang():
                self.game.s["settings"]["lang"] = code
                self.game.save()
                self.restart_app()
                return
            intro()

        d.show("IDIOMA · LANGUAGE", "Elegí el idioma · Choose your language · Escolha o idioma",
               (("Español", "primary" if lang() == "es" else ""), ("English", "primary" if lang() == "en" else ""),
                ("Português", "primary" if lang() == "pt" else "")), callback=pick_lang, icon="languages")

    def _intro_dialog(self, ask_name):
        self.dialogs.show(t("NOTIFICACIÓN"),
                          t("Bienvenido a <b style='color:#4fd8ff'>Arise Trainer</b>.<br><br>"
                            "Cada día tenés una sesión de entrenamiento. Cumplirla suma XP, racha y nivel.<br>"
                            "Fallarla tiene penalización.<br><br>La cámara cuenta tus repeticiones y revisa tu técnica: "
                            "solo valen las bien hechas."),
                          (t("Empezar"),), callback=ask_name)

    def _welcome(self):
        g = self.game
        q = g.quest
        if q and q.get("rest"):
            txt = t("Hoy es día de descanso.")
        elif q and q["completed"]:
            txt = t("El objetivo de hoy ya está cumplido.")
        else:
            rem = g.remaining()
            txt = (t("Objetivo de hoy:") + " " + " · ".join(f"{t(EX[k].name)} {int(v)}" for k, v in rem[:3])) if rem else ""
        self.notifier.show(t("SISTEMA ACTIVO · NIVEL {n}", n=g.player["level"]),
                           t("Bienvenido de vuelta, <b>{name}</b>.", name=g.player["name"]) + f"<br>{txt}", "power", "",
                           timeout=6, sound="open", on_click=lambda: self.show_page("mision"))

    def _quest_lines(self):
        from .exercises import EXERCISES
        out = []
        for it in self.game.session_items():
            e = EXERCISES[it["ex"]]
            out.append(f"{t(e.name)}: <b>{it['sets']} × {it['reps']}{' s' if e.timed else ''}</b>")
        return out

    def startup(self, minimized: bool):
        storage.migrate_autostart()
        self.apply_settings()
        if self.game.s["settings"].get("autoUpdate", True):
            QTimer.singleShot(8000, self.check_updates)
        self.update_timer.start(30 * 60 * 1000)
        self._check_failed_update()
        if "--actualizado" in sys.argv:
            from ._version import VERSION
            QTimer.singleShot(2500, lambda: self.notifier.show(
                t("ACTUALIZADO"), t("Arise Trainer se actualizó a la versión <b>{v}</b>.", v=VERSION), "circle-check", "gold",
                timeout=8, sound="level", on_click=lambda: self.show_page("estado")))
        if not minimized:
            self.show()
        if not self.game.registered:
            self.show()
            QTimer.singleShot(300, self.start_onboarding)
        else:
            self.game.rollover()
            self.game.check_achievements()
            self.refresh()
            QTimer.singleShot(1200, self._welcome)
            rem = self.game.s.setdefault("remind", {})
            if self.game.checkin_due() and rem.get("checkin") != self.game.today():
                rem["checkin"] = self.game.today()  # una sola vez por día, aunque abras y cierres la app
                self.game.save()
                QTimer.singleShot(4000, lambda: self.notifier.show(
                    t("CONTROL SEMANAL"), t("Hoy te toca el control corporal: 3 fotos y tu peso."), "scan-line", "gold",
                    actions=[(t("Hacer ahora"), lambda: (self.show_page("cuerpo"), self.pages["cuerpo"].start_checkin()))],
                    timeout=15))
        QTimer.singleShot(5000, self.guardian.check)
        QTimer.singleShot(9000, self.wellness.check)


def main():
    if sys.platform == "win32":
        try:  # ícono propio en la barra de tareas
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("arise.trainer")
        except Exception:
            pass
    if sys.platform == "win32":
        try:  # lo usa el instalador para saber si la app está abierta y cerrarla al actualizar
            import ctypes
            global _MUTEX
            _MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, "AriseTrainerAppMutex")
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
    app.arise_server = server

    # idioma: el elegido, o el del sistema la primera vez
    from .i18n import set_lang, system_lang
    try:
        data = storage.Store().load() or {}
    except Exception:
        data = {}
    set_lang((data.get("settings") or {}).get("lang") or system_lang())

    win = MainWindow()
    server.newConnection.connect(lambda: (server.nextPendingConnection(), win.show_page("estado")))
    win.startup(minimized="--minimizado" in sys.argv or "--actualizado" in sys.argv)
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
        # traducciones empaquetadas y detector de equipamiento
        from .i18n import lang, set_lang, t
        prev = lang()
        for code, word in (("en", "Set done"), ("pt", "Série pronta")):  # i18n: no
            set_lang(code)
            if t("Serie lista") != word:
                raise RuntimeError(f"falta el idioma {code}")  # i18n: no
        set_lang(prev)
        from .equipment import EquipmentDetector
        EquipmentDetector({"bar", "dumbbell"}).process(np.zeros((360, 640, 3), np.uint8), None)
        out.write_text("OK", encoding="utf-8")
    except Exception as e:
        out.write_text(f"ERROR {type(e).__name__}: {e}", encoding="utf-8")
    app.exit(0)
