#!/usr/bin/env python3
"""Extract ReData's inline JavaScript and validate its syntax with Node.js."""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
blocks = re.findall(r"<script\b[^>]*>([\s\S]*?)</script\s*>", HTML, flags=re.IGNORECASE)

if len(blocks) != 1:
    raise SystemExit(f"Expected one inline application script, found {len(blocks)}")

with tempfile.TemporaryDirectory(prefix="redata-js-check-") as directory:
    script = Path(directory) / "redata-inline.js"
    script.write_text(blocks[0], encoding="utf-8")
    result = subprocess.run(["node", "--check", str(script)], check=False)
    if result.returncode:
        raise SystemExit(result.returncode)

print("Inline application JavaScript syntax passed.")
