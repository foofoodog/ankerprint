@echo off
setlocal enabledelayedexpansion

:: =========================================================================
::  AnkerMake PrusaSlicer Post-Processing Script for Windows & WSL
::
::  In PrusaSlicer (Windows GUI):
::    Print Settings -> Output options -> Post-processing scripts
::    Add: "C:\path\to\ankerprint\scripts\prusa_print.cmd"
:: =========================================================================

set SCRIPT_DIR=%~dp0
set REPO_DIR=%SCRIPT_DIR%..

:: If running via native Windows Python venv
if exist "%REPO_DIR%\venv\Scripts\python.exe" (
    if exist "%REPO_DIR%\ankerprint.py" (
        "%REPO_DIR%\venv\Scripts\python.exe" "%REPO_DIR%\ankerprint.py" print %*
    ) else (
        "%REPO_DIR%\venv\Scripts\python.exe" "%REPO_DIR%\ankerctl.py" print %*
    )
    exit /b !errorlevel!
)

:: If running under WSL, convert path and execute in WSL
where wsl >nul 2>&1
if %errorlevel% equ 0 (
    wsl bash -c "$(wslpath '%SCRIPT_DIR%prusa_print.sh') '%*'"
    exit /b !errorlevel!
)

:: Fallback to Windows system python
where python >nul 2>&1
if %errorlevel% equ 0 (
    if exist "%REPO_DIR%\ankerprint.py" (
        python "%REPO_DIR%\ankerprint.py" print %*
    ) else (
        python "%REPO_DIR%\ankerctl.py" print %*
    )
    exit /b !errorlevel!
)

echo [Error] Neither Python nor WSL found to execute ankerprint. >&2
exit /b 1
