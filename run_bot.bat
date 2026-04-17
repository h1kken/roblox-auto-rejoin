@echo off
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -O main_bot.py
) else (
    python -O main_bot.py
)

pause
