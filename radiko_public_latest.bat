@echo off
setlocal EnableExtensions
cd /d %~dp0

echo Updating Radiko public runtime from GitHub...
set "BASE=https://raw.githubusercontent.com/ajiousama/himitsu/main"

curl.exe -fL --retry 3 --connect-timeout 10 --max-time 45 -o "radiko_proxy.py.tmp" "%BASE%/radiko_proxy.py"
if errorlevel 1 goto :updatefail
curl.exe -fL --retry 3 --connect-timeout 10 --max-time 45 -o "radiko_proxy_core.py.tmp" "%BASE%/radiko_proxy_core.py"
if errorlevel 1 goto :updatefail
curl.exe -fL --retry 3 --connect-timeout 10 --max-time 45 -o "radiko_public_start.bat.tmp" "%BASE%/radiko_public_start.bat"
if errorlevel 1 goto :updatefail

move /y "radiko_proxy.py.tmp" "radiko_proxy.py" >nul
move /y "radiko_proxy_core.py.tmp" "radiko_proxy_core.py" >nul
move /y "radiko_public_start.bat.tmp" "radiko_public_start.bat" >nul

echo Radiko runtime update: OK
call "radiko_public_start.bat"
exit /b %errorlevel%

:updatefail
echo.
echo Radiko runtime update failed.
del /q "radiko_proxy.py.tmp" "radiko_proxy_core.py.tmp" "radiko_public_start.bat.tmp" >nul 2>&1
pause
exit /b 1
