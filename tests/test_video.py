"""Regresión: con una persona detectada, la vista de cámara no debe taparse (antes se rellenaba de blanco)."""
import os
from types import SimpleNamespace as P

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_preview_not_covered_when_person_detected():
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from arise.ui.video import VideoView

    frame = QImage(640, 360, QImage.Format.Format_RGB888)
    frame.fill(QColor(20, 40, 70))
    lm = [P(x=0.5, y=0.5, z=0.0, visibility=0.99) for _ in range(33)]
    coords = {0: (.5, .15), 7: (.47, .14), 8: (.53, .14), 11: (.42, .3), 12: (.58, .3), 13: (.38, .45), 14: (.62, .45),
              15: (.36, .6), 16: (.64, .6), 23: (.45, .6), 24: (.55, .6), 25: (.45, .78), 26: (.55, .78),
              27: (.45, .95), 28: (.55, .95)}
    for i, (x, y) in coords.items():
        lm[i] = P(x=x, y=y, z=0.0, visibility=0.99)
    world = [P(x=p.x, y=p.y, z=0.0, visibility=0.99) for p in lm]

    v = VideoView()
    v.resize(640, 360)
    v.set_frame(frame, lm, "#3fa4ff", world)
    out = QImage(v.size(), QImage.Format.Format_ARGB32)
    v.render(out)
    c = out.pixelColor(60, 180)  # zona de la imagen lejos del cuerpo y de los textos
    assert (c.red(), c.green(), c.blue()) != (255, 255, 255)
    assert c.blue() < 150 and c.red() < 100, (c.red(), c.green(), c.blue())
