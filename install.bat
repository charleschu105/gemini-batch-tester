@echo off
title Install Dependencies - Gemini Image Batch Tester
echo ===================================================
echo [System] Installing Python dependencies...
echo ===================================================
echo.

cd /d "%~dp0"

:: Check if python command is available
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
    goto check_pip
)

:: If 'python' failed, try 'py' command
py --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=py
    goto check_pip
)

:: Both failed, Python is missing
echo [Error] Python is not installed or not in your system PATH!
echo.
echo Please follow these steps to install Python:
echo 1. Go to: https://www.python.org/downloads/
echo 2. Download and run the Python installer (Python 3.9 or higher).
echo 3. IMPORTANT: Make sure to check the option "Add python.exe to PATH" at the bottom of the installer window!
echo 4. After installation, close this command window and double-click "install.bat" again.
echo.
pause
exit /b 1

:check_pip
echo [System] Found Python. Checking pip...
%PYTHON_CMD% -m pip --version >nul 2>&1
if %errorlevel% equ 0 goto do_install

echo [Error] pip is not found!
echo Trying to bootstrap pip using python...
%PYTHON_CMD% -m ensurepip --default-pip
if %errorlevel% neq 0 (
    echo [Error] Could not bootstrap pip. Please reinstall Python and make sure pip is checked.
    pause
    exit /b 1
)

:do_install
echo [System] Executing: %PYTHON_CMD% -m pip install -r requirements.txt
%PYTHON_CMD% -m pip install -r requirements.txt
if %errorlevel% neq 0 goto install_failed

echo.
echo [Success] All dependencies installed successfully!
echo [Success] You can now close this window and double-click "run.bat" to start the application.
echo.
pause
exit /b 0

:install_failed
echo.
echo [Error] Installation failed. Please verify:
echo 1. You have a working internet connection.
echo 2. You have administrator permissions if required.
echo.
pause
exit /b 1
