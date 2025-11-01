@echo off
echo [pre-push] running preflight?
".\.venv\Scripts\python.exe" preflight.py
if errorlevel 1 exit /b 1