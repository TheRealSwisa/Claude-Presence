@echo off
setlocal

set REPO=%~dp0
if "%REPO:~-1%"=="\" set REPO=%REPO:~0,-1%

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$repo = '%REPO%';" ^
  "$q = [char]34;" ^
  "$local = Join-Path $repo 'claude-presence.exe';" ^
  "if (Test-Path $local) { $exe = $local } else {" ^
  "  $exe = (Get-Command pythonw -ErrorAction SilentlyContinue).Source;" ^
  "  if (-not $exe) {" ^
  "    $py = (Get-Command python -ErrorAction SilentlyContinue).Source;" ^
  "    if ($py) { $exe = $py -replace 'python\.exe$', 'pythonw.exe' }" ^
  "  }" ^
  "};" ^
  "if (-not $exe -or -not (Test-Path $exe)) {" ^
  "  Write-Host 'cannot find pythonw.exe. install python from python.org and tick add to PATH.';" ^
  "  exit 1" ^
  "};" ^
  "$lnk = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup\claude-presence.lnk';" ^
  "$vpath = Join-Path $repo 'vibe.py';" ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk);" ^
  "$s.TargetPath = $exe;" ^
  "$s.Arguments = $q + $vpath + $q;" ^
  "$s.WorkingDirectory = $repo;" ^
  "$s.WindowStyle = 7;" ^
  "$s.Save();" ^
  "if (Test-Path $lnk) { Write-Host 'installed. starts on login.' } else { Write-Host 'failed to create shortcut'; exit 1 }"

endlocal
