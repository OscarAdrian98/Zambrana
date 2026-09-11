@echo off
setlocal
cd /d "%~dp0..\.."
if not exist ".venv\Scripts\python.exe" exit /b 1
rem Configure las variables de entorno antes de iniciar este script.
".venv\Scripts\python.exe" run_server.py
