#!/usr/bin/env python3
"""Launcher for the ReData local engine, used by start-engine.sh / .bat.

The engine itself is the ``redata`` package next to this file. This script
keeps the old entry point working: it takes the same options as before and
runs ``redata serve``. ``Engine`` and ``UserError`` are re-exported for code
that imported them from here.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import duckdb  # noqa: F401
    import fastapi  # noqa: F401
    import uvicorn  # noqa: F401
except ImportError as exc:  # pragma: no cover - friendly message for first run
    sys.exit(
        "A required package is missing (%s). Run the start script (start-engine.bat / "
        "start-engine.sh) or: python -m pip install -r engine/requirements.txt" % exc.name
    )

from redata import __version__ as VERSION  # noqa: E402,F401
from redata.cli import main as _cli  # noqa: E402
from redata.engine import Engine  # noqa: E402,F401
from redata.util import UserError  # noqa: E402,F401


def main(argv=None):
    return _cli(["serve"] + list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
