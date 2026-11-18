"""Ejercicios: cómo se mide cada uno a partir de la pose y cómo se cuentan las repeticiones.

Índices de MediaPipe Pose:
  0 nariz | 11/12 hombros | 13/14 codos | 15/16 muñecas
  23/24 caderas | 25/26 rodillas | 27/28 tobillos
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional

VIS = 0.55  # visibilidad mínima para confiar en un punto


def _v(p) -> float:
    v = getattr(p, "visibility", None)
    return 1.0 if v is None else float(v)


def angle3(a, b, c) -> float:
    """Ángulo ABC en grados (3D, coordenadas de mundo en metros)."""
    ab = (a.x - b.x, a.y - b.y, (a.z or 0) - (b.z or 0))
    cb = (c.x - b.x, c.y - b.y, (c.z or 0) - (b.z or 0))
    dot = sum(i * j for i, j in zip(ab, cb))
    m = math.hypot(*ab) * math.hypot(*cb)
    if not m:
        return 180.0
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / m))))


def min_vis(lm, idx) -> float:
    return min(_v(lm[i]) for i in idx)


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def best_side(lm, left, right):
    l, r = min_vis(lm, left), min_vis(lm, right)
    if max(l, r) < VIS:
        return None
    return left if l >= r else right


def is_horizontal(lm, a, b, aspect) -> bool:
    dx = abs(lm[a].x - lm[b].x) * aspect
    dy = abs(lm[a].y - lm[b].y)
    return dx > dy * 1.2


@dataclass
class Measure:
    visible: bool
    value: Optional[float] = None
    issue: Optional[str] = None
    hint: Optional[str] = None
    ok: bool = False


# ---------------------------------------------------------------- mediciones
def m_pushup(lm, w, aspect):
    """Flexiones vistas de costado, de frente o en diagonal.

    En vez de exigir que el cuerpo se vea horizontal (solo funciona de costado), se decide por la postura:
    torso no vertical (no estás parado) + manos apoyadas más abajo que los hombros.
    """
    arms = [a for a in ((11, 13, 15), (12, 14, 16)) if min_vis(lm, a) > VIS * 0.8]
    if not arms:
        return Measure(False)
    shoulders = [i for i in (11, 12) if _v(lm[i]) > 0.4]
    hips = [i for i in (23, 24) if _v(lm[i]) > 0.4]
    sh_y = sum(lm[i].y for i in shoulders) / len(shoulders)
    if hips:
        hip_y = sum(lm[i].y for i in hips) / len(hips)
        torso_v = hip_y - sh_y                       # cuánto más abajo están las caderas que los hombros
        sh_w = abs(lm[11].x - lm[12].x) * aspect    # ancho de hombros en las mismas unidades
        if torso_v > 0.16 and torso_v > 1.15 * sh_w:
            return Measure(True, hint="Ponete en posición de flexión")
    # manos apoyadas: las muñecas tienen que estar más abajo que los hombros
    if not any(lm[a[2]].y > lm[a[0]].y + 0.02 for a in arms):
        return Measure(True, hint="Apoyá las manos en el piso, debajo de los hombros")
    elbow = sum(angle3(w[a], w[b], w[c]) for a, b, c in arms) / len(arms)
    issue = None
    # cadera caída: solo se puede juzgar si se ve el cuerpo de costado
    s = arms[0][0]
    hip, ankle = (23, 27) if s == 11 else (24, 28)
    if min_vis(lm, (hip, ankle)) > VIS and is_horizontal(lm, s, ankle, aspect):
        if angle3(w[s], w[hip], w[ankle]) < 145:
            issue = "Mantené la cadera alineada"
    return Measure(True, elbow, issue)


def m_squat(lm, w, aspect):
    sides = [s for s in ((23, 25, 27), (24, 26, 28)) if min_vis(lm, s) > VIS]
    if not sides:
        return Measure(False)
    knee = sum(angle3(w[a], w[b], w[c]) for a, b, c in sides) / len(sides)
    issue = None
    sh = 11 if sides[0][0] == 23 else 12
    if min_vis(lm, (sh,)) > VIS:
        torso = angle3(w[sh], w[sides[0][0]], w[sides[0][1]])
        if knee < 120 and torso < 45:
            issue = "Pecho arriba, no te inclines tanto"
    return Measure(True, knee, issue)


def m_situp(lm, w, aspect):
    side = best_side(lm, (11, 23, 25), (12, 24, 26))
    if not side:
        return Measure(False)
    return Measure(True, angle3(w[side[0]], w[side[1]], w[side[2]]))


def m_jack(lm, w, aspect):
    if min_vis(lm, (11, 12, 15, 16, 23, 24, 27, 28)) < VIS * 0.8:
        return Measure(False)
    sh_y = (lm[11].y + lm[12].y) / 2
    hip_y = (lm[23].y + lm[24].y) / 2
    torso = max(0.05, hip_y - sh_y)
    arm = sum(clamp01((sh_y - lm[i].y) / (torso * 0.55)) for i in (15, 16)) / 2
    sh_w = max(0.03, abs(lm[11].x - lm[12].x))
    leg = clamp01((abs(lm[27].x - lm[28].x) / sh_w - 1.0) / 0.6)
    return Measure(True, (arm + leg) / 2)


def m_lunge(lm, w, aspect):
    sides = [s for s in ((23, 25, 27), (24, 26, 28)) if min_vis(lm, s) > VIS * 0.85]
    if not sides:
        return Measure(False)
    return Measure(True, min(angle3(w[a], w[b], w[c]) for a, b, c in sides))


def m_plank(lm, w, aspect):
    side = best_side(lm, (11, 23, 27), (12, 24, 28)) or best_side(lm, (11, 23, 25), (12, 24, 26))
    if not side:
        return Measure(False)
    if not is_horizontal(lm, side[0], side[2], aspect):
        return Measure(True, hint="Ponete en posición de plancha")
    line = angle3(w[side[0]], w[side[1]], w[side[2]])
    if line < 155:
        hip_above = lm[side[1]].y < (lm[side[0]].y + lm[side[2]].y) / 2
        return Measure(True, hint="Bajá la cadera" if hip_above else "Subí la cadera, no la dejes caer")
    return Measure(True, ok=True)


@dataclass
class Exercise:
    id: str
    name: str
    icon: str
    stat: str
    xp: float
    tip: str
    measure: Callable
    unit: str = "reps"
    timed: bool = False
    direction: str = "lower"  # el valor baja al hacer el esfuerzo
    rest: float = 0
    mid: float = 0
    active: float = 0
    partial_msg: str = ""


EXERCISES: dict[str, Exercise] = {e.id: e for e in [
    Exercise("pushup", "Flexiones", "biceps-flexed", "FUE", 3,
             "Cámara a la altura del piso, de costado o en diagonal. Que se vean tus brazos y el torso.",
             m_pushup, rest=145, mid=122, active=102, partial_msg="Bajá más el pecho"),
    Exercise("squat", "Sentadillas", "person-standing", "FUE", 2,
             "Ponete de costado (o en diagonal) a la cámara, piernas y torso a la vista.",
             m_squat, rest=155, mid=130, active=100, partial_msg="Bajá más, muslos paralelos al piso"),
    Exercise("situp", "Abdominales", "flame", "RES", 2,
             "Acostate de costado a la cámara con las rodillas flexionadas.",
             m_situp, rest=105, mid=88, active=72, partial_msg="Subí más el torso"),
    Exercise("jack", "Jumping Jacks", "zap", "AGI", 1,
             "Ponete de frente a la cámara, cuerpo entero a la vista.",
             m_jack, direction="higher", rest=0.22, mid=0.45, active=0.72,
             partial_msg="Brazos bien arriba y piernas abiertas"),
    Exercise("lunge", "Zancadas", "footprints", "AGI", 2,
             "Ponete de costado. Alterná piernas: cada bajada cuenta.",
             m_lunge, rest=155, mid=132, active=105, partial_msg="Bajá más la rodilla de atrás"),
    Exercise("plank", "Plancha", "timer", "RES", 0.5,
             "Cámara de costado al piso. Solo cuenta el tiempo con el cuerpo recto.",
             m_plank, unit="seg", timed=True),
]}
EXERCISE_ORDER = list(EXERCISES)


@dataclass
class Update:
    status: str            # ok | warn | bad | hint | hidden
    msg: Optional[str] = None
    event: Optional[str] = None   # rep | bad | partial | second
    progress: Optional[float] = None
    count: int = 0


@dataclass
class RepCounter:
    """Máquina de estados: reposo -> moviéndose -> activo -> reposo = 1 repetición."""
    ex: Exercise
    reps: int = 0
    bad: int = 0
    seconds: float = 0.0
    phase: str = "rest"
    ema: Optional[float] = None
    issues: list = field(default_factory=list)
    last_rep_at: float = -10.0
    last_t: Optional[float] = None

    def update(self, lm, w, aspect: float, now: float) -> Update:
        ex = self.ex
        m = ex.measure(lm, w, aspect)
        if not m.visible:
            self.last_t = None
            return Update("hidden", "No te veo completo: alejate un poco de la cámara")

        if ex.timed:
            dt = 0.0 if self.last_t is None else now - self.last_t
            self.last_t = now
            if not m.ok:
                return Update("bad", m.hint)
            before = int(self.seconds)
            self.seconds += min(dt, 0.25)
            gained = int(self.seconds) - before
            return Update("ok", "¡Bien! Mantené", "second" if gained else None, 1.0, gained)

        if m.value is None:
            return Update("hint", m.hint)

        self.ema = m.value if self.ema is None else self.ema * 0.45 + m.value * 0.55
        v = self.ema
        lower = ex.direction == "lower"
        is_active = v < ex.active if lower else v > ex.active
        is_rest = v > ex.rest if lower else v < ex.rest
        past_mid = v < ex.mid if lower else v > ex.mid
        progress = clamp01((ex.rest - v) / (ex.rest - ex.active))

        event = msg = None
        if self.phase == "rest" and past_mid:
            self.phase = "moving"
        if self.phase != "rest" and m.issue and m.issue not in self.issues:
            self.issues.append(m.issue)

        if self.phase == "moving":
            if is_active:
                self.phase = "active"
            elif is_rest:
                event, msg = "partial", ex.partial_msg
                self._reset()
        elif self.phase == "active" and is_rest:
            if now - self.last_rep_at < 0.35:
                self._reset()
            elif not self.issues:
                self.reps += 1
                event, msg = "rep", "¡Perfecta!"
                self.last_rep_at = now
                self._reset()
            else:
                self.bad += 1
                event, msg = "bad", f"{self.issues[0]} (no cuenta)"
                self.last_rep_at = now
                self._reset()
        return Update("warn" if m.issue else "ok", msg or m.issue, event, progress)

    def _reset(self):
        self.phase = "rest"
        self.issues = []
