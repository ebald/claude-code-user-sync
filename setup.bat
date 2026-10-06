@echo off
setlocal
rem Execution policy applies only to this PowerShell process, not to the computer.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup-windows.ps1" %*
set "setup_exit_code=%errorlevel%"
if "%~1"=="" if not "%setup_exit_code%"=="0" pause
endlocal & exit /b %setup_exit_code%
