@echo off
echo Pre-push: running preflight?
".\.venv\Scripts\python.exe" tools\preflight.py
if errorlevel 1 exit /b 1