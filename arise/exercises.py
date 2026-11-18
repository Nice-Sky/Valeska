"""Ejercicios: cómo se mide cada uno a partir de la pose y cómo se cuentan las repeticiones.

Índices de MediaPipe Pose:
  0 nariz | 11/12 hombros | 13/14 codos | 15/16 muñecas
  23/24 caderas | 25/26 rodillas | 27/28 tobillos

Ideas clave para que funcione de frente, de costado y en diagonal:
  * Los ángulos se calculan con las coordenadas 3D de mundo (metros), que no dependen tanto del ángulo de la cámara.
  * Cuando un ángulo 3D se "aplasta" (por ejemplo la rodilla vista de frente), se combina con medidas verticales
    en la imagen normalizadas por otro segmento del cuerpo (la altura no cambia al girar la cámara).
  * Cada chequeo de técnica dice si está bien, mal, o si con esta vista NO se puede verificar (en vez de asumir
    que está todo bien).

Todos los textos están en español y se traducen al mostrarse (arise.i18n.t).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional

VIS = 0.55  # visibilidad mínima para confiar en un punto
ARMS = ((11, 13, 15), (12, 14, 16))
LEGS = ((23, 25, 27), (24, 26, 28))
HIPS_LINE = ((11, 23, 27), (12, 24, 28))


# ---------------------------------------------------------------- geometría
def _v(p) -> float:
    v = getattr(p, "visibility", None)
    return 1.0 if v is None else float(v)


def _z(p) -> float:
    return float(getattr(p, "z", 0.0) or 0.0)


def angle3(a, b, c) -> float:
    """Ángulo ABC en grados (3D, coordenadas de mundo en metros)."""
    ab = (a.x - b.x, a.y - b.y, _z(a) - _z(b))
    cb = (c.x - b.x, c.y - b.y, _z(c) - _z(b))
    dot = sum(i * j for i, j in zip(ab, cb))
    m = math.hypot(*ab) * math.hypot(*cb)
    if not m:
        return 180.0
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / m))))


def mid(a, b):
    class _P:
        pass
    p = _P()
    p.x, p.y, p.z = (a.x + b.x) / 2, (a.y + b.y) / 2, (_z(a) + _z(b)) / 2
    p.visibility = min(_v(a), _v(b))
    return p


def dist2(a, b, aspect) -> float:
    """Distancia en la imagen, en unidades de alto de imagen."""
    return math.hypot((a.x - b.x) * aspect, a.y - b.y)


def angle2(a, b, c, aspect) -> float:
    """Ángulo ABC en la imagen (2D). De costado es más preciso y estable que el 3D para movimientos de perfil."""
    ab = ((a.x - b.x) * aspect, a.y - b.y)
    cb = ((c.x - b.x) * aspect, c.y - b.y)
    m = math.hypot(*ab) * math.hypot(*cb)
    if not m:
        return 180.0
    return math.degrees(math.acos(max(-1.0, min(1.0, (ab[0] * cb[0] + ab[1] * cb[1]) / m))))


def dist3(a, b) -> float:
    return math.hypot(a.x - b.x, a.y - b.y, _z(a) - _z(b))


def elevation(a, b) -> float:
    """Cuánto sube el segmento a→b respecto de la horizontal, en grados (mundo: y apunta hacia abajo)."""
    dx, dy, dz = b.x - a.x, b.y - a.y, _z(b) - _z(a)
    h = math.hypot(dx, dz)
    if not h and not dy:
        return 0.0
    return math.degrees(math.atan2(-dy, h))


def min_vis(lm, idx) -> float:
    return min(_v(lm[i]) for i in idx)


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def mean(vals) -> float:
    vals = list(vals)
    return sum(vals) / len(vals) if vals else 0.0


def visible_sets(lm, sets, k=1.0):
    return [s for s in sets if min_vis(lm, s) > VIS * k]


def is_horizontal(lm, a, b, aspect) -> bool:
    dx = abs(lm[a].x - lm[b].x) * aspect
    dy = abs(lm[a].y - lm[b].y)
    return dx > dy * 1.2


def torso_elevation(lm, w) -> float:
    """Inclinación del tronco (cadera → hombros): 90 = parado, 0 = acostado."""
    src = w if w is not None else lm
    hip, sh = mid(src[23], src[24]), mid(src[11], src[12])
    if w is None:  # sin mundo: estimación 2D
        return math.degrees(math.atan2(hip.y - sh.y, abs(hip.x - sh.x) + 1e-6))
    return elevation(hip, sh)


def is_upright(lm, w, aspect, view: str, limit: float = 58) -> bool:
    """¿Está parado/sentado (no horizontal)? De frente la profundidad engaña, así que se usa la altura en la imagen."""
    if view == "front" and min_vis(lm, (11, 12)) > VIS * 0.6:
        ank = [i for i in (27, 28, 25, 26) if _v(lm[i]) > VIS * 0.6]
        sw = abs(lm[11].x - lm[12].x) * aspect
        if ank and sw > 0.02:
            sh_y = (lm[11].y + lm[12].y) / 2
            k = 1.0 if ank[0] in (27, 28) else 1.8
            return (max(lm[i].y for i in ank) - sh_y) * k / sw > 2.6
    return torso_elevation(lm, w) > limit


def body_yaw(lm, aspect) -> float:
    """Ángulo de la cámara respecto del cuerpo en grados: 0 = de frente, 90 = de costado.

    Se calcula en la imagen (sin profundidad, que MediaPipe estima mal): de frente se ve el ancho de los hombros;
    de costado, el largo del tronco (si estás horizontal) y nada de ancho.
    """
    sh, hip = mid(lm[11], lm[12]), mid(lm[23], lm[24])
    sw_x = abs(lm[11].x - lm[12].x) * aspect
    vert = hip.y - sh.y
    axis_x = abs(sh.x - hip.x) * aspect
    feet = [i for i in (27, 28) if _v(lm[i]) > VIS * 0.6]
    if feet:  # con los pies a la vista: parado si el cuerpo es mucho más alto que ancho
        ank = mid(lm[27], lm[28]) if len(feet) == 2 else lm[feet[0]]
        upright = (ank.y - sh.y) > 2.2 * max(sw_x, abs(ank.x - sh.x) * aspect)
    else:
        upright = vert > 0.9 * max(sw_x, axis_x)
    if upright:  # tronco vertical (parado / sentado)
        return math.degrees(math.acos(clamp01(sw_x / (0.76 * max(vert, 1e-6)))))
    return math.degrees(math.atan2(axis_x / 0.5, sw_x / 0.38))


def view_of(lm, w, aspect) -> str:
    """'front' (de frente), 'side' (de costado) o 'diag' (en diagonal), relativo al eje del cuerpo."""
    yaw = body_yaw(lm, aspect)
    return "front" if yaw < 22 else "side" if yaw > 62 else "diag"


def profile_angle(lm, a, b, c, aspect) -> float:
    """Ángulo ABC "de perfil" reconstruido desde la imagen: estira el eje horizontal según el ángulo de la cámara.

    Sirve para la línea del cuerpo en plancha/flexiones vistas en diagonal (de costado coincide con el 2D).
    """
    yaw = max(25.0, body_yaw(lm, aspect))
    k = aspect / math.sin(math.radians(yaw))
    ab = ((lm[a].x - lm[b].x) * k, lm[a].y - lm[b].y)
    cb = ((lm[c].x - lm[b].x) * k, lm[c].y - lm[b].y)
    m = math.hypot(*ab) * math.hypot(*cb)
    if not m:
        return 180.0
    return math.degrees(math.acos(max(-1.0, min(1.0, (ab[0] * cb[0] + ab[1] * cb[1]) / m))))


# ---------------------------------------------------------------- resultados
@dataclass
class Check:
    """Un aspecto de la técnica. state: ok | bad (la repetición no cuenta) | warn (consejo) | unknown (no se ve)."""
    key: str
    label: str
    state: str
    msg: str = ""


@dataclass
class Measure:
    visible: bool
    value: Optional[float] = None
    issue: Optional[str] = None
    hint: Optional[str] = None
    ok: bool = False
    checks: list = field(default_factory=list)
    view: str = ""
    missing: str = ""  # qué parte del cuerpo no se ve (para avisar)
    reach: list = field(default_factory=list)  # [(clave, alcanzado_en_este_cuadro, mensaje)]: metas de recorrido

    def check(self, key, label, state, msg=""):
        self.checks.append(Check(key, label, state, msg))
        if state == "bad" and not self.issue:
            self.issue = msg
        return self


def hidden(missing: str) -> Measure:
    return Measure(False, missing=missing)


def _depth_eq(lm, legs, aspect, pick=min) -> Optional[float]:
    """Profundidad de flexión de piernas medida en la imagen y convertida a "ángulo equivalente" de rodilla.

    Usa cuánto está la cadera por encima de la rodilla, relativo al largo de la pantorrilla en la imagen.
    Parado ≈ 180, muslos paralelos al piso ≈ 90. Funciona igual de frente, de costado o en diagonal.
    """
    vals = []
    for h, k, a in legs:
        shank = dist2(lm[k], lm[a], aspect)
        if shank < 0.02:
            continue
        r = (lm[k].y - lm[h].y) / shank
        vals.append(90 + 90 * clamp01(r))
    return pick(vals) if vals else None


def _elbow_from_reach(d: float, upper: float = 0.30, fore: float = 0.27) -> float:
    """Ángulo de codo a partir de la distancia hombro-muñeca (ley del coseno, brazo promedio)."""
    c = (upper ** 2 + fore ** 2 - d * d) / (2 * upper * fore)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def _px_per_m(lm, aspect) -> float:
    """Escala de la imagen usando las pantorrillas (casi verticales al estar parado): unidades de imagen por metro."""
    vals = [dist2(lm[k], lm[a], aspect) / 0.43 for k, a in ((25, 27), (26, 28)) if min_vis(lm, (k, a)) > VIS * 0.6]
    return max(vals) if vals else 0.0


def blend(view: str, a3d: float, eq: Optional[float], plane: str = "sag") -> float:
    """Combina el ángulo 3D con la medida 2D equivalente según la vista.

    Movimientos en el plano sagital (adelante/atrás: sentadilla, flexión, curl...) se ven bien de costado y se
    "aplastan" de frente; los del plano frontal (press, elevaciones laterales...) al revés.
    """
    if eq is None:
        return a3d
    good = "side" if plane == "sag" else "front"
    if view == good:
        return a3d
    if view == "diag":
        return (a3d + eq) / 2
    return eq


def _squat_eq(lm, legs, aspect) -> Optional[float]:
    """Ángulo de rodilla estimado por la altura de la cadera sobre la rodilla (sirve de frente)."""
    vals = []
    for h, k, a in legs:
        shank = dist2(lm[k], lm[a], aspect)
        if shank < 0.02:
            continue
        r = clamp01((lm[k].y - lm[h].y) / shank / 1.05)
        vals.append(180 - math.degrees(math.acos(r)) / 0.58)
    return mean(vals) if vals else None


def _body_line(lm, w, side):
    """Ángulo hombro-cadera-tobillo y si la cadera está por arriba (+) o por debajo (−) de la línea recta."""
    s, h, a = side
    line = angle3(w[s], w[h], w[a])
    # posición vertical de la cadera respecto de la recta hombro-tobillo (mundo: y hacia abajo)
    t = 0.5
    dx, dz = w[a].x - w[s].x, _z(w[a]) - _z(w[s])
    span = dx * dx + dz * dz
    if span > 1e-6:
        t = clamp01(((w[h].x - w[s].x) * dx + (_z(w[h]) - _z(w[s])) * dz) / span)
    y_line = w[s].y + (w[a].y - w[s].y) * t
    return line, (y_line - w[h].y)  # >0: cadera más alta que la línea


def knees_on_floor(lm, view: str) -> Optional[bool]:
    """¿Rodillas apoyadas? Altura de la rodilla sobre la línea "piso" (manos/codos → tobillos), relativa a la cadera.

    Las distancias verticales en la imagen no dependen del ángulo de la cámara (de costado o en diagonal).
    De frente no se puede saber bien (None).
    """
    if view == "front":
        return None
    best = None
    for s_, e, wr, h, k, a in ((11, 13, 15, 23, 25, 27), (12, 14, 16, 24, 26, 28)):
        v = min_vis(lm, (h, k, a)) + max(_v(lm[wr]), _v(lm[e]))
        if min_vis(lm, (h, k, a)) > VIS * 0.6 and (best is None or v > best[0]):
            hand = lm[wr] if lm[wr].y >= lm[e].y else lm[e]  # el punto apoyado (el más bajo)
            best = (v, hand, lm[h], lm[k], lm[a])
    if best is None:
        return None
    _, hand, hip, knee, ank = best

    def height(p):
        dx = ank.x - hand.x
        t = 0.5 if abs(dx) < 1e-6 else (p.x - hand.x) / dx
        return hand.y + (ank.y - hand.y) * t - p.y   # >0: por encima de la línea del piso

    hh = height(hip)
    if hh < 0.02:
        return None
    return height(knee) / hh < 0.22


# ---------------------------------------------------------------- mediciones (lm, w, aspect, ctx)
def m_pushup(lm, w, aspect, ctx):
    arms = visible_sets(lm, ARMS, 0.8)
    if not arms:
        return hidden("brazos")
    view = view_of(lm, w, aspect)
    m = Measure(True, view=view)
    if is_upright(lm, w, aspect, view, 60):
        m.hint = "Ponete en posición de flexión"
        return m
    if not any(lm[a[2]].y > lm[a[0]].y + 0.02 for a in arms):
        m.hint = "Apoyá las manos en el piso, debajo de los hombros"
        return m
    elbow = mean(angle3(w[a], w[b], w[c]) for a, b, c in arms)
    eq = None
    sw = abs(lm[11].x - lm[12].x) * aspect
    if view != "side" and sw > 0.03:  # de frente el codo se "aplasta": medimos la bajada del hombro hacia las manos
        d = mean(lm[c].y - lm[a].y for a, b, c in arms) / sw * 0.38  # distancia hombro-mano en metros aprox.
        eq = _elbow_from_reach(d)
    m.value = blend(view, elbow, eq)
    # línea del cuerpo y rodillas
    lines = visible_sets(lm, HIPS_LINE, 0.7)
    knees = visible_sets(lm, LEGS, 0.7)
    kang = (lambda h, k, a: profile_angle(lm, h, k, a, aspect)) if view != "front" else \
        (lambda h, k, a: angle3(w[h], w[k], w[a]))
    kd = knees_on_floor(lm, view)
    if knees and (kd or mean(kang(h, k, a) for h, k, a in knees) < 140):
        m.check("knees", "Rodillas", "bad", "Estirá las piernas: rodillas sin apoyar")
    elif knees:
        m.check("knees", "Rodillas", "ok")
    else:
        m.check("knees", "Rodillas", "unknown", "No veo tus piernas")
    if lines and view != "front":
        _, up = _body_line(lm, w, lines[0])
        s_, h_, a_ = lines[0]
        line = profile_angle(lm, s_, h_, a_, aspect)
        t = clamp01((lm[h_].x - lm[s_].x) / ((lm[a_].x - lm[s_].x) or 1e-6))
        up = (lm[s_].y + (lm[a_].y - lm[s_].y) * t) - lm[h_].y
        if line < 155:
            m.check("line", "Cadera", "bad", "Bajá la cadera, cuerpo recto" if up > 0 else "Subí la cadera, no la dejes caer")
        else:
            m.check("line", "Cadera", "ok")
    else:
        m.check("line", "Cadera", "unknown", "Cadera sin verificar: ponete de costado o en diagonal")
    if view == "front" and len(arms) == 2:
        sw = abs(lm[11].x - lm[12].x)
        ew = abs(lm[13].x - lm[14].x)
        if sw > 0.02 and elbow < 115 and ew > 2.0 * sw:
            m.check("elbows", "Codos", "warn", "Codos más cerca del cuerpo (a 45°)")
        else:
            m.check("elbows", "Codos", "ok")
    return m


def m_squat(lm, w, aspect, ctx):
    legs = visible_sets(lm, LEGS, 0.8)
    if not legs:
        return hidden("piernas")
    view = view_of(lm, w, aspect)
    m = Measure(True, view=view)
    knee = mean(angle3(w[a], w[b], w[c]) for a, b, c in legs)
    m.value = blend(view, knee, _squat_eq(lm, legs, aspect))
    deep = m.value < 130
    # rodillas hacia adentro: solo se ve de frente o en diagonal
    if len(legs) == 2 and view in ("front", "diag"):
        kd, ad = abs(lm[25].x - lm[26].x), abs(lm[27].x - lm[28].x)
        lim = 0.7 if view == "front" else 0.6
        if deep and ad > 0.02 and kd < lim * ad:
            m.check("knees", "Rodillas", "bad", "Rodillas hacia afuera, no las juntes")
        else:
            m.check("knees", "Rodillas", "ok")
    else:
        m.check("knees", "Rodillas", "unknown", "Alineación de rodillas sin verificar (de costado no se ve)")
    # pecho: inclinación del tronco, confiable de costado o en diagonal
    if min_vis(lm, (11, 12)) > VIS * 0.6 or min_vis(lm, (11,)) > VIS:
        lean = 90 - torso_elevation(lm, w)
        if view == "front":
            m.check("chest", "Pecho", "unknown", "Inclinación del pecho sin verificar de frente")
        elif deep and lean > 55:
            m.check("chest", "Pecho", "bad", "Pecho arriba, no te inclines tanto")
        else:
            m.check("chest", "Pecho", "ok")
    if len(legs) == 2 and view != "side" and deep:
        a1, a2 = (angle3(w[a], w[b], w[c]) for a, b, c in LEGS)
        if abs(a1 - a2) > 28:
            m.check("balance", "Equilibrio", "warn", "Repartí el peso en las dos piernas")
    return m


def m_situp(lm, w, aspect, ctx):
    """Elevación del tronco respecto del piso (sirve de costado, de frente o en diagonal)."""
    l, r = min_vis(lm, (11, 23)), min_vis(lm, (12, 24))
    if max(l, r) < VIS * 0.65:
        return hidden("tronco")
    view = view_of(lm, w, aspect)
    m = Measure(True, view=view)
    elev = torso_elevation(lm, w)
    knees = visible_sets(lm, LEGS, 0.6) or [s for s in LEGS if min_vis(lm, s[:2]) > VIS * 0.6]
    knee_ang = mean(angle3(w[h], w[k], w[a]) for h, k, a in knees) if knees and min_vis(lm, knees[0]) > VIS * 0.6 else None
    if elev > 70 and (knee_ang is None or knee_ang > 150):
        m.hint = "Acostate boca arriba con las rodillas flexionadas"
        return m
    m.value = 180 - elev
    if knee_ang is None:
        m.check("knees", "Rodillas", "unknown", "No veo tus rodillas")
    elif knee_ang > 160:
        m.check("knees", "Rodillas", "warn", "Flexioná las rodillas, pies apoyados")
    else:
        m.check("knees", "Rodillas", "ok")
    return m


def m_jack(lm, w, aspect, ctx):
    if min_vis(lm, (11, 12, 15, 16, 27, 28)) < VIS * 0.6:
        return hidden("cuerpo")
    view = view_of(lm, w, aspect)
    src = w if (w is not None and dist3(w[11], w[12]) > 0.05) else None
    if src is None:  # 2D (también los tests viejos)
        sh_y = (lm[11].y + lm[12].y) / 2
        hip_y = (lm[23].y + lm[24].y) / 2
        torso = max(0.05, hip_y - sh_y)
        arm = mean(clamp01((sh_y - lm[i].y) / (torso * 0.55)) for i in (15, 16))
        sh_w = max(0.03, abs(lm[11].x - lm[12].x))
        leg = clamp01((abs(lm[27].x - lm[28].x) / sh_w - 1.0) / 0.6)
    else:
        sh_y = (src[11].y + src[12].y) / 2
        torso = max(0.2, dist3(mid(src[11], src[12]), mid(src[23], src[24])))
        arm = mean(clamp01((sh_y - src[i].y) / (torso * 0.55)) for i in (15, 16))
        leg = clamp01((dist3(src[27], src[28]) / max(0.15, dist3(src[11], src[12])) - 1.0) / 0.6)
    m = Measure(True, (arm + leg) / 2, view=view)
    if view == "side":
        m.check("view", "Vista", "warn", "Para los jumping jacks ponete de frente")
    return m


def m_lunge(lm, w, aspect, ctx):
    legs = visible_sets(lm, LEGS, 0.75)
    if not legs:
        return hidden("piernas")
    view = view_of(lm, w, aspect)
    m = Measure(True, view=view)
    knee = min(angle3(w[a], w[b], w[c]) for a, b, c in legs)
    m.value = blend(view, knee, _depth_eq(lm, legs, aspect, pick=min))
    if view != "front" and min_vis(lm, (11,)) > VIS * 0.6:
        lean = 90 - torso_elevation(lm, w)
        m.check("chest", "Tronco", "bad" if (m.value < 125 and lean > 35) else "ok", "Tronco derecho")
    else:
        m.check("chest", "Tronco", "unknown", "Postura del tronco sin verificar de frente")
    return m


def m_plank(lm, w, aspect, ctx):
    """Plancha: cuerpo recto (sin cadera caída ni levantada) y sin apoyar las rodillas."""
    lines = visible_sets(lm, HIPS_LINE, 0.75)
    upper = [s for s in ((11, 23), (12, 24)) if min_vis(lm, s) > VIS * 0.75]
    if not upper:
        return hidden("tronco")
    view = view_of(lm, w, aspect)
    m = Measure(True, view=view)
    if is_upright(lm, w, aspect, view, 58):
        m.hint = "Ponete en posición de plancha"
        return m
    if not lines:
        m.missing = "piernas"
        m.check("line", "Cadera", "unknown", "No veo tus piernas: no cuento hasta verte completo")
        return m
    knees = visible_sets(lm, LEGS, 0.7)
    side = view != "front"
    ang = (lambda a, b, c: profile_angle(lm, a, b, c, aspect)) if side else (lambda a, b, c: angle3(w[a], w[b], w[c]))
    knee = mean(ang(h, k, a) for h, k, a in knees) if knees else None
    line3, up = _body_line(lm, w, lines[0])
    line = ang(*lines[0]) if side else line3
    if side:  # de perfil la imagen dice directo si la cadera está arriba o abajo de la recta
        s_, h_, a_ = lines[0]
        t = clamp01((lm[h_].x - lm[s_].x) / ((lm[a_].x - lm[s_].x) or 1e-6))
        up = (lm[s_].y + (lm[a_].y - lm[s_].y) * t) - lm[h_].y
    ema = ctx.get("line")
    line = line if ema is None else ema * 0.6 + line * 0.4
    ctx["line"] = line
    # histéresis: para "romper" la línea hay que bajar del umbral; para recuperarla, superarlo por 5°
    lim = 162
    was_bad = ctx.get("bad", False)
    bad_line = line < (lim + 5 if was_bad else lim)
    if knee is not None and (knee < 145 or knees_on_floor(lm, view)):
        m.check("knees", "Rodillas", "bad", "Levantá las rodillas del piso")
    elif knee is not None:
        m.check("knees", "Rodillas", "ok")
    else:
        m.check("knees", "Rodillas", "unknown", "No veo tus rodillas")
    if view == "front":
        # de frente la profundidad es poco confiable: solo se marca si el error es muy grande
        if line < 135:
            m.check("line", "Cadera", "bad", "Bajá la cadera" if up > 0 else "Subí la cadera, no la dejes caer")
        else:
            m.check("line", "Cadera", "unknown", "Cadera sin verificar de frente: ponete de costado o en diagonal")
    elif bad_line:
        m.check("line", "Cadera", "bad", "Bajá la cadera" if up > 0 else "Subí la cadera, no la dejes caer")
    else:
        m.check("line", "Cadera", "ok")
    ctx["bad"] = any(c.state == "bad" for c in m.checks if c.key == "line")
    m.ok = not any(c.state == "bad" for c in m.checks)
    return m


def m_side_plank(lm, w, aspect, ctx):
    lines = visible_sets(lm, HIPS_LINE, 0.7)
    if not lines:
        return hidden("cuerpo")
    view = view_of(lm, w, aspect)
    m = Measure(True, view=view)
    if torso_elevation(lm, w) > 55:
        m.hint = "Apoyá un antebrazo y elevá la cadera de costado"
        return m
    line = angle3(*(w[i] for i in lines[0]))
    ema = ctx.get("line")
    line = line if ema is None else ema * 0.6 + line * 0.4
    ctx["line"] = line
    if line < (152 if ctx.get("bad") else 146):
        m.check("line", "Cadera", "bad", "Subí la cadera, cuerpo recto")
    else:
        m.check("line", "Cadera", "ok")
    ctx["bad"] = bool(m.issue)
    m.ok = not m.issue
    return m


def m_bridge(lm, w, aspect, ctx):
    """Puente de glúteos: ángulo hombro-cadera-rodilla (sube al elevar la cadera)."""
    sides = [s for s in ((11, 23, 25), (12, 24, 26)) if min_vis(lm, s) > VIS * 0.7]
    if not sides:
        return hidden("cadera")
    view = view_of(lm, w, aspect)
    m = Measure(True, view=view)
    if torso_elevation(lm, w) > 55:
        m.hint = "Acostate boca arriba, rodillas flexionadas y pies apoyados"
        return m
    m.value = mean(angle3(w[a], w[b], w[c]) for a, b, c in sides)
    return m


def m_climber(lm, w, aspect, ctx):
    """Escaladores: en plancha, rodilla al pecho alternando. Mide la menor flexión de cadera."""
    sides = [s for s in ((11, 23, 25), (12, 24, 26)) if min_vis(lm, s) > VIS * 0.7]
    if not sides:
        return hidden("cadera y rodillas")
    view = view_of(lm, w, aspect)
    m = Measure(True, view=view)
    if torso_elevation(lm, w) > 50:
        m.hint = "Ponete en posición de plancha con los brazos estirados"
        return m
    if len(sides) < 2:
        m.missing = "piernas"
        m.hint = "Necesito ver las dos piernas: ponete en diagonal"
        return m
    # diferencia entre las dos caderas: 0 con las dos piernas atrás, grande con una rodilla al pecho
    a1, a2 = (angle3(w[a], w[b], w[c]) for a, b, c in sides)
    m.value = abs(a1 - a2)
    return m


def _hanging(lm) -> bool:
    return min_vis(lm, (15, 16)) > VIS * 0.6 and min(lm[15].y, lm[16].y) < lm[0].y + 0.02


def m_pullup(lm, w, aspect, ctx):
    arms = visible_sets(lm, ARMS, 0.7)
    if not arms:
        return hidden("brazos")
    view = view_of(lm, w, aspect)
    m = Measure(True, view=view)
    if not _hanging(lm):
        m.hint = "Colgate de la barra con los brazos estirados"
        return m
    elbow = mean(angle3(w[a], w[b], w[c]) for a, b, c in arms)
    # altura de los hombros respecto de las manos, relativa al largo del tronco (vertical al estar colgado)
    tl = dist2(mid(lm[11], lm[12]), mid(lm[23], lm[24]), aspect)
    eq = None
    if tl > 0.03:
        v = (mean(lm[a].y for a, b, c in arms) - mean(lm[c].y for a, b, c in arms)) / tl * 0.5  # metros
        eq = _elbow_from_reach(math.hypot(max(0.0, v), 0.15))
    m.value = blend(view, elbow, eq, plane="front")
    # mentón por encima de la barra (≈ altura de las manos) en la parte alta
    bar_y = mean(lm[c].y for a, b, c in arms)
    if _v(lm[0]) > 0.5:  # meta de recorrido: en algún momento de la repetición el mentón pasa la barra
        m.reach.append(("chin", lm[0].y < bar_y + 0.02, "Pasá el mentón por encima de la barra"))
    knees = visible_sets(lm, LEGS, 0.6)
    if knees:
        hip = min(angle3(w[s], w[h], w[k]) for s, h, k in ((11, 23, 25), (12, 24, 26)))
        ref = ctx.setdefault("hip", hip)
        ctx["hip"] = ref * 0.97 + hip * 0.03
        m.check("swing", "Balanceo", "warn" if abs(hip - ref) > 35 else "ok", "Sin balanceo: subí solo con los brazos")
    return m


def m_knee_raise(lm, w, aspect, ctx):
    sides = [s for s in ((11, 23, 25), (12, 24, 26)) if min_vis(lm, s) > VIS * 0.7]
    if not sides:
        return hidden("cadera y rodillas")
    m = Measure(True, view=view_of(lm, w, aspect))
    if not _hanging(lm):
        m.hint = "Colgate de la barra con los brazos estirados"
        return m
    m.value = mean(angle3(w[a], w[b], w[c]) for a, b, c in sides)
    return m


def _upper_arm_drift(w, s, e, h) -> float:
    return angle3(w[e], w[s], w[h])  # 0 = codo pegado al costado


def m_curl(lm, w, aspect, ctx):
    arms = visible_sets(lm, ARMS, 0.75)
    if not arms:
        return hidden("brazos")
    view = view_of(lm, w, aspect)
    m = Measure(True, view=view)
    if torso_elevation(lm, w) < 55:
        m.hint = "Parate derecho con las mancuernas a los costados"
        return m
    angs = []
    for a, b, c in arms:
        a3 = angle3(w[a], w[b], w[c])
        ua = dist2(lm[a], lm[b], aspect)
        eq = None
        if ua > 0.02:  # el brazo queda vertical: la altura de la mano respecto del codo da el ángulo
            rel = (lm[c].y - lm[b].y) / ua
            eq = 180 - math.degrees(math.acos(max(-1.0, min(1.0, rel * 1.11))))
        angs.append(blend(view, a3, eq))
    m.value = min(angs)
    i = angs.index(m.value)
    s, e, _ = arms[i]
    hip = 23 if s == 11 else 24
    if _v(lm[hip]) > VIS * 0.6:
        drift = _upper_arm_drift(w, s, e, hip)
        if m.value < 100 and drift > 40:
            m.check("elbow", "Codo", "bad", "Codo pegado al cuerpo: no lo adelantes")
        else:
            m.check("elbow", "Codo", "ok")
        elev = torso_elevation(lm, w)
        ref = ctx.setdefault("torso", elev)
        ctx["torso"] = ref * 0.98 + elev * 0.02
        if view != "front":
            m.check("swing", "Torso", "bad" if abs(elev - ref) > 14 else "ok", "Sin balancear el torso")
        else:
            m.check("swing", "Torso", "unknown", "Balanceo del torso sin verificar de frente")
    else:
        m.check("elbow", "Codo", "unknown", "No veo tu cadera para revisar el codo")
    return m


def m_press(lm, w, aspect, ctx):
    arms = visible_sets(lm, ARMS, 0.75)
    if not arms:
        return hidden("brazos")
    view = view_of(lm, w, aspect)
    m = Measure(True, view=view)
    if not any(lm[c].y < lm[b].y + 0.02 for a, b, c in arms):
        m.hint = "Llevá las mancuernas a la altura de los hombros"
        return m
    elbow = mean(angle3(w[a], w[b], w[c]) for a, b, c in arms)
    tl = dist2(mid(lm[11], lm[12]), mid(lm[23], lm[24]), aspect) if min_vis(lm, (23, 24)) > 0.3 else 0
    eq = None
    if tl > 0.03:  # altura de las manos sobre los hombros, relativa al tronco
        rn = mean(lm[a].y - lm[c].y for a, b, c in arms) / (1.14 * tl)
        eq = 75 + 105 * clamp01((rn - 0.42) / 0.57)
    m.value = blend(view, elbow, eq, plane="front")
    if view != "front" and _v(lm[23]) > VIS * 0.5:
        lean = 90 - torso_elevation(lm, w)
        m.check("back", "Espalda", "warn" if lean > 18 else "ok", "No arquees la espalda: abdomen firme")
    else:
        m.check("back", "Espalda", "unknown", "Espalda sin verificar de frente")
    return m


def m_lateral(lm, w, aspect, ctx):
    sides = [s for s in ((23, 11, 13), (24, 12, 14)) if min_vis(lm, s) > VIS * 0.7]
    if not sides:
        return hidden("brazos y cadera")
    m = Measure(True, view=view_of(lm, w, aspect))
    a3 = mean(angle3(w[a], w[b], w[c]) for a, b, c in sides)
    tl = dist2(mid(lm[11], lm[12]), mid(lm[23], lm[24]), aspect)
    eq = None
    if tl > 0.03:  # altura del codo respecto del hombro
        rel = mean(lm[e].y - lm[s_].y for h, s_, e in sides) / (0.6 * tl)
        eq = math.degrees(math.acos(max(-1.0, min(1.0, rel))))
    m.value = blend(m.view, a3, eq, plane="front")
    arms = visible_sets(lm, ARMS, 0.7)
    if arms and m.value > 50:
        el = min(angle3(w[a], w[b], w[c]) for a, b, c in arms)
        m.check("elbow", "Brazos", "warn" if el < 130 else "ok", "Brazos casi estirados, codo apenas flexionado")
    if m.value > 115:
        m.check("height", "Altura", "warn", "Subí solo hasta la altura de los hombros")
    return m


def m_row(lm, w, aspect, ctx):
    arms = visible_sets(lm, ARMS, 0.7)
    if not arms:
        return hidden("brazos")
    view = view_of(lm, w, aspect)
    m = Measure(True, view=view)
    elev = torso_elevation(lm, w)
    if elev > 72:
        m.hint = "Inclinate hacia adelante con la espalda recta"
        return m
    a3 = min(angle3(w[a], w[b], w[c]) for a, b, c in arms)
    ppm = _px_per_m(lm, aspect)
    eq = None
    if view != "side" and ppm > 0.05:  # cuánto suben las manos hacia el tronco
        r = max(lm[c].y - lm[a].y for a, b, c in arms) / (0.57 * ppm)
        eq = 85 + 85 * clamp01((r - 0.575) / 0.425)
    m.value = blend(view, a3, eq)
    ref = ctx.setdefault("torso", elev)
    ctx["torso"] = ref * 0.97 + elev * 0.03
    if view != "front":
        m.check("torso", "Tronco", "bad" if elev - ref > 18 else "ok", "Mantené el tronco inclinado, sin incorporarte")
    else:
        m.check("torso", "Tronco", "unknown", "Postura del tronco sin verificar de frente")
    return m


def m_rdl(lm, w, aspect, ctx):
    sides = [s for s in ((11, 23, 25), (12, 24, 26)) if min_vis(lm, s) > VIS * 0.7]
    if not sides:
        return hidden("cadera y rodillas")
    view = view_of(lm, w, aspect)
    m = Measure(True, view=view)
    a3 = mean(angle3(w[a], w[b], w[c]) for a, b, c in sides)
    ppm = _px_per_m(lm, aspect)
    eq = None
    if view != "side" and ppm > 0.05:  # cuánto baja el pecho hacia la altura de la cadera
        rr = (mean(lm[i].y for i in (23, 24)) - mean(lm[i].y for i in (11, 12))) / (0.5 * ppm)
        eq = 90 + math.degrees(math.asin(max(-1.0, min(1.0, rr))))
    m.value = blend(view, a3, eq)
    legs = visible_sets(lm, LEGS, 0.7)
    if legs:
        knee = mean(angle3(w[a], w[b], w[c]) for a, b, c in legs)
        if m.value < 140 and knee < 125:
            m.check("knees", "Rodillas", "bad", "Es bisagra de cadera: rodillas casi estiradas")
        else:
            m.check("knees", "Rodillas", "ok")
    if view == "front":
        m.check("back", "Espalda", "unknown", "Espalda sin verificar de frente: ponete de costado")
    return m


# ---------------------------------------------------------------- catálogo
@dataclass
class Exercise:
    id: str
    name: str
    icon: str
    stat: str
    xp: float
    tip: str
    measure: Callable
    group: str = "core"          # push | pull | legs | core | cardio
    equip: str = ""              # "" (peso corporal) | bar (barra de dominadas) | dumbbell (mancuernas)
    unit: str = "reps"
    timed: bool = False
    direction: str = "lower"     # el valor baja al hacer el esfuerzo
    rest: float = 0
    mid: float = 0
    active: float = 0
    partial_msg: str = ""
    return_msg: str = ""         # volvió a hacer fuerza sin completar el recorrido de vuelta
    adaptive: Optional[tuple] = None  # (activo, mitad, reposo): respecto de TU posición de reposo
    views: str = "front,side,diag"   # vistas en las que se puede medir
    best_view: str = ""
    level: int = 1               # dificultad: se van sumando a medida que progresás
    min_rep_s: float = 0.55      # menos que esto por repetición = demasiado rápido
    loaded: bool = False         # usa peso (kg)


EXERCISES: dict[str, Exercise] = {e.id: e for e in [
    Exercise("pushup", "Flexiones", "biceps-flexed", "FUE", 3,
             "Cámara a la altura del piso, de frente, de costado o en diagonal. Que se vean brazos y torso; "
             "de costado o en diagonal también reviso la cadera.",
             m_pushup, group="push", rest=145, mid=122, active=102, partial_msg="Bajá más el pecho",
             return_msg="Estirá los brazos arriba", best_view="diag", level=1),
    Exercise("squat", "Sentadillas", "person-standing", "FUE", 2,
             "De frente, de costado o en diagonal, con piernas y torso a la vista. "
             "De frente reviso las rodillas; de costado, el pecho.",
             m_squat, group="legs", rest=155, mid=132, active=106, partial_msg="Bajá más, muslos paralelos al piso",
             return_msg="Subí hasta quedar derecho", best_view="diag", level=1),
    Exercise("situp", "Abdominales", "flame", "RES", 2,
             "Boca arriba, rodillas flexionadas. La cámara baja (piso o silla), de costado o desde los pies. "
             "Valen crunches y abdominales completos.",
             m_situp, group="core", rest=0, mid=0, active=0, partial_msg="Subí un poco más el torso",
             adaptive=(20, 10, 5), best_view="side", level=1),
    Exercise("plank", "Plancha", "timer", "RES", 0.5,
             "Cámara al piso, de costado o en diagonal (de frente no puedo revisar la cadera). "
             "El tiempo corre solo con el cuerpo recto y las rodillas arriba.",
             m_plank, group="core", unit="seg", timed=True, best_view="side", level=1),
    Exercise("jack", "Jumping Jacks", "zap", "AGI", 1,
             "De frente a la cámara, cuerpo entero a la vista.",
             m_jack, group="cardio", direction="higher", rest=0.22, mid=0.45, active=0.72,
             partial_msg="Brazos bien arriba y piernas abiertas", best_view="front", level=2, min_rep_s=0.3),
    Exercise("lunge", "Zancadas", "footprints", "AGI", 2,
             "De frente, de costado o en diagonal. Alterná piernas: cada bajada cuenta.",
             m_lunge, group="legs", rest=155, mid=132, active=108, partial_msg="Bajá más la rodilla de atrás",
             best_view="side", level=2),
    Exercise("bridge", "Puente de glúteos", "activity", "FUE", 1.5,
             "Boca arriba, rodillas flexionadas. Cámara baja de costado o en diagonal. Subí la cadera y apretá.",
             m_bridge, group="legs", direction="higher", adaptive=(22, 11, 5), partial_msg="Subí más la cadera",
             best_view="side", level=2),
    Exercise("climber", "Escaladores", "footprints", "AGI", 1,
             "En plancha con brazos estirados, llevá una rodilla al pecho y alterná. Cámara al piso de costado o en diagonal.",
             m_climber, group="cardio", direction="higher", rest=14, mid=28, active=42, partial_msg="Llevá la rodilla más cerca del pecho",
             best_view="side", level=3, min_rep_s=0.25),
    Exercise("side_plank", "Plancha lateral", "timer", "RES", 0.5,
             "Apoyado en un antebrazo, de frente a la cámara. El tiempo corre con la cadera arriba.",
             m_side_plank, group="core", unit="seg", timed=True, best_view="front", level=3),
    # ---- barra de dominadas
    Exercise("pullup", "Dominadas", "hand-fist", "FUE", 6,
             "Cámara de frente o en diagonal, que se vean la barra, tus manos y tu cadera. "
             "Bajá hasta estirar los brazos y subí hasta pasar el mentón.",
             m_pullup, group="pull", equip="bar", rest=150, mid=118, active=92,
             partial_msg="Subí más, mentón sobre la barra", return_msg="Bajá hasta estirar los brazos",
             best_view="front", level=1, min_rep_s=0.8),
    Exercise("chinup", "Dominadas supinas", "hand-fist", "FUE", 5,
             "Palmas hacia vos. Cámara de frente o en diagonal, que se vean la barra, tus manos y tu cadera.",
             m_pullup, group="pull", equip="bar", rest=150, mid=118, active=92,
             partial_msg="Subí más, mentón sobre la barra", return_msg="Bajá hasta estirar los brazos",
             best_view="front", level=1, min_rep_s=0.8),
    Exercise("knee_raise", "Elevaciones de rodillas", "hand-fist", "RES", 3,
             "Colgado de la barra, subí las rodillas al pecho sin balancearte. Cámara de costado o en diagonal.",
             m_knee_raise, group="core", equip="bar", rest=150, mid=125, active=102,
             partial_msg="Subí más las rodillas", best_view="side", level=2, min_rep_s=0.7),
    # ---- mancuernas
    Exercise("curl", "Curl de bíceps", "dumbbell", "FUE", 1.5,
             "Parado, de costado o en diagonal (de frente no veo si balanceás). Codos pegados al cuerpo.",
             m_curl, group="pull", equip="dumbbell", rest=150, mid=105, active=72, partial_msg="Subí más la mancuerna",
             return_msg="Bajá hasta estirar el brazo", best_view="diag", level=1, loaded=True, min_rep_s=0.8),
    Exercise("press", "Press de hombros", "dumbbell", "FUE", 2,
             "Parado o sentado, mancuernas a la altura de los hombros. De frente o en diagonal.",
             m_press, group="push", equip="dumbbell", direction="higher", rest=100, mid=130, active=158,
             partial_msg="Estirá los brazos arriba", return_msg="Bajá hasta los hombros", best_view="front",
             level=1, loaded=True, min_rep_s=0.8),
    Exercise("row", "Remo con mancuernas", "dumbbell", "FUE", 2,
             "Inclinado hacia adelante, espalda recta, de costado o en diagonal. Llevá los codos hacia atrás.",
             m_row, group="pull", equip="dumbbell", rest=145, mid=118, active=95, partial_msg="Tirá más los codos hacia atrás",
             return_msg="Estirá los brazos abajo", best_view="side", level=1, loaded=True, min_rep_s=0.8),
    Exercise("lateral", "Elevaciones laterales", "dumbbell", "FUE", 1.5,
             "De frente a la cámara. Subí los brazos a los costados hasta la altura de los hombros.",
             m_lateral, group="push", equip="dumbbell", direction="higher", rest=30, mid=55, active=74,
             partial_msg="Subí hasta la altura de los hombros", best_view="front", level=2, loaded=True, min_rep_s=0.8),
    Exercise("goblet", "Sentadilla goblet", "dumbbell", "FUE", 3,
             "Una mancuerna contra el pecho. De frente, de costado o en diagonal.",
             m_squat, group="legs", equip="dumbbell", rest=155, mid=132, active=106,
             partial_msg="Bajá más, muslos paralelos al piso", return_msg="Subí hasta quedar derecho",
             best_view="diag", level=2, loaded=True),
    Exercise("rdl", "Peso muerto rumano", "dumbbell", "FUE", 2.5,
             "De costado a la cámara. Cadera hacia atrás, espalda recta y rodillas casi estiradas.",
             m_rdl, group="legs", equip="dumbbell", rest=160, mid=138, active=118,
             partial_msg="Llevá más la cadera hacia atrás", best_view="side", level=2, loaded=True, min_rep_s=0.9),
]}
EXERCISE_ORDER = list(EXERCISES)
GROUPS = {"push": "Empuje", "pull": "Tirón", "legs": "Piernas", "core": "Core", "cardio": "Cardio"}
EQUIPMENT = {"bar": "Barra de dominadas", "dumbbell": "Mancuernas"}
VIEW_NAMES = {"front": "FRENTE", "side": "COSTADO", "diag": "DIAGONAL"}


def available(equipment) -> list[str]:
    eq = set(equipment or [])
    return [k for k, e in EXERCISES.items() if not e.equip or e.equip in eq]


# ---------------------------------------------------------------- conteo
@dataclass
class Update:
    status: str            # ok | warn | bad | hint | hidden | unknown
    msg: Optional[str] = None
    event: Optional[str] = None   # rep | bad | partial | second
    progress: Optional[float] = None
    count: int = 0
    checks: list = field(default_factory=list)
    view: str = ""


@dataclass
class RepCounter:
    """Máquina de estados: reposo -> moviéndose -> activo -> volviendo -> reposo = 1 repetición.

    Además registra cada repetición (duración, si fue limpia y si la técnica se pudo verificar) para que la
    progresión sepa cómo te fue de verdad.
    """
    ex: Exercise
    reps: int = 0
    bad: int = 0
    seconds: float = 0.0
    phase: str = "rest"
    ema: Optional[float] = None
    issues: list = field(default_factory=list)
    last_rep_at: float = -10.0
    last_t: Optional[float] = None
    base: Optional[float] = None
    ctx: dict = field(default_factory=dict)
    log: list = field(default_factory=list)      # [{"d": duración, "clean": bool, "verified": bool, "fast": bool}]
    rep_start: Optional[float] = None
    unverified: set = field(default_factory=set)
    warns: list = field(default_factory=list)
    reached: dict = field(default_factory=dict)
    bad_frames: dict = field(default_factory=dict)  # un error tiene que verse en varios cuadros para contar
    unknown_frames: dict = field(default_factory=dict)
    rep_frames: int = 0
    view: str = ""
    _views: list = field(default_factory=list)
    bad_since: Optional[float] = None
    timed_good: float = 0.0
    timed_bad: float = 0.0
    timed_unknown: float = 0.0
    last_activity: float = 0.0

    def _smooth_view(self, v: str) -> str:
        if v:
            self._views.append(v)
            del self._views[:-12]
        if self._views:
            best = max(set(self._views), key=self._views.count)
            if self._views.count(best) >= 7 or not self.view:
                self.view = best
        return self.view

    def update(self, lm, w, aspect: float, now: float) -> Update:
        ex = self.ex
        m = ex.measure(lm, w, aspect, self.ctx)
        if not m.visible:
            self.last_t = None
            msg = {"piernas": "No veo tus piernas: alejate o bajá la cámara",
                   "brazos": "No veo tus brazos: alejate un poco de la cámara",
                   "tronco": "No veo tu tronco: acomodá la cámara"}.get(m.missing,
                                                                        "No te veo completo: alejate un poco de la cámara")
            return Update("hidden", msg)
        view = self._smooth_view(m.view)

        if ex.timed:
            dt = 0.0 if self.last_t is None else min(now - self.last_t, 0.25)
            self.last_t = now
            if m.hint:
                self.bad_since = None
                return Update("hint", m.hint, checks=m.checks, view=view)
            unknown_main = any(c.state == "unknown" and c.key == "line" and m.missing for c in m.checks)
            if unknown_main:
                self.timed_unknown += dt
                return Update("unknown", m.checks[0].msg, checks=m.checks, view=view)
            if not m.ok:
                # tolerancia: medio segundo de error antes de cortar (no cortamos por un temblor)
                self.bad_since = self.bad_since if self.bad_since is not None else now
                if now - self.bad_since < 0.5:
                    m_ok_grace = True
                else:
                    self.timed_bad += dt
                    return Update("bad", m.issue or m.hint, checks=m.checks, view=view)
            else:
                self.bad_since = None
                m_ok_grace = False
            before = int(self.seconds)
            self.seconds += dt
            self.timed_good += dt
            self.last_activity = now
            for c in m.checks:
                if c.state == "unknown":
                    self.unverified.add(c.msg)
            gained = int(self.seconds) - before
            msg = "¡Bien! Mantené" if not m_ok_grace else (m.issue or "")
            status = "ok" if not any(c.state == "unknown" for c in m.checks) else "warn"
            if m_ok_grace:
                status = "warn"
            return Update(status, msg, "second" if gained else None, 1.0, gained, checks=m.checks, view=view)

        self.last_t = now
        if m.value is None:
            return Update("hint", m.hint, checks=m.checks, view=view)

        self.ema = m.value if self.ema is None else self.ema * 0.45 + m.value * 0.55
        v = self.ema
        lower = ex.direction == "lower"
        rest_t, mid_t, active_t = ex.rest, ex.mid, ex.active
        if ex.adaptive:
            d_act, d_mid, d_rest = ex.adaptive
            sgn = -1 if lower else 1
            # aprende tu posición de reposo (el extremo reciente; se corre muy lento si no volvés)
            if self.base is None:
                self.base = v
            elif lower:
                self.base = max(v, self.base - 0.03)
            else:
                self.base = min(v, self.base + 0.03)
            active_t, mid_t, rest_t = self.base + sgn * d_act, self.base + sgn * d_mid, self.base + sgn * d_rest
        is_active = v < active_t if lower else v > active_t
        is_rest = v > rest_t if lower else v < rest_t
        past_mid = v < mid_t if lower else v > mid_t
        progress = clamp01((rest_t - v) / (rest_t - active_t)) if rest_t != active_t else 0.0

        event = msg = None
        if self.phase == "rest" and past_mid:
            self.phase = "moving"
            self.rep_start = now
        if self.phase != "rest":
            for c in m.checks:
                if c.state == "bad" and c.msg not in self.issues:
                    self.bad_frames[c.msg] = self.bad_frames.get(c.msg, 0) + 1
                    if self.bad_frames[c.msg] >= 3:
                        self.issues.append(c.msg)
                elif c.state == "unknown":
                    self.unknown_frames[c.msg] = self.unknown_frames.get(c.msg, 0) + 1
                elif c.state == "warn" and c.msg not in self.warns:
                    self.warns.append(c.msg)
            self.rep_frames += 1
            for key, ok, msg in m.reach:
                prev = self.reached.get(key, (False, msg))[0]
                self.reached[key] = (prev or ok, msg)
            self.last_activity = now

        if self.phase == "moving":
            if is_active:
                self.phase = "active"
            elif is_rest:
                event, msg = "partial", ex.partial_msg
                self._reset()
        elif self.phase == "active":
            if is_rest:
                event, msg = self._complete(now)
            elif not past_mid:
                self.phase = "returning"
        elif self.phase == "returning":
            if is_rest:
                event, msg = self._complete(now)
            elif is_active:
                # volvió a hacer fuerza sin completar el recorrido: esa repetición no se completó
                self.phase = "active"
                if ex.return_msg:
                    event, msg = "partial", ex.return_msg
        status = "warn" if (m.issue or any(c.state == "warn" for c in m.checks)) else "ok"
        if status == "ok" and any(c.state == "unknown" for c in m.checks):
            status = "unknown"
        if not msg:
            msg = m.issue or next((c.msg for c in m.checks if c.state == "warn"), None)
        return Update(status, msg, event, progress, checks=m.checks, view=view)

    def _complete(self, now):
        d = now - (self.rep_start if self.rep_start is not None else now)
        if now - self.last_rep_at < 0.3:
            self._reset()
            return None, None
        fast = d < self.ex.min_rep_s
        for ok, msg in self.reached.values():
            if not ok and msg not in self.issues:
                self.issues.append(msg)
        verified = not self.unverified and all(n < 0.5 * max(1, self.rep_frames) for n in self.unknown_frames.values())
        self.last_rep_at = now
        self.last_activity = now
        if not self.issues:
            self.reps += 1
            self.log.append({"d": round(d, 2), "clean": True, "verified": verified, "fast": fast})
            msg = "Más lento y controlado" if fast else "¡Perfecta!"
            self._reset()
            return "rep", msg
        self.bad += 1
        msg = self.issues[0]
        self.log.append({"d": round(d, 2), "clean": False, "verified": verified, "fast": fast})
        self._reset()
        return "bad", msg

    def _reset(self):
        self.phase = "rest"
        self.issues = []
        self.unverified = set()
        self.warns = []
        self.reached = {}
        self.bad_frames = {}
        self.unknown_frames = {}
        self.rep_frames = 0
        self.rep_start = None

    # ---- resumen para la progresión
    def summary(self) -> dict:
        """Calidad de la serie: % limpias, % verificadas y si las últimas repeticiones se hicieron más lentas."""
        if self.ex.timed:
            total = self.timed_good + self.timed_bad
            return {"good": int(self.seconds), "bad": 0,
                    "quality": self.timed_good / total if total else 1.0,
                    "verified": 1.0 if not self.unverified else 0.5, "slowdown": 1.0}
        n = len(self.log)
        if not n:
            return {"good": 0, "bad": 0, "quality": 1.0, "verified": 1.0, "slowdown": 1.0}
        clean = sum(1 for r in self.log if r["clean"]) / n
        ver = sum(1 for r in self.log if r["verified"]) / n
        durs = [r["d"] for r in self.log if r["d"] > 0]
        slow = 1.0
        if len(durs) >= 6:
            k = max(2, len(durs) // 3)
            first, last = mean(durs[:k]), mean(durs[-k:])
            slow = last / first if first > 0 else 1.0
        return {"good": self.reps, "bad": self.bad, "quality": clean, "verified": ver, "slowdown": round(slow, 2)}
