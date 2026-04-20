@echo off
REM Kills the running presence daemon. Handles both the copied
REM claude-presence.exe launcher and plain pythonw.exe fallback.

taskkill /F /IM claude-presence.exe >nul 2>&1
if %ERRORLEVEL%==0 (
    echo stopped claude-presence.exe
    goto :end
)

REM Fallback: find any pythonw.exe running vibe.py
for /f "tokens=2" %%p in ('wmic process where "name='pythonw.exe' and CommandLine like '%%vibe.py%%'" get ProcessId /format:table ^| findstr [0-9]') do (
    taskkill /F /PID %%p >nul 2>&1
    echo stopped pythonw pid %%p
    set KILLED=1
)

if not defined KILLED echo no presence daemon running

:end
