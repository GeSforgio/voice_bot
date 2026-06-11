@echo off
chcp 65001 >nul 2>&1
title Pizdun Bot 2.0
cd /d "%~dp0"

set LOG_DIR=logs
set MAX_LOGS=20

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM Generate timestamp for log filename
set LOG_FILE=%LOG_DIR%\pizdun_%DATE:~-4%%DATE:~3,2%%DATE:~0,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%.log
REM Replace spaces (from time) with zeros
set LOG_FILE=%LOG_FILE: =0%

REM Clean old logs
if %MAX_LOGS% gtr 0 (
    for /f "skip=%MAX_LOGS% delims=" %%F in (
        'dir /b /o-d "%LOG_DIR%\pizdun_*.log" 2^>nul'
    ) do del "%LOG_DIR%\%%F" 2>nul
)

echo ==============================================
echo    PIZDUN 2.0  -  Discord Bot
echo ==============================================
echo   Host: %COMPUTERNAME%
echo   Date: %DATE% %TIME%
echo ----------------------------------------------
echo   Log: %LOG_FILE%
echo ==============================================
echo.

call .venv\Scripts\activate.bat

if errorlevel 1 (
    echo [!] FAILED to activate .venv!
    echo    Check that .venv\Scripts\activate.bat exists
    pause
    exit /b 1
)

echo [OK] Environment activated
echo Starting bot...
echo ----------------------------------------------
echo.

set PYTHONIOENCODING=utf-8
python main.py > "%LOG_FILE%" 2>&1

set EXIT_CODE=%ERRORLEVEL%

echo.
echo ----------------------------------------------

if %EXIT_CODE% equ 0 (
    echo [OK] Bot stopped normally
    echo Log: %LOG_FILE%
) else (
    echo [!] Bot crashed with code %EXIT_CODE%!
    echo.
    echo Last 15 lines of log:
    echo ----------------------------------------------
    powershell -Command "Get-Content '%LOG_FILE%' -Tail 15" 2>nul
    if errorlevel 1 type "%LOG_FILE%" 2>nul
    echo ----------------------------------------------
    echo Full log: %LOG_FILE%
)

echo.
pause
