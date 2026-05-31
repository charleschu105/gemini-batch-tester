@echo off
title Gemini Image Batch Tester
echo ===================================================
echo [System] Starting Gemini Image Batch Tester...
echo ===================================================
echo.

:: Change working directory to the directory of this batch file
cd /d "%~dp0"

:: Test if python is installed and dependencies are met
python -c "import customtkinter, google.genai, PIL" >nul 2>&1
if %errorlevel% neq 0 (
    echo [System] Dependencies (customtkinter, etc.) are missing or Python is not set up!
    echo [System] Running installation script first...
    echo.
    call install.bat
    
    :: Re-check after installation
    python -c "import customtkinter, google.genai, PIL" >nul 2>&1
    if %errorlevel% neq 0 (
        echo [Error] Dependencies are still missing. Launch aborted.
        pause
        exit /b 1
    )
)

:: Start the Python application
python main.py

:: Pause if an error occurs to let the user see the traceback
if %errorlevel% neq 0 (
    echo.
    echo [Error] Application terminated unexpectedly.
    echo.
    pause
)
