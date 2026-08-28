@echo off
setlocal EnableExtensions
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
for /f "delims=" %%P in ('where py.exe 2^>nul') do if not defined PYEXE set "PYLAUNCH=%%P"
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
  if not defined PYEXE if exist "%ProgramFiles%\Python312\python.exe" set "PYEXE=%ProgramFiles%\Python312\python.exe"
)
if not defined PYEXE goto :needpython

if "%AUTO_MODE%"=="0" echo Python: %PYEXE%
"%PYEXE%" -m py_compile radiko_proxy.py radiko_epg.py radiko_public_gateway.py
if errorlevel 1 (
  if "%AUTO_MODE%"=="1" exit /b 1
  echo Python syntax/import preparation failed.
  pause
  exit /b 1
)

rem Load locally saved radiko credentials. Password is DPAPI-encrypted for this Windows user.
if "%RADIKO_MAIL%"=="" if exist ".radiko_mail.txt" set /p RADIKO_MAIL=<.radiko_mail.txt
if "%RADIKO_PASSWORD%"=="" if exist ".radiko_password.dpapi" (
  for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$s=Get-Content -Raw '.radiko_password.dpapi'|ConvertTo-SecureString;$p=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($s);try{[Runtime.InteropServices.Marshal]::PtrToStringBSTR($p)}finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p)}"`) do set "RADIKO_PASSWORD=%%P"
)

if "%RADIKO_MAIL%"=="" (
  if "%AUTO_MODE%"=="1" exit /b 1
  echo.
  echo radiko Premium login is needed on this PC.
  set /p "RADIKO_MAIL=radiko mail address: "
)
if "%RADIKO_MAIL%"=="" (
  if "%AUTO_MODE%"=="1" exit /b 1
  echo No mail address entered.
  pause
  exit /b 1
)

if "%RADIKO_PASSWORD%"=="" (
  if "%AUTO_MODE%"=="1" exit /b 1
  for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$s=Read-Host 'radiko Premium password' -AsSecureString;$p=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($s);try{[Runtime.InteropServices.Marshal]::PtrToStringBSTR($p)}finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p)}"`) do set "RADIKO_PASSWORD=%%P"
)
if "%RADIKO_PASSWORD%"=="" (
  if "%AUTO_MODE%"=="1" exit /b 1
  echo No password entered.
  pause
  exit /b 1
)

if not exist ".radiko_mail.txt" >.radiko_mail.txt echo %RADIKO_MAIL%
if not exist ".radiko_password.dpapi" powershell -NoProfile -Command "$s=ConvertTo-SecureString $env:RADIKO_PASSWORD -AsPlainText -Force;$s|ConvertFrom-SecureString|Set-Content -Encoding ascii '.radiko_password.dpapi'"

rem Old URL-key files are no longer used. GitHub FreeWiFi remains the only playlist URL.
del /a /q .radiko_access_key radiko_public_urls.txt >nul 2>&1

set RADIKO_PROXY_HOST=127.0.0.1
set RADIKO_PROXY_PORT=9395
set RADIKO_GATEWAY_HOST=127.0.0.1
set RADIKO_GATEWAY_PORT=9396
set RADIKO_PUBLIC_NO_KEY=1

powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:9395/health | Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if errorlevel 1 (
  del /q .radiko_proxy.out.log .radiko_proxy.err.log >nul 2>&1
  powershell -NoProfile -Command "Start-Process -WindowStyle Hidden -FilePath $env:PYEXE -ArgumentList @('-u','radiko_proxy.py') -WorkingDirectory (Get-Location).Path -RedirectStandardOutput '.radiko_proxy.out.log' -RedirectStandardError '.radiko_proxy.err.log'"
)

for /l %%N in (1,1,30) do (
  powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:9395/health | Out-Null; exit 0}catch{exit 1}" >nul 2>&1 && goto :proxyready
  timeout /t 1 /nobreak >nul
)
if "%AUTO_MODE%"=="1" exit /b 1
echo.
echo radiko proxy did not start. Error log:
if exist .radiko_proxy.err.log type .radiko_proxy.err.log
if exist .radiko_proxy.out.log type .radiko_proxy.out.log
pause
exit /b 1

:proxyready
rem Always restart the gateway so a previously key-protected process is replaced by public-restricted mode.
powershell -NoProfile -Command "$x=Get-NetTCPConnection -LocalPort 9396 -State Listen -ErrorAction SilentlyContinue|Select-Object -ExpandProperty OwningProcess -Unique;foreach($p in $x){Stop-Process -Id $p -Force -ErrorAction SilentlyContinue}" >nul 2>&1
timeout /t 1 /nobreak >nul
del /q .radiko_gateway.out.log .radiko_gateway.err.log >nul 2>&1
powershell -NoProfile -Command "Start-Process -WindowStyle Hidden -FilePath $env:PYEXE -ArgumentList @('-u','radiko_public_gateway.py') -WorkingDirectory (Get-Location).Path -RedirectStandardOutput '.radiko_gateway.out.log' -RedirectStandardError '.radiko_gateway.err.log'"

for /l %%N in (1,1,30) do (
  powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:9396/health | Out-Null; exit 0}catch{exit 1}" >nul 2>&1 && goto :gatewayready
  timeout /t 1 /nobreak >nul
)
if "%AUTO_MODE%"=="1" exit /b 1
echo.
echo radiko public gateway did not start. Error log:
if exist .radiko_gateway.err.log type .radiko_gateway.err.log
if exist .radiko_gateway.out.log type .radiko_gateway.out.log
pause
exit /b 1

:gatewayready
"%TS%" funnel --bg --yes 9396 >nul
if errorlevel 1 (
  if "%AUTO_MODE%"=="1" exit /b 1
  echo.
  echo Funnel needs approval. Complete the browser approval and run this file again.
  pause
  exit /b 1
)

rem Install an automatic restart at Windows logon after the first successful manual run.
if "%AUTO_MODE%"=="0" (
  set "RADIKO_BAT=%~f0"
  powershell -NoProfile -Command "$a=New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/c ""'+$env:RADIKO_BAT+'" /auto"');$t=New-ScheduledTaskTrigger -AtLogOn;Register-ScheduledTask -TaskName 'Radiko Public IPTV' -Action $a -Trigger $t -RunLevel Highest -Force|Out-Null" >nul 2>&1
)

if "%AUTO_MODE%"=="1" exit /b 0

echo.
echo ============================================================
echo radiko public gateway is ready.
echo Public host : https://%TSDNS%
echo IPTV playlist URL stays unchanged:
echo https://raw.githubusercontent.com/ajiousama/himitsu/main/freewifi
echo Windows logon auto-start was registered.
echo ============================================================
echo.
pause
exit /b 0

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
