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
  echo Finish the browser login, then press any key.
  pause >nul
)

for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$j=(& '%TS%' status --json | ConvertFrom-Json);if($j.Self.DNSName){$j.Self.DNSName.TrimEnd('.')}"`) do set "TSDNS=%%I"
if "%TSDNS%"=="" goto :needtailscale

set "PYEXE="
for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined PYEXE set "PYEXE=%%P"
if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python313\python.exe"
if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PYEXE (
  if "%AUTO_MODE%"=="1" exit /b 1
  where winget >nul 2>&1 || goto :needpython
  winget install --id Python.Python.3.12 -e --silent --scope user --accept-package-agreements --accept-source-agreements
  if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe"
)
if not defined PYEXE goto :needpython

"%PYEXE%" -m py_compile radiko_proxy_core.py radiko_epg.py radiko_public_front.py radiko_public_selftest.py
if errorlevel 1 goto :syntaxfail

rem Load saved Premium credentials. Password is stored with Windows DPAPI.
if "%RADIKO_MAIL%"=="" if exist ".radiko_mail.txt" set /p RADIKO_MAIL=<.radiko_mail.txt
if "%RADIKO_PASSWORD%"=="" if exist ".radiko_password.dpapi" (
  for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$s=Get-Content -Raw '.radiko_password.dpapi'|ConvertTo-SecureString;$p=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($s);try{[Runtime.InteropServices.Marshal]::PtrToStringBSTR($p)}finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p)}"`) do set "RADIKO_PASSWORD=%%P"
)
if "%RADIKO_MAIL%"=="" if "%AUTO_MODE%"=="0" set /p "RADIKO_MAIL=radiko Premium mail: "
if "%RADIKO_MAIL%"=="" goto :needpremium
if "%RADIKO_PASSWORD%"=="" if "%AUTO_MODE%"=="0" (
  for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$s=Read-Host 'radiko Premium password' -AsSecureString;$p=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($s);try{[Runtime.InteropServices.Marshal]::PtrToStringBSTR($p)}finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p)}"`) do set "RADIKO_PASSWORD=%%P"
)
if "%RADIKO_PASSWORD%"=="" goto :needpremium

>.radiko_mail.txt echo %RADIKO_MAIL%
powershell -NoProfile -Command "$s=ConvertTo-SecureString $env:RADIKO_PASSWORD -AsPlainText -Force;$s|ConvertFrom-SecureString|Set-Content -Encoding ascii '.radiko_password.dpapi'"
if not exist ".radiko_signing_secret" powershell -NoProfile -Command "(([guid]::NewGuid().ToString('N'))+([guid]::NewGuid().ToString('N')))|Set-Content -NoNewline -Encoding ascii '.radiko_signing_secret'"
set /p RADIKO_SIGNING_SECRET=<.radiko_signing_secret

set RADIKO_PROXY_HOST=127.0.0.1
set RADIKO_PROXY_PORT=9395
set RADIKO_FRONT_HOST=127.0.0.1
set RADIKO_FRONT_PORT=9396
set RADIKO_FRONT_UPSTREAM=http://127.0.0.1:9395
set RADIKO_PUBLIC_HOST=%TSDNS%

rem Stop stale listeners, then start the private Premium core and HTTPS-aware public front.
powershell -NoProfile -Command "$ports=9395,9396;foreach($port in $ports){$owners=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue|Select-Object -ExpandProperty OwningProcess -Unique;foreach($procId in $owners){Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue}}" >nul 2>&1
timeout /t 1 /nobreak >nul
del /q .radiko_proxy.out.log .radiko_proxy.err.log .radiko_front.out.log .radiko_front.err.log .radiko_ready.txt .radiko_ready_code.txt >nul 2>&1
set "PYEXE_ENV=%PYEXE%"
powershell -NoProfile -Command "Start-Process -WindowStyle Hidden -FilePath $env:PYEXE_ENV -ArgumentList @('-u','radiko_proxy_core.py') -WorkingDirectory (Get-Location).Path -RedirectStandardOutput '.radiko_proxy.out.log' -RedirectStandardError '.radiko_proxy.err.log'"

for /l %%N in (1,1,30) do (
  curl.exe -fsS --max-time 2 http://127.0.0.1:9395/health >nul 2>&1 && goto :corehealth
  timeout /t 1 /nobreak >nul
)
goto :proxyfail

:corehealth
curl.exe -sS --max-time 90 -o .radiko_ready.txt -w "%%{http_code}" http://127.0.0.1:9395/ready >.radiko_ready_code.txt
set "READYCODE="
set /p READYCODE=<.radiko_ready_code.txt
if not "%READYCODE%"=="200" goto :proxyfail

