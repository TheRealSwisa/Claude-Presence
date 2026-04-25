@echo off
cd /d "%~dp0"

if exist "%~dp0claude-presence.exe" (
    start "" "%~dp0claude-presence.exe" vibe.py
    exit /b 0
)

where pythonw >nul 2>&1
if %ERRORLEVEL%==0 (
    start "" pythonw vibe.py
    exit /b 0
)

echo cannot find pythonw.exe. install python from python.org.
exit /b 1
