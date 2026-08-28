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

powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:9395/health ^| Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if errorlevel 1 start "radiko proxy" /min cmd /c "python radiko_proxy.py"

for /l %%N in (1,1,30) do (
  powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:9395/health ^| Out-Null; exit 0}catch{exit 1}" >nul 2>&1 && goto :proxyready
  timeout /t 1 /nobreak >nul
)
echo radiko proxy did not start.
pause
exit /b 1

:proxyready
powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:9396/health ^| Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if errorlevel 1 start "radiko public gateway" /min cmd /c "set RADIKO_ACCESS_KEY=%RADIKO_ACCESS_KEY%&& python radiko_public_gateway.py"

for /l %%N in (1,1,30) do (
  powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:9396/health ^| Out-Null; exit 0}catch{exit 1}" >nul 2>&1 && goto :gatewayready
  timeout /t 1 /nobreak >nul
)
echo radiko public gateway did not start.
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

echo.
echo ============================================================
echo radiko public IPTV is ready.
echo Stable host : https://%TSDNS%
echo FreeWiFi    : https://%TSDNS%/freewifi.m3u?k=%RADIKO_ACCESS_KEY%
echo radiko only : https://%TSDNS%/playlist.m3u?k=%RADIKO_ACCESS_KEY%
echo EPG         : https://%TSDNS%/epg.xml?k=%RADIKO_ACCESS_KEY%
echo ============================================================
echo.
echo Keep .radiko_access_key private. Do not commit or share it.
pause
exit /b 0

:needtailscale
echo.
echo Tailscale could not be installed automatically.
echo Install Tailscale for Windows, sign in, then run this file again.
pause
exit /b 1
