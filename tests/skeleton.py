"""Esqueleto 3D sintético para probar los ejercicios desde cualquier ángulo de cámara.

Las poses se arman en coordenadas del cuerpo (f = adelante, u = arriba, l = lateral, en metros), se rotan según
el ángulo de la cámara (yaw: 0 = de frente, 90 = de costado) y se generan:
  * landmarks de mundo (metros, centrados en la cadera, y hacia abajo) como los de MediaPipe
  * landmarks de imagen normalizados (0..1) con proyección ortográfica
Se agrega ruido (más en la profundidad, como pasa con MediaPipe) y la visibilidad baja del lado tapado.
"""
from __future__ import annotations

import math
import random
from types import SimpleNamespace as P

ASPECT = 16 / 9
TORSO, SH_HALF, HIP_HALF = 0.50, 0.19, 0.12
UARM, FARM, THIGH, SHANK, NECK = 0.30, 0.27, 0.45, 0.43, 0.24


def _rot(yaw):
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    return c, s


def to_landmarks(pts: dict, yaw: float, noise: float = 0.0, seed: int = 0, scale: float = 0.42, cx=0.5, cy=0.5,
                 zk: float = 1.0):
    """pts: {índice: (f, u, l)} -> (lm, world). zk < 1 simula que MediaPipe subestima la profundidad."""
    rnd = random.Random(seed)
    c, s = _rot(yaw)
    cam = {}
    for i, (f, u, l) in pts.items():
        X = l * c + f * s
        Z = -l * s + f * c
        Y = -u
        cam[i] = (X, Y, Z)
    hx = (cam[23][0] + cam[24][0]) / 2
    hy = (cam[23][1] + cam[24][1]) / 2
    hz = (cam[23][2] + cam[24][2]) / 2
    # lado tapado: de costado, el lado más lejano de la cámara se ve menos
    far = set()
    if abs(math.sin(math.radians(yaw))) > 0.85:
        left_z = cam[11][2]
        right_z = cam[12][2]
        far = {11, 13, 15, 23, 25, 27} if left_z < right_z else {12, 14, 16, 24, 26, 28}
    lm, w = [], []
    for i in range(33):
        if i not in cam:
            lm.append(P(x=0.5, y=0.5, z=0.0, visibility=0.0))
            w.append(P(x=0.0, y=0.0, z=0.0, visibility=0.0))
            continue
        X, Y, Z = cam[i]
        nz = rnd.gauss(0, noise * 3)
        n2 = lambda: rnd.gauss(0, noise)
        vis = 0.62 if i in far else 0.98
        w.append(P(x=X - hx + n2(), y=Y - hy + n2(), z=(Z - hz) * zk + nz, visibility=vis))
        lm.append(P(x=cx + (X - hx) * scale / ASPECT + n2() * 0.3, y=cy + (Y - hy) * scale + n2() * 0.3,
                    z=Z, visibility=vis))
    return lm, w


def _both(pts, i_left, i_right, f, u, half):
    pts[i_left] = (f, u, -half)
    pts[i_right] = (f, u, half)


def _arms_hanging(pts, sh_f, sh_u, fwd=0.0):
    for s, e, wr, l in ((11, 13, 15, -SH_HALF), (12, 14, 16, SH_HALF)):
        pts[s] = (sh_f, sh_u, l)
        pts[e] = (sh_f + fwd * 0.3, sh_u - UARM, l * 1.05)
        pts[wr] = (sh_f + fwd * 0.5, sh_u - UARM - FARM, l * 1.05)


