@echo off
setlocal EnableExtensions EnableDelayedExpansion
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

echo Clearing stale Radiko listeners on ports 9395/9396...
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$ports=9395,9396; Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue ^| Where-Object { $ports -contains $_.LocalPort } ^| Select-Object -ExpandProperty OwningProcess -Unique"`) do (
  echo Killing PID %%P
  taskkill.exe /PID %%P /F /T >nul 2>&1
)

timeout /t 2 /nobreak >nul
set "LEFT="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$ports=9395,9396; Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue ^| Where-Object { $ports -contains $_.LocalPort } ^| Select-Object -ExpandProperty OwningProcess -Unique"`) do set "LEFT=%%P"
if defined LEFT (
  echo.
  echo ERROR: stale Radiko listener still owns port 9395/9396. PID=!LEFT!
  echo Trying one final force kill...
  taskkill.exe /PID !LEFT! /F /T
  timeout /t 2 /nobreak >nul
)

echo Starting Radiko public...
call "radiko_public_start.bat"
exit /b %errorlevel%

:fail
echo.
echo Force update failed.
del /q "radiko_proxy.py.tmp" "radiko_proxy_core.py.tmp" "radiko_public_start.bat.tmp" >nul 2>&1
pause
exit /b 1
