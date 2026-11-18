"""Genera los efectos de sonido con la API de efectos de ElevenLabs y los guarda en assets/sfx/ (WAV).

Requiere: la clave en la variable de entorno ELEVENLABS_API_KEY (o un proxy que la inyecte) y ffmpeg instalado.
Uso: python tools/generate_sfx_elevenlabs.py            # todos
     python tools/generate_sfx_elevenlabs.py notify level  # solo algunos
"""
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "assets" / "sfx"
API = "https://api.elevenlabs.io/v1/sound-generation"

PROMPTS = {
    "notify": ("Futuristic holographic system notification chime, crystalline glassy two-note ping, soft digital "
               "shimmer tail, clean sci-fi interface sound", 1.6),
    "open": ("Sci-fi holographic window materializing: quick rising digital whoosh, electric energy build-up and a "
             "crisp glassy activation click at the end, clean UI sound", 1.4),
    "close": ("Sci-fi holographic panel collapsing and closing, short descending digital whoosh, soft power-down", 0.8),
    "rep": ("Very short satisfying crystalline UI confirmation ding for counting a repetition, bright and clean", 0.5),
    "bad": ("Short low digital error buzz, sci-fi interface denial sound, two quick pulses", 0.5),
    "level": ("Epic level up sound, ascending magical crystal arpeggio with bright shimmering energy swell, "
              "futuristic game UI", 2.5),
    "quest": ("Quest complete fanfare for a futuristic system interface: deep impact, triumphant shimmering chord "
              "and sparkling tail", 2.8),
    "alarm": ("Futuristic system warning alert, urgent pulsing two-tone holographic alarm, sci-fi", 1.6),
    "tick": ("Short clean digital countdown tick, sci-fi interface beep", 0.4),
    "go": ("Bright energetic sci-fi start signal, short powerful chord stab with whoosh", 1.0),
    "achievement": ("Achievement unlocked sparkle, magical glittering crystal chimes, futuristic UI reward", 2.0),
    "penalty": ("Ominous deep digital impact for a penalty, heavy distorted sci-fi bass hit with dark tail", 1.8),
    "hover": ("Tiny subtle high pitched UI hover tick, glassy, very short", 0.3),
    "click": ("Short crisp futuristic UI button click, holographic, clean", 0.3),
}


def generate(name: str, prompt: str, seconds: float, key: str):
    body = json.dumps({"text": prompt, "duration_seconds": seconds, "prompt_influence": 0.55}).encode()
    req = urllib.request.Request(API, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "xi-api-key": key})
    with urllib.request.urlopen(req, timeout=120) as r:
        mp3 = r.read()
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(mp3)
    OUT.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f.name, "-ar", "44100", "-ac", "2",
                    "-sample_fmt", "s16", str(OUT / f"{name}.wav")], check=True)
    os.unlink(f.name)
    print(f"  {name}.wav listo")


def main():
    key = os.environ.get("ELEVENLABS_API_KEY", "proxy-injected")
    names = sys.argv[1:] or list(PROMPTS)
    for n in names:
        prompt, secs = PROMPTS[n]
        try:
            generate(n, prompt, secs, key)
        except Exception as e:  # noqa: BLE001
            print(f"  {n}: error -> {e}")


if __name__ == "__main__":
    main()
