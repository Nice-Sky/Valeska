@echo off
REM Compila AriseTrainer.exe en tu propia compu (requiere Python 3.12 instalado).
cd /d "%~dp0"
py -3.12 -m venv .venv || python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller
pyinstaller arise.spec --noconfirm
echo.
echo Listo: dist\AriseTrainer\AriseTrainer.exe
pause
