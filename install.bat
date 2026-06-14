@echo off
title Ebook TTS - Installer
echo ============================================
echo        Ebook TTS Player - Installer
echo ============================================
echo.

:: Check for Python 3.12
py -3.12 --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.12 not found!
    echo Please install Python 3.12 from https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo [OK] Found Python 3.12
py -3.12 --version
echo.

:: Create venv if it doesn't exist
if exist venv (
    echo [INFO] Virtual environment already exists.
    echo        Delete the "venv" folder first if you want a fresh install.
    echo.
) else (
    echo [1/3] Creating virtual environment...
    py -3.12 -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
    echo.
)

:: Activate venv
call venv\Scripts\activate

:: Ensure pip is available (bootstrap if missing)
python -m ensurepip --upgrade >nul 2>&1

:: Upgrade pip
echo [2/3] Upgrading pip...
python -m pip install --upgrade pip
echo.

:: Install PyTorch with CUDA support (must come BEFORE requirements.txt)
echo [3/4] Installing PyTorch with CUDA 12.4 support...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
if errorlevel 1 (
    echo.
    echo [WARNING] CUDA PyTorch install failed. Falling back to CPU-only.
    pip install torch torchvision torchaudio
)
echo.

:: Install remaining requirements
echo [4/4] Installing dependencies (this may take a few minutes)...
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Some packages failed to install. Check the output above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo        Installation Complete!
echo ============================================
echo.
echo Run the app with:  run_gui.bat
echo.
pause
