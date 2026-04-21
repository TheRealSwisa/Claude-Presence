@echo off
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
    echo installed. starts on login now.
) else (
    echo something went wrong
    exit /b 1
)
