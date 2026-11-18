@echo off
REM Hace que ASCENSO (y el Guardian) arranquen solos al prender la compu.
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "APPDIR=%~dp0"
set "PYW="
where pyw >nul 2>nul && set "PYW=pyw"
if not defined PYW where pythonw >nul 2>nul && set "PYW=pythonw"
if not defined PYW (
  echo No se encontro Python. Instalalo desde https://www.python.org/downloads/
  pause
  exit /b 1
)
(
  echo @echo off
  echo cd /d "%APPDIR%"
  echo start "" %PYW% "%APPDIR%servidor.py" --sin-abrir
) > "%STARTUP%\ascenso_guardian.bat"
echo.
echo Listo. El Sistema va a arrancar solo cada vez que prendas la compu.
echo Para desactivarlo borra: "%STARTUP%\ascenso_guardian.bat"
start "" %PYW% "%APPDIR%servidor.py"
pause
