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
rem Install on first run, and again whenever engine\requirements.txt changes.
set "NEEDINSTALL="
if not exist "engine\.venv\.installed" set "NEEDINSTALL=1"
if not defined NEEDINSTALL (
  fc /b "engine\requirements.txt" "engine\.venv\.installed" >nul 2>nul || set "NEEDINSTALL=1"
)
if defined NEEDINSTALL (
  echo Installing DuckDB and the database drivers (first run or after an update^) ...
  "engine\.venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --upgrade pip
  "engine\.venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r "engine\requirements.txt" || goto :fail
  copy /y "engine\requirements.txt" "engine\.venv\.installed" >nul
)

"engine\.venv\Scripts\python.exe" "engine\redata_engine.py" %*
exit /b %errorlevel%

:fail
echo.
echo Setup failed. Check your internet connection for the first run, then try again.
pause
exit /b 1
