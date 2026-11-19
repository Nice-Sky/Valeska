"""Detección de barra y mancuernas sobre imágenes sintéticas."""
from types import SimpleNamespace as P

import cv2
import numpy as np

from arise.equipment import EquipmentDetector, detect_bar, detect_dumbbell

W, H = 960, 540


def lm_base():
    return [P(x=0.5, y=0.5, z=0, visibility=0.9) for _ in range(33)]


def scene_bar(with_bar=True):
    img = np.full((H, W, 3), 60, np.uint8)
    cv2.randn(img, (60, 60, 60), (8, 8, 8))
    if with_bar:
        cv2.line(img, (150, 120), (810, 124), (200, 200, 205), 9)
    lm = lm_base()
    lm[0] = P(x=0.5, y=0.38, z=0, visibility=0.95)
    lm[15] = P(x=380 / W, y=122 / H, z=0, visibility=0.95)
    lm[16] = P(x=580 / W, y=122 / H, z=0, visibility=0.95)
    return img, lm


def scene_dumbbell(with_db=True):
    img = np.full((H, W, 3), 70, np.uint8)
    cv2.randn(img, (70, 70, 70), (6, 6, 6))
    lm = lm_base()
    lm[13] = P(x=480 / W, y=380 / H, z=0, visibility=0.95)   # codo
    lm[15] = P(x=480 / W, y=260 / H, z=0, visibility=0.95)   # muñeca (antebrazo vertical, mano arriba)
    lm[14], lm[16] = P(x=0.8, y=0.7, visibility=0.1), P(x=0.8, y=0.6, visibility=0.1)
    cv2.line(img, (480, 380), (480, 262), (150, 120, 100), 26)   # antebrazo
    if with_db:
        cy = 260 - 34
        cv2.rectangle(img, (430, cy - 9), (530, cy + 9), (25, 25, 25), -1)      # mango
        cv2.rectangle(img, (410, cy - 26), (440, cy + 26), (15, 15, 15), -1)    # discos
        cv2.rectangle(img, (520, cy - 26), (550, cy + 26), (15, 15, 15), -1)
    return img, lm


def test_bar_found_only_when_present():
    img, lm = scene_bar(True)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    f = detect_bar(gray, lm)
    assert f is not None
    (x1, y1), (x2, y2) = f.pts
    assert abs(y1 * H - 122) < 15 and abs(y2 * H - 122) < 15 and (x2 - x1) * W > 500
    img, lm = scene_bar(False)
    assert detect_bar(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), lm) is None


def test_bar_needs_hands_overhead():
    img, lm = scene_bar(True)
    lm[0] = P(x=0.5, y=0.1, z=0, visibility=0.95)
    assert detect_bar(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), lm) is None


def test_dumbbell_found_only_when_present():
    img, lm = scene_dumbbell(True)
    f = detect_dumbbell(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), lm, 0)
    assert f is not None
    xs = [p[0] * W for p in f.pts]
    assert min(xs) < 440 and max(xs) > 520
    img, lm = scene_dumbbell(False)
    assert detect_dumbbell(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), lm, 0) is None


def test_tracker_needs_stable_detections():
    det = EquipmentDetector({"dumbbell"})
    img, lm = scene_dumbbell(True)
    assert det.process(img, lm) == []
    for _ in range(4):
        out = det.process(img, lm)
    assert [f.kind for f in out] == ["dumbbell"]
    empty, _ = scene_dumbbell(False)
    for _ in range(12):
        out = det.process(empty, lm)
    assert out == []
