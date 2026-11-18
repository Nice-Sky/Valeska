"""Sintetiza los efectos de sonido de la interfaz (WAV estéreo 44.1 kHz) en assets/sfx/.

Uso: python tools/make_sfx.py
(Si tenés ElevenLabs al día, tools/generate_sfx_elevenlabs.py los reemplaza por sonidos generados por IA.)
"""
import math
import wave
from pathlib import Path

import numpy as np

SR = 44100
OUT = Path(__file__).resolve().parent.parent / "assets" / "sfx"
rng = np.random.default_rng(7)


def t(d):
    return np.arange(int(SR * d)) / SR


def env(n, a=0.005, d=0.3, curve=4.0):
    x = np.arange(n) / SR
    att = np.clip(x / max(a, 1e-4), 0, 1)
    dec = np.exp(-curve * np.clip(x - a, 0, None) / max(d, 1e-4))
    return att * dec


def bell(f, d, partials=((1, 1), (2.76, 0.45), (5.4, 0.25), (8.93, 0.12)), decay=1.0):
    x = t(d)
    s = np.zeros_like(x)
    for m, a in partials:
        s += a * np.sin(2 * np.pi * f * m * x) * np.exp(-x * (3 + m) / decay)
    return s * env(len(x), 0.002, d, 1.0)


def fm(fc, fm_, idx, d, decay=3.0):
    x = t(d)
    i = idx * np.exp(-x * decay)
    return np.sin(2 * np.pi * fc * x + i * np.sin(2 * np.pi * fm_ * x))


def lowpass(s, cutoff):
    """Filtro de un polo (cutoff puede ser array para barridos)."""
    cut = np.broadcast_to(np.asarray(cutoff, dtype=np.float64), s.shape)
    a = 1 - np.exp(-2 * np.pi * cut / SR)
    out = np.empty_like(s)
    y = 0.0
    for i in range(len(s)):
        y += a[i] * (s[i] - y)
        out[i] = y
    return out


def highpass(s, cutoff):
    return s - lowpass(s, cutoff)


def noise(d):
    return rng.standard_normal(int(SR * d))


def whoosh(d, f0, f1):
    n = noise(d)
    sweep = np.geomspace(f0, f1, len(n))
    s = lowpass(n, sweep) - lowpass(n, sweep * 0.35)
    e = np.sin(np.pi * np.linspace(0, 1, len(n))) ** 2
    return s * e


def reverb(s, length=1.4, mix=0.28, seed=1):
    r = np.random.default_rng(seed)
    n = int(SR * length)
    ir_l = r.standard_normal(n) * np.exp(-np.linspace(0, 6, n))
    ir_r = r.standard_normal(n) * np.exp(-np.linspace(0, 6, n))
    ir_l = lowpass(ir_l, 5000)
    ir_r = lowpass(ir_r, 5000)
    pad = len(s) + n
    S = np.fft.rfft(s, pad)
    wl = np.fft.irfft(S * np.fft.rfft(ir_l, pad), pad)
    wr = np.fft.irfft(S * np.fft.rfft(ir_r, pad), pad)
    dry = np.concatenate([s, np.zeros(n)])
    norm = max(np.abs(wl).max(), np.abs(wr).max(), 1e-9) / max(np.abs(s).max(), 1e-9)
    left = dry * (1 - mix) + wl / norm * mix
    right = dry * (1 - mix) + wr / norm * mix
    return np.stack([left, right], 1)


def mix(*parts):
    n = max(len(p) + int(off * SR) for p, off in parts)
    out = np.zeros(n)
    for p, off in parts:
        o = int(off * SR)
        out[o:o + len(p)] += p[: n - o]
    return out


def save(name, stereo, gain=0.85, tail_trim=True):
    if stereo.ndim == 1:
        stereo = np.stack([stereo, stereo], 1)
    if tail_trim:
        mag = np.abs(stereo).max(1)
        idx = np.where(mag > mag.max() * 0.002)[0]
        stereo = stereo[: idx[-1] + 1] if len(idx) else stereo
    fade = min(len(stereo), int(0.03 * SR))
    stereo[-fade:] *= np.linspace(1, 0, fade)[:, None]
    stereo = stereo / max(1e-9, np.abs(stereo).max()) * gain
    data = (stereo * 32767).astype("<i2")
    OUT.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT / f"{name}.wav"), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
    print(f"  {name}.wav  {len(stereo) / SR:.2f}s")


