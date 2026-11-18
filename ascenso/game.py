"""Reglas del Sistema: XP, niveles, rangos, misión diaria, penalizaciones, logros."""
from __future__ import annotations

import copy
import time
from datetime import date, datetime, timedelta
from html import escape
from typing import Callable, Optional

from .exercises import EXERCISE_ORDER, EXERCISES
from .storage import Store

DIFFICULTY = {
    "facil":   {"label": "Fácil",   "reward": 100, "targets": {"pushup": 10, "squat": 15, "situp": 10, "jack": 20}},
    "normal":  {"label": "Normal",  "reward": 200, "targets": {"pushup": 20, "squat": 30, "situp": 20, "jack": 40, "plank": 30}},
    "dificil": {"label": "Difícil", "reward": 350, "targets": {"pushup": 50, "squat": 60, "situp": 50, "jack": 80, "plank": 60}},
    "extremo": {"label": "Extremo", "reward": 600, "targets": {"pushup": 100, "squat": 100, "situp": 100, "plank": 120}},
}
DIFF_ORDER = list(DIFFICULTY)

RANKS = [(75, "S"), (50, "A"), (35, "B"), (20, "C"), (10, "D"), (1, "E")]


def rank_of(level: int) -> str:
    return next(r for lv, r in RANKS if level >= lv)


def xp_needed(level: int) -> int:
    return round(80 * level ** 1.4 + 20)


def total_reps(s) -> int:
    return sum(s["totals"].get(e, 0) for e in EXERCISE_ORDER if e != "plank")


