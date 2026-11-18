"""Colores y hoja de estilos (estilo "ventana del Sistema")."""
BG = "#02060f"
CYAN = "#5fe0ff"
PANEL = "#0a1630"
LINE = "#2d7cff"
GLOW = "#3fa4ff"
CORE = "#eaf6ff"
TEXT = "#dceaff"
MUTED = "#7f95bf"
GOLD = "#ffd166"
RED = "#ff3b5c"
GREEN = "#3dffa8"
PURPLE = "#b06bff"

FONT = "Montserrat"           # incluida en assets/fonts (licencia OFL)
FONT_FALLBACK = "Segoe UI"

QSS = f"""
* {{ font-family: "{FONT}", "{FONT_FALLBACK}", sans-serif; color: {TEXT}; }}
QMainWindow, #root {{ background: {BG}; }}
QWidget#page {{ background: transparent; }}
QToolTip {{ background: {PANEL}; border: 1px solid {GLOW}; color: {TEXT}; }}

#brand {{ font-size: 26px; font-weight: 700; letter-spacing: 7px; color: {CORE}; background: transparent; }}
#brandSub {{ font-size: 9px; letter-spacing: 1px; color: {GLOW}; background: transparent; }}

#nav QPushButton {{
  text-align: left; padding: 13px 18px; font-size: 15px; letter-spacing: 2px; color: {MUTED};
  background: transparent; border: none; border-left: 3px solid transparent;
}}
#nav QPushButton:hover {{ color: white; background: rgba(42,127,255,0.12); }}
#nav QPushButton:checked {{ color: white; border-left: 3px solid transparent; background: transparent; }}
#navPlayer {{ color: {MUTED}; font-size: 13px; }}

QLabel {{ background: transparent; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#lbl {{ color: {MUTED}; font-size: 13px; letter-spacing: 1px; }}
QLabel#big {{ font-size: 24px; font-weight: 700; color: white; }}
QLabel#warn {{ color: {RED}; font-weight: 600; }}
QLabel#ok {{ color: {GREEN}; font-weight: 600; }}
QLabel#gold {{ color: {GOLD}; font-weight: 700; }}
QLabel#countdown {{ color: {MUTED}; letter-spacing: 2px; }}

QPushButton {{
  background: rgba(10,30,70,0.55); border: 1px solid rgba(79,216,255,0.75); padding: 9px 18px;
  font-size: 15px; font-weight: 600; letter-spacing: 2px; color: {CORE};
}}
QPushButton:hover {{ background: rgba(47,125,255,0.38); border-color: {CORE}; color: white; }}
QPushButton:pressed {{ background: rgba(77,225,255,0.45); }}
QPushButton:disabled {{ color: {MUTED}; border-color: #1c3260; background: transparent; }}
QPushButton[kind="primary"] {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #1b5cff, stop:1 #2fb8ff); border-color: {GLOW}; }}
QPushButton[kind="primary"]:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #2d6bff, stop:1 #5ccbff); }}
QPushButton[kind="danger"] {{ border-color: {RED}; background: rgba(255,59,92,0.12); }}
QPushButton[kind="danger"]:hover {{ background: rgba(255,59,92,0.32); }}
QPushButton[kind="ghost"] {{ border: none; background: transparent; color: {MUTED}; font-size: 13px; }}
QPushButton[kind="ghost"]:hover {{ color: white; }}
QPushButton#exCard {{ padding: 16px 8px; font-size: 15px; }}

QProgressBar {{ background: rgba(0,0,0,0.45); border: 1px solid {LINE}; height: 20px; text-align: center; color: white; font-weight: 600; }}
QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #1b5cff, stop:1 {GLOW}); }}
QProgressBar[done="true"]::chunk {{ background: {GREEN}; }}
QProgressBar#thin {{ max-height: 6px; min-height: 6px; border-color: #1c3a70; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
  background: rgba(0,0,0,0.45); border: 1px solid {LINE}; padding: 7px 10px; font-size: 15px; color: white;
  selection-background-color: {LINE};
}}
QComboBox QAbstractItemView {{ background: {PANEL}; border: 1px solid {GLOW}; selection-background-color: {LINE}; }}
QCheckBox {{ font-size: 15px; spacing: 10px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border: 1px solid {LINE}; background: rgba(0,0,0,0.45); }}
QCheckBox::indicator:checked {{ background: {GLOW}; border-color: {GLOW}; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: #1c3a70; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QListWidget {{ background: transparent; border: none; font-size: 14px; }}
QListWidget::item {{ border-bottom: 1px solid rgba(42,127,255,0.15); padding: 5px 2px; }}

QLabel#sysBody {{ font-size: 17px; color: {CORE}; background: transparent; }}

"""
