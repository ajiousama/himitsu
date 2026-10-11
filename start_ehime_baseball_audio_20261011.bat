@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
 echo Pythonが見つかりません。Python 3をインストールしてください。
 pause
 exit /b 1
)
where ffmpeg >nul 2>nul
if errorlevel 1 (
 echo FFmpegが見つかりません。FFmpegをPATHに登録してください。
 pause
 exit /b 1
)
echo.
echo 高校野球 左=NHK松山 R1 右=eat  映像=eat
echo NHKがFMに切り替わった場合は、この窓を閉じて引数 --fm で再起動してください。
echo.
echo 再生URL: http://127.0.0.1:8765/index.m3u8
echo.
python tools\ehime_baseball_dual_audio_20261011.py %*
pause
