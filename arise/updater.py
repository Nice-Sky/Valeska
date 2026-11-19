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
API = f"https://api.github.com/repos/{REPO}/releases/latest"  # i18n: no
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"  # i18n: no
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
    asset = next((a for a in data.get("assets", []) if a.get("name") == ASSET), None)
    digest = (asset or {}).get("digest") or ""
    return {"version": data.get("tag_name", "").lstrip("v"), "name": data.get("name", ""),
            "url": asset and asset.get("browser_download_url"),
            "sha256": digest.split(":", 1)[1] if digest.startswith("sha256:") else None,
            "notes": data.get("body", "")}


def check_async(callback: Callable[[Optional[dict], Optional[str]], None]):
    """Consulta en segundo plano. callback(info, error) se llama desde otro hilo: usá QTimer/señales para la UI."""
    def run():
        try:
            callback(fetch_latest(), None)
        except Exception as e:  # noqa: BLE001
            callback(None, str(e))
    threading.Thread(target=run, daemon=True).start()


def download_async(url: str, progress: Callable[[float], None], done: Callable[[Optional[str], Optional[str]], None],
                   sha256: Optional[str] = None):
    """Descarga el instalador. Si GitHub informa la huella SHA-256, se verifica antes de aceptarlo."""
    import hashlib

    def run():
        try:
            path = os.path.join(tempfile.gettempdir(), ASSET)
            h = hashlib.sha256()
            req = urllib.request.Request(url, headers={"User-Agent": "AriseTrainer"})
            with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                got = 0
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
                    h.update(chunk)
                    got += len(chunk)
                    if total:
                        progress(got / total)
            if sha256 and h.hexdigest().lower() != sha256.lower():
                os.remove(path)
                from .i18n import t
                raise ValueError(t("la descarga no coincide con la huella publicada (archivo dañado)"))
            done(path, None)
        except Exception as e:  # noqa: BLE001
            done(None, str(e))
    threading.Thread(target=run, daemon=True).start()


def release_mutex():
    """Suelta el "candado" que usa el instalador para saber si la app está abierta.

    Si el instalador silencioso lo encuentra tomado, se cancela solo (sin avisar): por eso se suelta antes de lanzarlo.
    """
    try:
        import ctypes
        from . import app as _app
        h = getattr(_app, "_MUTEX", None)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            _app._MUTEX = None
    except Exception:
        pass


def run_installer(path: str, relaunch: bool = True, silent: bool = True) -> bool:
    """Lanza el instalador: cierra la app, actualiza y (si relaunch) la vuelve a abrir.

    Se lanza con unos segundos de espera (la app termina de cerrarse antes de que el instalador arranque).
    silent=False abre el asistente normal (para cuando la instalación automática no funcionó).
    """
    if sys.platform != "win32":
        return False
    release_mutex()
    args = [path]
    if silent:
        args += ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]
        if not relaunch:
            args.append("/NORELAUNCH")
    quoted = " ".join(f'"{a}"' if " " in a else a for a in args)
    # "ping" como pausa de ~3 s (timeout no funciona sin consola); start "" lanza el instalador desacoplado
    cmd = f'ping -n 4 127.0.0.1 >nul & start "" {quoted}'  # i18n: no
    # como texto (no lista): así cmd recibe las comillas tal cual, sin escapes de Python
    subprocess.Popen("cmd /c " + cmd, close_fds=True,  # i18n: no
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return True
