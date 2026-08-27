@echo off
setlocal
cd /d %~dp0

if "%RADIKO_MAIL%"=="" (
  echo RADIKO_MAIL is not set.
  echo Example: set RADIKO_MAIL=your_mail@example.com
  pause
  exit /b 1
)
if "%RADIKO_PASSWORD%"=="" (
  echo RADIKO_PASSWORD is not set.
  echo Example: set RADIKO_PASSWORD=your_password
  pause
  exit /b 1
)

set RADIKO_PROXY_HOST=0.0.0.0
set RADIKO_PROXY_PORT=9395

for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$x=(Get-NetIPAddress -AddressFamily IPv4 ^| ? {$_.IPAddress -notlike '169.254*' -and $_.IPAddress -ne '127.0.0.1' -and $_.InterfaceOperationalStatus -eq 'Up'} ^| sort InterfaceMetric ^| select -First 1 -ExpandProperty IPAddress); if($x){$x}else{'PC-LAN-IP'}"`) do set LANIP=%%I

echo Starting radiko Premium IPTV proxy for LAN...
echo.
echo PC only : http://127.0.0.1:9395/playlist.m3u
echo iPhone/TV radiko : http://%LANIP%:9395/playlist.m3u
echo iPhone/TV FreeWiFi: http://%LANIP%:9395/freewifi.m3u
echo EPG : http://%LANIP%:9395/epg.xml
echo.
echo If Windows Firewall asks, allow Python on Private networks.
echo.
python radiko_proxy.py

pause
