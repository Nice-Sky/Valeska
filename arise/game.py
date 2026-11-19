"""Reglas: XP, niveles, rangos, objetivo diario, progresión, récords, descanso y penalizaciones."""
from __future__ import annotations

import copy
import math
import time
from datetime import date, datetime, timedelta
from html import escape
from typing import Callable, Optional

from . import coach
from .exercises import EXERCISE_ORDER, EXERCISES
from .i18n import t
from .storage import Store

PLANS = {
    "principiante": {"label": "Principiante", "reward": 100,
                     "desc": "Para arrancar o volver después de un tiempo parado.",
                     "targets": {"pushup": 10, "squat": 20, "situp": 15, "plank": 30}},
    "intermedio":   {"label": "Intermedio", "reward": 200,
                     "desc": "Ya entrenás con algo de regularidad.",
                     "targets": {"pushup": 25, "squat": 40, "situp": 30, "jack": 50, "plank": 60}},
    "avanzado":     {"label": "Avanzado", "reward": 350,
                     "desc": "Buena base física, querés exigirte.",
                     "targets": {"pushup": 50, "squat": 75, "situp": 50, "jack": 100, "plank": 90}},
    "extremo":      {"label": "Extremo", "reward": 600,
                     "desc": "100 flexiones, 100 abdominales, 100 sentadillas y 2 minutos de plancha. Todos los días.",
                     "targets": {"pushup": 100, "squat": 100, "situp": 100, "plank": 120}},
}
PLAN_ORDER = list(PLANS)
_OLD_PLANS = {"facil": "principiante", "normal": "intermedio", "dificil": "avanzado", "extremo": "extremo"}

WEEKDAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
PENALTY_FACTOR = 1.3
PROGRESS_EVERY = 7      # cada 7 días cumplidos...
PROGRESS_STEP = 0.05    # ...los objetivos suben 5%
PROGRESS_MAX = 2.5

RANKS = [(75, "S"), (50, "A"), (35, "B"), (20, "C"), (10, "D"), (1, "E")]


def rank_of(level: int) -> str:
    return next(r for lv, r in RANKS if level >= lv)


def next_rank(level: int):
    for lv, r in sorted(RANKS):
        if lv > level:
            return lv, r
    return None


def xp_needed(level: int) -> int:
    return round(80 * level ** 1.4 + 20)


def total_reps(s) -> int:
    return sum(s["totals"].get(e, 0) for e in EXERCISE_ORDER if e != "plank")


def fmt(n) -> str:
    return f"{int(n):,}".replace(",", ".")


