@echo off
REM Ejecuta Arise Trainer desde el codigo (sin compilar). La primera vez instala lo necesario.
cd /d "%~dp0"
if not exist .venv (
  py -3.12 -m venv .venv || python -m venv .venv
  call .venv\Scripts\activate
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate
)
start "" pythonw main.py
