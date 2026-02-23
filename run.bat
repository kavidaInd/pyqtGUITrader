@echo off
setlocal enabledelayedexpansion

:: ============================================================================
:: Algo Trading Dashboard Launcher
:: ============================================================================
:: This script launches the Trading GUI application with proper environment
:: detection, error handling, and logging.
:: ============================================================================

:: Set console title and colors
title Algo Trading Dashboard Launcher
color 0F

:: Get script directory (works even if run from different location)
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

:: Set log file
set "LOG_DIR=%SCRIPT_DIR%\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" 2>nul
if !errorlevel! neq 0 (
    echo WARNING: Could not create log directory, using current directory
    set "LOG_DIR=%SCRIPT_DIR%"
)

:: Generate timestamp-safe filename
for /f "tokens=1-3 delims=/ " %%a in ('echo %date%') do (
    set "YYYY=%%c"
    set "MM=%%a"
    set "DD=%%b"
)
for /f "tokens=1-3 delims=:." %%a in ('echo %time%') do (
    set "HH=%%a"
    set "MIN=%%b"
    set "SEC=%%c"
)
:: Remove leading spaces
set "HH=%HH: =0%"
set "MIN=%MIN: =0%"
set "SEC=%SEC: =0%"

set "LOG_FILE=%LOG_DIR%\launcher_%YYYY%%MM%%DD%_%HH%%MIN%%SEC%.log"

:: ============================================================================
:: Logging function
:: ============================================================================
:log
echo [%date% %time%] %* >> "%LOG_FILE%" 2>nul
echo %*
goto :eof

:: ============================================================================
:: Error handling
:: ============================================================================
:error
call :log "❌ ERROR: %*"
echo.
echo Press any key to exit...
pause > nul 2>nul
exit /b 1

:: ============================================================================
:: Check for Python installation
:: ============================================================================
call :log "=== Starting Algo Trading Dashboard ==="
call :log "Script directory: %SCRIPT_DIR%"

:: Try to find Python in common locations
set "PYTHON_CMD="

:: Check if python is in PATH
where python >nul 2>nul
if !errorlevel! equ 0 (
    set "PYTHON_CMD=python"
    call :log "Found Python in PATH"
    goto :found_python
)

:: Check for python3
where python3 >nul 2>nul
if !errorlevel! equ 0 (
    set "PYTHON_CMD=python3"
    call :log "Found Python3 in PATH"
    goto :found_python
)

:: Check common installation paths
set "PYTHON_PATHS[0]=C:\Python313\python.exe"
set "PYTHON_PATHS[1]=C:\Python312\python.exe"
set "PYTHON_PATHS[2]=C:\Python311\python.exe"
set "PYTHON_PATHS[3]=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
set "PYTHON_PATHS[4]=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
set "PYTHON_PATHS[5]=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
set "PYTHON_PATHS[6]=%USERPROFILE%\AppData\Local\Programs\Python\Python313\python.exe"
set "PYTHON_PATHS[7]=%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe"
set "PYTHON_PATHS[8]=%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe"

set "path_index=0"
:check_path_loop
if defined PYTHON_PATHS[%path_index%] (
    if exist "!PYTHON_PATHS[%path_index%]!" (
        set "PYTHON_CMD=!PYTHON_PATHS[%path_index%]!"
        call :log "Found Python at: !PYTHON_PATHS[%path_index%]!"
        goto :found_python
    )
    set /a "path_index+=1"
    goto :check_path_loop
)

:: Check for virtual environment
if exist "%SCRIPT_DIR%\venv\Scripts\python.exe" (
    set "PYTHON_CMD=%SCRIPT_DIR%\venv\Scripts\python.exe"
    call :log "Found virtual environment Python"
    goto :found_python
)

:: If we get here, Python not found
call :log "Python not found in any common location"
echo.
echo ⚠️ Python not found!
echo.
echo Please install Python 3.11 or later from python.org
echo or activate your virtual environment.
echo.
echo Press any key to exit...
pause > nul 2>nul
exit /b 1

:found_python
call :log "Using Python: %PYTHON_CMD%"

:: ============================================================================
:: Check Python version
:: ============================================================================
call :log "Checking Python version..."
for /f "delims=" %%i in ('"%PYTHON_CMD%" --version 2^>^&1') do set "PY_VERSION=%%i"
call :log "%PY_VERSION%"

:: Extract major.minor version safely
set "PY_MAJOR=0"
set "PY_MINOR=0"
for /f "tokens=2 delims= " %%a in ("%PY_VERSION%") do (
    set "VER=%%a"
)
for /f "tokens=1,2 delims=." %%a in ("%VER%") do (
    set "PY_MAJOR=%%a"
    set "PY_MINOR=%%b"
)

