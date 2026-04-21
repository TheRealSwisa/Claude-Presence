@echo off
taskkill /F /IM claude-presence.exe >nul 2>&1
if %ERRORLEVEL%==0 (
    echo stopped
    goto :end
)

for /f "tokens=2" %%p in ('wmic process where "name='pythonw.exe' and CommandLine like '%%vibe.py%%'" get ProcessId /format:table ^| findstr [0-9]') do (
    taskkill /F /PID %%p >nul 2>&1
    echo stopped pythonw pid %%p
    set KILLED=1
)

if not defined KILLED echo not running

:end
