@echo off
chcp 65001 >nul
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw sts2_mod_maker.py
) else (
    python sts2_mod_maker.py
    if errorlevel 1 pause
)
