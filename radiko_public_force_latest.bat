@echo off
setlocal EnableExtensions
cd /d %~dp0

echo Forcing newest Radiko runtime from GitHub...
set "BASE=https://raw.githubusercontent.com/ajiousama/himitsu/main"
set "BUST=%RANDOM%%RANDOM%%RANDOM%"

curl.exe -fL -H "Cache-Control: no-cache" -H "Pragma: no-cache" --retry 3 --connect-timeout 10 --max-time 45 -o "radiko_proxy.py.tmp" "%BASE%/radiko_proxy.py?v=%BUST%"
if errorlevel 1 goto :fail
curl.exe -fL -H "Cache-Control: no-cache" -H "Pragma: no-cache" --retry 3 --connect-timeout 10 --max-time 45 -o "radiko_proxy_core.py.tmp" "%BASE%/radiko_proxy_core.py?v=%BUST%"
if errorlevel 1 goto :fail
curl.exe -fL -H "Cache-Control: no-cache" -H "Pragma: no-cache" --retry 3 --connect-timeout 10 --max-time 45 -o "radiko_public_start.bat.tmp" "%BASE%/radiko_public_start.bat?v=%BUST%"
if errorlevel 1 goto :fail

move /y "radiko_proxy.py.tmp" "radiko_proxy.py" >nul
move /y "radiko_proxy_core.py.tmp" "radiko_proxy_core.py" >nul
move /y "radiko_public_start.bat.tmp" "radiko_public_start.bat" >nul

echo Force update: OK
findstr /c:"launcher build" radiko_proxy.py
findstr /c:"BUILD='" radiko_proxy_core.py
call "radiko_public_start.bat"
exit /b %errorlevel%

:fail
echo.
echo Force update failed.
del /q "radiko_proxy.py.tmp" "radiko_proxy_core.py.tmp" "radiko_public_start.bat.tmp" >nul 2>&1
pause
exit /b 1
