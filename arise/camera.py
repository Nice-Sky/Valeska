"""Captura de cámara + detección de pose (MediaPipe) en un hilo aparte."""
from __future__ import annotations

import sys
import time

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from .i18n import t
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
    from .i18n import t
    return [t("Cámara {n}", n=i + 1) for i in range(3)]


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
        self._pending = False  # hay un cuadro enviado que la interfaz todavía no procesó
        self.equip_kinds: set = set()  # "bar" / "dumbbell": buscar ese equipamiento en la imagen
        self.objects: list = []        # lo encontrado (arise.equipment.Found)

    def ack(self):
        """La interfaz avisa que terminó con el cuadro anterior (evita que se acumulen cuadros y haya retraso)."""
        self._pending = False

    def stop(self):
        self._stop = True
        self.wait(3000)

    @staticmethod
    def _configure(cap, cv2):
        # MJPG: muchas webcams en Windows (DirectShow) van lentas/parpadean a 720p sin comprimir
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # siempre el cuadro más nuevo (sin retraso acumulado)
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)  # exposición automática (DirectShow: 0.75 = auto)
        cap.set(cv2.CAP_PROP_AUTO_WB, 1)

    @staticmethod
    def _warmup(cap, cv2, max_s: float = 2.5) -> float:
        """Descarta los primeros cuadros hasta que el brillo se estabiliza (evita el "flash" blanco al arrancar).
        Devuelve el brillo medio final (0-255)."""
        start = time.monotonic()
        prev = None
        stable = 0
        m = 128.0
        while time.monotonic() - start < max_s:
            ok, f = cap.read()
            if not ok or f is None:
                time.sleep(0.03)
                continue
            m = float(cv2.resize(f, (32, 18), interpolation=cv2.INTER_AREA).mean())
            if prev is not None and abs(m - prev) < 4 and 15 < m < 235:
                stable += 1
                if stable >= 4:
                    return m
            else:
                stable = 0
            prev = m
        return m

    def run(self):
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks.python import BaseOptions
            from mediapipe.tasks.python import vision
        except Exception as e:  # pragma: no cover
            self.failed.emit(t("Falta una librería: {e}", e=e))
            return

        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        cap = cv2.VideoCapture(self.index, backend)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.index)
        if not cap.isOpened():
            self.failed.emit(t("No pude abrir la cámara. ¿Está conectada o la está usando otro programa?"))
            return
        self.status.emit(t("Ajustando cámara…"))
        self._configure(cap, cv2)
        if self._warmup(cap, cv2) > 230 and sys.platform == "win32":
            # la imagen sigue quemada en blanco: probamos con el otro sistema de video de Windows
            self.status.emit(t("Probando otro modo de cámara…"))
            cap.release()
            cap = cv2.VideoCapture(self.index, cv2.CAP_MSMF)
            if not cap.isOpened():
                cap = cv2.VideoCapture(self.index, backend)
            self._configure(cap, cv2)
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
            self.failed.emit(t("No pude cargar el modelo de visión: {e}", e=e))
            return

        from .equipment import EquipmentDetector
        detector = EquipmentDetector(set())
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
                        self.failed.emit(t("La cámara dejó de enviar imagen."))
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
                if w > 960:  # se achica para mostrar (en este hilo): dibujarla es mucho más barato
                    view = cv2.resize(view, (960, int(h * 960 / w)), interpolation=cv2.INTER_AREA)
                    h, w = view.shape[:2]
                view = view.copy() if not view.flags["C_CONTIGUOUS"] else view
                if self.equip_kinds:
                    detector.kinds = set(self.equip_kinds)
                    try:
                        self.objects = detector.process(view, lm)
                    except Exception:
                        self.objects = []
                elif self.objects:
                    self.objects = []
                if self._pending:  # la interfaz viene atrasada: se descarta este cuadro (se manda el próximo)
                    continue
                img = QImage(view.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
                self._pending = True
                self.frame.emit(img, lm, world, w / h, now)
        finally:
            landmarker.close()
            cap.release()
