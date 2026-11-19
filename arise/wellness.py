"""Recordatorios de agua y sueño. Ayudan, no castigan: no hay pérdida de XP ni rachas en juego.

Agua: si vas atrasado respecto de tu meta para esta hora, avisa cada tanto (con botón "+1 vaso") hasta que te
pongas al día. Sueño: aviso suave antes de la hora de dormir, "hora de dormir" con "me voy a dormir", y a la
mañana te pregunta cómo dormiste (si dormiste poco, la sesión te sugiere ir más tranqui).
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, QTimer

from .i18n import t


def _hm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


class Wellness(QObject):
    CHECK_MS = 60_000

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.game = win.game
        self.next_water = time.time() + 20 * 60  # no avisar apenas abrís la app
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check)
        self.timer.start(self.CHECK_MS)

    @property
    def rem(self) -> dict:
        return self.game.s.setdefault("remind", {})

    def check(self, now: datetime | None = None):
        try:
            if not self.game.registered:
                return
            now = now or datetime.now()
            self._water(now)
            self._sleep(now)
        except Exception as e:  # nunca debe romper la app
            print("Bienestar:", e)

    # ------------------------------------------------------------ agua
    def _water(self, now: datetime):
        st = self.game.settings["water"]
        if not st.get("enabled", True) or time.time() < self.next_water:
            return
        if self.win.is_training() or self.win.dialogs.busy:
            return
        start, end = int(st.get("start", 9)), int(st.get("end", 22))
        if not start <= now.hour < end:
            return
        goal = self.game.water_goal()
        should, have = self.game.water_pace(now)
        glass = int(st.get("glassMl", 250))
        if have >= goal or should - have < glass:
            self.next_water = time.time() + 15 * 60
            return
        self.next_water = time.time() + int(st.get("everyMin", 90)) * 60
        txt = t("Llevás {have} de {goal} L. Tomá un vaso de agua.", have=f"{have / 1000:.1f}",
                goal=f"{goal / 1000:.1f}")
        self.win.notifier.show(t("HIDRATACIÓN"), txt, "glass-water", "",
                               actions=[(t("+1 vaso"), lambda: self.drink(glass)),
                                        (t("En 30 min"), self.water_later)],
                               timeout=30, sound="water")

    def drink(self, ml: int):
        total = self.game.add_water(ml)
        self.win.sounds.play("water")
        goal = self.game.water_goal()
        if total < goal:
            self.win.toaster.show(t("Agua: {have} / {goal} L", have=f"{total / 1000:.1f}", goal=f"{goal / 1000:.1f}"),
                                  icon="droplet")

    def water_later(self):
        self.next_water = time.time() + 30 * 60

    # ------------------------------------------------------------ sueño
    def _sleep(self, now: datetime):
        st = self.game.settings["sleep"]
        if not st.get("enabled", True):
            return
        today = now.date().isoformat()
        bh, bm = _hm(st.get("bed", "23:30"))
        wh, wm = _hm(st.get("wake", "07:30"))
        bed = now.replace(hour=bh, minute=bm, second=0, microsecond=0)
        wake = now.replace(hour=wh, minute=wm, second=0, microsecond=0)
        if bed < wake and now > wake:  # se acuesta pasada la medianoche (ej. 00:30)
            bed += timedelta(days=1)
        r = self.rem
        # mañana: ¿cómo dormiste?
        if wake <= now < wake + timedelta(hours=6) and today not in self.game.s["sleepLog"] \
                and r.get("morning") != today:
            r["morning"] = today
            self.game.save()
            self._ask_morning()
            return
        if not st.get("remind", True) or self.win.is_training():
            return
        if bed - timedelta(minutes=30) <= now < bed and r.get("bedSoon") != today:
            r["bedSoon"] = today
            self.game.save()
            self.win.notifier.show(t("SE ACERCA LA HORA DE DORMIR"),
                                   t("En 30 minutos. Bajá el brillo y dejá las pantallas: dormir bien también es entrenar."),
                                   "moon", "", timeout=12, sound="sleep")
        elif bed <= now < bed + timedelta(hours=2) and r.get("bed") != today \
                and time.time() >= r.get("bedSnooze", 0) and not r.get("sleepStart"):
            r["bed"] = today
            self.game.save()
            self.win.notifier.show(t("HORA DE DORMIR"),
                                   t("Objetivo: {h} h de sueño. Tocá «Me voy a dormir» y mañana te digo cuánto dormiste.",
                                     h=f"{self.game.sleep_target_hours():g}"),
                                   "bed", "", actions=[(t("Me voy a dormir"), self.going_to_sleep),
                                                       (t("En 30 min"), self.bed_later)],
                                   timeout=40, sound="sleep")

    def going_to_sleep(self):
        self.game.sleep_start()
        self.win.toaster.show(t("Buenas noches. Mañana registramos cuánto dormiste."), icon="moon")

    def bed_later(self):
        r = self.rem
        r["bed"] = ""
        r["bedSnooze"] = time.time() + 30 * 60
        self.game.save()

    def _ask_morning(self):
        hours = self.game.pending_sleep()
        if hours:
            txt = t("Dormiste ~{h} h. ¿Cómo descansaste?", h=f"{hours:g}")
            acts = [(t("Bien"), lambda: self.game.log_sleep(hours, "bien")),
                    (t("Regular"), lambda: self.game.log_sleep(hours, "regular")),
                    (t("Mal"), lambda: self.game.log_sleep(hours, "mal"))]
        else:
            target = self.game.sleep_target_hours()
            txt = t("¿Cómo dormiste anoche?")
            acts = [(t("Bien ({h} h)", h=f"{target:g}"), lambda: self.game.log_sleep(target, "bien")),
                    (t("Poco"), lambda: self.game.log_sleep(min(5.5, target - 2), "mal")),
                    (t("Registrar"), lambda: self.win.show_page("mision"))]
        self.win.notifier.show(t("BUEN DÍA"), txt, "sunrise", "", actions=acts, timeout=60, sound="notify")
