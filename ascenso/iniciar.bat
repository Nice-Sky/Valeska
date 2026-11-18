@echo off
cd /d "%~dp0"
where py >nul 2>nul && (py servidor.py & goto :eof)
where python >nul 2>nul && (python servidor.py & goto :eof)
echo No se encontro Python. Instalalo desde https://www.python.org/downloads/ (marca "Add Python to PATH").
pause