STATS = {
    "FUE": ("Fuerza", lambda t, s: t["pushup"] // 15 + t["squat"] // 30),
    "AGI": ("Agilidad", lambda t, s: t["jack"] // 40 + t["lunge"] // 20),
    "RES": ("Resistencia", lambda t, s: t["situp"] // 20 + int(t["plank"]) // 60 + t["squat"] // 30),
    "DIS": ("Disciplina", lambda t, s: s["questsDone"] + s["bestStreak"] // 3),
}

ACHIEVEMENTS = [
    ("first", "El Despertar", "Completá tu primera repetición", lambda s: total_reps(s) >= 1 or s["totals"]["plank"] >= 1),
    ("quest1", "Jugador", "Completá tu primera misión diaria", lambda s: s["questsDone"] >= 1),
    ("streak3", "Constante", "Racha de 3 días", lambda s: s["bestStreak"] >= 3),
    ("streak7", "Imparable", "Racha de 7 días", lambda s: s["bestStreak"] >= 7),
    ("streak30", "Voluntad de Hierro", "Racha de 30 días", lambda s: s["bestStreak"] >= 30),
    ("push100", "Brazos de Acero", "100 flexiones en total", lambda s: s["totals"]["pushup"] >= 100),
    ("push1000", "Rompe Pisos", "1.000 flexiones en total", lambda s: s["totals"]["pushup"] >= 1000),
    ("squat1000", "Piernas de Titán", "1.000 sentadillas en total", lambda s: s["totals"]["squat"] >= 1000),
    ("plank600", "Muralla", "10 minutos de plancha en total", lambda s: s["totals"]["plank"] >= 600),
    ("reps5000", "Máquina", "5.000 repeticiones en total", lambda s: total_reps(s) >= 5000),
    ("lvl10", "Cazador Rango D", "Llegá al nivel 10", lambda s: s["player"]["level"] >= 10),
    ("lvl20", "Cazador Rango C", "Llegá al nivel 20", lambda s: s["player"]["level"] >= 20),
    ("lvl50", "Élite", "Llegá al nivel 50", lambda s: s["player"]["level"] >= 50),
    ("extremo", "Monarca del Esfuerzo", "Completá una misión en dificultad Extremo", lambda s: s["extremeDone"] >= 1),
    ("redemption", "Redención", "Completá una misión de penalización", lambda s: s["penaltiesCleared"] >= 1),
]


def new_state() -> dict:
    return {
        "version": 2,
        "player": {"name": "", "level": 1, "xp": 0.0, "freePoints": 0,
                   "alloc": {k: 0 for k in STATS}, "createdAt": time.time()},
        "settings": {
            "difficulty": "facil", "voice": True, "sound": True, "camera": 0, "mirror": True,
            "nag": {"enabled": True, "startHour": 18, "intervalMin": 20, "snoozesPerDay": 2, "hard": False},
        },
        "quest": None,
        "streak": 0, "bestStreak": 0, "questsDone": 0, "extremeDone": 0, "penaltiesCleared": 0,
        "totals": {e: 0 for e in EXERCISE_ORDER},
        "history": {},
        "achievements": [],
        "log": [],
        "guardian": {"date": "", "snoozes": 0, "surrender": False},
    }


def _merge(base: dict, extra: dict) -> dict:
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict) and k not in ("history",):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def fmt(n) -> str:
    return f"{int(n):,}".replace(",", ".")


class Game:
    """Contiene el estado y aplica las reglas. Avisa a la interfaz mediante `on_event`.

    Eventos: ("modal", dict(title, body, color, sound)), ("toast", dict(text, gold)),
             ("say", dict(text, force)), ("changed", {})
    """

    def __init__(self, store: Store | None = None, on_event: Optional[Callable] = None,
                 today: Optional[Callable[[], date]] = None):
        self.store = store or Store()
        self.on_event = on_event or (lambda kind, data: None)
        self._today = today or date.today
        loaded = self.store.load()
        self.s = _merge(new_state(), loaded) if loaded else new_state()

    # ------------------------------------------------------------ helpers
    def today(self) -> str:
        return self._today().isoformat()

    def save(self):
        self.store.save(self.s)

    def emit(self, kind, **data):
        self.on_event(kind, data)

    def modal(self, title, body, color="", sound="open"):
        self.emit("modal", title=title, body=body, color=color, sound=sound)

    def log(self, msg):
        self.s["log"].insert(0, {"t": time.time(), "msg": msg})
        del self.s["log"][150:]

    @property
    def player(self):
        return self.s["player"]

    @property
    def quest(self):
        return self.s["quest"]

    @property
    def registered(self) -> bool:
        return bool(self.player["name"])

    def stat_value(self, k) -> int:
        return 10 + self.player["alloc"].get(k, 0) + STATS[k][1](self.s["totals"], self.s)

    def current_title(self) -> str:
        for aid, title, *_ in reversed(ACHIEVEMENTS):
            if aid in self.s["achievements"]:
                return title
        return "Ninguno"

    # ------------------------------------------------------------ registro
    def register(self, name: str, difficulty: str):
        self.player["name"] = name.strip()[:24]
        self.s["settings"]["difficulty"] = difficulty
        self.new_quest(self.today(), False)
        self.log(f"{self.player['name']} despertó como Jugador.")
        self.save()
        self.emit("changed")

    # ------------------------------------------------------------ XP / niveles
    def gain_xp(self, amount: float):
        p = self.player
        p["xp"] += amount
        leveled = 0
        while p["xp"] >= xp_needed(p["level"]):
            p["xp"] -= xp_needed(p["level"])
            old_rank = rank_of(p["level"])
            p["level"] += 1
            p["freePoints"] += 3
            leveled += 1
            self.log(f"¡Subiste al nivel {p['level']}!")
            new_rank = rank_of(p["level"])
            if new_rank != old_rank:
                self.log(f"Rango ascendido: {old_rank} → {new_rank}")
                self.modal("ASCENSO DE RANGO",
                           f"Tu rango cambió de <b>{old_rank}</b> a "
                           f"<span style='font-size:30px;color:#ffd166'><b>{new_rank}</b></span><br>"
                           "El Sistema reconoce tu esfuerzo.", "gold", "level")
        if leveled:
            self.emit("say", text=f"Subiste de nivel. Nivel {p['level']}", force=True)
            self.modal("¡SUBISTE DE NIVEL!",
                       f"NIVEL <span style='font-size:34px;color:#ffd166'><b>{p['level']}</b></span><br>"
                       f"+{3 * leveled} puntos de estadística para asignar.<br>"
                       "<small>Repartilos en la pestaña Estado.</small>", "gold", "level")

    def allocate(self, stat: str):
        if self.player["freePoints"] > 0 and stat in STATS:
            self.player["freePoints"] -= 1
            self.player["alloc"][stat] += 1
            self.save()
            self.emit("changed")

    # ------------------------------------------------------------ misión diaria
    def build_targets(self, penalty: bool) -> dict:
        d = DIFFICULTY.get(self.s["settings"]["difficulty"], DIFFICULTY["facil"])
        scale = min(2.0, 1 + ((self.player["level"] - 1) // 5) * 0.1) * (1.5 if penalty else 1)
        return {k: int(-(-v * scale // 5) * 5) for k, v in d["targets"].items()}

    def new_quest(self, day: str, penalty: bool):
        self.s["quest"] = {
            "date": day, "penalty": penalty, "difficulty": self.s["settings"]["difficulty"],
            "targets": self.build_targets(penalty), "progress": {}, "completed": False,
        }

    def set_difficulty(self, diff: str):
        self.s["settings"]["difficulty"] = diff
        q = self.quest
        if q and not q["completed"] and not any(q["progress"].values()):
            q["difficulty"] = diff
            q["targets"] = self.build_targets(q["penalty"])
            self.emit("toast", text="Misión de hoy actualizada", gold=False)
        self.save()
        self.emit("changed")

    def rollover(self) -> bool:
        """Cierra el día anterior si cambió la fecha. Devuelve True si hubo cambio."""
        if not self.registered:
            return False
        today = self.today()
        q = self.quest
        if not q:
            self.new_quest(today, False)
            self.save()
            return True
        if q["date"] == today:
            return False

        self.s["history"][q["date"]] = {k: q[k] for k in ("completed", "penalty", "progress", "targets")}
        gap = (date.fromisoformat(today) - date.fromisoformat(q["date"])).days
        if gap < 0:  # el reloj fue para atrás: reiniciamos sin castigar
            self.new_quest(today, False)
            self.save()
            return True
        for i in range(1, gap):
            d = (date.fromisoformat(q["date"]) + timedelta(days=i)).isoformat()
            self.s["history"][d] = {"completed": False, "penalty": False, "progress": {}, "targets": q["targets"]}
        missed = (0 if q["completed"] else 1) + max(0, gap - 1)

        if missed:
            p = self.player
            lost = min(p["xp"], round(xp_needed(p["level"]) * 0.15 * min(missed, 5)))
            p["xp"] -= lost
            prev = self.s["streak"]
            self.s["streak"] = 0
            self.log(f"PENALIZACIÓN: {missed} día(s) sin cumplir. -{fmt(lost)} XP. Racha perdida ({prev}).")
            self.new_quest(today, True)
            dias = f" durante <b>{missed} días</b>" if missed > 1 else ""
            self.modal("PENALIZACIÓN",
                       f"No completaste la misión diaria{dias}.<br><br>"
                       f"<span style='color:#ff3b5c'><b>-{fmt(lost)} XP</b></span> · Racha perdida: {prev} días<br><br>"
                       "Hoy te toca la <b>MISIÓN DE PENALIZACIÓN</b> (+50% de volumen).<br>"
                       "Si la cumplís, recuperás el honor.", "red", "alarm")
        else:
            self.new_quest(today, False)
        self.save()
        self.emit("changed")
        return True

    def remaining(self) -> list[tuple[str, float]]:
        q = self.quest
        if not q:
            return []
        return [(k, t - q["progress"].get(k, 0)) for k, t in q["targets"].items() if q["progress"].get(k, 0) < t]

    def _check_complete(self):
        q = self.quest
        if q["completed"] or self.remaining():
            return
        q["completed"] = True
        s = self.s
        s["streak"] += 1
        s["bestStreak"] = max(s["bestStreak"], s["streak"])
        s["questsDone"] += 1
        if q["difficulty"] == "extremo":
            s["extremeDone"] += 1
        if q["penalty"]:
            s["penaltiesCleared"] += 1
        base = DIFFICULTY.get(q["difficulty"], DIFFICULTY["facil"])["reward"]
        bonus = min(200, s["streak"] * 10)
        total = round(base * (1.5 if q["penalty"] else 1) + bonus)
        self.log(f"Misión diaria completada. +{fmt(total)} XP. Racha: {s['streak']}")
        self.emit("say", text="Misión diaria completada", force=True)
        tipo = "misión de penalización" if q["penalty"] else "misión diaria"
        self.modal("MISIÓN COMPLETADA",
                   f"Completaste la {tipo}.<br><br>"
                   f"<span style='font-size:26px;color:#ffd166'><b>+{fmt(total)} XP</b></span><br>"
                   f"Racha: <b>{s['streak']}</b> día{'s' if s['streak'] != 1 else ''} (+{bonus} bonus)<br>"
                   "Disciplina +1<br><br><small>Hoy el Sistema te deja en paz. Mañana, más.</small>",
                   "gold", "level")
        self.gain_xp(total)

    def add_reps(self, ex: str, n: float, manual: bool = False) -> float:
        """Suma repeticiones (o segundos de plancha). Devuelve la XP ganada."""
        if n <= 0 or not self.registered:
            return 0.0
        self.rollover()
        self.s["totals"][ex] = self.s["totals"].get(ex, 0) + n
        q = self.quest
        if ex in q["targets"]:
            before = q["progress"].get(ex, 0)
            q["progress"][ex] = before + n
            if before < q["targets"][ex] <= q["progress"][ex]:
                name = EXERCISES[ex].name
                self.emit("toast", text=f"✔ {name}: objetivo cumplido", gold=True)
                self.emit("say", text=f"Objetivo de {name} cumplido", force=True)
        xp = n * EXERCISES[ex].xp * (0.7 if manual else 1.0)
        self.gain_xp(xp)
        self._check_complete()
        self.check_achievements()
        self.save()
        self.emit("changed")
        return xp

    def log_set(self, ex: str, good: float, bad: int, xp: float):
        e = EXERCISES[ex]
        unit = " seg" if e.timed else " reps"
        extra = f", {bad} mal hechas" if bad else ""
        self.log(f"Serie de {e.name}: {fmt(good)}{unit}{extra}. +{fmt(xp)} XP")
        self.save()

    def check_achievements(self):
        for aid, title, desc, test in ACHIEVEMENTS:
            if aid not in self.s["achievements"] and test(self.s):
                self.s["achievements"].append(aid)
                self.log(f"Logro desbloqueado: {title}")
                self.modal("LOGRO DESBLOQUEADO",
                           f"Título obtenido:<br><span style='font-size:22px;color:#ffd166'><b>«{escape(title)}»</b></span>"
                           f"<br><small>{escape(desc)}</small>", "gold", "open")

    # ------------------------------------------------------------ Guardián
    def guardian(self) -> dict:
        g = self.s["guardian"]
        if g.get("date") != self.today():
            g.update(date=self.today(), snoozes=0, surrender=False)
        return g

    def nag_settings(self) -> dict:
        return self.s["settings"]["nag"]

    def should_nag(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now()
        nag = self.nag_settings()
        if not nag["enabled"] or not self.registered:
            return False
        self.rollover()
        if self.quest["completed"] or self.guardian()["surrender"]:
            return False
        return now.hour >= int(nag["startHour"])

    def snooze(self):
        self.guardian()["snoozes"] += 1
        self.save()

    def snoozes_left(self) -> int:
        return max(0, int(self.nag_settings()["snoozesPerDay"]) - self.guardian()["snoozes"])

    def surrender(self):
        self.guardian()["surrender"] = True
        self.log("Te rendiste por hoy. El Sistema no lo olvida.")
        self.save()

    # ------------------------------------------------------------ datos
    def export(self) -> dict:
        return copy.deepcopy(self.s)

    def import_state(self, data: dict):
        if not isinstance(data, dict) or "player" not in data:
            raise ValueError("Archivo inválido")
        self.s = _merge(new_state(), data)
        self.save()
        self.emit("changed")

    def reset(self):
        self.s = new_state()
        self.save()
        self.emit("changed")