# Atributos calculados a partir de tus récords y volumen real (no se reparten a mano)
STATS = {
    "FUE": ("Fuerza", "Récords y volumen de flexiones, sentadillas, dominadas y pesas",
            lambda s, r, t: 10 + r["pushup"] // 2 + r["squat"] // 4 + t["pushup"] // 150 + t["squat"] // 300
            + r.get("pullup", 0) + r.get("chinup", 0) // 2 + (t.get("curl", 0) + t.get("press", 0) + t.get("row", 0)) // 200),
    "RES": ("Resistencia", "Récords de plancha y abdominales, y volumen total",
            lambda s, r, t: 10 + int(r["plank"]) // 10 + r["situp"] // 4 + t["situp"] // 150 + int(t["plank"]) // 300
            + int(r.get("side_plank", 0)) // 15),
    "AGI": ("Agilidad", "Récords y volumen de jumping jacks, zancadas y escaladores",
            lambda s, r, t: 10 + r["jack"] // 6 + r["lunge"] // 4 + t["jack"] // 300 + t["lunge"] // 150
            + r.get("climber", 0) // 8),
}

ACHIEVEMENTS = [
    ("first", "Primer paso", "Primera repetición registrada", lambda s: total_reps(s) >= 1 or s["totals"]["plank"] >= 1),
    ("quest1", "Primer día cumplido", "Completá tu primer objetivo diario", lambda s: s["questsDone"] >= 1),
    ("streak7", "Una semana sin fallar", "Racha de 7 días", lambda s: s["bestStreak"] >= 7),
    ("streak30", "Un mes sin fallar", "Racha de 30 días", lambda s: s["bestStreak"] >= 30),
    ("streak100", "100 días", "Racha de 100 días", lambda s: s["bestStreak"] >= 100),
    ("push100", "100 flexiones", "100 flexiones en total", lambda s: s["totals"]["pushup"] >= 100),
    ("push1000", "1.000 flexiones", "1.000 flexiones en total", lambda s: s["totals"]["pushup"] >= 1000),
    ("pr30", "30 seguidas", "30 flexiones en una sola serie", lambda s: s["records"]["pushup"] >= 30),
    ("pr50", "50 seguidas", "50 flexiones en una sola serie", lambda s: s["records"]["pushup"] >= 50),
    ("squat1000", "1.000 sentadillas", "1.000 sentadillas en total", lambda s: s["totals"]["squat"] >= 1000),
    ("plank120", "2 minutos firmes", "Plancha de 2 minutos en una serie", lambda s: s["records"]["plank"] >= 120),
    ("reps5000", "5.000 repeticiones", "5.000 repeticiones en total", lambda s: total_reps(s) >= 5000),
    ("reps25000", "25.000 repeticiones", "25.000 repeticiones en total", lambda s: total_reps(s) >= 25000),
    ("rankD", "Rango D", "Llegá al nivel 10", lambda s: s["player"]["level"] >= 10),
    ("rankC", "Rango C", "Llegá al nivel 20", lambda s: s["player"]["level"] >= 20),
    ("rankB", "Rango B", "Llegá al nivel 35", lambda s: s["player"]["level"] >= 35),
    ("rankA", "Rango A", "Llegá al nivel 50", lambda s: s["player"]["level"] >= 50),
    ("rankS", "Rango S", "Llegá al nivel 75", lambda s: s["player"]["level"] >= 75),
    ("extremo", "Plan extremo", "Cumplí un día en el plan Extremo", lambda s: s["extremeDone"] >= 1),
    ("redemption", "Deuda saldada", "Cumplí un día de penalización", lambda s: s["penaltiesCleared"] >= 1),
    ("pull1", "Primera dominada", "Tu primera dominada con buena técnica", lambda s: s["records"].get("pullup", 0) >= 1),
    ("pull10", "10 dominadas seguidas", "10 dominadas en una sola serie", lambda s: s["records"].get("pullup", 0) >= 10),
    ("sessions25", "25 sesiones", "Completá 25 sesiones de entrenamiento", lambda s: s.get("sessionsDone", 0) >= 25),
    ("water7", "Bien hidratado", "Cumplí tu meta de agua 7 días", lambda s: sum(1 for v in s.get("water", {}).values() if v.get("done")) >= 7),
    ("sleep7", "Descanso de verdad", "7 noches durmiendo lo que te propusiste", lambda s: sum(1 for v in s.get("sleepLog", {}).values() if v.get("ok")) >= 7),
    ("checkin1", "Punto de partida", "Hacé tu primer control corporal", lambda s: len(s.get("checkins", [])) >= 1),
    ("checkin4", "Un mes documentado", "4 controles corporales", lambda s: len(s.get("checkins", [])) >= 4),
    ("checkin12", "Tres meses de cambios", "12 controles corporales", lambda s: len(s.get("checkins", [])) >= 12),
]


def new_state() -> dict:
    return {
        "version": 3,
        "player": {"name": "", "level": 1, "xp": 0.0, "createdAt": time.time()},
        "settings": {
            "plan": "principiante", "autoProgress": True, "restDays": [6], "checkinDay": 0,
            "voice": True, "sound": True, "camera": 0, "mirror": True, "volume": 70, "quality": "alto",
            "autoUpdate": True, "lang": "", "equipment": [], "adjustableKg": True, "autoSets": True,
            "nag": {"enabled": True, "startHour": 18, "intervalMin": 20, "snoozesPerDay": 2, "hard": False},
            "water": {"enabled": True, "goalMl": 0, "glassMl": 250, "start": 9, "end": 22, "everyMin": 90},
            "sleep": {"enabled": True, "bed": "23:30", "wake": "07:30", "remind": True},
        },
        "progression": 1.0, "progressCount": 0,
        "quest": None,
        "streak": 0, "bestStreak": 0, "questsDone": 0, "extremeDone": 0, "penaltiesCleared": 0,
        "totals": {e: 0 for e in EXERCISE_ORDER},
        "records": {e: 0 for e in EXERCISE_ORDER},
        "daily": {},
        "history": {},
        "achievements": [],
        "log": [],
        "guardian": {"date": "", "snoozes": 0, "surrender": False},
        "profile": {"heightCm": 0, "sex": ""},
        "weights": {},
        "checkins": [],
        "prog": {}, "fatigue": 0.0, "sessionsDone": 0, "lastRecovery": "",
        "water": {}, "sleepLog": {},
        "remind": {},
    }


def _merge(base: dict, extra: dict) -> dict:
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict) and k not in ("history", "daily", "weights", "prog",
                                                                                "water", "sleepLog"):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def _migrate(s: dict) -> dict:
    st = s["settings"]
    if "difficulty" in st:  # datos de la versión anterior
        st["plan"] = _OLD_PLANS.get(st.pop("difficulty"), "principiante")
    if s.get("quest") and "difficulty" in s["quest"]:
        s["quest"]["plan"] = _OLD_PLANS.get(s["quest"].pop("difficulty"), "principiante")
    s["player"].pop("freePoints", None)
    s["player"].pop("alloc", None)
    for e in EXERCISE_ORDER:  # ejercicios nuevos
        s["totals"].setdefault(e, 0)
        s["records"].setdefault(e, 0)
    if s.get("version", 3) < 4:
        # la progresión vieja (factor global) se convierte en el punto de partida de cada ejercicio
        s["prog"] = {}
        s["sessionsDone"] = max(s.get("sessionsDone", 0), s.get("questsDone", 0))
        q = s.get("quest")
        if q and "session" not in q:  # objetivo de hoy en formato viejo: se rearma al cargar
            q["legacy"] = True
    s["version"] = 4
    return s


class Game:
    """Contiene el estado y aplica las reglas. Avisa a la interfaz mediante `on_event`.

    Eventos: ("modal", dict(title, body, color, sound, icon)), ("toast", dict(text, gold, icon)),
             ("say", dict(text, force)), ("changed", {})
    """

    def __init__(self, store: Store | None = None, on_event: Optional[Callable] = None,
                 today: Optional[Callable[[], date]] = None):
        self.store = store or Store()
        self.on_event = on_event or (lambda kind, data: None)
        self._today = today or date.today
        loaded = self.store.load()
        self.s = _migrate(_merge(new_state(), loaded)) if loaded else new_state()
        q = self.s.get("quest")
        if q and q.pop("legacy", False):  # objetivo de la versión anterior: se pasa a series
            if q["date"] == self.today() and not q["completed"] and not any(q["progress"].values()):
                self.new_quest(q["date"], q.get("penalty", False))
            else:
                q["session"] = [{"ex": k, "sets": 3, "reps": max(1, -(-v // 3)), "kg": 0.0,
                                 "rest": coach.rest_seconds(k, q.get("plan", "principiante"))}
                                for k, v in q.get("targets", {}).items()]
                q.setdefault("results", {})

    # ------------------------------------------------------------ helpers
    def today(self) -> str:
        return self._today().isoformat()

    def save(self):
        self.store.save(self.s)

    def emit(self, kind, **data):
        self.on_event(kind, data)

    def modal(self, title, body, color="", sound="open", icon=""):
        self.emit("modal", title=t(title), key=title, body=body, color=color, sound=sound, icon=icon)

    def log(self, msg):
        self.s["log"].insert(0, {"t": time.time(), "msg": msg})
        del self.s["log"][200:]

    @property
    def player(self):
        return self.s["player"]

    @property
    def quest(self):
        return self.s["quest"]

    @property
    def settings(self):
        return self.s["settings"]

    @property
    def registered(self) -> bool:
        return bool(self.player["name"])

    def is_rest_day(self, day: str | date) -> bool:
        d = date.fromisoformat(day) if isinstance(day, str) else day
        return d.weekday() in self.settings.get("restDays", [])

    def stat_value(self, k) -> int:
        return STATS[k][2](self.s, self.s["records"], self.s["totals"])

    def adherence(self, days: int = 30) -> Optional[int]:
        """% de días de entrenamiento cumplidos (sin contar descansos). None si todavía no hay datos."""
        today = self._today()
        created = date.fromtimestamp(self.player["createdAt"])
        start = max(created, today - timedelta(days=days - 1))
        total = done = 0
        d = start
        while d <= today:
            k = d.isoformat()
            if k == today.isoformat():
                q = self.quest
                if q and not q.get("rest") and q["completed"]:
                    total += 1
                    done += 1
            else:
                h = self.s["history"].get(k)
                if h and not h.get("rest"):
                    total += 1
                    done += 1 if h.get("completed") else 0
            d += timedelta(days=1)
        return round(100 * done / total) if total else None

    def last_achievement(self) -> str:
        for aid, title, *_ in reversed(ACHIEVEMENTS):
            if aid in self.s["achievements"]:
                return t(title)
        return "—"

    # ------------------------------------------------------------ registro
    def register(self, name: str, plan: str):
        self.player["name"] = name.strip()[:24]
        self.player["createdAt"] = time.time()
        self.settings["plan"] = plan
        self.new_quest(self.today(), False)
        self.log(t("Registro: {name}, plan {plan}.", name=self.player["name"], plan=t(PLANS[plan]["label"])))
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
            leveled += 1
            self.log(t("Nivel {n}.", n=p["level"]))
            new_rank = rank_of(p["level"])
            if new_rank != old_rank:
                self.log(t("Nuevo rango: {r}.", r=new_rank))
                self.modal("NUEVO RANGO",
                           t("Rango") + f" <span style='font-size:30px;color:#ffd166'><b>{new_rank}</b></span><br>"
                           + t("Nivel {n} alcanzado. Seguí así.", n=p["level"]), "gold", "level", "crown")
        if leveled:
            self.emit("say", text=t("Nivel {n}", n=p["level"]), force=True)
            nr = next_rank(p["level"])
            extra = ("<br><small>" + t("Próximo rango ({r}) en el nivel {n}.", r=nr[1], n=nr[0]) + "</small>") if nr else ""
            self.modal("NIVEL ALCANZADO",
                       f"<span style='font-size:34px;color:#ffd166'><b>{p['level']}</b></span>{extra}", "gold", "level",
                       "sparkles")

    # ------------------------------------------------------------ objetivo diario
    # ------------------------------------------------------------ entrenador: sesión del día
    def day_index(self, day: str) -> int:
        return date.fromisoformat(day).toordinal()

    def pool(self) -> list[str]:
        return coach.unlocked(self.s["sessionsDone"], self.settings["plan"], self.settings.get("equipment", []))

    def prog_for(self, ex: str) -> dict:
        p = self.s["prog"].get(ex)
        if p is None:
            factor = self.s.get("progression", 1.0) or 1.0
            p = coach.initial(ex, self.settings["plan"], factor)
            self.s["prog"][ex] = p
        return p

    def build_session(self, day: str, penalty: bool) -> list[dict]:
        plan = self.settings["plan"]
        chosen = coach.pick_exercises(self.pool(), plan, self.s["sessionsDone"], self.day_index(day))
        out = []
        for k in chosen:
            p = self.prog_for(k)
            reps = p["reps"]
            if penalty:
                reps = int(math.ceil(reps * PENALTY_FACTOR))
            out.append({"ex": k, "sets": p["sets"], "reps": reps, "kg": p.get("kg", 0.0),
                        "rest": coach.rest_seconds(k, plan)})
        return out

    def build_targets(self, penalty: bool) -> dict:
        return {it["ex"]: coach.volume(it) for it in self.build_session(self.today(), penalty)}

    def new_quest(self, day: str, penalty: bool):
        reason = ""
        if not self.is_rest_day(day) and not penalty:
            reason = coach.needs_rest(self.s["history"], date.fromisoformat(day), self.settings["plan"],
                                      self.settings.get("restDays", []), self.s.get("fatigue", 0.0)) or ""
        if self.is_rest_day(day) or reason:
            self.s["quest"] = {"date": day, "penalty": False, "rest": True, "restReason": reason,
                               "plan": self.settings["plan"], "targets": {}, "progress": {}, "completed": True,
                               "session": [], "results": {}}
            return
        session = self.build_session(day, penalty)
        session, why = coach.adapt(session, "", self.s.get("fatigue", 0.0))
        self.s["quest"] = {
            "date": day, "penalty": penalty, "rest": False, "plan": self.settings["plan"],
            "session": session, "targets": {it["ex"]: coach.volume(it) for it in session},
            "progress": {}, "completed": False, "adapted": why, "readiness": None, "results": {},
        }

    def session_items(self) -> list[dict]:
        q = self.quest
        return list(q.get("session", [])) if q else []

    def set_readiness(self, level: str) -> str:
        """Cómo te sentís hoy: adapta la sesión si todavía no empezaste. Devuelve el motivo (o '')."""
        q = self.quest
        if not q or q.get("rest") or q["completed"]:
            return ""
        q["readiness"] = level
        if level == "dolorido":
            if self.s.get("lastRecovery") and (self._today() - date.fromisoformat(self.s["lastRecovery"])).days < 7:
                q["readiness"] = "cansado"
                level = "cansado"
            else:
                self.s["lastRecovery"] = self.today()
        if any(q["progress"].values()) and level != "dolorido":
            self.save()
            return ""
        base = self.build_session(q["date"], q["penalty"]) if not q.get("adaptedFrom") else q["adaptedFrom"]
        session, why = coach.adapt(base, level, self.s.get("fatigue", 0.0))
        if why:
            q["adaptedFrom"] = base
        q["session"] = session
        q["targets"] = {it["ex"]: coach.volume(it) for it in session}
        q["adapted"] = why
        if why:
            self.log(t(why) + ".")
        self.save()
        self.emit("changed")
        return why

    def record_exercise(self, ex: str, sets: list[dict], rpe: Optional[int] = None) -> tuple[str, str]:
        """Guarda cómo te fue en un ejercicio de la sesión y ajusta la progresión. Devuelve (tipo, texto)."""
        q = self.quest
        recovery = any(it.get("recovery") for it in q.get("session", []) if it["ex"] == ex) if q else False
        if q is not None:
            q.setdefault("results", {})[ex] = {"rpe": rpe, "sets": sets}
        if recovery:
            self.save()
            return "hold", t("Recuperación: no cambia tu progresión")
        p = self.prog_for(ex)
        item = next((it for it in (q or {}).get("session", []) if it["ex"] == ex), None)
        if item and item.get("sets", 0) < p["sets"]:
            # sesión adaptada por cansancio: no cuenta como fallo ni como avance
            new = dict(p, hist=(p.get("hist", []) + [{"d": self.today(), "sets": [x.get("good", 0) for x in sets],
                                                         "q": 1.0, "rpe": rpe or 3, "target": "adaptada"}])[-12:])
            kind, txt = "hold", t("Sesión adaptada: tu progresión se mantiene")
        else:
            # en días de penalización se pidió más: se evalúa contra tu objetivo normal
            new, kind, txt = coach.progress(p, ex, sets, rpe, self.settings.get("adjustableKg", True), self.today())
        self.s["prog"][ex] = new
        name = EXERCISES[ex].name
        if kind == "up":
            self.log(t("Progresión: {name} → {txt}", name=t(name), txt=txt) + ".")
        elif kind == "down":
            self.log(t("Ajuste: {name} → {txt}", name=t(name), txt=txt) + ".")
        self.save()
        return kind, txt

    def set_weight_kg(self, ex: str, kg: float):
        p = self.prog_for(ex)
        p["kg"] = max(0.0, round(float(kg), 1))
        q = self.quest
        for it in (q or {}).get("session", []):
            if it["ex"] == ex:
                it["kg"] = p["kg"]
        self.save()
        self.emit("changed")

    def _untouched(self) -> bool:
        q = self.quest
        return bool(q) and not q["completed"] and not any(q["progress"].values())

    def set_plan(self, plan: str):
        self.settings["plan"] = plan
        self.s["prog"] = {k: v for k, v in self.s["prog"].items() if v.get("hist")}  # los no usados se recalculan
        if self._untouched():
            self.new_quest(self.quest["date"], self.quest["penalty"])
            self.emit("toast", text=t("Objetivo de hoy actualizado"), gold=False, icon="check")
        self.save()
        self.emit("changed")

    def set_rest_days(self, days: list[int]):
        self.settings["restDays"] = sorted(set(days))
        q = self.quest
        if q and (self._untouched() or q.get("rest")):
            self.new_quest(q["date"], q.get("penalty", False))
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

        self.s["history"][q["date"]] = {k: q.get(k) for k in ("completed", "penalty", "progress", "targets", "rest")}
        gap = (date.fromisoformat(today) - date.fromisoformat(q["date"])).days
        if gap < 0:  # el reloj fue para atrás: reiniciamos sin castigar
            self.new_quest(today, False)
            self.save()
            return True
        missed = 0 if q["completed"] else 1
        for i in range(1, gap):
            d = (date.fromisoformat(q["date"]) + timedelta(days=i))
            rest = self.is_rest_day(d)
            self.s["history"][d.isoformat()] = {"completed": rest, "penalty": False, "progress": {},
                                                "targets": {}, "rest": rest}
            missed += 0 if rest else 1

        if missed:
            p = self.player
            lost = min(p["xp"], round(xp_needed(p["level"]) * 0.15 * min(missed, 5)))
            p["xp"] -= lost
            prev = self.s["streak"]
            self.s["streak"] = 0
            self.log(t("Día no cumplido ({n}). -{xp} XP. Racha reiniciada (era {prev}).", n=missed, xp=fmt(lost), prev=prev))
            self.new_quest(today, True)
            dias = t("<b>{n} días</b> sin cumplir", n=missed) if missed > 1 else t("Ayer no cumpliste el objetivo")
            penal = (t("Hoy los objetivos son <b>+30%</b>. Cumplilos para recuperar el ritmo.")
                     if not self.quest.get("rest") else t("Hoy es día de descanso: mañana se retoma."))
            self.modal("PENALIZACIÓN",
                       f"{dias}.<br><br>"
                       f"<span style='color:#ff3b5c'><b>-{fmt(lost)} XP</b></span>  ·  "
                       + t("Racha reiniciada (era {n} días)", n=prev) + f"<br><br>{penal}", "red", "penalty",
                       "triangle-alert")
        else:
            self.new_quest(today, False)
        self.save()
        self.emit("changed")
        return True

    def remaining(self) -> list[tuple[str, float]]:
        q = self.quest
        if not q:
            return []
        return [(k, v - q["progress"].get(k, 0)) for k, v in q["targets"].items() if q["progress"].get(k, 0) < v]

    def _check_complete(self):
        q = self.quest
        if q["completed"] or q.get("rest") or self.remaining():
            return
        q["completed"] = True
        s = self.s
        s["streak"] += 1
        s["bestStreak"] = max(s["bestStreak"], s["streak"])
        s["questsDone"] += 1
        if q.get("plan") == "extremo":
            s["extremeDone"] += 1
        if q["penalty"]:
            s["penaltiesCleared"] += 1
        base = PLANS.get(q.get("plan"), PLANS["principiante"])["reward"]
        bonus = min(200, s["streak"] * 10)
        total = round(base * (1.3 if q["penalty"] else 1) + bonus)
        self.log(t("Objetivo diario cumplido. +{xp} XP. Racha: {n}.", xp=fmt(total), n=s["streak"]))
        self.emit("say", text=t("Objetivo diario cumplido"), force=True)
        prog = ""
        s["sessionsDone"] = s.get("sessionsDone", 0) + 1
        res = q.get("results", {})
        rpes = [r["rpe"] for r in res.values() if r.get("rpe")]
        missed = 0
        if res:
            missed = sum(1 for k, r in res.items()
                         if any(st.get("good", 0) < next((it["reps"] for it in q["session"] if it["ex"] == k), 0)
                                for st in r.get("sets", []))) / len(res)
        s["fatigue"] = coach.update_fatigue(s.get("fatigue", 0.0), rpes, missed)
        before = set(coach.unlocked(s["sessionsDone"] - 1, self.settings["plan"], self.settings.get("equipment", [])))
        new = [k for k in self.pool() if k not in before]
        if new:
            names = ", ".join(t(EXERCISES[k].name) for k in new)
            self.log(t("Ejercicios nuevos en tu rotación: {names}.", names=names))
            prog = "<br><br>" + t("<b>Nuevo en tu rotación:</b> {names}.", names=names)
        self.modal("OBJETIVO CUMPLIDO",
                   f"<span style='font-size:26px;color:#ffd166'><b>+{fmt(total)} XP</b></span><br>"
                   + t("Racha: <b>{n}</b> días (+{bonus} por racha)", n=s["streak"], bonus=bonus) + prog,
                   "gold", "quest", "circle-check")
        self.gain_xp(total)

    def add_reps(self, ex: str, n: float, manual: bool = False) -> float:
        """Suma repeticiones (o segundos de plancha). Devuelve la XP ganada."""
        if n <= 0 or not self.registered:
            return 0.0
        self.rollover()
        self.s["totals"][ex] = self.s["totals"].get(ex, 0) + n
        day = self.s["daily"].setdefault(self.today(), {})
        day[ex] = day.get(ex, 0) + n
        if len(self.s["daily"]) > 400:
            for k in sorted(self.s["daily"])[:-400]:
                del self.s["daily"][k]
        q = self.quest
        if ex in q["targets"]:
            before = q["progress"].get(ex, 0)
            q["progress"][ex] = before + n
            if before < q["targets"][ex] <= q["progress"][ex]:
                name = t(EXERCISES[ex].name)
                self.emit("toast", text=t("{name}: objetivo cumplido", name=name), gold=True, icon="circle-check")
                self.emit("say", text=t("{name} completo", name=name), force=True)
        xp = n * EXERCISES[ex].xp * (0.7 if manual else 1.0)
        self.gain_xp(xp)
        self._check_complete()
        self.check_achievements()
        self.save()
        self.emit("changed")
        return xp

    def finish_set(self, ex: str, good: float, bad: int, xp: float) -> bool:
        """Registra una serie terminada. Devuelve True si fue récord personal."""
        e = EXERCISES[ex]
        unit = " s" if e.timed else " reps"
        extra = t(", {n} mal hechas", n=bad) if bad else ""
        self.log(t("Serie de {name}: {n}{u}{extra}. +{xp} XP", name=t(e.name), n=fmt(good), u=unit, extra=extra,
                   xp=fmt(xp)))
        record = False
        prev = self.s["records"].get(ex, 0)
        if good > prev:
            self.s["records"][ex] = int(good)
            record = prev > 0
            if record:
                self.log(t("Récord personal: {name} {n}{u} en una serie (antes {prev}).", name=t(e.name), n=fmt(good),
                           u=unit, prev=fmt(prev)))
        self.check_achievements()
        self.save()
        self.emit("changed")
        return record

    def check_achievements(self):
        for aid, title, desc, test in ACHIEVEMENTS:
            if aid not in self.s["achievements"] and test(self.s):
                self.s["achievements"].append(aid)
                self.log(t("Logro: {name}.", name=t(title)))
                self.modal("LOGRO",
                           f"<span style='font-size:22px;color:#ffd166'><b>{escape(t(title))}</b></span>"
                           f"<br><small>{escape(t(desc))}</small>", "gold", "achievement", "award")

    # ------------------------------------------------------------ cuerpo: peso y controles semanales
    @property
    def profile(self):
        return self.s["profile"]

    def log_weight(self, kg: float, day: Optional[str] = None):
        if not (20 <= kg <= 350):
            raise ValueError(t("Peso fuera de rango"))
        self.s["weights"][day or self.today()] = round(float(kg), 2)
        self.save()
        self.emit("changed")

    def _avg(self, days: int, end: Optional[date] = None) -> Optional[float]:
        end = end or self._today()
        vals = [v for k, v in self.s["weights"].items()
                if 0 <= (end - date.fromisoformat(k)).days < days]
        return round(sum(vals) / len(vals), 2) if vals else None

    def weight_stats(self) -> dict:
        w = self.s["weights"]
        if not w:
            return {"count": 0}
        last_day = max(w)
        avg7, prev7 = self._avg(7), self._avg(7, self._today() - timedelta(days=7))
        return {
            "count": len(w), "last": w[last_day], "last_day": last_day,
            "avg7": avg7, "avg30": self._avg(30), "avg_all": round(sum(w.values()) / len(w), 2),
            "week_change": None if (avg7 is None or prev7 is None) else round(avg7 - prev7, 2),
            "min": min(w.values()), "max": max(w.values()),
        }

    def last_checkin(self) -> Optional[dict]:
        return self.s["checkins"][-1] if self.s["checkins"] else None

    def checkin_due(self) -> bool:
        if not self.registered:
            return False
        last = self.last_checkin()
        today = self._today()
        if last is None:
            return True
        days = (today - date.fromisoformat(last["date"])).days
        if days >= 7:
            return True
        return today.weekday() == self.settings.get("checkinDay", 0) and days >= 4

    def next_checkin(self) -> str:
        if self.checkin_due():
            return t("hoy")
        today = self._today()
        last = date.fromisoformat(self.last_checkin()["date"])
        target = self.settings.get("checkinDay", 0)
        d = today + timedelta(days=1)
        while d.weekday() != target or (d - last).days < 4:
            d += timedelta(days=1)
        return f"{t(WEEKDAYS[d.weekday()]).lower()} {d.day}/{d.month}"

    def add_checkin(self, weight: float, photos: dict, metrics: dict, findings: list, landmarks: dict | None = None) -> dict:
        today = self.today()
        self.log_weight(weight, today)
        entry = {"date": today, "weight": round(weight, 2), "photos": photos, "metrics": metrics, "findings": findings,
                 "landmarks": landmarks or {}}
        self.s["checkins"] = [c for c in self.s["checkins"] if c["date"] != today] + [entry]
        bf = metrics.get("body_fat")
        self.log(t("Control corporal: {kg} kg", kg=f"{weight:.1f}") + (t(", ~{p}% grasa", p=f"{bf:.1f}") if bf else "") +
                 (t(", cintura {cm} cm", cm=f"{metrics['waist_cm']:.1f}") if metrics.get("reliable") else "") + ".")
        self.gain_xp(100)
        self.check_achievements()
        self.save()
        self.emit("changed")
        return entry

    # ------------------------------------------------------------ bienestar: agua y sueño (ayudan, no castigan)
    def water_goal(self) -> int:
        """Meta de agua en ml: la tuya, o 35 ml por kg (+500 ml si hoy entrenás)."""
        st = self.settings["water"]
        if st.get("goalMl"):
            return int(st["goalMl"])
        w = self.weight_stats().get("last") or 0
        base = int(round(w * 35 / 50) * 50) if w else 2500
        q = self.quest
        if q and not q.get("rest"):
            base += 500
        return max(1500, min(5000, base))

    def water_today(self) -> int:
        return int(self.s["water"].get(self.today(), {}).get("ml", 0))

    def add_water(self, ml: int) -> int:
        d = self.s["water"].setdefault(self.today(), {"ml": 0, "done": False})
        before_done = d.get("done", False)
        d["ml"] = max(0, int(d.get("ml", 0)) + int(ml))
        d["done"] = d["ml"] >= self.water_goal()
        if len(self.s["water"]) > 400:
            for k in sorted(self.s["water"])[:-400]:
                del self.s["water"][k]
        if d["done"] and not before_done:
            self.log(t("Meta de agua cumplida ({l} L).", l=f"{d['ml'] / 1000:.1f}"))
            self.emit("toast", text=t("Meta de agua cumplida"), gold=True, icon="droplet")
            self.gain_xp(20)
            self.check_achievements()
        self.save()
        self.emit("changed")
        return d["ml"]

    def water_pace(self, now: Optional[datetime] = None) -> tuple[int, int]:
        """(lo que deberías llevar a esta hora, lo que llevás)."""
        now = now or datetime.now()
        st = self.settings["water"]
        start, end = int(st.get("start", 9)), int(st.get("end", 22))
        h = now.hour + now.minute / 60
        k = 0.0 if h <= start else 1.0 if h >= end else (h - start) / max(1, end - start)
        return int(self.water_goal() * k), self.water_today()

    def sleep_target_hours(self) -> float:
        st = self.settings["sleep"]
        bh, bm = (int(x) for x in st.get("bed", "23:30").split(":"))
        wh, wm = (int(x) for x in st.get("wake", "07:30").split(":"))
        mins = (wh * 60 + wm) - (bh * 60 + bm)
        if mins <= 0:
            mins += 24 * 60
        return round(mins / 60, 2)

    def sleep_start(self, when: Optional[datetime] = None):
        self.s["remind"]["sleepStart"] = (when or datetime.now()).isoformat(timespec="minutes")
        self.save()

    def pending_sleep(self, now: Optional[datetime] = None) -> Optional[float]:
        """Horas dormidas desde "me voy a dormir" (si todavía no lo registraste)."""
        st = self.s["remind"].get("sleepStart")
        if not st:
            return None
        now = now or datetime.now()
        h = (now - datetime.fromisoformat(st)).total_seconds() / 3600
        if h < 3:
            return None
        if h > 16:
            self.s["remind"].pop("sleepStart", None)
            return None
        return round(h, 1)

    def log_sleep(self, hours: float, quality: str = "", day: Optional[str] = None):
        """Registra la noche (se guarda con la fecha del día en que te despertás)."""
        hours = max(0.0, min(16.0, float(hours)))
        ok = hours >= self.sleep_target_hours() - 0.5
        self.s["sleepLog"][day or self.today()] = {"h": round(hours, 1), "q": quality, "ok": ok}
        self.s["remind"].pop("sleepStart", None)
        if len(self.s["sleepLog"]) > 400:
            for k in sorted(self.s["sleepLog"])[:-400]:
                del self.s["sleepLog"][k]
        self.log(t("Sueño: {h} h.", h=f"{hours:.1f}"))
        if ok:
            self.gain_xp(15)
        self.check_achievements()
        self.save()
        self.emit("changed")

    def sleep_stats(self, days: int = 7) -> dict:
        today = self._today()
        vals = [v for k, v in self.s["sleepLog"].items() if 0 <= (today - date.fromisoformat(k)).days < days]
        last = self.s["sleepLog"].get(self.today())
        if not vals:
            return {"count": 0, "last": last}
        avg = sum(v["h"] for v in vals) / len(vals)
        return {"count": len(vals), "avg": round(avg, 1), "ok": sum(1 for v in vals if v.get("ok")), "last": last}

    def suggested_readiness(self) -> Optional[str]:
        """Si dormiste poco, sugiere entrenar en modo "cansado" (no obliga)."""
        last = self.s["sleepLog"].get(self.today())
        if last and (last["h"] < 6 or last.get("q") == "mal"):
            return "cansado"
        return None

    # ------------------------------------------------------------ Guardián
    def guardian(self) -> dict:
        g = self.s["guardian"]
        if g.get("date") != self.today():
            g.update(date=self.today(), snoozes=0, surrender=False)
        return g

    def nag_settings(self) -> dict:
        return self.settings["nag"]

    def should_nag(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now()
        nag = self.nag_settings()
        if not nag["enabled"] or not self.registered:
            return False
        self.rollover()
        if self.quest["completed"] or self.quest.get("rest") or self.guardian()["surrender"]:
            return False
        return now.hour >= int(nag["startHour"])

    def snooze(self):
        self.guardian()["snoozes"] += 1
        self.save()

    def snoozes_left(self) -> int:
        return max(0, int(self.nag_settings()["snoozesPerDay"]) - self.guardian()["snoozes"])

    def surrender(self):
        self.guardian()["surrender"] = True
        self.log(t("Te rendiste por hoy."))
        self.save()

    # ------------------------------------------------------------ datos
    def export(self) -> dict:
        return copy.deepcopy(self.s)

    def import_state(self, data: dict):
        if not isinstance(data, dict) or "player" not in data:
            raise ValueError(t("Archivo inválido"))
        self.s = _migrate(_merge(new_state(), data))
        self.save()
        self.emit("changed")

    def reset(self):
        self.s = new_state()
        self.save()
        self.emit("changed")
