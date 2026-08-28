@echo off
setlocal EnableExtensions
cd /d %~dp0

echo ========================================
echo Radiko SIMPLE mode
echo No Tailscale / Funnel / public gateway
echo ========================================
echo.

set "PYEXE="
for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined PYEXE set "PYEXE=%%P"
if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python313\python.exe"
if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PYEXE (
  echo Python was not found.
  pause
  exit /b 1
)

set "BASE=https://raw.githubusercontent.com/ajiousama/himitsu/main"
set "BUST=%RANDOM%%RANDOM%%RANDOM%"

echo Getting latest simple runner...
curl.exe -fsSL -H "Cache-Control: no-cache" -o "radiko_simple.py" "%BASE%/radiko_simple.py?v=%BUST%"
if errorlevel 1 goto :downloadfail
curl.exe -fsSL -H "Cache-Control: no-cache" -o "radiko_proxy_core.py" "%BASE%/radiko_proxy_core.py?v=%BUST%"
if errorlevel 1 goto :downloadfail

echo Starting minimal Radiko test on port 9495...
echo.
set RADIKO_PROXY_HOST=127.0.0.1
set RADIKO_PROXY_PORT=9495
"%PYEXE%" -u radiko_simple.py
exit /b %errorlevel%

:downloadfail
echo Failed to download the latest Radiko files from GitHub.
pause
exit /b 1
