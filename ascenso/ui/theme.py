"""Colores y hoja de estilos (estilo "ventana del Sistema")."""
BG = "#050914"
PANEL = "#0a1630"
LINE = "#2a7fff"
GLOW = "#4de1ff"
TEXT = "#dceaff"
MUTED = "#7f95bf"
GOLD = "#ffd166"
RED = "#ff3b5c"
GREEN = "#3dffa8"
PURPLE = "#b06bff"

FONT = "Bahnschrift"          # viene con Windows 10/11, aspecto técnico
FONT_FALLBACK = "Segoe UI"

QSS = f"""
* {{ font-family: "{FONT}", "{FONT_FALLBACK}", sans-serif; color: {TEXT}; }}
QMainWindow, #root {{ background: {BG}; }}
QWidget#page {{ background: transparent; }}
QToolTip {{ background: {PANEL}; border: 1px solid {GLOW}; color: {TEXT}; }}

#brand {{ font-size: 26px; font-weight: 700; letter-spacing: 6px; color: white; }}
#brandSub {{ font-size: 9px; letter-spacing: 1px; color: {GLOW}; }}

#nav QPushButton {{
  text-align: left; padding: 12px 16px; font-size: 15px; letter-spacing: 2px; color: {MUTED};
  background: transparent; border: none; border-left: 3px solid transparent;
}}
#nav QPushButton:hover {{ color: white; background: rgba(42,127,255,0.12); }}
#nav QPushButton:checked {{ color: white; border-left: 3px solid {GLOW}; background: rgba(42,127,255,0.22); }}
#navPlayer {{ color: {MUTED}; font-size: 13px; }}

QFrame#panel {{ background: rgba(10,22,48,0.92); border: 1px solid {LINE}; }}
QFrame#panel[tone="red"] {{ border-color: {RED}; }}
QFrame#panel[tone="gold"] {{ border-color: {GOLD}; }}
QLabel#panelTitle {{
  font-size: 15px; font-weight: 700; letter-spacing: 4px; color: white;
  border: 1px solid {GLOW}; padding: 6px 18px; background: rgba(77,225,255,0.06);
}}
QFrame#panel[tone="red"] QLabel#panelTitle {{ border-color: {RED}; color: {RED}; }}
QFrame#panel[tone="gold"] QLabel#panelTitle {{ border-color: {GOLD}; color: {GOLD}; }}

QLabel#muted {{ color: {MUTED}; }}
QLabel#lbl {{ color: {MUTED}; font-size: 13px; letter-spacing: 1px; }}
QLabel#big {{ font-size: 24px; font-weight: 700; color: white; }}
QLabel#warn {{ color: {RED}; font-weight: 600; }}
QLabel#ok {{ color: {GREEN}; font-weight: 600; }}
QLabel#gold {{ color: {GOLD}; font-weight: 700; }}
QLabel#countdown {{ color: {MUTED}; letter-spacing: 2px; }}

QPushButton {{
  background: rgba(42,127,255,0.15); border: 1px solid {LINE}; padding: 9px 16px;
  font-size: 15px; font-weight: 600; letter-spacing: 1px; color: white;
}}
QPushButton:hover {{ background: rgba(42,127,255,0.35); border-color: {GLOW}; }}
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

QLineEdit, QSpinBox, QComboBox {{
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

QDialog#sysDialog {{ background: transparent; }}
QFrame#sysBox {{ background: rgba(8,18,40,0.98); border: 2px solid {GLOW}; }}
QFrame#sysBox[tone="red"] {{ border-color: {RED}; }}
QFrame#sysBox[tone="gold"] {{ border-color: {GOLD}; }}
QLabel#sysTitle {{ font-size: 17px; font-weight: 700; letter-spacing: 4px; padding: 6px 16px; border: 1px solid {GLOW}; color: white; }}
QFrame#sysBox[tone="red"] QLabel#sysTitle {{ border-color: {RED}; color: {RED}; }}
QFrame#sysBox[tone="gold"] QLabel#sysTitle {{ border-color: {GOLD}; color: {GOLD}; }}
QLabel#sysBody {{ font-size: 16px; }}

QLabel#toast {{ background: rgba(8,18,40,0.97); border: 1px solid {GLOW}; padding: 9px 16px; font-weight: 600; }}
QLabel#toast[gold="true"] {{ border-color: {GOLD}; color: {GOLD}; }}
"""
