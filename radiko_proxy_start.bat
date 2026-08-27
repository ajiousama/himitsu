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

set RADIKO_PROXY_HOST=127.0.0.1
set RADIKO_PROXY_PORT=9395

echo Starting radiko Premium IPTV proxy...
echo VLC playlist: http://127.0.0.1:9395/playlist.m3u
python radiko_proxy.py

pause
