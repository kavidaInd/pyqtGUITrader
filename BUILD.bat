@echo off
:: ==========================================================================
:: BUILD.bat - TradingAssistant Windows Build Script
:: Place in project root (same folder as main.py). Double-click to run.
:: ==========================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set APP_NAME=TradingAssistant
set APP_VERSION=1.0.0
set SPEC_FILE=trading_assistant.spec
set NSI_FILE=scripts\build_installer.nsi
set DIST_DIR=dist\%APP_NAME%
set OUTPUT_INSTALLER=scripts\%APP_NAME%_Setup_%APP_VERSION%.exe
set OUTPUT_ZIP=scripts\%APP_NAME%_Portable_%APP_VERSION%.zip
set NSIS_PATH=C:\Program Files (x86)\NSIS\makensis.exe
if not exist "%NSIS_PATH%" set NSIS_PATH=C:\Program Files\NSIS\makensis.exe

echo.
echo ==========================================================
echo   %APP_NAME% %APP_VERSION% - Windows Build Script
echo ==========================================================
echo.

:: ------------------------------------------------------------------
:: Step 1: Verify Python
:: ------------------------------------------------------------------
echo [1/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo   ERROR: Python not found on PATH.
    echo   Install Python 3.10+ from https://python.org
    echo   Tick "Add Python to PATH" during install.
    pause
    exit /b 1
)
python -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo   ERROR: Python 3.10+ required.
    python --version
    pause
    exit /b 1
)
python --version
echo   OK
echo.

:: ------------------------------------------------------------------
:: Step 2: Install dependencies
:: ------------------------------------------------------------------
echo [2/5] Installing dependencies...

echo   Upgrading pip...
python -m pip install --upgrade pip --quiet

echo   Checking SQLAlchemy (must be 2.0.37+ for Python 3.13)...
python -c "import sqlalchemy; from packaging.version import Version; exit(0 if Version(sqlalchemy.__version__) >= Version('2.0.37') else 1)" >nul 2>&1
if errorlevel 1 (
    echo   Upgrading SQLAlchemy to 2.0.37+...
    python -m pip install "sqlalchemy>=2.0.37" --quiet
)
python -c "import sqlalchemy; print('  SQLAlchemy', sqlalchemy.__version__, '- OK')"

echo   Installing requirements.txt...
python -m pip install -r requirements.txt --quiet

echo   Installing broker SDKs...
python -m pip install logzero --quiet

echo   Installing PyInstaller...
python -m pip install pyinstaller --upgrade --quiet

echo   Dependencies OK
echo.

:: ------------------------------------------------------------------
:: Step 3: Verify environment
:: ------------------------------------------------------------------
echo [3/5] Verifying environment...
python -c "import sqlalchemy; print('  SQLAlchemy', sqlalchemy.__version__)"
python -c "import PyQt5; print('  PyQt5 OK')"
python -c "import pandas; print('  pandas', pandas.__version__)"
echo   Environment OK
echo.

:: ------------------------------------------------------------------
:: Step 4: PyInstaller
:: ------------------------------------------------------------------
echo [4/5] Running PyInstaller...
echo   Spec: %SPEC_FILE%
echo   First run takes 5-10 minutes. Please wait...
echo   Lines starting with "WARNING" about missing modules are NORMAL.
echo.

python -m PyInstaller --clean --noconfirm %SPEC_FILE%
if errorlevel 1 (
    echo.
    echo   ERROR: PyInstaller failed. Read the output above carefully.
    echo.
    echo   Most common causes and fixes:
    echo     1. Package crashes on import during analysis
    echo        Fix: add it to the excludes list in trading_assistant.spec
    echo     2. Missing package: pip install package-name
    echo     3. SQLAlchemy too old: pip install "sqlalchemy>=2.0.37"
    echo.
    pause
    exit /b 1
)

if not exist "%DIST_DIR%\%APP_NAME%.exe" (
    echo.
    echo   ERROR: Exe not found after build. Check output above.
    pause
    exit /b 1
)
echo.
echo   Executable ready: %DIST_DIR%\%APP_NAME%.exe
echo.

:: ------------------------------------------------------------------
:: Step 5: Package (NSIS installer or ZIP fallback)
:: ------------------------------------------------------------------
echo [5/5] Packaging...

if exist "%NSIS_PATH%" (
    echo   Building Windows installer with NSIS...
    "%NSIS_PATH%" /V2 "%NSI_FILE%"
    if errorlevel 1 (
        echo   NSIS failed - falling back to portable ZIP...
        goto :make_zip
    )
    echo.
    echo ==========================================================
    echo   BUILD COMPLETE
    echo ==========================================================
    echo   Installer : %OUTPUT_INSTALLER%
    echo   Exe folder: %DIST_DIR%\
    echo.
    pause
    exit /b 0
)

:make_zip
echo   Creating portable ZIP (NSIS not installed)...
powershell -NoProfile -Command "Compress-Archive -Path '%DIST_DIR%\*' -DestinationPath '%OUTPUT_ZIP%' -Force"
echo.
echo ==========================================================
echo   BUILD COMPLETE
echo ==========================================================
echo   Portable ZIP : %OUTPUT_ZIP%
echo   Exe folder   : %DIST_DIR%\
echo.
echo   For a proper Setup.exe, install NSIS:
echo   https://nsis.sourceforge.io/Download
echo.
pause
exit /b 0