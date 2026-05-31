@echo off
title Install Dependencies - Gemini Image Batch Tester
echo ===================================================
echo [System] Installing Python dependencies...
echo ===================================================
echo.

:: Change working directory to the directory of this batch file
cd /d "%~dp0"

echo [System] Executing: pip install -r requirements.txt
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo [Error] Installation failed. Please verify:
    echo 1. Python and pip are installed and added to your system PATH.
    echo 2. You have an active internet connection.
    echo.
) else (
    echo.
    echo [Success] All dependencies installed successfully!
    echo [Success] You can now close this window and double-click "run.bat" to start the application.
    echo.
)

pause
