"""Entrenador: arma la sesión del día y ajusta la progresión según cómo te fue de verdad.

Reglas (doble progresión, como haría un entrenador):
  * Cada ejercicio tiene series × repeticiones (o segundos) y, si usa mancuernas, un peso.
  * Si completás todas las series con buena técnica y sin demasiado esfuerzo → sube un poco (repeticiones,
    después una serie más o más peso).
  * Si te costó mucho → se mantiene. Si fallaste o la técnica fue mala dos veces → baja un 10%.
  * El cansancio acumulado (esfuerzo de las últimas sesiones) recorta volumen y programa descansos.
  * A medida que sumás sesiones se desbloquean ejercicios nuevos y la sesión crece.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

from .exercises import EXERCISES
from .i18n import t

# repeticiones por serie (o segundos) para el plan intermedio; los demás planes escalan
BASE_REPS = {
    "pushup": 12, "squat": 20, "situp": 20, "plank": 40, "jack": 30, "lunge": 16, "bridge": 15, "climber": 24,
    "side_plank": 25, "pullup": 5, "chinup": 6, "knee_raise": 10, "curl": 10, "press": 10, "row": 10,
    "lateral": 12, "goblet": 12, "rdl": 10,
}
PLAN_SCALE = {"principiante": (3, 0.6), "intermedio": (3, 1.0), "avanzado": (4, 1.45), "extremo": (5, 1.7)}
PLAN_EXERCISES = {"principiante": 4, "intermedio": 5, "avanzado": 5, "extremo": 6}
MAX_STREAK = {"principiante": 3, "intermedio": 4, "avanzado": 5, "extremo": 6}  # días seguidos antes de un descanso
LOADED_RANGE = (8, 12)
MAX_SETS = 5
GROUP_ORDER = ["legs", "push", "pull", "core", "cardio"]
RPE = {1: "Fácil", 2: "Bien", 3: "Difícil", 4: "Al límite"}
READINESS = {"energia": "Con energía", "normal": "Normal", "cansado": "Cansado", "dolorido": "Dolorido"}


def _round_reps(v: float, timed: bool) -> int:
    if timed:
        return max(10, int(round(v / 5.0) * 5))
    return max(3, int(round(v)))


def initial(ex_id: str, plan: str, factor: float = 1.0) -> dict:
    e = EXERCISES[ex_id]
    sets, scale = PLAN_SCALE.get(plan, PLAN_SCALE["principiante"])
    reps = _round_reps(BASE_REPS.get(ex_id, 10) * scale * factor, e.timed)
    if e.loaded:
        reps = max(LOADED_RANGE[0], min(LOADED_RANGE[1], reps))
    if e.equip == "bar":
        sets = min(sets, 4)
    return {"sets": sets, "reps": reps, "kg": 0.0, "fails": 0, "holds": 0, "hist": []}


def unlocked(sessions: int, plan: str, equipment) -> list[str]:
    """Ejercicios disponibles según tu experiencia y el equipamiento."""
    bonus = {"principiante": 0, "intermedio": 4, "avanzado": 10, "extremo": 10}.get(plan, 0)
    exp = sessions + bonus
    eq = set(equipment or [])
    out = []
    for k, e in EXERCISES.items():
        if e.equip and e.equip not in eq:
            continue
        need = {1: 0, 2: 5, 3: 14}.get(e.level, 0)
        if exp >= need:
            out.append(k)
    return out


def session_size(plan: str, sessions: int) -> int:
    return min(7, PLAN_EXERCISES.get(plan, 4) + sessions // 15)


def pick_exercises(pool: list[str], plan: str, sessions: int, day_index: int) -> list[str]:
    """Elige los ejercicios del día cubriendo grupos musculares y rotando entre opciones."""
    if plan == "extremo":
        core4 = [k for k in ("pushup", "squat", "situp", "plank") if k in pool]
        rest = [k for k in pool if k not in core4]
        extra = rest[day_index % len(rest):][:2] if rest else []
        return core4 + extra
    by_group: dict[str, list[str]] = {}
    for k in pool:
        by_group.setdefault(EXERCISES[k].group, []).append(k)
    n = session_size(plan, sessions)
    # alternamos días "A" (empuje) y "B" (tirón) cuando hay ejercicios de tirón
    groups = list(GROUP_ORDER)
    if "pull" in by_group and day_index % 2:
        groups = ["legs", "pull", "push", "core", "cardio"]
    chosen: list[str] = []
    rnd = 0
    while len(chosen) < n and rnd < 4:
        for g in groups:
            opts = [k for k in by_group.get(g, []) if k not in chosen]
            if not opts or len(chosen) >= n:
                continue
            chosen.append(opts[(day_index + rnd) % len(opts)])
        rnd += 1
    order = {g: i for i, g in enumerate(GROUP_ORDER)}
    return sorted(chosen, key=lambda k: (order.get(EXERCISES[k].group, 9), EXERCISES[k].timed))


def rest_seconds(ex_id: str, plan: str) -> int:
    e = EXERCISES[ex_id]
    base = {"legs": 75, "push": 75, "pull": 90, "core": 45, "cardio": 40}.get(e.group, 60)
    if e.loaded or e.equip == "bar":
        base += 15
    if plan in ("avanzado", "extremo"):
        base -= 10
    return base


def infer_rpe(sets: list[dict], target: int) -> int:
    """Esfuerzo estimado si no contestás: series falladas y cuánto te frenaste al final."""
    if not sets:
        return 3
    missed = sum(1 for s in sets if s.get("good", 0) < target)
    slow = max((s.get("slowdown", 1.0) for s in sets), default=1.0)
    if missed >= 2:
        return 4
    if missed == 1 or slow > 1.55:
        return 3
    if slow < 1.2:
        return 2
    return 2


def progress(p: dict, ex_id: str, sets: list[dict], rpe: Optional[int], adjustable_kg: bool = True,
             day: str = "") -> tuple[dict, str, str]:
    """Aplica la progresión a un ejercicio. Devuelve (nuevo estado, tipo de cambio, explicación).

    tipo: up | hold | down | first
    """
    e = EXERCISES[ex_id]
    p = dict(p)
    p["hist"] = list(p.get("hist", []))
    target, nsets = p["reps"], p["sets"]
    done = [s for s in sets if (s.get("good", 0) + s.get("bad", 0)) > 0]
    q = (sum(s.get("quality", 1.0) * max(1, s.get("good", 0) + s.get("bad", 0)) for s in done)
         / max(1, sum(max(1, s.get("good", 0) + s.get("bad", 0)) for s in done))) if done else 0.0
    hit = len(done) >= nsets and all(s.get("good", 0) >= target for s in done[:nsets])
    eff = rpe if rpe in RPE else infer_rpe(done, target)
    p["hist"].append({"d": day, "sets": [s.get("good", 0) for s in done], "q": round(q, 2), "rpe": eff,
                      "target": f"{nsets}x{target}"})
    del p["hist"][:-12]

    if not done:
        return p, "hold", t("Sin datos: se mantiene")
    step = max(5, int(round(target * 0.1 / 5) * 5)) if e.timed else max(1, int(round(target * 0.08)))

    if hit and q >= 0.8 and eff <= 2:
        p["fails"] = 0
        p["holds"] = 0
        if e.loaded:
            if target + step > LOADED_RANGE[1] and adjustable_kg and p.get("kg", 0) > 0:
                p["kg"] = round(p["kg"] + (1.0 if p["kg"] < 6 else 2.0), 1)
                p["reps"] = LOADED_RANGE[0]
                return p, "up", t("+peso: {kg} kg × {reps}", kg=f"{p['kg']:g}", reps=p["reps"])
            if target + step > LOADED_RANGE[1] and p["sets"] < MAX_SETS:
                p["sets"] += 1
                p["reps"] = LOADED_RANGE[0] + 1
                return p, "up", t("+1 serie: {sets}×{reps}", sets=p["sets"], reps=p["reps"])
        elif not e.timed and target + step > 25 and p["sets"] < MAX_SETS:
            p["sets"] += 1
            p["reps"] = max(5, int(target * 0.8))
            return p, "up", t("+1 serie: {sets}×{reps}", sets=p["sets"], reps=p["reps"])
        p["reps"] = target + step
        return p, "up", f"{p['sets']}×{p['reps']}{' s' if e.timed else ''}"
    if hit and q >= 0.8 and eff == 3:
        p["fails"] = 0
        p["holds"] = p.get("holds", 0) + 1
        if p["holds"] >= 3:  # tres veces seguidas "difícil" pero cumplido: sube un poquito igual
            p["holds"] = 0
            p["reps"] = target + max(1, step // 2) if not e.timed else target + 5
            return p, "up", f"{p['sets']}×{p['reps']}{' s' if e.timed else ''}"
        return p, "hold", t("Se mantiene para consolidar")
    # no se cumplió, técnica floja o al límite
    p["fails"] = p.get("fails", 0) + 1
    p["holds"] = 0
    if p["fails"] >= 2 or eff == 4 and not hit:
        p["fails"] = 0
        new = _round_reps(target * 0.9, e.timed)
        if new >= target:
            new = max(1, target - 1)
        p["reps"] = new
        why = t("Primero la técnica") if q < 0.6 else t("Ajuste por cansancio")
        return p, "down", f"{why}: {p['sets']}×{p['reps']}{' s' if e.timed else ''}"
    return p, "hold", t("Se mantiene: la próxima sale")


def update_fatigue(fatigue: float, rpes: list[int], missed_ratio: float) -> float:
    """Cansancio 0..1 (media móvil): esfuerzo de la sesión y objetivos no cumplidos."""
    if not rpes:
        return fatigue
    load = (sum(rpes) / len(rpes) - 1) / 3  # 0 fácil … 1 al límite
    load = min(1.0, load * 0.8 + missed_ratio * 0.5)
    return round(fatigue * 0.6 + load * 0.4, 3)


def adapt(session: list[dict], readiness: str, fatigue: float) -> tuple[list[dict], str]:
    """Recorta la sesión si estás cansado (o te sentís mal). Devuelve (sesión, motivo)."""
    out = [dict(it) for it in session]
    if readiness == "dolorido":
        rec = []
        for k, sets, reps in (("plank", 2, 20), ("bridge", 2, 10), ("situp", 2, 10)):
            rec.append({"ex": k, "sets": sets, "reps": reps, "kg": 0.0, "rest": 45, "recovery": True})
        return rec, "Sesión de recuperación: movimiento suave para no cortar la racha"
    cut = 0
    reason = ""
    if readiness == "cansado":
        cut, reason = 1, "Sesión adaptada: hoy estás cansado"
    if fatigue > 0.65:
        cut = max(cut, 1)
        reason = reason or "Sesión adaptada: venís acumulando cansancio"
    if not cut:
        return out, ""
    for it in out:
        it["sets"] = max(2, it["sets"] - cut)
        if readiness == "cansado" and fatigue > 0.65:
            e = EXERCISES[it["ex"]]
            it["reps"] = _round_reps(it["reps"] * 0.85, e.timed)
    return out, reason


def needs_rest(history: dict, today: date, plan: str, rest_days: list[int], fatigue: float) -> Optional[str]:
    """¿Hoy conviene descansar? Por días seguidos entrenando o por cansancio alto."""
    streak = 0
    d = today - timedelta(days=1)
    while True:
        h = history.get(d.isoformat())
        if not h or h.get("rest") or not h.get("completed"):
            break
        streak += 1
        d -= timedelta(days=1)
    if streak >= MAX_STREAK.get(plan, 4):
        return t("Descanso programado: llevás {n} días seguidos entrenando", n=streak)
    if fatigue > 0.8 and streak >= 2:
        return "Descanso programado: tu cansancio está alto, el cuerpo se adapta descansando"
    return None


def volume(item: dict) -> int:
    return int(item["sets"]) * int(item["reps"])


def estimate_minutes(session: list[dict]) -> int:
    total = 0.0
    for it in session:
        e = EXERCISES[it["ex"]]
        work = it["reps"] if e.timed else it["reps"] * 2.6
        total += it["sets"] * (work + it.get("rest", 60)) + 45
    return max(5, int(math.ceil(total / 60)))
