"""ENTRENAR: la sesión del día, guiada de punta a punta.

Flujo: elegís cómo llegás hoy → INICIAR SESIÓN → la cámara arranca sola → cada ejercicio se presenta, te ubicás,
cuenta regresiva → cuenta las repeticiones → la serie se cierra sola al llegar al objetivo (o si parás) →
descanso con cuenta regresiva y sonidos → siguiente serie → al terminar el ejercicio, una pregunta rápida de
esfuerzo (se responde sola si no tocás nada) → la progresión se ajusta → siguiente ejercicio.
"""
from __future__ import annotations

import time
from html import escape
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import coach
from ..camera import CameraWorker
from ..exercises import EXERCISES, GROUPS, VIEW_NAMES, RepCounter
from ..game import fmt
from ..i18n import plural, t
from . import holo, icons
from . import theme as T
from .video import VideoView
from .widgets import Panel, button, label, restyle

READINESS_ORDER = ["energia", "normal", "cansado", "dolorido"]
READINESS_ICON = {"energia": "zap", "normal": "activity", "cansado": "hourglass", "dolorido": "shield"}
VIEW_HINT = {"front": "de frente", "side": "de costado", "diag": "en diagonal"}


def unit(ex) -> str:
    return " s" if ex.timed else ""


def prescription(it: dict) -> str:
    ex = EXERCISES[it["ex"]]
    txt = f"{it['sets']} × {it['reps']}{unit(ex)}"
    if ex.loaded and it.get("kg"):
        txt += f"  ·  {it['kg']:g} kg"
    return txt


# ------------------------------------------------------------------ piezas visuales
class Divider(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(9)

    def paintEvent(self, e):
        p = QPainter(self)
        y = self.height() / 2
        p.setPen(QPen(QColor(63, 164, 255, 60), 1))
        p.drawLine(QPointF(0, y), QPointF(self.width(), y))


def caption(text: str) -> QLabel:
    """Etiqueta chica en mayúsculas espaciadas (estilo instrumental)."""
    lb = QLabel(text.upper())
    f = QFont(T.FONT, 8)
    f.setWeight(QFont.Weight.DemiBold)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.2)
    lb.setFont(f)
    lb.setStyleSheet(f"color:{T.MUTED};")
    return lb


class SessionRow(QPushButton):
    """Fila de la sesión: número, ejercicio, prescripción, descanso y estado."""

    def __init__(self, n: int, item: dict, done: float, target: float, current: bool = False):
        super().__init__()
        self.n, self.item, self.done, self.target, self.current = n, item, done, target, current
        self.ex = EXERCISES[item["ex"]]
        self.setFixedHeight(64)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
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
        W, H = self.width(), self.height()
        k = min(1.0, self.done / self.target) if self.target else 0.0
        complete = k >= 1
        accent = QColor(T.GREEN if complete else T.GLOW)
        if self.hover or self.current:
            p.fillRect(QRectF(0, 2, W, H - 4), QColor(63, 164, 255, 22 if self.hover else 14))
            p.fillRect(QRectF(0, 2, 2, H - 4), accent)
        p.setPen(QPen(QColor(63, 164, 255, 40), 1))
        p.drawLine(QPointF(0, H - 0.5), QPointF(W, H - 0.5))
        mono = QFont(T.FONT, 11)
        mono.setWeight(QFont.Weight.DemiBold)
        p.setFont(mono)
        p.setPen(QColor(T.MUTED))
        p.drawText(QRectF(14, 0, 34, H), Qt.AlignmentFlag.AlignVCenter, f"{self.n:02d}")
        icons.paint(p, self.ex.icon, QRectF(52, H / 2 - 11, 22, 22), T.CORE if not complete else T.GREEN, 1.6)
        f = QFont(T.FONT, 12)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(QRectF(88, 10, W * 0.42, 24), Qt.AlignmentFlag.AlignVCenter, t(self.ex.name))
        sf = QFont(T.FONT, 9)
        p.setFont(sf)
        p.setPen(QColor(T.MUTED))
        tag = t(GROUPS.get(self.ex.group, "")).upper()
        if self.item.get("recovery"):
            tag = t("RECUPERACIÓN")
        p.drawText(QRectF(88, 34, W * 0.42, 20), Qt.AlignmentFlag.AlignVCenter,
                   f"{tag}  ·  {t('mejor')} {t(VIEW_HINT.get(self.ex.best_view, ''))}")
        # prescripción y descanso
        pf = QFont(T.FONT, 13)
        pf.setWeight(QFont.Weight.Bold)
        p.setFont(pf)
        p.setPen(QColor(T.CORE))
        x = W * 0.50
        p.drawText(QRectF(x, 0, W * 0.2, H), Qt.AlignmentFlag.AlignVCenter, prescription(self.item))
        p.setFont(sf)
        p.setPen(QColor(T.MUTED))
        p.drawText(QRectF(W * 0.71, 0, W * 0.1, H), Qt.AlignmentFlag.AlignVCenter,
                   t("{s} s desc.", s=self.item.get("rest", 60)))
        # estado
        bx = W * 0.82
        bw = W - bx - 18
        r = QRectF(bx, H / 2 - 2, bw, 4)
        p.fillRect(r, QColor(20, 40, 80, 180))
        if k > 0:
            p.fillRect(QRectF(r.left(), r.top(), r.width() * k, r.height()), accent)
        p.setPen(QColor(T.GREEN if complete else T.MUTED))
        p.drawText(QRectF(bx, H / 2 + 4, bw, 18), Qt.AlignmentFlag.AlignRight,
                   t("Completo") if complete else f"{fmt(min(self.done, self.target))}/{fmt(self.target)}{unit(self.ex)}")


