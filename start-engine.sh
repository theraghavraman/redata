#!/usr/bin/env sh
# ReData local engine - macOS / Linux launcher.
# First run creates engine/.venv and installs DuckDB and the database drivers;
# it installs again whenever engine/requirements.txt changes.
set -e
cd "$(dirname "$0")"

PY=$(command -v python3 || command -v python || true)
if [ -z "$PY" ]; then
  echo "Python 3.9 or newer is required: https://www.python.org/downloads/"
  exit 1
fi

if [ ! -x engine/.venv/bin/python ]; then
  echo "Creating a private Python environment in engine/.venv ..."
  "$PY" -m venv engine/.venv
fi
if ! cmp -s engine/requirements.txt engine/.venv/.installed 2>/dev/null; then
  echo "Installing DuckDB and the database drivers (first run or after an update) ..."
  engine/.venv/bin/python -m pip install --disable-pip-version-check -q --upgrade pip
  engine/.venv/bin/python -m pip install --disable-pip-version-check -q -r engine/requirements.txt
  cp engine/requirements.txt engine/.venv/.installed
fi

exec engine/.venv/bin/python engine/redata_engine.py "$@"