def standing_squat(knee_deg: float, valgus: float = 0.0, lean_extra: float = 0.0):
    """Sentadilla con ángulo de rodilla dado. valgus: cuánto se juntan las rodillas (m)."""
    k = 180 - knee_deg
    phi = math.radians(k * 0.35)          # inclinación de la pantorrilla hacia adelante
    alpha = math.radians(k) - phi         # muslo respecto de la vertical, hacia atrás
    beta = math.radians(k * 0.4 + lean_extra)  # inclinación del tronco hacia adelante
    pts = {}
    for a, kn, h, l in ((27, 25, 23, -HIP_HALF), (28, 26, 24, HIP_HALF)):
        ank = (0.0, 0.0)
        knee = (ank[0] + SHANK * math.sin(phi), ank[1] + SHANK * math.cos(phi))
        hip = (knee[0] - THIGH * math.sin(alpha), knee[1] + THIGH * math.cos(alpha))
        kl = l - math.copysign(valgus * min(1.0, k / 95), l)
        pts[a] = (ank[0], ank[1], l * 1.1)
        pts[kn] = (knee[0], knee[1], kl)
        pts[h] = (hip[0], hip[1], l)
    hip_f, hip_u = pts[23][0], pts[23][1]
    sh_f, sh_u = hip_f + TORSO * math.sin(beta), hip_u + TORSO * math.cos(beta)
    _arms_hanging(pts, sh_f, sh_u, fwd=1.0)
    pts[0] = (sh_f + 0.08, sh_u + NECK, 0.0)
    return pts


def pushup(elbow_deg: float, sag: float = 0.0, knees_down: bool = False):
    """Flexión: el cuerpo apunta hacia +f (cabeza). sag > 0 baja la cadera (m), < 0 la sube."""
    th = math.radians(elbow_deg)
    d = math.sqrt(UARM ** 2 + FARM ** 2 - 2 * UARM * FARM * math.cos(th))
    g = math.acos(max(-1, min(1, (FARM ** 2 + d ** 2 - UARM ** 2) / (2 * FARM * d))))
    pts = {}
    for s, e, wr, l in ((11, 13, 15, -SH_HALF), (12, 14, 16, SH_HALF)):
        pts[wr] = (0.0, 0.0, l)
        pts[e] = (-FARM * math.sin(g), FARM * math.cos(g), l * 1.15)
        pts[s] = (0.0, d, l)
    if knees_down:
        reach = TORSO + THIGH
        tilt = math.asin(min(1.0, d / reach))
        hip = (-TORSO * math.cos(tilt), d - TORSO * math.sin(tilt) - sag)
        knee = (-reach * math.cos(tilt), 0.03)
        ank = (knee[0] - SHANK * 0.95, 0.12)
    else:
        L = TORSO + THIGH + SHANK
        tilt = math.asin(min(1.0, (d - 0.05) / L))
        hip = (-TORSO * math.cos(tilt), d - TORSO * math.sin(tilt) - sag)
        knee = (-(TORSO + THIGH) * math.cos(tilt), d - (TORSO + THIGH) * math.sin(tilt) - sag * 0.5)
        ank = (-L * math.cos(tilt), 0.05)
    _both(pts, 23, 24, hip[0], hip[1], HIP_HALF)
    _both(pts, 25, 26, knee[0], knee[1], HIP_HALF)
    _both(pts, 27, 28, ank[0], ank[1], HIP_HALF)
    pts[0] = (0.22, d + 0.02, 0.0)
    return pts


def plank(sag: float = 0.0, knees_down: bool = False):
    return pushup(172, sag, knees_down)


def situp(elev_deg: float):
    """Boca arriba (cabeza hacia −f), rodillas flexionadas; el tronco sube elev_deg grados."""
    e = math.radians(elev_deg)
    pts = {}
    _both(pts, 23, 24, 0.0, 0.1, HIP_HALF)
    _both(pts, 25, 26, THIGH * math.cos(math.radians(50)), 0.1 + THIGH * math.sin(math.radians(50)), HIP_HALF)
    kf, ku = pts[25][0], pts[25][1]
    _both(pts, 27, 28, kf + SHANK * 0.55, 0.05, HIP_HALF)
    sf, su = -TORSO * math.cos(e), 0.1 + TORSO * math.sin(e)
    for s, el, wr, l in ((11, 13, 15, -SH_HALF), (12, 14, 16, SH_HALF)):
        pts[s] = (sf, su, l)
        pts[el] = (sf + 0.12, su + 0.12, l * 0.9)
        pts[wr] = (sf + 0.05, su + 0.18, l * 0.3)
    pts[0] = (sf - NECK * math.cos(e), su + NECK * math.sin(e) + 0.05, 0.0)
    return pts


