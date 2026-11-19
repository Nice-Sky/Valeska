"""Detección de la barra de dominadas y de las mancuernas (visión clásica con OpenCV, sin modelos extra).

Usa la pose para saber dónde buscar:
  * Barra: con las manos arriba de la cabeza, busca una recta casi horizontal y larga que pase por las dos manos.
  * Mancuerna: alrededor de cada mano busca un objeto compacto y alargado (bordes fuertes) que cruce el puño.
Los resultados se suavizan entre cuadros y solo se muestran cuando son estables, para no "inventar" objetos.
Coordenadas de salida: normalizadas 0..1 respecto de la imagen.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

try:
    import cv2
    import numpy as np
except Exception:  # pragma: no cover
    cv2 = None
    np = None


@dataclass
class Found:
    kind: str                      # "bar" | "dumbbell"
    pts: list                      # bar: [(x1,y1),(x2,y2)]; dumbbell: 4 esquinas del rectángulo rotado
    conf: float = 0.0


def _vis(p) -> float:
    v = getattr(p, "visibility", None)
    return 1.0 if v is None else float(v)


def detect_bar(gray, lm) -> Optional[Found]:
    """Recta horizontal que pasa cerca de las dos muñecas (colgado de la barra)."""
    if cv2 is None or lm is None or min(_vis(lm[15]), _vis(lm[16])) < 0.4:
        return None
    h, w = gray.shape[:2]
    if not (lm[15].y < lm[0].y and lm[16].y < lm[0].y):
        return None
    xs = sorted((lm[15].x * w, lm[16].x * w))
    yc = (lm[15].y + lm[16].y) / 2 * h
    span = max(20.0, xs[1] - xs[0])
    y0, y1 = int(max(0, yc - 0.09 * h)), int(min(h, yc + 0.06 * h))
    x0, x1 = int(max(0, xs[0] - 0.6 * span)), int(min(w, xs[1] + 0.6 * span))
    if y1 - y0 < 6 or x1 - x0 < 20:
        return None
    roi = gray[y0:y1, x0:x1]
    edges = cv2.Canny(cv2.GaussianBlur(roi, (5, 5), 0), 40, 120)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=int(span * 0.5), minLineLength=int(span * 0.9),
                            maxLineGap=int(max(8, span * 0.12)))
    if lines is None:
        return None
    best, best_score = None, 0.0
    for x_a, y_a, x_b, y_b in lines[:, 0]:
        ang = abs(math.degrees(math.atan2(y_b - y_a, x_b - x_a)))
        ang = min(ang, 180 - ang)
        if ang > 9:
            continue
        ln = math.hypot(x_b - x_a, y_b - y_a)
        ymid = (y_a + y_b) / 2 + y0
        dist = abs(ymid - yc) / (0.08 * h)
        score = ln / span - dist
        if score > best_score:
            best_score = score
            best = (x_a + x0, y_a + y0, x_b + x0, y_b + y0)
    if best is None or best_score < 0.7:
        return None
    xa, ya, xb, yb = best
    # une los tramos colineales (Hough suele partir la barra en pedazos)
    yref = (ya + yb) / 2
    pts = [(xa, ya), (xb, yb)]
    for x_a, y_a, x_b, y_b in lines[:, 0]:
        if abs((y_a + y_b) / 2 + y0 - yref) < 6 and abs(y_b - y_a) < 0.15 * max(1, abs(x_b - x_a)):
            pts += [(x_a + x0, y_a + y0), (x_b + x0, y_b + y0)]
    pts.sort()
    (xa, ya), (xb, yb) = pts[0], pts[-1]
    # se extiende un poco hacia los costados (la barra suele ser más ancha que el agarre)
    dx, dy = xb - xa, yb - ya
    ext = 0.25
    pa = ((xa - dx * ext) / w, (ya - dy * ext) / h)
    pb = ((xb + dx * ext) / w, (yb + dy * ext) / h)
    return Found("bar", [pa, pb], min(1.0, best_score / 1.6))


def detect_dumbbell(gray, lm, side: int) -> Optional[Found]:
    """Objeto alargado que cruza el puño (side 0 = izquierda: codo 13 / muñeca 15; 1 = derecha: 14 / 16)."""
    if cv2 is None or lm is None:
        return None
    e, wr = (13, 15) if side == 0 else (14, 16)
    if min(_vis(lm[e]), _vis(lm[wr])) < 0.45:
        return None
    h, w = gray.shape[:2]
    ex, ey, wx, wy = lm[e].x * w, lm[e].y * h, lm[wr].x * w, lm[wr].y * h
    fl = math.hypot(wx - ex, wy - ey)
    if fl < 12:
        return None
    ux, uy = (wx - ex) / fl, (wy - ey) / fl
    cx, cy = wx + ux * fl * 0.28, wy + uy * fl * 0.28     # centro del puño
    r = int(fl * 0.75)
    x0, y0, x1, y1 = int(max(0, cx - r)), int(max(0, cy - r)), int(min(w, cx + r)), int(min(h, cy + r))
    if x1 - x0 < 16 or y1 - y0 < 16:
        return None
    roi = gray[y0:y1, x0:x1]
    blur = cv2.GaussianBlur(roi, (3, 3), 0)
    edges = cv2.Canny(blur, 50, 140)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2)
    cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best, best_score = None, 0.0
    hx, hy = cx - x0, cy - y0
    for c in cnts:
        area = cv2.contourArea(c)
        if area < (fl * 0.12) ** 2:
            continue
        (rx, ry), (rw, rh), ang = cv2.minAreaRect(c)
        long_, short = max(rw, rh), max(1.0, min(rw, rh))
        if not (0.45 * fl <= long_ <= 1.7 * fl) or not (1.6 <= long_ / short <= 7):
            continue
        d = math.hypot(rx - hx, ry - hy) / fl
        if d > 0.45:
            continue
        # la mancuerna cruza el antebrazo (más o menos perpendicular) o queda alineada con él (martillo)
        axis = math.radians(ang if rw >= rh else ang + 90)
        cross = abs(math.cos(axis) * ux + math.sin(axis) * uy)
        score = (1 - d) * (0.6 + 0.4 * (1 - cross)) * min(1.0, area / (short * long_ + 1) + 0.3)
        if score > best_score:
            best_score = score
            box = cv2.boxPoints(((rx + x0, ry + y0), (rw, rh), ang))
            best = [(float(px) / w, float(py) / h) for px, py in box]
    if best is None or best_score < 0.35:
        return None
    return Found("dumbbell", best, min(1.0, best_score))


@dataclass
class Tracker:
    """Suaviza las detecciones: muestra un objeto recién cuando se vio varias veces seguidas."""
    kind: str
    hits: int = 0
    miss: int = 0
    pts: Optional[list] = None
    shown: bool = False
    history: list = field(default_factory=list)

    def update(self, f: Optional[Found]):
        if f is None:
            self.miss += 1
            self.hits = max(0, self.hits - 1)
            if self.miss > 8:
                self.shown = False
                self.pts = None
            return
        self.miss = 0
        self.hits += 1
        if self.pts is None or len(self.pts) != len(f.pts):
            self.pts = list(f.pts)
        else:
            self.pts = [(a[0] * 0.6 + b[0] * 0.4, a[1] * 0.6 + b[1] * 0.4) for a, b in zip(self.pts, f.pts)]
        if self.hits >= 4:
            self.shown = True


class EquipmentDetector:
    def __init__(self, kinds: set[str]):
        self.kinds = set(kinds)
        self.bar = Tracker("bar")
        self.left = Tracker("dumbbell")
        self.right = Tracker("dumbbell")

    def process(self, rgb, lm) -> list[Found]:
        if cv2 is None or lm is None or not self.kinds:
            for tr in (self.bar, self.left, self.right):
                tr.update(None)
            return self.visible()
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        if "bar" in self.kinds:
            self.bar.update(detect_bar(gray, lm))
        if "dumbbell" in self.kinds:
            self.left.update(detect_dumbbell(gray, lm, 0))
            self.right.update(detect_dumbbell(gray, lm, 1))
        return self.visible()

    def visible(self) -> list[Found]:
        out = []
        for tr in (self.bar, self.left, self.right):
            if tr.shown and tr.pts:
                out.append(Found(tr.kind, tr.pts, 1.0))
        return out
