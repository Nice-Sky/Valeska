"""Voz (texto a voz de Windows) y efectos de sonido sintetizados."""
from __future__ import annotations

import math
import queue
import struct
import tempfile
import threading
import time
import wave
from pathlib import Path

# pistas para elegir una voz de Windows en el idioma de la app
VOICE_HINTS = {
    "es": ("spanish", "español", "espanol", "es-", "es_", "sabina", "helena", "laura", "pablo", "raul", "elvira"),
    "en": ("english", "en-", "en_", "zira", "david", "mark", "hazel", "susan", "aria", "guy", "jenny"),
    "pt": ("portuguese", "português", "portugues", "pt-", "pt_", "maria", "daniel", "francisca", "antonio", "helia"),
}
SPANISH_HINTS = VOICE_HINTS["es"]


class Voice:
    def __init__(self):
        self.enabled = True
        self._q: queue.Queue[str] = queue.Queue()
        self._last = 0.0
        self._ok = True
        threading.Thread(target=self._run, daemon=True).start()

    def say(self, text: str, force: bool = False):
        if not self.enabled or not self._ok or not text:
            return
        now = time.monotonic()
        if not force and now - self._last < 1.8:
            return
        self._last = now
        while not self._q.empty():  # solo importa lo último
            try:
                self._q.get_nowait()
            except queue.Empty:
                break
        self._q.put(text)

    def _run(self):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            from .i18n import lang
            hints = VOICE_HINTS.get(lang(), SPANISH_HINTS)
            for v in engine.getProperty("voices"):
                desc = f"{v.id} {v.name} {getattr(v, 'languages', '')}".lower()  # i18n: no
                if any(h in desc for h in hints):
                    engine.setProperty("voice", v.id)
                    break
            engine.setProperty("rate", 190)
        except Exception:
            self._ok = False
            return
        while True:
            text = self._q.get()
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception:
                pass


# ------------------------------------------------------------------ sonidos
SOUNDS = {
    "rep":   ([(880, 0.08), (1320, 0.10)], "square", 0.25),
    "bad":   ([(220, 0.20)], "saw", 0.25),
    "open":  ([(660, 0.07), (990, 0.07), (1320, 0.12)], "tri", 0.35),
    "level": ([(523, 0.12), (659, 0.12), (784, 0.12), (1047, 0.35)], "tri", 0.4),
    "alarm": ([(440, 0.22), (330, 0.22), (440, 0.22), (330, 0.30)], "saw", 0.3),
    "tick":  ([(600, 0.10)], "square", 0.2),
    "go":    ([(1200, 0.18)], "square", 0.25),
}


def _synth(notes, kind, vol, rate=22050) -> bytes:
    frames = bytearray()
    for f, d in notes:
        n = int(rate * d)
        for i in range(n):
            t = i / rate
            ph = (t * f) % 1.0
            if kind == "square":
                s = 1.0 if ph < 0.5 else -1.0
            elif kind == "saw":
                s = 2 * ph - 1
            else:
                s = 4 * abs(ph - 0.5) - 1
            env = min(1.0, i / 200) * math.exp(-3.0 * i / n)
            frames += struct.pack("<h", int(s * env * vol * 32767))
    return bytes(frames)


SOUNDS_REF = None  # instancia global, para que los botones puedan sonar


class Sounds:
    """Efectos de sonido. Usa los WAV de assets/sfx (si existen); si no, sintetiza unos básicos."""

    def __init__(self):
        self.enabled = True
        self.volume = 0.7
        self._effects = {}
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QSoundEffect
            from .storage import resource
            d = Path(tempfile.gettempdir()) / "arise_sfx"
            d.mkdir(exist_ok=True)
            names = set(SOUNDS) | {p.stem for p in resource("sfx").glob("*.wav")}
            for name in names:
                p = resource("sfx", f"{name}.wav")
                if not p.exists():
                    if name not in SOUNDS:
                        continue
                    p = d / f"{name}.wav"
                    if not p.exists():
                        notes, kind, vol = SOUNDS[name]
                        with wave.open(str(p), "wb") as w:
                            w.setnchannels(1)
                            w.setsampwidth(2)
                            w.setframerate(22050)
                            w.writeframes(_synth(notes, kind, vol))
                fx = QSoundEffect()
                fx.setSource(QUrl.fromLocalFile(str(p)))
                fx.setVolume(self.volume)
                self._effects[name] = fx
        except Exception:
            self._effects = {}

    def set_volume(self, v: float):
        self.volume = max(0.0, min(1.0, v))
        for fx in self._effects.values():
            fx.setVolume(self.volume)

    def play(self, name: str):
        if self.enabled and name in self._effects:
            fx = self._effects[name]
            if fx.isPlaying() and name in ("rep", "tick", "hover", "click", "beep", "second"):
                fx.stop()
            fx.play()
