# Bundled third-party libraries

Unmodified copies, loaded only in the browser (Web Workers), verified with SHA-384 before use.

| File | Library | Version | License | SHA-384 |
|---|---|---|---|---|
| xlsx.full.min.js | SheetJS Community Edition | 0.20.3 (cdn.sheetjs.com) | Apache-2.0 (LICENSE-sheetjs.txt) | EnyY0/GSHQGSxSgMwaIPzSESbqoOLSexfnSMN2AP+39Ckmn92stwABZynq1JyzdT |
| sql-wasm.js | sql.js | 1.14.2 (cdnjs) | MIT (LICENSE-sqljs.txt) | 7Zym2PlgXfg8ap8cqJUwlZrLl+VEwt0NVbzYfhH28IWLnSpAgQOnSCY2+EXo5MtM |
| sql-wasm.wasm | sql.js (SQLite) | 1.14.2 (cdnjs) | MIT; SQLite is public domain | x0YkuPkDHnKTZcB1JO4eb6j5+eU36aka+jBA6tOKTFaTz98b9V7fPT0QgZ9qyQW2 |

All three files are shipped, so ReData works with no network access. If a bundled
file is missing or altered, ReData falls back to the pinned CDN copy (same
fingerprint).

Note for anyone re-vendoring these: the fingerprints are over the exact bytes of
the official artifacts. Trimming a leading or trailing newline changes the hash,
the browser then rejects the local copy, and the app quietly falls back to the
CDN. `python scripts/audit_browser_dependencies.py` re-checks every bundled file
against the pins in index.html.
