#!/usr/bin/env python3
"""Fail closed if ReData's pinned browser libraries regress to known-vulnerable versions."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
NOTICES = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

checks = [
    (
        "SheetJS uses the official patched 0.20.3 browser build",
        "https://cdn.sheetjs.com/xlsx-0.20.3/package/dist/xlsx.full.min.js" in HTML,
    ),
    (
        "SQL.js loader uses pinned 1.14.2",
        (
            "https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.14.2/sql-wasm.js" in HTML
            or (
                'const SQLJS_BASE = "https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.14.2/";' in HTML
                and 'lib("sql-wasm.js", SRI.js)' in HTML
            )
        ),
    ),
    (
        "SQL.js WebAssembly asset path uses the same 1.14.2 version",
        "https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.14.2/" in HTML,
    ),
    (
        "Known-vulnerable SheetJS 0.18.5 reference is absent",
        "xlsx@0.18.5" not in HTML and "xlsx-0.18.5" not in HTML,
    ),
    (
        "Old SQL.js 1.8.0 reference is absent",
        "sql.js/1.8.0/" not in HTML,
    ),
    (
        "Third-party notices record SheetJS 0.20.3 and Apache-2.0",
        "xlsx-0.20.3" in NOTICES and "Apache-2.0" in NOTICES,
    ),
    (
        "Third-party notices record SQL.js 1.14.2 and MIT",
        "sql.js/1.14.2" in NOTICES and "MIT" in NOTICES,
    ),
]

failed = False
for description, ok in checks:
    print(f"[{'PASS' if ok else 'FAIL'}] {description}")
    failed |= not ok

if failed:
    print("Browser dependency audit failed; do not publish this revision.", file=sys.stderr)
    raise SystemExit(1)

print("Browser dependency pin and notice checks passed.")
