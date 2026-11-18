"""Captura de cámara + detección de pose (MediaPipe) en un hilo aparte."""
from __future__ import annotations

import sys
import time

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from .storage import resource

MODEL = resource("models", "pose_landmarker_lite.task")


def list_cameras() -> list[str]:
    """Nombres de las cámaras (en el mismo orden que usa OpenCV en Windows)."""
    try:
        from PySide6.QtMultimedia import QMediaDevices
        names = [d.description() for d in QMediaDevices.videoInputs()]
        if names:
            return names
    except Exception:
        pass
    return [f"Cámara {i + 1}" for i in range(3)]


class CameraWorker(QThread):
    frame = Signal(QImage, object, object, float, float)  # imagen, landmarks, world, aspecto, t
    failed = Signal(str)
    ready = Signal()
    status = Signal(str)  # mensajes mientras la cámara ajusta la luz

    def __init__(self, index: int = 0, mirror: bool = True, parent=None, segmentation: bool = False,
                 holo_view: bool = False):
        super().__init__(parent)
        self.holo_view = holo_view
        self.index = index
        self.mirror = mirror
        self.segmentation = segmentation
        self.latest = None  # (rgb, mask, landmarks) del último cuadro, para sacar fotos
        self._stop = False

    def stop(self):
        self._stop = True
        self.wait(3000)

    @staticmethod
    def _warmup(cap, cv2, max_s: float = 2.0):
        """Descarta los primeros cuadros hasta que el brillo se estabiliza (evita el "flash" blanco al arrancar)."""
        start = time.monotonic()
        prev = None
        stable = 0
        while time.monotonic() - start < max_s:
            ok, f = cap.read()
            if not ok or f is None:
                time.sleep(0.03)
                continue
            m = float(cv2.resize(f, (32, 18), interpolation=cv2.INTER_AREA).mean())
            if prev is not None and abs(m - prev) < 4 and 15 < m < 235:
                stable += 1
                if stable >= 4:
                    return
            else:
                stable = 0
            prev = m

    def run(self):
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks.python import BaseOptions
            from mediapipe.tasks.python import vision
        except Exception as e:  # pragma: no cover
            self.failed.emit(f"Falta una librería: {e}")
            return

        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        cap = cv2.VideoCapture(self.index, backend)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.index)
        if not cap.isOpened():
            self.failed.emit("No pude abrir la cámara. ¿Está conectada o la está usando otro programa?")
            return
        # MJPG: muchas webcams en Windows (DirectShow) van lentas/parpadean a 720p sin comprimir
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # siempre el cuadro más nuevo (sin retraso acumulado)
        self.status.emit("Ajustando cámara…")
        self._warmup(cap, cv2)

        try:
            options = vision.PoseLandmarkerOptions(
                base_options=BaseOptions(model_asset_buffer=MODEL.read_bytes()),
                running_mode=vision.RunningMode.VIDEO,
                num_poses=1,
                min_pose_detection_confidence=0.5,
                min_pose_presence_confidence=0.5,
                min_tracking_confidence=0.5,
                output_segmentation_masks=self.segmentation,
            )
            landmarker = vision.PoseLandmarker.create_from_options(options)
        except Exception as e:
            cap.release()
            self.failed.emit(f"No pude cargar el modelo de visión: {e}")
            return

        self.ready.emit()
        t0 = time.monotonic()
        last_ts = -1
        fails = 0
        last_bright = 128.0
        try:
            while not self._stop:
                ok, bgr = cap.read()
                if not ok or bgr is None:
                    fails += 1
                    if fails > 60:
                        self.failed.emit("La cámara dejó de enviar imagen.")
                        break
                    time.sleep(0.02)
                    continue
                fails = 0
                # cuadros "quemados" en blanco (la cámara reajustando la exposición): no se muestran
                small = cv2.resize(bgr, (32, 18), interpolation=cv2.INTER_AREA)
                bright = float(small.mean())
                if bright > 242 and last_bright < 230:
                    last_bright = bright
                    continue
                last_bright = bright
                if self.mirror:
                    bgr = cv2.flip(bgr, 1)
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                now = time.monotonic() - t0
                ts = max(last_ts + 1, int(now * 1000))
                last_ts = ts
                res = landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)
                lm = res.pose_landmarks[0] if res.pose_landmarks else None
                world = res.pose_world_landmarks[0] if res.pose_world_landmarks else None
                if self.segmentation:
                    mask = res.segmentation_masks[0].numpy_view().copy() if res.segmentation_masks else None
                    if mask is not None and mask.ndim == 3:
                        mask = mask[..., 0]
                    self.latest = (rgb, mask, lm)
                h, w = rgb.shape[:2]
                view = rgb
                if self.holo_view:  # monocromo azul holográfico (solo para mostrar; el análisis usa el original)
                    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
                    g = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(g) if w <= 1920 else g
                    gf = g.astype("float32") / 255.0
                    view = cv2.merge([(gf * 45 + 3), (gf * 110 + 8), (gf * 190 + 16)]).clip(0, 255).astype("uint8")
                img = QImage(view.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
                self.frame.emit(img, lm, world, w / h, now)
        finally:
            landmarker.close()
            cap.release()
