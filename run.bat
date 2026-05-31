@echo off
title Gemini Image Batch Tester
echo ===================================================
echo [System] Starting Gemini Image Batch Tester...
echo ===================================================
echo.

:: Change working directory to the directory of this batch file
cd /d "%~dp0"

:: Start the Python application
python main.py

:: Pause if an error occurs to let the user see the traceback
if %errorlevel% neq 0 (
    echo.
    echo [Error] Application terminated unexpectedly. Please verify:
    echo 1. Python 3.9+ is installed and added to your system PATH.
    echo 2. Dependencies are installed by running: pip install -r requirements.txt
    echo.
    pause
)
