"""Buscar e instalar actualizaciones desde las Releases de GitHub."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.request
from typing import Callable, Optional

from ._version import VERSION

REPO = "Nice-Sky/Valeska"   # si el repo se renombra, GitHub redirige la API al nombre nuevo
API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
ASSET = "AriseTrainer-Instalador.exe"


def parse(v: str) -> tuple:
    v = v.strip().lstrip("vV")
    out = []
    for part in v.split("."):
        try:
            out.append(int(part))
        except ValueError:
            return ()
    return tuple(out)


def is_newer(latest: str, current: str = VERSION) -> bool:
    a, b = parse(latest), parse(current)
    return bool(a) and (not b or a > b)


def fetch_latest(timeout: float = 10) -> Optional[dict]:
    req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json", "User-Agent": "AriseTrainer"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    url = next((a["browser_download_url"] for a in data.get("assets", []) if a.get("name") == ASSET), None)
    return {"version": data.get("tag_name", "").lstrip("v"), "name": data.get("name", ""), "url": url,
            "notes": data.get("body", "")}


def check_async(callback: Callable[[Optional[dict], Optional[str]], None]):
    """Consulta en segundo plano. callback(info, error) se llama desde otro hilo: usá QTimer/señales para la UI."""
    def run():
        try:
            callback(fetch_latest(), None)
        except Exception as e:  # noqa: BLE001
            callback(None, str(e))
    threading.Thread(target=run, daemon=True).start()


def download_async(url: str, progress: Callable[[float], None], done: Callable[[Optional[str], Optional[str]], None]):
    def run():
        try:
            path = os.path.join(tempfile.gettempdir(), ASSET)
            req = urllib.request.Request(url, headers={"User-Agent": "AriseTrainer"})
            with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                got = 0
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if total:
                        progress(got / total)
            done(path, None)
        except Exception as e:  # noqa: BLE001
            done(None, str(e))
    threading.Thread(target=run, daemon=True).start()


def run_installer(path: str) -> bool:
    """Lanza el instalador en modo actualización silenciosa (cierra la app, actualiza y la vuelve a abrir)."""
    if sys.platform != "win32":
        return False
    subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
                     close_fds=True)
    return True