powershell -NoProfile -Command "Start-Process -WindowStyle Hidden -FilePath $env:PYEXE_ENV -ArgumentList @('-u','radiko_public_front.py') -WorkingDirectory (Get-Location).Path -RedirectStandardOutput '.radiko_front.out.log' -RedirectStandardError '.radiko_front.err.log'"
for /l %%N in (1,1,30) do (
  curl.exe -fsS --max-time 2 http://127.0.0.1:9396/health >nul 2>&1 && goto :fronthealth
  timeout /t 1 /nobreak >nul
)
goto :frontfail

:fronthealth
rem Funnel exposes only the public front. The private Radiko core stays on localhost:9395.
"%TS%" funnel --bg --yes 9396 >nul
if errorlevel 1 goto :funnelfail
timeout /t 3 /nobreak >nul

curl.exe -fsS --max-time 90 "https://%TSDNS%/ready" >nul 2>&1
if errorlevel 1 goto :publicfail

rem End-to-end test: follow public HLS playlists until real audio bytes are downloaded.
"%PYEXE%" radiko_public_selftest.py "https://%TSDNS%/live/KBS" >.radiko_public_test.txt 2>&1
if errorlevel 1 "%PYEXE%" radiko_public_selftest.py "https://%TSDNS%/live/RNB" >.radiko_public_test.txt 2>&1
if errorlevel 1 goto :audiofail

if "%AUTO_MODE%"=="0" (
  set "RADIKO_BAT=%~f0"
  powershell -NoProfile -Command "$a=New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/c ""'+$env:RADIKO_BAT+'" /auto"');$t=New-ScheduledTaskTrigger -AtLogOn;Register-ScheduledTask -TaskName 'Radiko Public IPTV' -Action $a -Trigger $t -RunLevel Highest -Force|Out-Null" >nul 2>&1
)
if "%AUTO_MODE%"=="1" exit /b 0

echo.
echo ============================================================
echo Radiko Premium gateway: READY - PUBLIC AUDIO VERIFIED
echo Public base: https://%TSDNS%
echo FreeWiFi: https://raw.githubusercontent.com/ajiousama/himitsu/main/freewifi
echo EPG: https://raw.githubusercontent.com/ajiousama/himitsu/main/guides.xml
echo KBS/RNB public HLS audio test passed.
echo ============================================================
type .radiko_ready.txt
if exist .radiko_public_test.txt type .radiko_public_test.txt
echo.
pause
exit /b 0

:proxyfail
if "%AUTO_MODE%"=="1" exit /b 1
echo.
echo Radiko local gateway failed.
if exist .radiko_ready.txt type .radiko_ready.txt
if exist .radiko_proxy.err.log type .radiko_proxy.err.log
if exist .radiko_proxy.out.log type .radiko_proxy.out.log
pause
exit /b 1

:frontfail
if "%AUTO_MODE%"=="1" exit /b 1
echo.
echo Radiko public HTTPS front failed.
if exist .radiko_front.err.log type .radiko_front.err.log
if exist .radiko_front.out.log type .radiko_front.out.log
pause
exit /b 1

:funnelfail
if "%AUTO_MODE%"=="1" exit /b 1
echo Tailscale Funnel could not be enabled for port 9396.
pause
exit /b 1

:publicfail
if "%AUTO_MODE%"=="1" exit /b 1
echo Local Radiko is ready, but the public Tailscale URL failed.
echo Public URL: https://%TSDNS%/ready
if exist .radiko_front.err.log type .radiko_front.err.log
pause
exit /b 1

:audiofail
if "%AUTO_MODE%"=="1" exit /b 1
echo Public URL is reachable, but actual Radiko audio bytes could not be downloaded.
if exist .radiko_public_test.txt type .radiko_public_test.txt
if exist .radiko_proxy.err.log type .radiko_proxy.err.log
if exist .radiko_front.err.log type .radiko_front.err.log
pause
exit /b 1

:needpremium
if "%AUTO_MODE%"=="1" exit /b 1
echo Radiko Premium mail/password are required.
pause
exit /b 1

:syntaxfail
if "%AUTO_MODE%"=="1" exit /b 1
echo Python syntax check failed.
pause
exit /b 1

:needpython
if "%AUTO_MODE%"=="1" exit /b 1
echo Python 3.12 or newer is required.
pause
exit /b 1

:needtailscale
if "%AUTO_MODE%"=="1" exit /b 1
echo Tailscale is required for the public FreeWiFi Radiko gateway.
pause
exit /b 1
