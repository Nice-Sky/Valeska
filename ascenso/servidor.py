#!/usr/bin/env python3
"""
ASCENSO - Servidor local + Guardián

  * Sirve la app en http://localhost:8765 (la cámara funciona en localhost)
  * Guarda tu progreso en datos/progreso.json
  * El Guardián revisa cada pocos segundos si completaste la misión diaria.
    Desde la hora configurada, si no la completaste, te tira una alerta
    encima de todo (ventana del Sistema) cada X minutos hasta que entrenes.

Uso:
    python servidor.py              -> abre la app en el navegador
    python servidor.py --sin-abrir  -> solo arranca (para inicio automático)
    python servidor.py --puerto 9000
"""
import argparse
import json
import os
import platform
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import date, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "datos")
STATE_FILE = os.path.join(DATA_DIR, "progreso.json")
GUARD_FILE = os.path.join(DATA_DIR, "guardian.json")
os.makedirs(DATA_DIR, exist_ok=True)

NAMES = {
    "pushup": "Flexiones", "squat": "Sentadillas", "situp": "Abdominales",
    "jack": "Jumping Jacks", "lunge": "Zancadas", "plank": "Plancha (seg)",
}
DEFAULT_NAG = {"enabled": True, "startHour": 18, "intervalMin": 20, "snoozesPerDay": 2, "hard": False}
SURRENDER_PHRASE = "ME RINDO"

lock = threading.Lock()
last_training_beat = 0.0


# ------------------------------------------------------------------ datos
def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def load_state():
    with lock:
        return read_json(STATE_FILE, {})


def guardian_today():
    g = read_json(GUARD_FILE, {})
    today = date.today().isoformat()
    if g.get("date") != today:
        g = {"date": today, "snoozes": 0, "surrender": False}
    return g


def quest_status(state):
    """Devuelve (completada, lista_de_pendientes)."""
    q = state.get("quest") or {}
    if not state.get("player"):
        return False, ["Abrí el Sistema y registrate como Jugador"]
    if q.get("date") != date.today().isoformat():
        return False, ["Abrí el Sistema para recibir la misión de hoy"]
    if q.get("completed"):
        return True, []
    pending = []
    prog = q.get("progress") or {}
    for k, target in (q.get("targets") or {}).items():
        left = target - (prog.get(k) or 0)
        if left > 0:
            pending.append(f"{NAMES.get(k, k)}: faltan {int(left)}")
    return False, pending


# ------------------------------------------------------------------ HTTP
class Handler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript", ".mjs": "text/javascript", ".wasm": "application/wasm",
        ".task": "application/octet-stream", ".json": "application/json",
    }

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=APP_DIR, **kw)

    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/state":
            return self._json(200, load_state())
        if path == "/api/guardian":
            done, pending = quest_status(load_state())
            return self._json(200, {"done": done, "pending": pending, **guardian_today()})
        if path.startswith("/datos"):
            return self._json(403, {"error": "prohibido"})
        return super().do_GET()

    def do_POST(self):
        global last_training_beat
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length") or 0)
        if length > 5_000_000:
            return self._json(413, {"error": "demasiado grande"})
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            return self._json(400, {"error": "json inválido"})
        if path == "/api/state":
            if not isinstance(data, dict) or "player" not in data:
                return self._json(400, {"error": "estado inválido"})
            with lock:
                write_json(STATE_FILE, data)
            return self._json(200, {"ok": True})
        if path == "/api/heartbeat":
            if data.get("training"):
                last_training_beat = time.time()
            return self._json(200, {"ok": True})
        return self._json(404, {"error": "no existe"})


