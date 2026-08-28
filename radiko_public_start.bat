@echo off
setlocal EnableExtensions
cd /d %~dp0

fltmc >nul 2>&1
if errorlevel 1 (
  echo Re-opening as Administrator...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

set "TS=%ProgramFiles%\Tailscale\tailscale.exe"
if not exist "%TS%" (
  echo Tailscale is not installed. Installing...
  where winget >nul 2>&1 || goto :needtailscale
  winget install --id Tailscale.Tailscale -e --silent --accept-package-agreements --accept-source-agreements
)
if not exist "%TS%" goto :needtailscale

"%TS%" status >nul 2>&1
if errorlevel 1 (
  echo Tailscale login is required.
  "%TS%" up
  echo.
  echo Finish the browser login, then press any key.
  pause >nul
)

for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$j=(& '%TS%' status --json | ConvertFrom-Json); if($j.Self.DNSName){$j.Self.DNSName.TrimEnd('.')}"`) do set "TSDNS=%%I"
if "%TSDNS%"=="" (
  echo Could not determine the stable Tailscale hostname.
  pause
  exit /b 1
)

rem Find a real Python executable. Windows Store aliases often make plain "python" unreliable.
set "PYEXE="
for /f "delims=" %%P in ('where py.exe 2^>nul') do if not defined PYEXE set "PYLAUNCH=%%P"
if defined PYLAUNCH (
  for /f "usebackq delims=" %%P in (`"%PYLAUNCH%" -3 -c "import sys;print(sys.executable)" 2^>nul`) do if not defined PYEXE set "PYEXE=%%P"
)
if not defined PYEXE for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined PYEXE set "PYEXE=%%P"
if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PYEXE if exist "%ProgramFiles%\Python312\python.exe" set "PYEXE=%ProgramFiles%\Python312\python.exe"

if not defined PYEXE (
  echo Python was not found. Installing Python 3.12...
  where winget >nul 2>&1 || goto :needpython
  winget install --id Python.Python.3.12 -e --silent --scope user --accept-package-agreements --accept-source-agreements
  if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe"
  if not defined PYEXE if exist "%ProgramFiles%\Python312\python.exe" set "PYEXE=%ProgramFiles%\Python312\python.exe"
)
if not defined PYEXE goto :needpython

echo Python: %PYEXE%
"%PYEXE%" -m py_compile radiko_proxy.py radiko_epg.py radiko_public_gateway.py
if errorlevel 1 (
  echo Python syntax/import preparation failed.
  pause
  exit /b 1
)

if not exist ".radiko_access_key" (
  powershell -NoProfile -Command "$a=[guid]::NewGuid().ToString('N');$b=[guid]::NewGuid().ToString('N');Set-Content -NoNewline -Encoding ascii '.radiko_access_key' ($a+$b)"
)
set /p RADIKO_ACCESS_KEY=<.radiko_access_key

if "%RADIKO_MAIL%"=="" (
  echo.
  echo radiko Premium login is needed on this PC.
  set /p "RADIKO_MAIL=radiko mail address: "
)
if "%RADIKO_MAIL%"=="" (
  echo No mail address entered.
  pause
  exit /b 1
)

if "%RADIKO_PASSWORD%"=="" (
  for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$s=Read-Host 'radiko Premium password' -AsSecureString;$p=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($s);try{[Runtime.InteropServices.Marshal]::PtrToStringBSTR($p)}finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p)}"`) do set "RADIKO_PASSWORD=%%P"
)
if "%RADIKO_PASSWORD%"=="" (
  echo No password entered.
  pause
  exit /b 1
)

set RADIKO_PROXY_HOST=127.0.0.1
set RADIKO_PROXY_PORT=9395
set RADIKO_GATEWAY_HOST=127.0.0.1
set RADIKO_GATEWAY_PORT=9396

powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:9395/health | Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if errorlevel 1 (
  del /q .radiko_proxy.out.log .radiko_proxy.err.log >nul 2>&1
  powershell -NoProfile -Command "Start-Process -WindowStyle Minimized -FilePath $env:PYEXE -ArgumentList @('-u','radiko_proxy.py') -WorkingDirectory (Get-Location).Path -RedirectStandardOutput '.radiko_proxy.out.log' -RedirectStandardError '.radiko_proxy.err.log'"
)

for /l %%N in (1,1,30) do (
  powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:9395/health | Out-Null; exit 0}catch{exit 1}" >nul 2>&1 && goto :proxyready
  timeout /t 1 /nobreak >nul
)
echo.
echo radiko proxy did not start. Error log:
if exist .radiko_proxy.err.log type .radiko_proxy.err.log
if exist .radiko_proxy.out.log type .radiko_proxy.out.log
pause
exit /b 1

:proxyready
powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:9396/health | Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if errorlevel 1 (
  del /q .radiko_gateway.out.log .radiko_gateway.err.log >nul 2>&1
  powershell -NoProfile -Command "Start-Process -WindowStyle Minimized -FilePath $env:PYEXE -ArgumentList @('-u','radiko_public_gateway.py') -WorkingDirectory (Get-Location).Path -RedirectStandardOutput '.radiko_gateway.out.log' -RedirectStandardError '.radiko_gateway.err.log'"
)

for /l %%N in (1,1,30) do (
  powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:9396/health | Out-Null; exit 0}catch{exit 1}" >nul 2>&1 && goto :gatewayready
  timeout /t 1 /nobreak >nul
)
echo.
echo radiko public gateway did not start. Error log:
if exist .radiko_gateway.err.log type .radiko_gateway.err.log
if exist .radiko_gateway.out.log type .radiko_gateway.out.log
pause
exit /b 1

:gatewayready
"%TS%" funnel --bg --yes 9396
if errorlevel 1 (
  echo.
  echo Funnel needs approval. Complete the browser approval and run this file again.
  pause
  exit /b 1
)

set "PUBLIC_BASE=https://%TSDNS%"
set "FREEWIFI_URL=%PUBLIC_BASE%/freewifi.m3u?k=%RADIKO_ACCESS_KEY%"
set "RADIKO_URL=%PUBLIC_BASE%/playlist.m3u?k=%RADIKO_ACCESS_KEY%"
set "EPG_URL=%PUBLIC_BASE%/epg.xml?k=%RADIKO_ACCESS_KEY%"

>radiko_public_urls.txt (
  echo FreeWiFi=%FREEWIFI_URL%
  echo radiko=%RADIKO_URL%
  echo EPG=%EPG_URL%
)

powershell -NoProfile -Command "Set-Clipboard -Value $env:FREEWIFI_URL" >nul 2>&1

echo.
echo ============================================================
echo radiko public IPTV is ready.
echo Stable host : %PUBLIC_BASE%
echo FreeWiFi URL was copied to the clipboard.
echo Full URLs are saved locally in: radiko_public_urls.txt
echo Access key is intentionally NOT shown on this screen.
echo ============================================================
echo.
echo Keep .radiko_access_key and radiko_public_urls.txt private.
pause
exit /b 0

:needpython
echo.
echo Python 3 could not be found or installed automatically.
echo Install Python 3.12 for Windows, then run this file again.
pause
exit /b 1

:needtailscale
echo.
echo Tailscale could not be installed automatically.
echo Install Tailscale for Windows, sign in, then run this file again.
pause
exit /b 1