def build():
    # Notificación: dos campanas de cristal + brillo de ruido agudo
    shimmer = highpass(noise(0.6), 6000) * env(int(0.6 * SR), 0.02, 0.25, 3) * 0.06
    save("notify", reverb(mix((bell(1318, 1.2) * 0.6, 0), (bell(1976, 1.0) * 0.45, 0.09), (shimmer, 0)), 1.6, 0.35))
    # Apertura de ventana del Sistema: barrido ascendente + tono + clic de "encendido"
    sweep_t = t(0.45)
    tone = np.sin(2 * np.pi * np.cumsum(np.geomspace(260, 1240, len(sweep_t))) / SR) * env(len(sweep_t), 0.25, 0.25, 2) * 0.35
    click = highpass(noise(0.03), 3000) * env(int(0.03 * SR), 0.001, 0.01, 6) * 0.5
    save("open", reverb(mix((whoosh(0.5, 400, 7000) * 0.9, 0), (tone, 0.02), (click, 0.43), (bell(1760, 0.8) * 0.35, 0.44)), 1.3, 0.3))
    # Cierre: barrido descendente
    save("close", reverb(mix((whoosh(0.32, 6000, 300) * 0.9, 0), (bell(880, 0.4) * 0.15, 0.05)), 0.8, 0.25))
    # Repetición válida: "ding" cristalino corto
    save("rep", reverb(mix((bell(1568, 0.5, decay=0.5) * 0.8, 0), (bell(2349, 0.35, decay=0.4) * 0.3, 0.035),
                           (highpass(noise(0.02), 4000) * 0.15, 0)), 0.7, 0.2))
    # Repetición mal hecha: zumbido grave desafinado
    x = t(0.32)
    buzz = (np.sign(np.sin(2 * np.pi * 110 * x)) + np.sign(np.sin(2 * np.pi * 116.5 * x))) * 0.5
    save("bad", reverb(lowpass(buzz * env(len(x), 0.004, 0.18, 2.5), 1400) * 0.9, 0.6, 0.15), 0.7)
    # Subida de nivel: arpegio de campanas + pad brillante
    arp = mix(*[(bell(f, 1.6) * 0.5, i * 0.085) for i, f in enumerate((523, 659, 784, 1047, 1319))])
    pad_t = t(1.8)
    pad = sum(np.sin(2 * np.pi * f * pad_t) for f in (523, 784, 1047)) * env(len(pad_t), 0.35, 1.2, 1.5) * 0.12
    save("level", reverb(mix((arp, 0), (pad, 0.2), (whoosh(0.6, 800, 9000) * 0.3, 0)), 2.0, 0.4))
    # Objetivo cumplido: acorde grande con impacto
    boom = np.sin(2 * np.pi * 55 * t(0.9)) * env(int(0.9 * SR), 0.003, 0.5, 2) * 0.9
    chord = mix(*[(bell(f, 2.2, decay=1.6) * 0.35, 0.05) for f in (392, 494, 587, 784)])
    save("quest", reverb(mix((boom, 0.12), (chord, 0.12), (whoosh(0.5, 300, 8000) * 0.5, 0)), 2.2, 0.4))
    # Alarma / penalización suave: pulsos de dos tonos
    x = t(0.22)
    beep = lambda f: lowpass(np.sign(np.sin(2 * np.pi * f * x)) * env(len(x), 0.005, 0.2, 1.2), 2400) * 0.6
    save("alarm", reverb(mix((beep(660), 0), (beep(495), 0.26), (beep(660), 0.52), (beep(495), 0.78)), 0.9, 0.25), 0.75)
    # Cuenta regresiva y "¡ya!"
    save("tick", reverb(mix((bell(1046, 0.25, decay=0.3) * 0.7, 0), (highpass(noise(0.01), 5000) * 0.3, 0)), 0.5, 0.15), 0.7)
    save("go", reverb(mix(*[(bell(f, 0.9, decay=0.9) * 0.4, 0) for f in (784, 1175, 1568)],
                          (whoosh(0.25, 2000, 9000) * 0.4, 0)), 1.0, 0.3))
    # Logro: destellos agudos aleatorios
    sparkle = mix(*[(bell(rng.uniform(2000, 3600), 0.6, decay=0.5) * rng.uniform(0.15, 0.35), i * 0.05) for i in range(9)])
    save("achievement", reverb(mix((sparkle, 0), (bell(1319, 1.5) * 0.4, 0)), 1.8, 0.45))
    # Penalización: impacto grave distorsionado
    x = t(1.2)
    imp = np.tanh(3 * np.sin(2 * np.pi * np.geomspace(90, 38, len(x)) * x)) * env(len(x), 0.002, 0.6, 2)
    save("penalty", reverb(mix((imp * 0.9, 0), (lowpass(noise(0.4), 600) * env(int(0.4 * SR), 0.001, 0.15, 3), 0)), 1.6, 0.3))
    # Interfaz: hover y clic
    save("hover", mix((bell(2637, 0.12, decay=0.15) * 0.25, 0)), 0.35)
    save("click", reverb(mix((highpass(noise(0.015), 2500) * env(int(0.015 * SR), 0.0005, 0.006, 5), 0),
                             (bell(1760, 0.15, decay=0.2) * 0.3, 0.004)), 0.4, 0.15), 0.55)


if __name__ == "__main__":
    build()
