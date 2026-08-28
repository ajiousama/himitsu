@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d %~dp0
set "AUTO_MODE=0"
if /i "%~1"=="/auto" set "AUTO_MODE=1"

fltmc >nul 2>&1
if errorlevel 1 (
  if "%AUTO_MODE%"=="1" exit /b 1
  echo Re-opening as Administrator...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '/elevated' -Verb RunAs"
  exit /b
)
if /i "%~1"=="/elevated" set "AUTO_MODE=0"

set "TS=%ProgramFiles%\Tailscale\tailscale.exe"
if not exist "%TS%" (
  if "%AUTO_MODE%"=="1" exit /b 1
  echo Tailscale is not installed. Installing...
  where winget >nul 2>&1 || goto :needtailscale
  winget install --id Tailscale.Tailscale -e --silent --accept-package-agreements --accept-source-agreements
)
if not exist "%TS%" goto :needtailscale

"%TS%" status >nul 2>&1
if errorlevel 1 (
  if "%AUTO_MODE%"=="1" exit /b 1
  echo Tailscale login is required.
  "%TS%" up
  echo.
  echo Finish the browser login, then press any key.
  pause >nul
)

for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$j=(& '%TS%' status --json | ConvertFrom-Json); if($j.Self.DNSName){$j.Self.DNSName.TrimEnd('.')}"`) do set "TSDNS=%%I"
if "%TSDNS%"=="" (
  if "%AUTO_MODE%"=="1" exit /b 1
  echo Could not determine the stable Tailscale hostname.
  pause
  exit /b 1
)

set "PYEXE="
set "PYLAUNCH="
for /f "delims=" %%P in ('where py.exe 2^>nul') do if not defined PYLAUNCH set "PYLAUNCH=%%P"
if defined PYLAUNCH (
  for /f "usebackq delims=" %%P in (`"%PYLAUNCH%" -3 -c "import sys;print(sys.executable)" 2^>nul`) do if not defined PYEXE set "PYEXE=%%P"
)
if not defined PYEXE for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined PYEXE set "PYEXE=%%P"
if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python313\python.exe"
if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PYEXE if exist "%ProgramFiles%\Python313\python.exe" set "PYEXE=%ProgramFiles%\Python313\python.exe"
if not defined PYEXE if exist "%ProgramFiles%\Python312\python.exe" set "PYEXE=%ProgramFiles%\Python312\python.exe"
if not defined PYEXE (
  if "%AUTO_MODE%"=="1" exit /b 1
  echo Python was not found. Installing Python 3.12...
  where winget >nul 2>&1 || goto :needpython
  winget install --id Python.Python.3.12 -e --silent --scope user --accept-package-agreements --accept-source-agreements
  if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe"
  if not defined PYEXE if exist "%ProgramFiles%\Python312\python.exe" set "PYEXE=%ProgramFiles%\Python\Python312\python.exe"
)
if not defined PYEXE goto :needpython

if "%AUTO_MODE%"=="0" echo Python: %PYEXE%

rem Runtime self-update is handled inside radiko_proxy.py now. Avoid PowerShell web-download commands because Defender flags that pattern.
"%PYEXE%" -m py_compile radiko_proxy.py radiko_epg.py radiko_public_gateway.py radiko_selftest.py
if errorlevel 1 (
  if "%AUTO_MODE%"=="1" exit /b 1
  echo Python syntax/import preparation failed.
  pause
  exit /b 1
)

