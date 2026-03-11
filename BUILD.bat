@echo off
:: ============================================================================
:: BUILD.bat
:: ============================================================================
:: One-click build script for TradingAssistant Windows installer.
::
:: What it does:
::   1. Checks Python and pip are available
::   2. Installs / upgrades PyInstaller
::   3. Runs PyInstaller with trading_assistant.spec
::   4. Runs NSIS to produce the final Setup.exe
::
:: Usage:
::   Double-click BUILD.bat   — or run from Command Prompt / PowerShell
::
:: Output:
::   scripts\TradingAssistant_Setup_1.0.0.exe
:: ============================================================================

setlocal EnableDelayedExpansion
cd /d "%~dp0"   & :: change to folder containing this .bat file

set APP_NAME=TradingAssistant
set APP_VERSION=1.0.0
set SPEC_FILE=trading_assistant.spec
set NSI_FILE=scripts\build_installer.nsi
set DIST_DIR=dist\%APP_NAME%
set OUTPUT_EXE=scripts\%APP_NAME%_Setup_%APP_VERSION%.exe

:: ── NSIS detection ───────────────────────────────────────────────────────────
set NSIS_PATH=C:\Program Files (x86)\NSIS\makensis.exe
if not exist "%NSIS_PATH%" (
    set NSIS_PATH=C:\Program Files\NSIS\makensis.exe
)

echo.
echo ============================================================
echo   %APP_NAME% %APP_VERSION% - Windows Installer Build
echo ============================================================
echo.

:: ── Step 1: Check Python ─────────────────────────────────────────────────────
echo [1/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found. Install from https://python.org and try again.
    goto :error
)
python --version
echo  OK
echo.

:: ── Step 2: Install / upgrade PyInstaller ────────────────────────────────────
echo [2/4] Installing PyInstaller...
python -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo  ERROR: Failed to install PyInstaller.
    goto :error
)
echo  OK
echo.

:: ── Step 3: PyInstaller build ────────────────────────────────────────────────
echo [3/4] Building executable with PyInstaller...
echo  Spec file: %SPEC_FILE%
echo  This may take 2-5 minutes...
echo.

python -m PyInstaller --clean --noconfirm %SPEC_FILE%
if errorlevel 1 (
    echo.
    echo  ERROR: PyInstaller build failed. Check the output above for details.
    echo.
    echo  Common fixes:
    echo    - Missing module? Add it to hiddenimports in %SPEC_FILE%
    echo    - Import error?  Run: python new_main.py  to see the error
    goto :error
)

:: Check the output folder exists
if not exist "%DIST_DIR%\%APP_NAME%.exe" (
    echo  ERROR: Build completed but %DIST_DIR%\%APP_NAME%.exe not found.
    goto :error
)
echo.
echo  Executable built: %DIST_DIR%\%APP_NAME%.exe
echo.

:: ── Step 4: NSIS installer ───────────────────────────────────────────────────
echo [4/4] Creating Windows installer with NSIS...

if not exist "%NSIS_PATH%" (
    echo.
    echo  WARNING: NSIS not found at expected locations:
    echo    C:\Program Files (x86)\NSIS\makensis.exe
    echo    C:\Program Files\NSIS\makensis.exe
    echo.
    echo  To create the installer:
    echo    1. Download NSIS from https://nsis.sourceforge.io/Download
    echo    2. Install it
    echo    3. Run this script again
    echo.
    echo  Your executable is still usable — distribute the folder:
    echo    %DIST_DIR%\
    echo.
    goto :skip_nsis
)

"%NSIS_PATH%" "%NSI_FILE%"
if errorlevel 1 (
    echo.
    echo  ERROR: NSIS build failed. Check the output above.
    echo  Your executable is still usable — distribute the folder: %DIST_DIR%\
    goto :error
)

:: ── Done ─────────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo   BUILD SUCCESSFUL
echo ============================================================
echo.
echo  Installer: %OUTPUT_EXE%
echo  Executable only: %DIST_DIR%\
echo.
echo  The installer file is ready to distribute to users.
echo  They just double-click it — no Python required.
echo.
pause
exit /b 0

:skip_nsis
echo ============================================================
echo   BUILD PARTIALLY SUCCESSFUL (no installer - NSIS missing)
echo ============================================================
echo.
echo  Executable folder: %DIST_DIR%\
echo  You can zip this folder and distribute it manually.
echo.
pause
exit /b 0

:error
echo.
echo ============================================================
echo   BUILD FAILED
echo ============================================================
echo.
pause
exit /b 1