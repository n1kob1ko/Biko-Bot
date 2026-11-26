@echo off
REM Biko-Arbeiter starten: holt Code-Aufgaben von Biko-Chef und erledigt sie mit Claude Code (dein Abo).
cd /d "%~dp0"
set ANTHROPIC_API_KEY=
where py >nul 2>nul
if %errorlevel%==0 (py -3 biko_arbeiter.py) else (python biko_arbeiter.py)
pause
