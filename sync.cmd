@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.10 or newer from python.org.
  echo Then reopen this launcher, or use the PowerShell instructions in README.md.
  pause
  exit /b 1
)
py -3 claude_sync.py sync --live
set "SYNC_EXIT_CODE=%ERRORLEVEL%"
echo.
if "%SYNC_EXIT_CODE%"=="0" (
  echo Synchronization complete. Reopen Claude and sign in to your other account.
) else (
  echo Synchronization did not finish. Review the error above before trying again.
)
pause
exit /b %SYNC_EXIT_CODE%
