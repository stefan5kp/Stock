@echo off
cd /d "%~dp0"
set "PY=C:\ProgramData\anaconda3\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" server.py
pause