class Segmented(QWidget):
    """Selector de opciones (cómo llegás hoy)."""

    def __init__(self, options: list[tuple[str, str, str]], on_pick):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.btns = {}
        for key, text, ic in options:
            b = QPushButton("  " + text)
            b.setIcon(icons.icon(ic, 16))
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setProperty("kind", "seg")
            b.clicked.connect(lambda _=False, k=key: on_pick(k))
            lay.addWidget(b, 1)
            self.btns[key] = b

    def set(self, key: Optional[str]):
        for k, b in self.btns.items():
            b.setChecked(k == key)


class ChecksView(QWidget):
    """Lista de chequeos de técnica en vivo: ✓ bien, ✕ mal, ! consejo, ? no se puede verificar."""

    GLYPH = {"ok": ("check", T.GREEN), "bad": ("x", T.RED), "warn": ("triangle-alert", T.GOLD),
             "unknown": ("eye", T.MUTED)}

    def __init__(self):
        super().__init__()
        self.checks = []
        self.view = ""
        self.best = ""
        self.setMinimumHeight(120)

    def set(self, checks, view: str, best: str):
        sig = ([(c.key, c.state, c.msg) for c in checks], view, best)
        if sig != getattr(self, "_sig", None):
            self._sig = sig
            self.checks, self.view, self.best = list(checks), view, best
            self.setMinimumHeight(40 + 34 * max(1, len(self.checks)) + 30)
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W = self.width()
        y = 0
        f = QFont(T.FONT, 10)
        f.setWeight(QFont.Weight.DemiBold)
        small = QFont(T.FONT, 8)
        # vista de la cámara
        if self.view:
            good = self.view == self.best or not self.best
            col = QColor(T.GREEN if good else T.GOLD)
            p.setFont(small)
            p.setPen(QColor(T.MUTED))
            p.drawText(QRectF(0, y, W, 16), Qt.AlignmentFlag.AlignLeft, t("VISTA DE LA CÁMARA"))
            p.setFont(f)
            p.setPen(col)
            txt = t(VIEW_NAMES.get(self.view, ""))
            if not good:
                txt += "  ·  " + t("mejor {v}", v=t(VIEW_HINT.get(self.best, "")))
            p.drawText(QRectF(0, y + 16, W, 20), Qt.AlignmentFlag.AlignLeft, txt)
            y += 44
        p.setFont(small)
        p.setPen(QColor(T.MUTED))
        p.drawText(QRectF(0, y, W, 16), Qt.AlignmentFlag.AlignLeft, t("TÉCNICA"))
        y += 20
        if not self.checks:
            p.setFont(f)
            p.setPen(QColor(T.MUTED))
            p.drawText(QRectF(0, y, W, 22), Qt.AlignmentFlag.AlignLeft, t("Esperando movimiento…"))
            return
        for c in self.checks:
            ic, col = self.GLYPH.get(c.state, ("circle-alert", T.MUTED))
            r = QRectF(0, y + 3, 16, 16)
            icons.paint(p, ic, r, col, 2.0)
            p.setFont(f)
            p.setPen(QColor("white" if c.state != "unknown" else T.MUTED))
            p.drawText(QRectF(24, y, 120, 22), Qt.AlignmentFlag.AlignVCenter, t(c.label))
            if c.state != "ok" and c.msg:
                p.setFont(small)
                p.setPen(QColor(col))
                fm = p.fontMetrics()
                p.drawText(QRectF(24, y + 18, W - 24, 14), Qt.AlignmentFlag.AlignLeft,
                           fm.elidedText(t(c.msg), Qt.TextElideMode.ElideRight, int(W - 26)))
            y += 34


class SetDots(QWidget):
    def __init__(self):
        super().__init__()
        self.total, self.done, self.current = 3, 0, 0
        self.setFixedHeight(14)

    def set(self, total, done, current):
        self.total, self.done, self.current = total, done, current
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        n = max(1, self.total)
        gap = 6
        w = (self.width() - gap * (n - 1)) / n
        for i in range(n):
            r = QRectF(i * (w + gap), 4, w, 5)
            if i < self.done:
                p.fillRect(r, QColor(T.GREEN))
            elif i == self.current:
                p.fillRect(r, QColor(T.GLOW))
            else:
                p.fillRect(r, QColor(30, 60, 110, 200))