rem Load saved Radiko credentials when available. Premium enables the full 110-station list.
if "%RADIKO_MAIL%"=="" if exist ".radiko_mail.txt" set /p RADIKO_MAIL=<.radiko_mail.txt
if "%RADIKO_PASSWORD%"=="" if exist ".radiko_password.dpapi" (
  for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$s=Get-Content -Raw '.radiko_password.dpapi'|ConvertTo-SecureString;$p=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($s);try{[Runtime.InteropServices.Marshal]::PtrToStringBSTR($p)}finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p)}"`) do set "RADIKO_PASSWORD=%%P"
)
if "%RADIKO_MAIL%"=="" if "%AUTO_MODE%"=="0" (
  echo.
  echo Enter Radiko Premium login for all stations.
  echo Or press Enter for local-area Radiko only.
  set /p "RADIKO_MAIL=radiko mail address: "
)
if not "%RADIKO_MAIL%"=="" if "%RADIKO_PASSWORD%"=="" if "%AUTO_MODE%"=="0" (
  for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$s=Read-Host 'radiko Premium password' -AsSecureString;$p=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($s);try{[Runtime.InteropServices.Marshal]::PtrToStringBSTR($p)}finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p)}"`) do set "RADIKO_PASSWORD=%%P"
)
if not "%RADIKO_MAIL%"=="" if not "%RADIKO_PASSWORD%"=="" (
  >.radiko_mail.txt echo %RADIKO_MAIL%
  powershell -NoProfile -Command "$s=ConvertTo-SecureString $env:RADIKO_PASSWORD -AsPlainText -Force;$s|ConvertFrom-SecureString|Set-Content -Encoding ascii '.radiko_password.dpapi'"
)

if not exist ".radiko_signing_secret" powershell -NoProfile -Command "(([guid]::NewGuid().ToString('N'))+([guid]::NewGuid().ToString('N')))|Set-Content -NoNewline -Encoding ascii '.radiko_signing_secret'"
set /p RADIKO_GATEWAY_SIGNING_SECRET=<.radiko_signing_secret
if "%RADIKO_GATEWAY_SIGNING_SECRET%"=="" (
  if "%AUTO_MODE%"=="1" exit /b 1
  echo Could not create local signing secret.
  pause
  exit /b 1
)

del /a /q .radiko_access_key radiko_public_urls.txt >nul 2>&1
set RADIKO_PROXY_HOST=127.0.0.1
set RADIKO_PROXY_PORT=9395
set RADIKO_GATEWAY_HOST=127.0.0.1
set RADIKO_GATEWAY_PORT=9396
set RADIKO_PUBLIC_NO_KEY=1

rem Stop stale listeners. Do NOT use $pid here: $PID is PowerShell's read-only automatic variable.
powershell -NoProfile -Command "$ports=9395,9396;foreach($port in $ports){$owners=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue|Select-Object -ExpandProperty OwningProcess -Unique;foreach($procId in $owners){Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue}}" >nul 2>&1
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command "$busy=Get-NetTCPConnection -LocalPort 9395,9396 -State Listen -ErrorAction SilentlyContinue;if($busy){exit 1}else{exit 0}" >nul 2>&1
if errorlevel 1 (
  if "%AUTO_MODE%"=="1" exit /b 1
  echo Could not stop the old Radiko listener on port 9395 or 9396.
  pause
  exit /b 1
)
if "%AUTO_MODE%"=="0" echo Old Radiko listeners stopped: OK

del /q .radiko_proxy.out.log .radiko_proxy.err.log .radiko_gateway.out.log .radiko_gateway.err.log .radiko_ready.txt .radiko_ready_code.txt >nul 2>&1
powershell -NoProfile -Command "Start-Process -WindowStyle Hidden -FilePath $env:PYEXE -ArgumentList @('-u','radiko_proxy.py') -WorkingDirectory (Get-Location).Path -RedirectStandardOutput '.radiko_proxy.out.log' -RedirectStandardError '.radiko_proxy.err.log'"

for /l %%N in (1,1,30) do (
  curl.exe -fsS --max-time 2 http://127.0.0.1:9395/health >nul 2>&1 && goto :proxyhealth
  timeout /t 1 /nobreak >nul
)
goto :proxyfail

:proxyhealth
for /l %%N in (1,1,3) do (
  curl.exe -sS --max-time 35 -o .radiko_ready.txt -w "%%{http_code}" http://127.0.0.1:9395/ready >.radiko_ready_code.txt 2>nul
  set "READYCODE="
  set /p READYCODE=<.radiko_ready_code.txt
  if "!READYCODE!"=="200" goto :authready
  timeout /t 2 /nobreak >nul
)
goto :proxyfail

