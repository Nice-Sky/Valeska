"""Rutas, guardado del progreso e inicio automático con Windows."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_NAME = "AriseTrainer"
_OLD_APP_NAMES = ("Ascenso",)


def resource(*parts) -> Path:
    """Ruta a un recurso empaquetado (funciona tanto en desarrollo como en el .exe)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base.joinpath("assets", *parts)


def data_dir() -> Path:
    if os.environ.get("ARISE_DATA"):
        d = Path(os.environ["ARISE_DATA"])
    elif sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", Path.home()))
        d = root / APP_NAME
        _migrate_dir(d, [root / n for n in _OLD_APP_NAMES])
    else:
        d = Path.home() / ".config" / "arise-trainer"
        _migrate_dir(d, [Path.home() / ".config" / "ascenso"])
    d.mkdir(parents=True, exist_ok=True)
    return d


def _migrate_dir(new: Path, olds) -> None:
    """Si existe la carpeta de una versión anterior (Ascenso), se renombra para no perder el progreso."""
    if new.exists():
        return
    for old in olds:
        if (old / "progreso.json").exists():
            try:
                os.replace(old, new)
            except OSError:
                pass
            return


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "progreso.json"

    def load(self) -> dict | None:
        for p in (self.path, self.path.with_suffix(".bak")):
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "player" in data:
                    return data
            except (OSError, ValueError):
                continue
        return None

    def save(self, state: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=1)
        if self.path.exists():
            try:
                os.replace(self.path, self.path.with_suffix(".bak"))
            except OSError:
                pass
        os.replace(tmp, self.path)


# ------------------------------------------------------------ inicio automático
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimizado'
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    main = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{pyw if pyw.exists() else exe}" "{main}" --minimizado'


def autostart_supported() -> bool:
    return sys.platform == "win32"


def autostart_enabled() -> bool:
    if not autostart_supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def migrate_autostart() -> None:
    """Si la versión anterior (Ascenso) arrancaba con Windows, pasa ese ajuste a Arise Trainer."""
    if not autostart_supported():
        return
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            for old in _OLD_APP_NAMES:
                try:
                    winreg.QueryValueEx(k, old)
                except OSError:
                    continue
                set_autostart(True)
                return
    except OSError:
        pass


def set_autostart(on: bool) -> bool:
    if not autostart_supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            for old in _OLD_APP_NAMES:
                try:
                    winreg.DeleteValue(k, old)
                except OSError:
                    pass
            if on:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _launch_command())
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
