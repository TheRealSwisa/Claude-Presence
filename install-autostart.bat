@echo off
REM Drops a shortcut to run.bat into your Windows Startup folder so the
REM presence daemon launches silently when you log in.
REM
REM To undo: delete the shortcut from shell:startup (Win+R -> shell:startup).

set TARGET=%~dp0run.bat
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set LINK=%STARTUP%\claude-presence.lnk

powershell -NoProfile -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%LINK%');" ^
  "$s.TargetPath = '%TARGET%';" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "$s.WindowStyle = 7;" ^
  "$s.Save()"

if exist "%LINK%" (
    echo installed: %LINK%
    echo claude-presence will now start when you log in.
) else (
    echo failed to create shortcut
    exit /b 1
)
