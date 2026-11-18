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

    def __init__(self, index: int = 0, mirror: bool = True, parent=None, segmentation: bool = False):
        super().__init__(parent)
        self.index = index
        self.mirror = mirror
        self.segmentation = segmentation
        self.latest = None  # (rgb, mask, landmarks) del último cuadro, para sacar fotos
        self._stop = False

    def stop(self):
        self._stop = True
        self.wait(3000)

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
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

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
                img = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
                self.frame.emit(img, lm, world, w / h, now)
        finally:
            landmarker.close()
            cap.release()