def jack(s: float):
    """s = 0 brazos abajo y piernas juntas; 1 brazos arriba y piernas abiertas."""
    pts = {}
    spread = HIP_HALF + s * 0.25
    _both(pts, 27, 28, 0.0, 0.0, spread)
    _both(pts, 25, 26, 0.0, SHANK, (HIP_HALF + spread) / 2 + 0.02)
    _both(pts, 23, 24, 0.0, SHANK + THIGH, HIP_HALF)
    su = SHANK + THIGH + TORSO
    a = math.radians(10 + 160 * s)  # abducción del brazo
    for sh, el, wr, sign in ((11, 13, 15, -1), (12, 14, 16, 1)):
        pts[sh] = (0.0, su, sign * SH_HALF)
        pts[el] = (0.0, su - UARM * math.cos(a), sign * (SH_HALF + UARM * math.sin(a)))
        pts[wr] = (0.0, su - (UARM + FARM) * math.cos(a), sign * (SH_HALF + (UARM + FARM) * math.sin(a)))
    pts[0] = (0.08, su + NECK, 0.0)
    return pts


def lunge(depth: float):
    """depth 0..1: 0 parado, 1 zancada profunda (rodilla de atrás casi al piso)."""
    pts = {}
    hip_u = SHANK + THIGH - 0.005 - depth * 0.42
    stride = 0.02 + depth * 0.48
    # pierna de adelante (izquierda)
    for (h, k, a, l, sign) in ((23, 25, 27, -HIP_HALF, 1), (24, 26, 28, HIP_HALF, -1)):
        ank = (sign * stride, 0.0 if sign > 0 else 0.05 * depth)
        # resolver rodilla por ley de cosenos entre cadera (0, hip_u) y tobillo
        dx, du = ank[0], ank[1] - hip_u
        dd = math.hypot(dx, du)
        dd = min(dd, THIGH + SHANK - 1e-3)
        cosA = (THIGH ** 2 + dd ** 2 - SHANK ** 2) / (2 * THIGH * dd)
        A = math.acos(max(-1, min(1, cosA)))
        base = math.atan2(du, dx)
        ang = base + (A if sign > 0 else -A)
        knee = (THIGH * math.cos(ang), hip_u + THIGH * math.sin(ang))
        pts[h] = (0.0, hip_u, l)
        pts[k] = (knee[0], knee[1], l)
        pts[a] = (ank[0], ank[1], l)
    su = hip_u + TORSO
    _arms_hanging(pts, 0.0, su)
    pts[0] = (0.08, su + NECK, 0.0)
    return pts


def pullup(elbow_deg: float, chin_ok: bool = True):
    """Colgado de una barra (manos fijas arriba, en el plano lateral)."""
    th = math.radians(elbow_deg)
    d = math.sqrt(UARM ** 2 + FARM ** 2 - 2 * UARM * FARM * math.cos(th))
    pts = {}
    bar_u = 2.2
    grip = SH_HALF + 0.15
    sh_u = bar_u - math.sqrt(max(0.0, d ** 2 - 0.15 ** 2))
    for s, e, wr, sign in ((11, 13, 15, -1), (12, 14, 16, 1)):
        pts[wr] = (0.0, bar_u, sign * grip)
        pts[s] = (0.0, sh_u, sign * SH_HALF)
        # codo hacia afuera: resolver con ley de cosenos en el plano lateral
        dx, du = sign * grip - sign * SH_HALF, bar_u - sh_u
        dd = math.hypot(dx, du)
        cosA = (UARM ** 2 + dd ** 2 - FARM ** 2) / (2 * UARM * dd)
        A = math.acos(max(-1, min(1, cosA)))
        base = math.atan2(du, dx)
        ang = base - sign * A
        pts[e] = (0.0, sh_u + UARM * math.sin(ang), sign * SH_HALF + UARM * math.cos(ang))
    hip_u = sh_u - TORSO
    _both(pts, 23, 24, 0.0, hip_u, HIP_HALF)
    _both(pts, 25, 26, 0.02, hip_u - THIGH, HIP_HALF)
    _both(pts, 27, 28, 0.0, hip_u - THIGH - SHANK, HIP_HALF)
    pts[0] = (0.08, sh_u + NECK * (1.0 if chin_ok else 0.2) - (0 if chin_ok else 0.25), 0.0)
    return pts


