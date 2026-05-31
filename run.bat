@echo off
title Gemini Image Batch Tester
echo ===================================================
echo [System] Starting Gemini Image Batch Tester...
echo ===================================================
echo.

cd /d "%~dp0"

python -c "import customtkinter, google.genai, PIL" >nul 2>&1
if %errorlevel% neq 0 (
    echo [System] Dependencies (customtkinter, etc.) are missing or Python is not set up!
    echo [System] Running installation script first...
    echo.
    call install.bat
    
    rem Re-check after installation
    python -c "import customtkinter, google.genai, PIL" >nul 2>&1
    if %errorlevel% neq 0 (
        echo [Error] Dependencies are still missing. Launch aborted.
        pause
        exit /b 1
    )
)

python main.py

if %errorlevel% neq 0 (
    echo.
    echo [Error] Application terminated unexpectedly.
    echo.
    pause
)