# ------------------------------------------------------------------ Guardián
class Guardian:
    def __init__(self, url):
        self.url = url
        self.next_nag = 0.0
        self.window = None
        self.root = None

    # decide si toca molestar ahora
    def should_nag(self):
        state = load_state()
        nag = {**DEFAULT_NAG, **((state.get("settings") or {}).get("nag") or {})}
        done, pending = quest_status(state)
        if done or not nag["enabled"]:
            return None
        if datetime.now().hour < int(nag["startHour"]):
            return None
        if guardian_today().get("surrender"):
            return None
        if time.time() - last_training_beat < 120:  # está entrenando ahora mismo
            return None
        if time.time() < self.next_nag:
            return None
        return nag, pending, state

    def schedule(self, minutes):
        self.next_nag = time.time() + minutes * 60

    def open_app(self):
        webbrowser.open(self.url + "#mision")

    # ---------------- modo con ventana (tkinter)
    def run_tk(self):
        import tkinter as tk
        self.tk = tk
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.after(3000, self.tick_tk)
        print("  Guardián activo (ventanas del Sistema habilitadas).")
        self.root.mainloop()

    def tick_tk(self):
        try:
            state = load_state()
            done, _ = quest_status(state)
            if done and self.window is not None:
                self.close_window()
            if self.window is None:
                res = self.should_nag()
                if res:
                    self.show_window(*res)
        except Exception as e:  # nunca dejar morir al guardián
            print("Guardián error:", e)
        self.root.after(10000, self.tick_tk)

    def close_window(self):
        if self.window is not None:
            try:
                self.window.grab_release()
            except Exception:
                pass
            self.window.destroy()
            self.window = None

    def show_window(self, nag, pending, state):
        tk = self.tk
        hard = bool(nag.get("hard"))
        interval = max(5, int(nag["intervalMin"]))
        g = guardian_today()
        snoozes_left = max(0, int(nag["snoozesPerDay"]) - g["snoozes"])
        name = (state.get("player") or {}).get("name") or "Jugador"
        penalty = (state.get("quest") or {}).get("penalty")

        BG, FG, CY, RED = "#050914", "#dceaff", "#4de1ff", "#ff3b5c"
        w = tk.Toplevel(self.root)
        self.window = w
        w.title("ALERTA DEL SISTEMA")
        w.configure(bg=BG, highlightthickness=3, highlightbackground=RED)
        w.attributes("-topmost", True)
        if hard:
            w.overrideredirect(True)
            sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
            w.geometry(f"{sw}x{sh}+0+0")
            w.protocol("WM_DELETE_WINDOW", lambda: None)
        else:
            ww, wh = 620, 470
            x = (w.winfo_screenwidth() - ww) // 2
            y = (w.winfo_screenheight() - wh) // 3
            w.geometry(f"{ww}x{wh}+{x}+{y}")
            w.protocol("WM_DELETE_WINDOW", lambda: (self.schedule(interval), self.close_window()))

        box = tk.Frame(w, bg=BG)
        box.place(relx=0.5, rely=0.5, anchor="center")
        big = 34 if hard else 22
        tk.Label(box, text="⚠  ALERTA DEL SISTEMA  ⚠", fg=RED, bg=BG, font=("Arial Black", big)).pack(pady=(0, 10))
        msg = (f"{name}, tu {'MISIÓN DE PENALIZACIÓN' if penalty else 'misión diaria'} sigue incompleta.\n"
               "Si no la completás antes de medianoche recibirás una penalización.")
        tk.Label(box, text=msg, fg=FG, bg=BG, font=("Arial", 15 if hard else 12), justify="center").pack(pady=6)
        tk.Label(box, text="\n".join("•  " + p for p in pending[:6]), fg=CY, bg=BG,
                 font=("Consolas", 15 if hard else 12), justify="left").pack(pady=10)

        def train():
            self.open_app()
            self.schedule(interval)
            self.close_window()

        def snooze():
            g2 = guardian_today()
            g2["snoozes"] += 1
            write_json(GUARD_FILE, g2)
            self.schedule(15)
            self.close_window()

        def surrender():
            win = tk.Toplevel(w)
            win.configure(bg=BG)
            win.attributes("-topmost", True)
            win.title("Rendirse")
            tk.Label(win, text=f'Escribí "{SURRENDER_PHRASE}" para que el Sistema\nte deje en paz hoy (igual recibirás la penalización).',
                     fg=FG, bg=BG, font=("Arial", 12)).pack(padx=20, pady=12)
            e = tk.Entry(win, font=("Arial", 14), justify="center")
            e.pack(padx=20, pady=6)
            e.focus_force()

            def ok(*_):
                if e.get().strip().upper() == SURRENDER_PHRASE:
                    g3 = guardian_today()
                    g3["surrender"] = True
                    write_json(GUARD_FILE, g3)
                    win.destroy()
                    self.close_window()
                else:
                    e.delete(0, "end")
            e.bind("<Return>", ok)
            tk.Button(win, text="Confirmar", command=ok).pack(pady=10)

        btn = dict(font=("Arial", 14, "bold"), bd=0, padx=18, pady=10, cursor="hand2")
        tk.Button(box, text="⚔  ENTRENAR AHORA", bg="#1b5cff", fg="white", activebackground=CY,
                  command=train, **btn).pack(pady=(14, 6), fill="x")
        if snoozes_left > 0:
            tk.Button(box, text=f"Posponer 15 min  (te quedan {snoozes_left})", bg="#16213e", fg=FG,
                      command=snooze, **btn).pack(pady=6, fill="x")
        tk.Button(box, text="Me rindo por hoy…", bg=BG, fg="#7f95bf", font=("Arial", 10), bd=0,
                  cursor="hand2", command=surrender).pack(pady=(8, 0))

        self.beep()

        def keep_on_top():
            if self.window is not w:
                return
            try:
                sub_open = any(isinstance(c, tk.Toplevel) for c in w.winfo_children())
                if not sub_open:
                    w.lift()
                    w.attributes("-topmost", True)
                    if hard:
                        w.focus_force()
            except Exception:
                return
            w.after(1500, keep_on_top)
        keep_on_top()

    def beep(self):
        try:
            if platform.system() == "Windows":
                import winsound
                for f in (880, 660, 880, 660):
                    winsound.Beep(f, 180)
            elif self.root is not None:
                self.root.bell()
        except Exception:
            pass

    # ---------------- modo sin tkinter (alertas del sistema operativo)
    def run_fallback(self):
        print("  Guardián activo (modo notificaciones: tkinter no disponible).")
        while True:
            try:
                res = self.should_nag()
                if res:
                    nag, pending, _ = res
                    self.schedule(max(5, int(nag["intervalMin"])))
                    self.fallback_alert(pending)
            except Exception as e:
                print("Guardián error:", e)
            time.sleep(15)

    def fallback_alert(self, pending):
        title = "ALERTA DEL SISTEMA"
        text = "Tu misión diaria sigue incompleta.\n" + "\n".join(pending[:6]) + "\n\n¿Ir a entrenar ahora?"
        system = platform.system()
        go = True
        try:
            if system == "Windows":
                import ctypes
                # MB_YESNO | MB_ICONWARNING | MB_SYSTEMMODAL | MB_SETFOREGROUND
                r = ctypes.windll.user32.MessageBoxW(0, text, title, 0x4 | 0x30 | 0x1000 | 0x10000)
                go = r == 6
            elif system == "Darwin":
                safe = text.replace('"', "'")
                r = subprocess.run(["osascript", "-e",
                                    f'display dialog "{safe}" with title "{title}" buttons {{"Después", "Entrenar"}} default button "Entrenar" with icon caution'],
                                   capture_output=True, text=True)
                go = "Entrenar" in r.stdout
            else:
                if subprocess.run(["which", "zenity"], capture_output=True).returncode == 0:
                    go = subprocess.run(["zenity", "--question", "--title", title, "--text", text]).returncode == 0
                else:
                    subprocess.run(["notify-send", "-u", "critical", title, text])
                    print(f"\n[{datetime.now():%H:%M}] {title}: {text}\n")
        except Exception:
            print(f"\n[{datetime.now():%H:%M}] {title}: {text}\n")
        if go:
            self.open_app()


def main():
    ap = argparse.ArgumentParser(description="ASCENSO - Sistema de entrenamiento")
    ap.add_argument("--puerto", type=int, default=8765)
    ap.add_argument("--sin-abrir", action="store_true", help="no abrir el navegador al iniciar")
    ap.add_argument("--sin-guardian", action="store_true", help="no molestar con alertas")
    args = ap.parse_args()

    url = f"http://localhost:{args.puerto}/"
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", args.puerto), Handler)
    except OSError:
        print(f"El puerto {args.puerto} ya está en uso (¿ASCENSO ya está abierto?).")
        if not args.sin_abrir:
            webbrowser.open(url)
        return
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print("=" * 52)
    print("  ASCENSO · Sistema de entrenamiento")
    print(f"  App: {url}")
    print("  Cerrá esta ventana para apagar el Sistema.")
    print("=" * 52)
    if not args.sin_abrir:
        webbrowser.open(url)

    if args.sin_guardian:
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return

    guardian = Guardian(url)
    try:
        import tkinter  # noqa: F401
        guardian.run_tk()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        if not isinstance(e, ImportError):
            print("  (No se pudo abrir ventanas:", e, ")")
        try:
            guardian.run_fallback()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