def curl(elbow_deg: float, elbow_forward: float = 0.0, torso_lean: float = 0.0):
    pts = {}
    _both(pts, 27, 28, 0.0, 0.0, HIP_HALF)
    _both(pts, 25, 26, 0.0, SHANK, HIP_HALF)
    _both(pts, 23, 24, 0.0, SHANK + THIGH, HIP_HALF)
    b = math.radians(torso_lean)
    hu = SHANK + THIGH
    sf, su = -TORSO * math.sin(b), hu + TORSO * math.cos(b)
    ef = math.radians(elbow_forward)
    for s, e, wr, l in ((11, 13, 15, -SH_HALF), (12, 14, 16, SH_HALF)):
        pts[s] = (sf, su, l)
        el = (sf + UARM * math.sin(ef), su - UARM * math.cos(ef))
        pts[e] = (el[0], el[1], l)
        # el antebrazo gira hacia adelante: ángulo de codo = elbow_deg
        fa = math.radians(180 - elbow_deg) + ef
        pts[wr] = (el[0] + FARM * math.sin(fa), el[1] - FARM * math.cos(fa), l)
    pts[0] = (sf + 0.08, su + NECK, 0.0)
    return pts


def press(elbow_deg: float):
    pts = curl(180)
    su = pts[11][1]
    for s, e, wr, sign in ((11, 13, 15, -1), (12, 14, 16, 1)):
        # brazo en el plano lateral: el codo baja a los costados, las manos siempre arriba del codo
        k = (elbow_deg - 70) / 110  # 0 abajo, 1 arriba
        up = math.radians(-10 + 100 * max(0, min(1, k)))  # elevación del brazo superior
        e_l = sign * (SH_HALF + UARM * math.cos(up))
        e_u = su + UARM * math.sin(up)
        # muñeca: ángulo de codo dado, apuntando arriba/adentro
        inner = math.radians(180 - elbow_deg)
        dirx, diru = math.cos(up), math.sin(up)
        rx = dirx * math.cos(inner) + sign * 0 - diru * math.sin(inner) * 0
        ang = up + math.radians(180 - elbow_deg)
        pts[e] = (0.0, e_u, e_l)
        pts[wr] = (0.0, e_u + FARM * math.sin(ang), e_l + sign * FARM * math.cos(ang))
    return pts


def lateral(abd_deg: float):
    pts = curl(180)
    su = pts[11][1]
    a = math.radians(abd_deg)
    for s, e, wr, sign in ((11, 13, 15, -1), (12, 14, 16, 1)):
        pts[e] = (0.0, su - UARM * math.cos(a), sign * (SH_HALF + UARM * math.sin(a)))
        pts[wr] = (0.0, su - (UARM + FARM * 0.97) * math.cos(a), sign * (SH_HALF + (UARM + FARM) * math.sin(a)))
    return pts


