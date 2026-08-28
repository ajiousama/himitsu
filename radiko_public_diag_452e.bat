@echo off
setlocal EnableExtensions
cd /d %~dp0
set "PIN=452e57cf490ecff2c8cd4c5d41d83caf6ba165f7"
set "BASE=https://raw.githubusercontent.com/ajiousama/himitsu/%PIN%"
echo Fetching pinned Radiko diagnostic runtime %PIN% ...
curl.exe -fL --retry 3 --connect-timeout 10 --max-time 45 -H "Cache-Control: no-cache" -o "radiko_proxy.py.tmp" "%BASE%/radiko_proxy.py"
if errorlevel 1 goto :fail
curl.exe -fL --retry 3 --connect-timeout 10 --max-time 45 -H "Cache-Control: no-cache" -o "radiko_proxy_core.py.tmp" "%BASE%/radiko_proxy_core.py"
if errorlevel 1 goto :fail
curl.exe -fL --retry 3 --connect-timeout 10 --max-time 45 -H "Cache-Control: no-cache" -o "radiko_public_start.bat.tmp" "%BASE%/radiko_public_start.bat"
if errorlevel 1 goto :fail
move /y "radiko_proxy.py.tmp" "radiko_proxy.py" >nul
move /y "radiko_proxy_core.py.tmp" "radiko_proxy_core.py" >nul
move /y "radiko_public_start.bat.tmp" "radiko_public_start.bat" >nul
echo Pinned diagnostic update: OK
call "radiko_public_start.bat"
exit /b %errorlevel%

:fail
echo.
echo Pinned diagnostic update failed.
del /q "radiko_proxy.py.tmp" "radiko_proxy_core.py.tmp" "radiko_public_start.bat.tmp" >nul 2>&1
pause
exit /b 1