:authready
"%PYEXE%" radiko_selftest.py "http://127.0.0.1:9395/live/RNB" >nul 2>&1
if errorlevel 1 "%PYEXE%" radiko_selftest.py "http://127.0.0.1:9395/live-auto" >nul 2>&1
if errorlevel 1 goto :livefail

powershell -NoProfile -Command "Start-Process -WindowStyle Hidden -FilePath $env:PYEXE -ArgumentList @('-u','radiko_public_gateway.py') -WorkingDirectory (Get-Location).Path -RedirectStandardOutput '.radiko_gateway.out.log' -RedirectStandardError '.radiko_gateway.err.log'"
for /l %%N in (1,1,30) do (
  curl.exe -fsS --max-time 2 http://127.0.0.1:9396/health >nul 2>&1 && goto :gatewayready
  timeout /t 1 /nobreak >nul
)
goto :gatewayfail

:gatewayready
"%TS%" funnel --bg --yes 9396 >nul
if errorlevel 1 (
  if "%AUTO_MODE%"=="1" exit /b 1
  echo.
  echo Funnel needs approval. Complete the browser approval and run this file again.
  pause
  exit /b 1
)

timeout /t 2 /nobreak >nul
"%PYEXE%" radiko_selftest.py "https://%TSDNS%/live/RNB" >nul 2>&1
if errorlevel 1 "%PYEXE%" radiko_selftest.py "https://%TSDNS%/live-auto" >nul 2>&1
if errorlevel 1 goto :publicfail

if "%AUTO_MODE%"=="0" (
  set "RADIKO_BAT=%~f0"
  powershell -NoProfile -Command "$a=New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/c ""'+$env:RADIKO_BAT+'" /auto"');$t=New-ScheduledTaskTrigger -AtLogOn;Register-ScheduledTask -TaskName 'Radiko Public IPTV' -Action $a -Trigger $t -RunLevel Highest -Force|Out-Null" >nul 2>&1
)
if "%AUTO_MODE%"=="1" exit /b 0

echo.
echo ============================================================
echo radiko AUDIO test OK - public gateway is ready.
echo IPTV playlist URL stays unchanged:
echo https://raw.githubusercontent.com/ajiousama/himitsu/main/freewifi
echo Windows logon auto-start was registered.
echo ============================================================
echo.
pause
exit /b 0

:proxyfail
if "%AUTO_MODE%"=="1" exit /b 1
echo.
echo Radiko authorization/proxy failed.
if exist .radiko_ready.txt (
  echo ----- /ready response -----
  type .radiko_ready.txt
  echo.
)
if exist .radiko_proxy.err.log (
  echo ----- proxy stderr -----
  type .radiko_proxy.err.log
)
if exist .radiko_proxy.out.log (
  echo ----- proxy log -----
  type .radiko_proxy.out.log
)
pause
exit /b 1

:livefail
if "%AUTO_MODE%"=="1" exit /b 1
echo.
echo Radiko authorization succeeded, but no live audio could be obtained.
if exist .radiko_proxy.err.log type .radiko_proxy.err.log
if exist .radiko_proxy.out.log type .radiko_proxy.out.log
pause
exit /b 1

:gatewayfail
if "%AUTO_MODE%"=="1" exit /b 1
echo.
echo radiko public gateway failed to start.
if exist .radiko_gateway.err.log type .radiko_gateway.err.log
if exist .radiko_gateway.out.log type .radiko_gateway.out.log
pause
exit /b 1

:publicfail
if "%AUTO_MODE%"=="1" exit /b 1
echo.
echo Local Radiko audio is OK, but the public Funnel audio test failed.
if exist .radiko_gateway.err.log type .radiko_gateway.err.log
if exist .radiko_gateway.out.log type .radiko_gateway.out.log
pause
exit /b 1

:needpython
if "%AUTO_MODE%"=="1" exit /b 1
echo.
echo Python 3 could not be found or installed automatically.
echo Install Python 3.12 for Windows, then run this file again.
pause
exit /b 1

:needtailscale
if "%AUTO_MODE%"=="1" exit /b 1
echo.
echo Tailscale could not be installed automatically.
echo Install Tailscale for Windows, sign in, then run this file again.
pause
exit /b 1
