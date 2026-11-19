"""Análisis corporal a partir de la silueta (máscara de segmentación) de 3 fotos: frente, perfil izq. y der.

Idea: con la foto de frente se mide el ANCHO de cuello, cintura y cadera; con las de perfil, la PROFUNDIDAD.
Ancho + profundidad -> contorno (elipse, fórmula de Ramanujan), escalado a cm con la altura de la persona.
Con los contornos se estima el % de grasa con el método de la Marina de EE.UU., que usa medidas y altura
(no el peso), así que ganar músculo no se cuenta como grasa como pasa con el IMC.
Es una ESTIMACIÓN (error típico ±3-4%): lo valioso es la tendencia semana a semana con fotos parecidas.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Optional

from .i18n import t

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None


# ------------------------------------------------------------------ silueta
def largest_component(mask: np.ndarray) -> np.ndarray:
    m = (mask > 0.5).astype(np.uint8)
    if cv2 is None:
        return m
    n, labels, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    if n <= 1:
        return m
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return (labels == big).astype(np.uint8)


def vertical_extent(m: np.ndarray) -> tuple[int, int]:
    rows = np.where(m.any(axis=1))[0]
    if len(rows) == 0:
        return 0, 0
    return int(rows[0]), int(rows[-1])


def row_width(m: np.ndarray, y: int, cx: Optional[float] = None) -> int:
    """Ancho del tramo de silueta en la fila `y` que contiene `cx` (así no se suman los brazos separados)."""
    y = int(max(0, min(m.shape[0] - 1, y)))
    row = m[y]
    xs = np.where(row > 0)[0]
    if len(xs) == 0:
        return 0
    # tramos contiguos
    splits = np.where(np.diff(xs) > 1)[0]
    starts = np.concatenate(([xs[0]], xs[splits + 1]))
    ends = np.concatenate((xs[splits], [xs[-1]]))
    if cx is not None:
        for s, e in zip(starts, ends):
            if s <= cx <= e:
                return int(e - s + 1)
        # el centro cayó en un hueco: el tramo más cercano
        d = [min(abs(s - cx), abs(e - cx)) for s, e in zip(starts, ends)]
        i = int(np.argmin(d))
        return int(ends[i] - starts[i] + 1)
    return int(max(e - s + 1 for s, e in zip(starts, ends)))


def _scan(m, y0, y1, cx, mode="min"):
    y0, y1 = int(min(y0, y1)), int(max(y0, y1))
    best_y, best_w = y0, None
    for y in range(y0, y1 + 1):
        w = row_width(m, y, cx)
        if w <= 0:
            continue
        if best_w is None or (w < best_w if mode == "min" else w > best_w):
            best_w, best_y = w, y
    return best_y, best_w or 0


@dataclass
class FrontMeasure:
    top: int
    bottom: int
    neck_px: int
    waist_px: int
    hip_px: int
    shoulder_px: int
    neck_frac: float
    waist_frac: float
    hip_frac: float
    warnings: list = field(default_factory=list)

    @property
    def height_px(self) -> int:
        return max(1, self.bottom - self.top)


def measure_front(mask: np.ndarray, lm) -> FrontMeasure:
    """mask: HxW (0..1); lm: landmarks normalizados de MediaPipe (x, y en 0..1)."""
    m = largest_component(mask)
    h, w = m.shape
    top, bottom = vertical_extent(m)
    Y = lambda i: lm[i].y * h
    X = lambda i: lm[i].x * w
    sh_y = (Y(11) + Y(12)) / 2
    hip_y = (Y(23) + Y(24)) / 2
    nose_y = Y(0)
    cx = (X(23) + X(24) + X(11) + X(12)) / 4
    torso = max(1.0, hip_y - sh_y)
    neck_y, neck = _scan(m, nose_y + (sh_y - nose_y) * 0.55, sh_y - (sh_y - nose_y) * 0.10, cx, "min")
    waist_y, waist = _scan(m, sh_y + torso * 0.45, hip_y - torso * 0.02, cx, "min")
    hip_yy, hip = _scan(m, hip_y - torso * 0.08, hip_y + torso * 0.35, cx, "max")
    shoulder = row_width(m, int(sh_y + torso * 0.06), cx)
    warns = []
    if shoulder and waist / shoulder > 0.92:
        warns.append(t("Separá un poco los brazos del cuerpo en la foto de frente"))
    hh = max(1, bottom - top)
    return FrontMeasure(top, bottom, neck, waist, hip, shoulder,
                        (neck_y - top) / hh, (waist_y - top) / hh, (hip_yy - top) / hh, warns)


@dataclass
class SideMeasure:
    top: int
    bottom: int
    neck_px: int
    waist_px: int
    hip_px: int

    @property
    def height_px(self) -> int:
        return max(1, self.bottom - self.top)


def measure_side(mask: np.ndarray, lm, front: FrontMeasure) -> SideMeasure:
    """Profundidad del cuerpo a las mismas alturas relativas que se midieron de frente."""
    m = largest_component(mask)
    h, w = m.shape
    top, bottom = vertical_extent(m)
    hh = max(1, bottom - top)
    cx = None
    if lm is not None:
        cx = (lm[23].x + lm[24].x) / 2 * w
    def at(frac, mode, span=0.025):
        y = top + frac * hh
        if mode == "median":
            ws = [row_width(m, int(yy), cx) for yy in range(int(y - span * hh), int(y + span * hh) + 1)]
            ws = [v for v in ws if v > 0]
            return int(np.median(ws)) if ws else 0
        return _scan(m, y - span * hh, y + span * hh, cx, mode)[1]
    return SideMeasure(top, bottom, at(front.neck_frac, "median", 0.01), at(front.waist_frac, "median", 0.015),
                       at(front.hip_frac, "max", 0.03))


# ------------------------------------------------------------------ fórmulas
def ellipse_perimeter(width: float, depth: float) -> float:
    a, b = width / 2, depth / 2
    return math.pi * (3 * (a + b) - math.sqrt((3 * a + b) * (a + 3 * b)))


def navy_body_fat(sex: str, height_cm: float, waist_cm: float, neck_cm: float, hip_cm: float = 0.0) -> Optional[float]:
    try:
        if sex == "f":
            v = 495 / (1.29579 - 0.35004 * math.log10(waist_cm + hip_cm - neck_cm) + 0.22100 * math.log10(height_cm)) - 450
        else:
            v = 495 / (1.0324 - 0.19077 * math.log10(waist_cm - neck_cm) + 0.15456 * math.log10(height_cm)) - 450
    except ValueError:
        return None
    return max(3.0, min(60.0, v))


@dataclass
class BodyMetrics:
    neck_cm: float
    waist_cm: float
    hip_cm: float
    shoulder_cm: float
    body_fat: Optional[float]
    fat_kg: Optional[float]
    lean_kg: Optional[float]
    shoulder_waist: float
    waist_height: float
    reliable: bool
    warnings: list

    def to_dict(self):
        return asdict(self)


def analyze(front_mask, front_lm, left_mask, left_lm, right_mask, right_lm,
            height_cm: float, sex: str, weight_kg: Optional[float]) -> BodyMetrics:
    f = measure_front(front_mask, front_lm)
    sides = [measure_side(m, l, f) for m, l in ((left_mask, left_lm), (right_mask, right_lm)) if m is not None]
    warns = list(f.warnings)
    cm_f = height_cm / f.height_px

    def depth_cm(attr):
        vals = [getattr(s, attr) * height_cm / s.height_px for s in sides if getattr(s, attr) > 0]
        return sum(vals) / len(vals) if vals else 0.0

    neck = ellipse_perimeter(f.neck_px * cm_f, depth_cm("neck_px"))
    waist = ellipse_perimeter(f.waist_px * cm_f, depth_cm("waist_px"))
    hip = ellipse_perimeter(f.hip_px * cm_f, depth_cm("hip_px"))
    reliable = 22 <= neck <= 65 and 50 <= waist <= 180 and 60 <= hip <= 190 and waist > neck
    if not reliable:
        warns.append(t("Las medidas salieron fuera de rango: repetí las fotos con el cuerpo entero, buena luz y fondo "
                       "despejado"))
    bf = navy_body_fat(sex, height_cm, waist, neck, hip) if reliable else None
    fat = lean = None
    if bf is not None and weight_kg:
        fat = weight_kg * bf / 100
        lean = weight_kg - fat
    shoulder_cm = f.shoulder_px * cm_f
    return BodyMetrics(round(neck, 1), round(waist, 1), round(hip, 1), round(shoulder_cm, 1),
                       None if bf is None else round(bf, 1), None if fat is None else round(fat, 1),
                       None if lean is None else round(lean, 1),
                       round(f.shoulder_px / max(1, f.waist_px), 2), round(waist / height_cm, 3), reliable, warns)


# ------------------------------------------------------------------ comparación entre semanas
def compare(prev: dict, cur: dict, prev_weight: Optional[float], cur_weight: Optional[float]) -> list[str]:
    """Conclusiones en lenguaje claro. Prioriza cintura vs peso para no confundir músculo con grasa."""
    out = []
    dw = (cur_weight - prev_weight) if (cur_weight and prev_weight) else None
    dwaist = cur["waist_cm"] - prev["waist_cm"] if prev.get("reliable") and cur.get("reliable") else None
    if dw is not None and dwaist is not None:
        if dw > 0.3 and dwaist <= 0.3:
            out.append(t("Subiste {kg} kg pero la cintura no creció ({cm} cm): lo más probable es que sea "
                         "músculo (o agua/glucógeno), no grasa.", kg=f"{dw:.1f}", cm=f"{dwaist:+.1f}"))
        elif dw > 0.3 and dwaist > 0.5:
            out.append(t("Subiste {kg} kg y la cintura creció {cm} cm: parte de ese aumento probablemente sea grasa.",
                         kg=f"{dw:.1f}", cm=f"{dwaist:.1f}"))
        elif dw < -0.3 and dwaist < -0.3:
            out.append(t("Bajaste {kg} kg y {cm} cm de cintura: estás perdiendo grasa.", kg=f"{abs(dw):.1f}",
                         cm=f"{abs(dwaist):.1f}"))
        elif dw < -0.3 and dwaist >= -0.3:
            out.append(t("Bajaste {kg} kg pero la cintura no bajó: puede ser agua o músculo. "
                         "Cuidá la proteína y no recortes demasiado las calorías.", kg=f"{abs(dw):.1f}"))
        elif abs(dw) <= 0.3 and dwaist < -0.5:
            out.append(t("Peso estable y {cm} cm menos de cintura: recomposición (menos grasa, más músculo).",
                         cm=f"{abs(dwaist):.1f}"))
        elif abs(dw) <= 0.3 and abs(dwaist) <= 0.5:
            out.append(t("Peso y cintura estables esta semana."))
    elif dw is not None:
        out.append(t("Peso: {kg} kg respecto del último control.", kg=f"{dw:+.1f}"))
    if prev.get("lean_kg") and cur.get("lean_kg"):
        dl = cur["lean_kg"] - prev["lean_kg"]
        df = cur["fat_kg"] - prev["fat_kg"]
        out.append(t("Estimado: masa magra {lean} kg · masa grasa {fat} kg.", lean=f"{dl:+.1f}", fat=f"{df:+.1f}"))
    if prev.get("shoulder_waist") and cur.get("shoulder_waist"):
        d = cur["shoulder_waist"] - prev["shoulder_waist"]
        if abs(d) >= 0.02:
            out.append(t("Relación hombros/cintura {r} ({d}): ", r=f"{cur['shoulder_waist']:.2f}", d=f"{d:+.2f}")
                       + (t("más forma en V.") if d > 0 else t("menos forma en V.")))
    return out


# ------------------------------------------------------------------ alineación de fotos entre semanas
ALIGN_POINTS = (0, 11, 12, 23, 24, 25, 26, 27, 28)


def lm_to_list(lm) -> list:
    """Landmarks de MediaPipe -> lista serializable [[x, y, visibilidad], ...]."""
    return [[round(p.x, 5), round(p.y, 5), round(p.visibility or 0, 3)] for p in lm]


def _bbox_points(mask: np.ndarray):
    m = largest_component(mask)
    top, bottom = vertical_extent(m)
    if bottom <= top:
        return None
    cols = np.where(m[top:bottom + 1].any(axis=0))[0]
    cx = float(cols.mean()) if len(cols) else m.shape[1] / 2
    return np.float32([[cx, top], [cx, bottom]])


def alignment_matrix(prev_size, cur_size, prev_lm=None, cur_lm=None, prev_mask=None, cur_mask=None):
    """Matriz 2x3 (escala uniforme + rotación + traslación) que lleva la foto anterior sobre la actual.

    Usa los puntos del cuerpo (nariz, hombros, caderas, rodillas, tobillos) y, si no hay, el contorno de la silueta.
    """
    (pw, ph), (cw, chh) = prev_size, cur_size
    if cv2 is not None and prev_lm and cur_lm:
        src, dst = [], []
        for i in ALIGN_POINTS:
            a, b = prev_lm[i], cur_lm[i]
            if a[2] > 0.5 and b[2] > 0.5:
                src.append([a[0] * pw, a[1] * ph])
                dst.append([b[0] * cw, b[1] * chh])
        if len(src) >= 4:
            M, _ = cv2.estimateAffinePartial2D(np.float32(src), np.float32(dst), method=cv2.RANSAC,
                                               ransacReprojThreshold=max(cw, chh) * 0.03)
            if M is not None:
                return M
    if prev_mask is not None and cur_mask is not None:
        a, b = _bbox_points(prev_mask), _bbox_points(cur_mask)
        if a is not None and b is not None:
            s = (b[1, 1] - b[0, 1]) / max(1.0, a[1, 1] - a[0, 1])
            tx = b[0, 0] - a[0, 0] * s
            ty = b[0, 1] - a[0, 1] * s
            return np.float32([[s, 0, tx], [0, s, ty]])
    return np.float32([[cw / pw, 0, 0], [0, chh / ph, 0]])


def warp(img: np.ndarray, M: np.ndarray, size) -> np.ndarray:
    w, h = size
    interp = cv2.INTER_LINEAR if img.ndim == 3 else cv2.INTER_NEAREST
    return cv2.warpAffine(img, M, (w, h), flags=interp, borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def body_crop(*masks, pad: float = 0.08):
    """Rectángulo (x, y, w, h) que encierra a la persona en todas las máscaras, con margen."""
    boxes = []
    for m in masks:
        if m is None:
            continue
        c = largest_component(m)
        ys, xs = np.where(c > 0)
        if len(ys):
            boxes.append((xs.min(), ys.min(), xs.max(), ys.max()))
    if not boxes:
        return None
    h, w = masks[0].shape[:2]
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    py, px = (y1 - y0) * pad, (y1 - y0) * pad
    x0, y0 = max(0, int(x0 - px)), max(0, int(y0 - py))
    x1, y1 = min(w - 1, int(x1 + px)), min(h - 1, int(y1 + py))
    return x0, y0, x1 - x0 + 1, y1 - y0 + 1
