"""Siluetas sintéticas con medidas conocidas -> el análisis debe recuperarlas."""
from types import SimpleNamespace as P

import numpy as np
import cv2

from arise.body import analyze, compare, ellipse_perimeter, navy_body_fat

H, W = 1000, 600
HEIGHT_CM = 175.0
PX = 900 / HEIGHT_CM  # la figura mide 900 px de alto (de y=50 a y=950)


def figure(neck, chest, waist, hip, head=0.0):
    """Dibuja una silueta: valores en cm (ancho visible en esa vista)."""
    m = np.zeros((H, W), np.uint8)
    c = W // 2
    w = lambda cm: int(cm * PX / 2)
    cv2.ellipse(m, (c, 50 + 55), (w(head or 16), 55), 0, 0, 360, 1, -1)           # cabeza 50..160
    cv2.rectangle(m, (c - w(neck), 150), (c + w(neck), 200), 1, -1)                 # cuello 150..200
    pts = np.array([[c - w(chest), 200], [c + w(chest), 200], [c + w(waist), 380], [c - w(waist), 380]])
    cv2.fillPoly(m, [pts], 1)                                                       # pecho -> cintura
    pts = np.array([[c - w(waist), 380], [c + w(waist), 380], [c + w(hip), 480], [c - w(hip), 480]])
    cv2.fillPoly(m, [pts], 1)                                                       # cintura -> cadera
    cv2.rectangle(m, (c - w(hip), 480), (c + w(hip), 520), 1, -1)
    cv2.rectangle(m, (c - w(hip), 520), (c - 3, 950), 1, -1)                        # piernas
    cv2.rectangle(m, (c + 3, 520), (c + w(hip), 950), 1, -1)
    return m.astype(np.float32)


def landmarks():
    lm = [P(x=0.5, y=0.5, z=0, visibility=0.99) for _ in range(33)]
    lm[0] = P(x=0.5, y=110 / H, visibility=.99)
    for i, x in ((11, 0.42), (12, 0.58)):
        lm[i] = P(x=x, y=205 / H, visibility=.99)
    for i, x in ((23, 0.46), (24, 0.54)):
        lm[i] = P(x=x, y=470 / H, visibility=.99)
    return lm


def test_recovers_circumferences():
    front = figure(neck=12, chest=40, waist=28, hip=34)
    side = figure(neck=12, chest=24, waist=20, hip=24)
    lm = landmarks()
    m = analyze(front, lm, side, lm, side, lm, HEIGHT_CM, "m", 80)
    exp_waist = ellipse_perimeter(28, 20)
    exp_neck = ellipse_perimeter(12, 12)
    assert abs(m.waist_cm - exp_waist) < 3, (m.waist_cm, exp_waist)
    assert abs(m.neck_cm - exp_neck) < 3, (m.neck_cm, exp_neck)
    assert m.reliable and m.body_fat is not None
    assert abs(m.fat_kg + m.lean_kg - 80) < 0.2


def test_navy_reference_values():
    # Hombre 178 cm, cintura 85, cuello 38 -> ~16-18 %
    bf = navy_body_fat("m", 178, 85, 38)
    assert 14 < bf < 20
    assert navy_body_fat("f", 165, 75, 33, 98) > 20


def test_muscle_not_counted_as_fat():
    prev = {"waist_cm": 84.0, "reliable": True, "lean_kg": 64.0, "fat_kg": 14.0, "shoulder_waist": 1.40}
    cur = {"waist_cm": 83.8, "reliable": True, "lean_kg": 65.3, "fat_kg": 13.9, "shoulder_waist": 1.43}
    msgs = compare(prev, cur, 78.0, 79.2)
    assert "músculo" in msgs[0]
    assert "no grasa" in msgs[0]