def row(elbow_deg: float, torso_deg: float = 45):
    """Inclinado (tronco a torso_deg sobre la horizontal), brazos tirando hacia atrás."""
    pts = {}
    _both(pts, 27, 28, 0.0, 0.0, HIP_HALF)
    _both(pts, 25, 26, 0.08, SHANK - 0.02, HIP_HALF)
    hu = SHANK + THIGH - 0.06
    _both(pts, 23, 24, -0.05, hu, HIP_HALF)
    t = math.radians(torso_deg)
    sf, su = -0.05 + TORSO * math.cos(t), hu + TORSO * math.sin(t)
    k = (180 - elbow_deg) / 100
    up = math.radians(-90 + 0)  # brazo colgando
    for s, e, wr, l in ((11, 13, 15, -SH_HALF), (12, 14, 16, SH_HALF)):
        pts[s] = (sf, su, l)
        back = math.radians(80 * max(0, min(1, k)))  # el codo va hacia atrás y arriba
        ef, eu = sf - UARM * math.sin(back), su - UARM * math.cos(back)
        pts[e] = (ef, eu, l)
        ang = back - math.radians(180 - elbow_deg)
        pts[wr] = (ef - FARM * math.sin(ang), eu - FARM * math.cos(ang), l)
    pts[0] = (sf + NECK * math.cos(t), su + NECK * math.sin(t), 0.0)
    return pts


def rdl(hinge_deg: float, knee_deg: float = 165):
    """Bisagra: hinge_deg = ángulo hombro-cadera-rodilla."""
    pts = {}
    k = math.radians(180 - knee_deg)
    _both(pts, 27, 28, 0.0, 0.0, HIP_HALF)
    _both(pts, 25, 26, SHANK * math.sin(k * 0.5), SHANK * math.cos(k * 0.5), HIP_HALF)
    kf, ku = pts[25][0], pts[25][1]
    hf, hu = kf - THIGH * math.sin(k * 0.5), ku + THIGH * math.cos(k * 0.5)
    _both(pts, 23, 24, hf, hu, HIP_HALF)
    # el muslo apunta hacia abajo; el tronco forma hinge_deg con él
    thigh_dir = math.atan2(ku - hu, kf - hf)
    td = thigh_dir + math.radians(hinge_deg)
    sf, su = hf + TORSO * math.cos(td), hu + TORSO * math.sin(td)
    if su < hu:
        td = thigh_dir - math.radians(hinge_deg)
        sf, su = hf + TORSO * math.cos(td), hu + TORSO * math.sin(td)
    _arms_hanging(pts, sf, su)
    pts[0] = (sf + 0.15, su + 0.1, 0.0)
    return pts


def bridge(lift: float):
    """lift 0..1: cadera en el piso → arriba."""
    pts = {}
    _both(pts, 27, 28, 0.55, 0.05, HIP_HALF)
    hip_u = 0.1 + lift * 0.22
    _both(pts, 23, 24, 0.0, hip_u, HIP_HALF)
    _both(pts, 25, 26, 0.35, 0.5, HIP_HALF)
    for s, e, wr, l in ((11, 13, 15, -SH_HALF), (12, 14, 16, SH_HALF)):
        pts[s] = (-TORSO * math.cos(math.asin(min(1, (hip_u - 0.08) / TORSO))), 0.08, l)
        pts[e] = (pts[s][0] + 0.25, 0.03, l * 1.2)
        pts[wr] = (pts[s][0] + 0.5, 0.03, l * 1.2)
    pts[0] = (pts[11][0] - NECK, 0.1, 0.0)
    return pts


def climber(drive: float, leg: int = 0):
    """drive 0..1: una rodilla (leg 0 = izquierda, 1 = derecha) va hacia el pecho desde la plancha."""
    pts = pushup(172)
    h, k, a = ((23, 25, 27), (24, 26, 28))[leg]
    hf, hu, hl = pts[h]
    kf, ku, _ = pts[k]
    ang = math.atan2(ku - hu, kf - hf) + math.radians(110 * drive)
    kn = (hf + THIGH * math.cos(ang), hu + THIGH * math.sin(ang))
    sang = ang - math.radians(110 * drive) - math.radians(10 * drive)
    an = (kn[0] + SHANK * math.cos(sang), max(0.03, kn[1] + SHANK * math.sin(sang)))
    pts[k] = (kn[0], kn[1], hl)
    pts[a] = (an[0], an[1], hl)
    return pts
