@echo off
title Gemini Image Batch Tester
echo ===================================================
echo [System] Starting Gemini Image Batch Tester...
echo ===================================================
echo.

cd /d "%~dp0"

:: Test if python is installed and dependencies are met
python -c "import customtkinter, google.genai, PIL" >nul 2>&1
if %errorlevel% equ 0 goto start_app

echo [System] Dependencies (customtkinter, etc.) are missing or Python is not set up!
echo [System] Running installation script first...
echo.
call install.bat

:: Recheck after running install.bat
python -c "import customtkinter, google.genai, PIL" >nul 2>&1
if %errorlevel% equ 0 goto start_app

echo [Error] Dependencies are still missing. Launch aborted.
pause
exit /b 1

:start_app
python main.py
if %errorlevel% neq 0 (
    echo.
    echo [Error] Application terminated unexpectedly.
    echo.
    pause
)
