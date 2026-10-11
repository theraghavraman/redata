#!/usr/bin/env sh
# ReData local engine - macOS / Linux launcher.
# First run creates engine/.venv and installs DuckDB; later runs start straight away.
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
if [ ! -f engine/.venv/.installed ]; then
  echo "Installing DuckDB and Excel readers (first run only) ..."
  engine/.venv/bin/python -m pip install --disable-pip-version-check -q -r engine/requirements.txt
  echo ok > engine/.venv/.installed
fi

exec engine/.venv/bin/python engine/redata_engine.py "$@"