# ------------------------------------------------------------------ página
class EntrenarPage(QWidget):
    IDLE_END = 8.0       # segundos quieto (después de al menos una repetición) para cerrar la serie
    GONE_END = 6.0       # segundos sin verte para cerrar la serie
    EFFORT_WAIT = 12     # segundos para responder el esfuerzo (después se usa el estimado)

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("page")
        self.worker: Optional[CameraWorker] = None
        self.camera_failed = False
        self.items: list[dict] = []
        self.idx = 0
        self.item: Optional[dict] = None
        self.ex = None
        self.counter: Optional[RepCounter] = None
        self.state = "idle"
        self.set_no = 0
        self.set_results: list[dict] = []
        self.free = False
        self.good = self.bad = 0
        self.xp = 0.0
        self.sess_xp = 0.0
        self.sess_log: list[str] = []
        self.visible_since = None
        self.gone_since = None
        self.countdown_end = 0.0
        self.last_center = ""
        self.rest_end = 0.0
        self.effort_deadline = 0.0
        self.inferred = 2
        self.last_second_sound = -1

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_overview())
        self.stack.addWidget(self._build_free())
        self.stack.addWidget(self._build_hud())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stack)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(100)

    # ================================================================ construcción
    def _build_overview(self) -> QWidget:
        from .pages import scroll_page
        self.ov = Panel(t("SESIÓN DE HOY"), "swords")
        lay = self.ov.lay
        self.ov_meta = label("", "muted", wrap=True)
        self.ov_meta.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.ov_meta)
        self.ov_banner = label("", wrap=True)
        self.ov_banner.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.ov_banner)
        lay.addWidget(caption(t("¿Cómo llegás hoy?")))
        self.readiness = Segmented([(k, t(coach.READINESS[k]), READINESS_ICON[k]) for k in READINESS_ORDER],
                                   self._pick_readiness)
        lay.addWidget(self.readiness)
        lay.addSpacing(6)
        head = QHBoxLayout()
        for txt, stretch in ((t("EJERCICIO"), 50), (t("SERIES × REPS"), 21), (t("DESCANSO"), 11), (t("ESTADO"), 18)):
            c = caption(txt)
            head.addWidget(c, stretch)
        lay.addLayout(head)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(0)
        lay.addLayout(self.rows)
        lay.addSpacing(8)
        actions = QHBoxLayout()
        self.btn_start = button(t("INICIAR SESIÓN"), "primary", self.start_session, icon="play")
        self.btn_start.setMinimumHeight(64)
        actions.addWidget(self.btn_start, 2)
        actions.addWidget(button(t("Entrenamiento libre"), "", lambda: self.stack.setCurrentIndex(1), icon="dumbbell"), 1)
        lay.addLayout(actions)
        self.ov_foot = label("", "muted", wrap=True, align=Qt.AlignmentFlag.AlignCenter)
        self.ov_foot.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.ov_foot)
        return scroll_page(self.ov)

    def _build_free(self) -> QWidget:
        from .pages import scroll_page
        pn = Panel(t("ENTRENAMIENTO LIBRE"), "dumbbell")
        top = QHBoxLayout()
        top.addWidget(label(t("Elegí un ejercicio. Cuenta para el objetivo de hoy si está en tu sesión."), "muted",
                            wrap=True), 1)
        top.addWidget(button(t("Volver"), "", lambda: self.stack.setCurrentIndex(0), icon="arrow-left"))
        pn.lay.addLayout(top)
        self.free_grid = QGridLayout()
        self.free_grid.setSpacing(4)
        pn.lay.addLayout(self.free_grid)
        return scroll_page(pn)

    def _build_hud(self) -> QWidget:
        wrap = QWidget()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(4, 4, 12, 8)
        h.setSpacing(12)
        self.video = VideoView()
        h.addWidget(self.video, 1)

        side = Panel("", compact=True)
        side.setFixedWidth(350)
        sl = side.lay
        sl.setSpacing(6)
        self.h_pos = caption("")
        sl.addWidget(self.h_pos)
        self.h_name = QLabel("")
        nf = QFont(T.FONT, 17)
        nf.setWeight(QFont.Weight.Bold)
        self.h_name.setFont(nf)
        self.h_name.setStyleSheet("color:white;")
        self.h_name.setWordWrap(True)
        sl.addWidget(self.h_name)
        self.h_target = label("", wrap=True)
        self.h_target.setTextFormat(Qt.TextFormat.RichText)
        sl.addWidget(self.h_target)
        self.dots = SetDots()
        sl.addWidget(self.dots)
        sl.addWidget(Divider())

        self.side_stack = QStackedWidget()
        # 0: chequeos en vivo
        live = QWidget()
        ll = QVBoxLayout(live)
        ll.setContentsMargins(0, 0, 0, 0)
        self.checks = ChecksView()
        ll.addWidget(self.checks)
        self.h_quality = label("", "muted", wrap=True)
        self.h_quality.setTextFormat(Qt.TextFormat.RichText)
        ll.addWidget(self.h_quality)
        self.kg_row = QWidget()
        kr = QHBoxLayout(self.kg_row)
        kr.setContentsMargins(0, 0, 0, 0)
        kr.addWidget(caption(t("Peso por mancuerna")))
        self.kg = QDoubleSpinBox()
        self.kg.setRange(0, 80)
        self.kg.setDecimals(1)
        self.kg.setSingleStep(0.5)
        self.kg.setSuffix(" kg")
        self.kg.valueChanged.connect(self._kg_changed)
        kr.addWidget(self.kg)
        ll.addWidget(self.kg_row)
        ll.addStretch()
        self.side_stack.addWidget(live)
        # 1: pregunta de esfuerzo
        eff = QWidget()
        el = QVBoxLayout(eff)
        el.setContentsMargins(0, 0, 0, 0)
        el.addWidget(caption(t("¿Cómo te resultó?")))
        self.eff_txt = label("", "muted", wrap=True)
        self.eff_txt.setTextFormat(Qt.TextFormat.RichText)
        el.addWidget(self.eff_txt)
        self.eff_btns = {}
        for k in (1, 2, 3, 4):
            b = button(t(coach.RPE[k]), "", lambda _=False, k=k: self._answer_effort(k))
            b.setMinimumHeight(50)
            self.eff_btns[k] = b
            el.addWidget(b)
        el.addStretch()
        self.side_stack.addWidget(eff)
        sl.addWidget(self.side_stack, 1)

        sl.addWidget(Divider())
        self.h_next = label("", "muted", wrap=True)
        self.h_next.setTextFormat(Qt.TextFormat.RichText)
        sl.addWidget(self.h_next)
        self.manual_row = QWidget()
        mr = QHBoxLayout(self.manual_row)
        mr.setContentsMargins(0, 0, 0, 0)
        mr.addWidget(caption(t("Sin cámara")))
        for n in (1, 5):
            mr.addWidget(button(f"+{n}", "", lambda _=False, n=n: self.manual(n)))
        sl.addWidget(self.manual_row)
        row = QHBoxLayout()
        self.btn_set = button(t("Serie lista"), "primary", self.end_set, icon="check")
        row.addWidget(self.btn_set, 1)
        self.btn_rest_add = button("+30", "", lambda: self._add_rest(30))
        self.btn_rest_add.setFixedWidth(84)
        row.addWidget(self.btn_rest_add)
        sl.addLayout(row)
        row2 = QHBoxLayout()
        self.btn_skip = button(t("Saltar"), "", self.skip, icon="arrow-right")
        row2.addWidget(self.btn_skip, 1)
        row2.addWidget(button(t("Terminar"), "danger", self.end_session, icon="flag"), 1)
        sl.addLayout(row2)
        h.addWidget(side)
        return wrap

    # ================================================================ vista general
    def refresh(self):
        if self.stack.currentIndex() == 2:
            return
        g = self.win.game
        q = g.quest
        from .pages import clear_layout
        clear_layout(self.rows)
        self.items = g.session_items()
        self.readiness.setVisible(bool(q and not q.get("rest") and not q["completed"]))
        self.readiness.set(q.get("readiness") if q else None)
        if not q:
            return
        if q.get("rest"):
            reason = q.get("restReason") or t("Hoy es tu día de descanso.")
            self.ov_meta.setText(t("Descanso"))
            self.ov_banner.setText(f"<span style='color:{T.GREEN}'>{icons.img('moon', 15, T.GREEN)}&nbsp; "
                                   f"{escape(t(reason))}</span><br><span style='color:{T.MUTED}'>"
                                   + t("El músculo crece cuando descansás. Podés hacer entrenamiento libre si querés.")
                                   + "</span>")
            self.btn_start.setEnabled(False)
            self.ov_foot.setText("")
            return
        self.btn_start.setEnabled(True)
        mins = coach.estimate_minutes(self.items) if self.items else 0
        from ..game import PLANS
        self.ov_meta.setText(f"{t('Plan')} {t(PLANS[g.settings['plan']]['label'])}  ·  "
                             + plural(len(self.items), "{n} ejercicio", "{n} ejercicios")
                             + "  ·  " + t("~{n} min", n=mins) + "  ·  " + t("Sesión {n}", n=g.s.get("sessionsDone", 0) + 1))
        banners = []
        if q.get("penalty"):
            banners.append(f"<span style='color:{T.RED}'>{icons.img('triangle-alert', 15, T.RED)}&nbsp; "
                           + t("Día de penalización: +30% de repeticiones.") + "</span>")
        if q.get("adapted"):
            banners.append(f"<span style='color:{T.GOLD}'>{icons.img('activity', 15, T.GOLD)}&nbsp; "
                           + escape(t(q["adapted"])) + "</span>")
        if q["completed"]:
            banners.append(f"<span style='color:{T.GREEN}'>{icons.img('circle-check', 15, T.GREEN)}&nbsp; "
                           + t("Sesión completada. Podés seguir con entrenamiento libre.") + "</span>")
        self.ov_banner.setText("<br>".join(banners))
        self.ov_banner.setVisible(bool(banners))
        cur = self._first_pending()
        for i, it in enumerate(self.items):
            target = q["targets"].get(it["ex"], 0)
            done = q["progress"].get(it["ex"], 0)
            row = SessionRow(i + 1, it, done, target, current=(i == cur and not q["completed"]))
            row.clicked.connect(lambda _=False, i=i: self.start_session(i))
            self.rows.addWidget(row)
        started = any(q["progress"].get(it["ex"], 0) for it in self.items)
        self.btn_start.setText(t("CONTINUAR SESIÓN") if started and not q["completed"] else
                               t("REPETIR SESIÓN") if q["completed"] else t("INICIAR SESIÓN"))
        self.ov_foot.setText(t("La cámara se enciende sola. Las series se cierran solas al llegar al objetivo, "
                               "y el descanso arranca automáticamente."))
        self._fill_free()

    def _fill_free(self):
        from .pages import ExCard, clear_layout
        clear_layout(self.free_grid)
        g = self.win.game
        pool = g.pool()
        for i, k in enumerate(pool):
            ex = EXERCISES[k]
            p = g.prog_for(k)
            sub = f"{p['sets']} × {p['reps']}{unit(ex)}  ·  {t(GROUPS.get(ex.group, ''))}"
            b = ExCard(ex.icon, t(ex.name), sub)
            b.setMinimumHeight(160)
            b.clicked.connect(lambda _=False, k=k: self.start_free(k))
            self.free_grid.addWidget(b, i // 3, i % 3)
        locked = [k for k in EXERCISES if k not in pool]
        if locked:
            names = ", ".join(t(EXERCISES[k].name) for k in locked)
            lb = label(t("Se desbloquean más adelante o con equipamiento (Ajustes): {names}.", names=names),
                       "muted", wrap=True)
            self.free_grid.addWidget(lb, len(pool) // 3 + 1, 0, 1, 3)

    def _first_pending(self) -> int:
        q = self.win.game.quest
        for i, it in enumerate(self.items):
            if q["progress"].get(it["ex"], 0) < q["targets"].get(it["ex"], 0):
                return i
        return 0

    def _pick_readiness(self, key: str):
        why = self.win.game.set_readiness(key)
        if why:
            self.win.toaster.show(t(why), icon="activity")
        self.refresh()

    # ================================================================ sesión
    @property
    def training(self) -> bool:
        return self.stack.currentIndex() == 2 and self.state not in ("idle", "done")

    def open(self, k: str):  # compatibilidad: entrar directo a un ejercicio
        idx = next((i for i, it in enumerate(self.win.game.session_items()) if it["ex"] == k), None)
        if idx is not None:
            self.start_session(idx)
        else:
            self.start_free(k)

    def start_session(self, start: Optional[int] = None):
        g = self.win.game
        self.items = g.session_items()
        if not self.items:
            return
        self.free = False
        self.idx = self._first_pending() if start is None else start
        self.sess_xp = 0.0
        self.sess_log = []
        self._enter_hud()
        self._begin_exercise()

    def start_free(self, k: str):
        g = self.win.game
        p = g.prog_for(k)
        in_session = next((it for it in g.session_items() if it["ex"] == k), None)
        self.items = [dict(in_session) if in_session else
                      {"ex": k, "sets": p["sets"], "reps": p["reps"], "kg": p.get("kg", 0.0),
                       "rest": coach.rest_seconds(k, g.settings["plan"])}]
        self.free = in_session is None
        self.idx = 0
        self.sess_xp = 0.0
        self.sess_log = []
        self._enter_hud()
        self._begin_exercise()

    def _enter_hud(self):
        self.stack.setCurrentIndex(2)
        if not self.worker and not self.camera_failed:
            self.start_camera()
        self.manual_row.setVisible(self.camera_failed)

    def _begin_exercise(self):
        self.item = self.items[self.idx]
        self.ex = EXERCISES[self.item["ex"]]
        self.set_no = 0
        self.set_results = []
        q = self.win.game.quest
        # si ya hiciste parte de este ejercicio hoy, se retoma desde las series que faltan
        if q and not self.free:
            done = q["progress"].get(self.ex.id, 0)
            self.set_no = min(self.item["sets"] - 1, int(done // max(1, self.item["reps"])))
        self.h_pos.setText(t("Ejercicio {i} de {n}", i=self.idx + 1, n=len(self.items)) if not self.free
                           else t("Entrenamiento libre"))
        self.h_name.setText(t(self.ex.name))
        self.kg_row.setVisible(self.ex.loaded)
        if self.ex.loaded:
            self.kg.blockSignals(True)
            self.kg.setValue(self.item.get("kg", 0.0))
            self.kg.blockSignals(False)
        self.side_stack.setCurrentIndex(0)
        if self.worker:
            self.worker.equip_kinds = {self.ex.equip} if self.ex.equip else set()
        self._new_set()
        self._update_next()
        self.win.voice.say(t(self.ex.name), True)

    def _new_set(self):
        self.counter = RepCounter(self.ex)
        self.good = self.bad = 0
        self.xp = 0.0
        self.gone_since = None
        self.video.count = "0"
        self.video.progress = 0
        self.video.center = ""
        self._update_target()
        tip = t(self.ex.tip)
        if self.worker or not self.camera_failed:
            self.state = "position"
            self.visible_since = None
            self.video.center_small = ""
            self.video.set_feedback(t("Ubicate: {v}", v=t(VIEW_HINT.get(self.ex.best_view, "de costado"))), "")
            self.h_quality.setText(f"<span style='color:{T.MUTED}'>{escape(tip)}</span>")
        else:
            self.state = "running"
            self.video.set_feedback(t("Modo sin cámara: usá +1 / +5 y «Serie lista»"), "")
        self._buttons()

    def _update_target(self):
        it = self.item
        tgt = it["reps"]
        kg = f"  ·  {it.get('kg', 0):g} kg" if self.ex.loaded and it.get("kg") else ""
        self.h_target.setText(
            f"<span style='color:{T.MUTED}'>{t('SERIE')}</span> <b style='color:white'>{self.set_no + 1}/{it['sets']}</b>"
            f"&nbsp;&nbsp;<span style='color:{T.MUTED}'>{t('OBJETIVO')}</span> "
            f"<b style='color:{T.GLOW}'>{tgt}{unit(self.ex)}</b>{kg}")
        self.dots.set(it["sets"], self.set_no, self.set_no)
        self.video.target = f"/ {tgt}{unit(self.ex)}"

    def _update_next(self):
        if self.free or self.idx + 1 >= len(self.items):
            self.h_next.setText(f"{t('A CONTINUACIÓN')}<br><span style='color:white'>{t('Fin de la sesión')}</span>")
            return
        nx = self.items[self.idx + 1]
        self.h_next.setText(f"{t('A CONTINUACIÓN')}<br>{icons.img(EXERCISES[nx['ex']].icon, 14)}&nbsp; "
                            f"<span style='color:white'>{t(EXERCISES[nx['ex']].name)}</span>  ·  {prescription(nx)}")

    def _buttons(self):
        resting = self.state == "rest"
        self.btn_rest_add.setVisible(resting)
        self.btn_set.setText(t("Empezar ya") if resting else t("Serie lista"))
        self.btn_set.setEnabled(self.state in ("running", "rest", "position", "countdown"))
        self.btn_skip.setText(t("Saltar"))

    # ================================================================ cámara
    def start_camera(self):
        s = self.win.game.s["settings"]
        self.video.center_small = t("Iniciando cámara y modelo de visión…")
        self.video.update()
        self.worker = CameraWorker(s.get("camera", 0), s.get("mirror", True), self)
        self.worker.ready.connect(self.on_ready)
        self.worker.status.connect(lambda m: (setattr(self.video, "center_small", t(m)), self.video.update()))
        self.worker.failed.connect(self.on_failed)
        self.worker.frame.connect(self.on_frame)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def on_ready(self):
        self.win.atmo.paused = True
        if self.worker and self.ex is not None:
            self.worker.equip_kinds = {self.ex.equip} if self.ex.equip else set()
        self.video.center_small = ""

    def on_failed(self, msg: str):
        self.camera_failed = True
        self.manual_row.show()
        self.win.toaster.show(t("No pude usar la cámara: modo sin cámara (70% XP)"), icon="camera-off")
        if self.state == "position":
            self.state = "running"
            self.video.set_feedback(t("Modo sin cámara: usá +1 / +5 y «Serie lista»"), "")
            self._buttons()

    def on_worker_finished(self):
        self.worker = None
        self.win.atmo.paused = False
        self.video.clear()

    def stop_camera(self):
        if self.worker:
            self.worker.stop()

    # ================================================================ cuadro a cuadro
    def on_frame(self, img, lm, world, aspect, t_):
        if self.worker:
            QTimer.singleShot(0, self.worker.ack)
        v = self.video
        v.objects = list(getattr(self.worker, "objects", []) or [])
        color = T.GLOW
        st = self.state
        if self.ex is None or st in ("idle", "done"):
            v.set_frame(img, lm, color, world)
            return
        if st in ("rest", "effort"):
            v.set_frame(img, lm, T.MUTED, world)
            return
        if lm is None:
            if st == "position":
                self.visible_since = None
                v.center_small = t("Buscando tu cuerpo…")
            elif st == "running" and (self.good or self.bad or self.counter.seconds):
                self.gone_since = self.gone_since or t_
                if t_ - self.gone_since > self.GONE_END:
                    self.end_set()
                    return
            v.set_feedback(t("No te detecto: alejate y que se vea todo tu cuerpo"), "bad")
            v.set_frame(img, None, color)
            return
        self.gone_since = None
        if st == "position":
            m = self.ex.measure(lm, world, aspect, {})
            ready = m.visible and not m.hint
            if ready:
                self.visible_since = self.visible_since or t_
                v.center_small = t("Te veo. Quedate en posición…")
                v.set_feedback(t("Vista: {v}", v=t(VIEW_NAMES.get(m.view, "")).capitalize()), "")
                if t_ - self.visible_since > 1.0:
                    self.state = "countdown"
                    self.countdown_end = time.monotonic() + 3
                    self.last_center = ""
                    v.center_small = ""
            else:
                self.visible_since = None
                v.center_small = t(m.hint) if m.hint else t("Ubicate para que se vea todo el ejercicio")
            self.checks.set(m.checks, m.view, self.ex.best_view)
        elif st == "running" and self.counter is not None:
            color = self.process(lm, world, aspect, t_)
        v.set_frame(img, lm, color, world)

    def process(self, lm, world, aspect, t_) -> str:
        r = self.counter.update(lm, world, aspect, t_)
        ex, v, g = self.ex, self.video, self.win.game
        self.checks.set(r.checks, r.view, ex.best_view)
        if ex.timed:
            if r.event == "second":
                self.good += r.count
                secs = int(self.counter.seconds)
                v.count = str(secs)
                self.xp += g.add_reps(ex.id, r.count)
                left = self.item["reps"] - secs
                if 0 < left <= 3:
                    self.win.sounds.play("beep")
                elif secs % 10 == 0:
                    self.win.sounds.play("tick")
                    self.win.voice.say(t("{n} segundos", n=secs))
                else:
                    self.win.sounds.play("second")
                v.progress = min(1.0, secs / max(1, self.item["reps"]))
                if secs >= self.item["reps"]:
                    QTimer.singleShot(200, self.end_set)
            col = {"ok": T.GREEN, "warn": T.GOLD, "unknown": T.MUTED}.get(r.status, T.RED)
            tone = {"ok": "good", "warn": "warn", "unknown": "warn"}.get(r.status, "bad")
            v.set_feedback(t(r.msg) if r.msg else "", tone)
            if r.status in ("bad", "unknown", "hint") and r.msg:
                self.win.voice.say(t(r.msg))
            self._quality_line()
            return col

        if r.progress is not None:
            v.progress = r.progress
        if r.event == "rep":
            self.good += 1
            v.count = str(self.counter.reps)
            v.bump()
            self.win.sounds.play("rep")
            self.win.voice.say(str(self.counter.reps), True)
            self.xp += g.add_reps(ex.id, 1)
            v.set_feedback(t(r.msg), "good" if r.msg == "¡Perfecta!" else "warn")
            if self.good >= self.item["reps"]:
                QTimer.singleShot(500, self.end_set)
        elif r.event in ("bad", "partial"):
            if r.event == "bad":
                self.bad += 1
            self.win.sounds.play("bad")
            self.win.voice.say(t(r.msg))
            v.set_feedback(t(r.msg) + (t(" (no cuenta)") if r.event == "bad" else ""), "bad")
        elif r.status == "hint" and r.msg:
            v.set_feedback(t(r.msg), "warn")
        elif r.msg and r.status == "warn":
            v.set_feedback(t(r.msg), "warn")
        self._quality_line()
        return {"warn": T.GOLD, "ok": T.GLOW, "unknown": T.GLOW}.get(r.status, T.RED)

    def _quality_line(self):
        c = self.counter
        if self.ex.timed:
            tot = c.timed_good + c.timed_bad
            k = c.timed_good / tot if tot else 1.0
            txt = t("Tiempo válido {p}%", p=int(k * 100))
        else:
            n = len(c.log)
            if not n:
                return
            k = sum(1 for r in c.log if r["clean"]) / n
            ver = sum(1 for r in c.log if r["verified"]) / n
            txt = t("Técnica limpia {p}%", p=int(k * 100))
            if ver < 1:
                txt += "  ·  " + t("{p}% sin verificar", p=int((1 - ver) * 100))
        col = T.GREEN if k >= 0.85 else T.GOLD if k >= 0.6 else T.RED
        self.h_quality.setText(f"<span style='color:{col}'><b>{txt}</b></span>")

    def manual(self, n: int):
        if not self.ex or self.state not in ("running", "position"):
            return
        self.state = "running"
        self.good += n
        self.video.count = str(self.good)
        self.video.bump()
        self.xp += self.win.game.add_reps(self.ex.id, n, manual=True)
        if self.good >= self.item["reps"]:
            QTimer.singleShot(300, self.end_set)

    # ================================================================ reloj: cuentas regresivas, descansos, inactividad
    def _tick(self):
        now = time.monotonic()
        v = self.video
        if self.state == "countdown":
            left = self.countdown_end - now
            txt = str(int(left) + 1) if left > 0 else t("¡YA!")
            if txt != self.last_center:
                self.last_center = txt
                v.center = txt
                self.win.sounds.play("beep_go" if left <= 0 else "beep")
                v.update()
            if left <= 0:
                self.state = "running"
                self.counter = RepCounter(self.ex)
                self.counter.last_activity = None
                self._run_started = now
                self.win.voice.say(t("Empezá"), True)
                QTimer.singleShot(600, lambda: setattr(self.video, "center", "") if self.state == "running" else None)
                self._buttons()
        elif self.state == "running" and self.worker and self.counter is not None:
            # cierre automático: quieto un rato después de haber hecho algo
            c = self.counter
            did = self.good or self.bad or c.seconds >= 1
            if did and c.last_activity and c.last_t is not None and c.phase == "rest":
                idle = c.last_t - c.last_activity
                if idle > self.IDLE_END:
                    v.center_small = ""
                    self.end_set()
                elif idle > self.IDLE_END - 3:
                    v.center_small = t("¿Terminaste? La serie se cierra en {n} s", n=int(self.IDLE_END - idle) + 1)
                elif v.center_small:
                    v.center_small = ""
        elif self.state == "rest":
            left = self.rest_end - now
            if left <= 0:
                self._rest_done()
                return
            v.rest = (left, self._rest_total, t("DESCANSO"), self._rest_sub)
            v.update()
            txt = str(int(left) + 1)
            if txt != getattr(self, "_rest_txt", ""):
                self._rest_txt = txt
                n = int(left) + 1
                if n <= 3:
                    self.win.sounds.play("beep")
                elif n == 10:
                    self.win.sounds.play("tick")
                    self.win.voice.say(t("Diez segundos"))

        elif self.state == "effort":
            left = self.effort_deadline - now
            self.eff_btns[self.inferred].setText(f"{t(coach.RPE[self.inferred])}  ·  {int(max(0, left)) + 1}")
            if left <= 0:
                self._answer_effort(None)

    # ================================================================ series
    def end_set(self):
        if self.state == "rest":
            self._rest_done()
            return
        if self.state not in ("running", "position", "countdown") or self.counter is None:
            return
        if self.state != "running" and not (self.good or self.bad):
            # todavía no empezó: "Serie lista" = arrancar ya sin esperar la cuenta
            self.state = "countdown"
            self.countdown_end = time.monotonic()
            return
        summ = self.counter.summary() if not self.camera_failed else {"good": self.good, "bad": 0, "quality": 1.0,
                                                                        "verified": 0.0, "slowdown": 1.0}
        summ["good"] = self.good if self.ex.timed or self.camera_failed else summ["good"]
        self.set_results.append(summ)
        g = self.win.game
        if self.good or self.bad:
            rec = g.finish_set(self.ex.id, self.good, self.bad, self.xp)
            if rec:
                self.win.toaster.show(t("Récord personal: {n}{u} en una serie", n=fmt(self.good), u=unit(self.ex)),
                                      gold=True, icon="trophy")
        self.sess_xp += self.xp
        self.win.sounds.play("set")
        self.set_no += 1
        self.dots.set(self.item["sets"], self.set_no, self.set_no)
        tgt = self.item["reps"]
        msg = t("Serie {n}: {g}/{t}{u}", n=self.set_no, g=self.good, t=tgt, u=unit(self.ex))
        if self.set_no >= self.item["sets"]:
            self.video.set_feedback(msg, "good" if self.good >= tgt else "warn")
            self._ask_effort()
        else:
            self._start_rest(self.item.get("rest", 60), msg)

    def _start_rest(self, seconds: int, msg: str = ""):
        self.state = "rest"
        self._rest_total = seconds
        self.rest_end = time.monotonic() + seconds
        self.video.count = ""
        self.video.target = ""
        self.video.center = self.video.center_small = ""
        self._rest_sub = t("Después: serie {n} de {m}  ·  {r}{u}", n=self.set_no + 1, m=self.item["sets"],
                           r=self.item["reps"], u=unit(self.ex))
        self.video.rest = (seconds, seconds, t("DESCANSO"), self._rest_sub)
        self.video.set_feedback(msg, "good")
        self._update_target()
        self._buttons()

    def _add_rest(self, s: int):
        if self.state == "rest":
            self.rest_end += s
            self._rest_total += s

    def _rest_done(self):
        self.video.rest = None
        self._rest_txt = ""
        self.win.sounds.play("beep_go")
        self.win.voice.say(t("Serie {n}", n=self.set_no + 1), True)
        self.video.center = ""
        self._new_set()

    # ================================================================ esfuerzo y progresión
    def _ask_effort(self):
        self.state = "effort"
        self.video.count = ""
        self.video.target = ""
        self.video.progress = 0
        self.video.center_small = ""
        tgt = self.item["reps"]
        self.inferred = coach.infer_rpe(self.set_results, tgt)
        done = "  ·  ".join(str(s["good"]) for s in self.set_results)
        self.eff_txt.setText(t("Series: {done}. Si no elegís, uso mi estimación.", done=done))
        for k, b in self.eff_btns.items():
            b.setText(t(coach.RPE[k]))
            b.setProperty("kind", "primary" if k == self.inferred else "")
            restyle(b)
        self.side_stack.setCurrentIndex(1)
        self.effort_deadline = time.monotonic() + self.EFFORT_WAIT
        self._buttons()

    def _answer_effort(self, rpe: Optional[int]):
        if self.state != "effort":
            return
        g = self.win.game
        in_session = self.ex.id in g.quest.get("targets", {}) if g.quest else False
        if in_session and not g.quest.get("rest"):
            kind, txt = g.record_exercise(self.ex.id, self.set_results, rpe)
            word = {"up": t("Sube"), "down": t("Baja"), "hold": t("Se mantiene")}.get(kind, "")
            nice = txt
            self.sess_log.append(f"{icons.img(self.ex.icon, 14)}&nbsp; <b>{t(self.ex.name)}</b>: {word} → {nice}")
            self.win.toaster.show(f"{t(self.ex.name)}: {word} → {nice}", gold=kind == "up",
                                  icon="trending-up" if kind == "up" else "activity")
        self.side_stack.setCurrentIndex(0)
        self.idx += 1
        if self.idx >= len(self.items):
            self._finish_session()
        else:
            self.state = "between"
            self.video.center_small = t("Siguiente: {name}", name=t(EXERCISES[self.items[self.idx]["ex"]].name))
            QTimer.singleShot(1800, self._next_exercise)

    def _next_exercise(self):
        if self.state == "between":
            self._begin_exercise()

    def skip(self):
        if self.state in ("idle", "done"):
            return
        if self.set_results or self.good or self.bad:
            if self.state == "running" and (self.good or self.bad):
                self.end_set()
                if self.state == "effort":
                    return
            self.state = "effort"
            self._answer_effort(None)
            return
        self.idx += 1
        if self.idx >= len(self.items):
            self._finish_session()
        else:
            self._begin_exercise()

    def _finish_session(self):
        g = self.win.game
        self.state = "done"
        q = g.quest
        rem = g.remaining() if q else []
        lines = "<br>".join(self.sess_log) or t("Sin cambios de progresión.")
        status = (f"<span style='color:{T.GREEN}'>{t('Objetivo de hoy cumplido.')}</span>" if q and q["completed"] else
                  f"<span style='color:{T.GOLD}'>" + t("Falta hoy: {list}", list="  ·  ".join(
                      f"{t(EXERCISES[k].name)} {fmt(v)}" for k, v in rem)) + "</span>" if rem else "")
        self.win.dialogs.show(t("SESIÓN TERMINADA"),
                              f"<span style='font-size:22px;color:{T.GOLD}'><b>+{fmt(self.sess_xp)} XP</b></span><br><br>"
                              f"<b>{t('Próxima vez')}</b><br>{lines}<br><br>{status}", icon="flag")
        self.end_session(silent=True)

    def end_session(self, silent: bool = False):
        if not silent and self.state == "running" and (self.good or self.bad):
            self.end_set()
        self.state = "idle"
        self.video.rest = None
        self.ex = None
        self.item = None
        self.counter = None
        self.video.center = self.video.center_small = ""
        self.video.count = "0"
        self.stop_camera()
        self.camera_failed = False
        self.stack.setCurrentIndex(0)
        self.refresh()

    def _kg_changed(self, v: float):
        if self.ex and self.ex.loaded:
            self.item["kg"] = v
            self.win.game.set_weight_kg(self.ex.id, v)
            self._update_target()

    # compatibilidad con la ventana principal
    def update_stats(self):
        pass

    def finish(self):
        self.end_session()
