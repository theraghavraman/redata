@echo off
rem ReData local engine - Windows launcher.
rem First run creates engine\.venv and installs DuckDB; later runs start straight away.
setlocal
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo Python 3.9 or newer is required. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during setup, then run this file again.
  pause
  exit /b 1
)

if not exist "engine\.venv\Scripts\python.exe" (
  echo Creating a private Python environment in engine\.venv ...
  %PY% -m venv "engine\.venv" || goto :fail
)
if not exist "engine\.venv\.installed" (
  echo Installing DuckDB and Excel readers (first run only^) ...
  "engine\.venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r "engine\requirements.txt" || goto :fail
  echo ok> "engine\.venv\.installed"
)

"engine\.venv\Scripts\python.exe" "engine\redata_engine.py" %*
exit /b %errorlevel%

:fail
echo.
echo Setup failed. Check your internet connection for the first run, then try again.
pause
exit /b 1
