@echo off
setlocal

set DATA=%~dp0data
set STOP=%DATA%\stop

if not exist "%DATA%" mkdir "%DATA%" >nul 2>&1
type nul > "%STOP%" 2>nul

REM wait for daemon to clear and exit
for /l %%i in (1,1,15) do (
    if not exist "%STOP%" goto :done
    timeout /t 1 /nobreak >nul
)

REM nobody consumed the file - daemon must be dead. force kill anything left
del "%STOP%" >nul 2>&1

powershell -NoProfile -Command ^
  "$ids = @();" ^
  "$ids += (Get-Process -Name 'claude-presence' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id);" ^
  "$ids += (Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'vibe.py' } | Select-Object -ExpandProperty ProcessId);" ^
  "if ($ids) { $ids | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }; Write-Host 'force-stopped' } else { Write-Host 'not running' }"

goto :end

:done
echo stopped

:end
endlocal