if %PY_MAJOR% lss 3 (
    call :error "Python 3 required, found %PY_VERSION%"
    exit /b 1
)
if %PY_MAJOR% equ 3 (
    if %PY_MINOR% lss 8 (
        call :error "Python 3.8 or higher required, found %PY_VERSION%"
        exit /b 1
    )
)

:: ============================================================================
:: Check for required packages
:: ============================================================================
call :log "Checking required packages..."

:: List of required packages - updated for PyQt5
set "REQUIRED_PKGS=PyQt5 PyQt5.QtWebEngineWidgets pandas numpy plotly fyers_apiv3"

set "MISSING_PKG=0"
for %%p in (%REQUIRED_PKGS%) do (
    "%PYTHON_CMD%" -c "import %%p" 2>nul
    if !errorlevel! neq 0 (
        call :log "⚠️ Package '%%p' not found"
        set "MISSING_PKG=1"
    ) else (
        call :log "✅ Package '%%p' found"
    )
)

if !MISSING_PKG! equ 1 (
    echo.
    echo ⚠️ Some required packages are missing.
    echo.
    echo Would you like to install them now? (y/n)
    choice /c yn /n /m "Install missing packages? (y/n): "
    if !errorlevel! equ 1 (
        call :log "Installing missing packages..."
        "%PYTHON_CMD%" -m pip install --upgrade pip
        if !errorlevel! neq 0 (
            call :error "Failed to upgrade pip"
            exit /b 1
        )
        "%PYTHON_CMD%" -m pip install -r "%SCRIPT_DIR%\requirements.txt"
        if !errorlevel! neq 0 (
            call :error "Failed to install packages from requirements.txt"
            exit /b 1
        )
        call :log "Packages installed successfully"
    ) else (
        call :log "User chose not to install packages"
        echo.
        echo Continuing with possibly missing packages...
    )
)

:: ============================================================================
:: Check if main script exists
:: ============================================================================
set "MAIN_SCRIPT=%SCRIPT_DIR%\main.py"
if not exist "%MAIN_SCRIPT%" (
    call :error "Main script not found: %MAIN_SCRIPT%"
    exit /b 1
)

:: ============================================================================
:: Parse command line arguments
:: ============================================================================
set "MODE=normal"
set "DEBUG="

:parse_args
if "%1"=="" goto :run_app
if "%1"=="--debug" set "DEBUG=--debug" & shift & goto :parse_args
if "%1"=="--safe" set "MODE=safe" & shift & goto :parse_args
if "%1"=="--help" goto :show_help
shift
goto :parse_args

:show_help
echo.
echo Algo Trading Dashboard Launcher
echo.
echo Usage: %~nx0 [options]
echo.
echo Options:
echo   --debug    Run in debug mode (more verbose logging)
echo   --safe     Run in safe mode (disables live trading)
echo   --help     Show this help message
echo.
pause
exit /b 0

:: ============================================================================
:: Run the application
:: ============================================================================
:run_app
call :log "Starting application in %MODE% mode..."

:: Change to script directory
cd /d "%SCRIPT_DIR%" 2>nul
if !errorlevel! neq 0 (
    call :error "Could not change to script directory: %SCRIPT_DIR%"
    exit /b 1
)

:: Set Python path to include current directory
set "PYTHONPATH=%SCRIPT_DIR%;%PYTHONPATH%"

:: Run the application
if "%MODE%"=="safe" (
    call :log "SAFE MODE: Trading will be simulated"
    set "ALGO_MODE=--safe"
) else (
    set "ALGO_MODE="
)

call :log "Command: %PYTHON_CMD% %MAIN_SCRIPT% %DEBUG% %ALGO_MODE%"

:: Run with error handling
echo.
echo ========================================
echo  Starting Algo Trading Dashboard...
echo ========================================
echo.

"%PYTHON_CMD%" "%MAIN_SCRIPT%" %DEBUG% %ALGO_MODE%

:: Check exit code
set "EXIT_CODE=!errorlevel!"
if !EXIT_CODE! neq 0 (
    call :log "❌ Application exited with code !EXIT_CODE!"
) else (
    call :log "✅ Application exited normally"
)

echo.
echo ========================================
echo  Application closed.
echo ========================================
echo.
echo Log file: %LOG_FILE%
echo.

:: Wait for user input in debug mode
if defined DEBUG (
    echo Press any key to exit...
    pause > nul 2>nul
)

exit /b !EXIT_CODE!