# Changelog

All notable changes to ReData are documented here.

## [Unreleased]

Fixes from a review of the engine and the browser app.

### Fixed
- JSON and NDJSON imports no longer reserve a 2 GiB buffer. `_json_source` set `maximum_object_size=1073741824`, which DuckDB honours by allocating about twice that up front, so a three-line file failed with `OutOfMemoryException` on any machine whose DuckDB memory limit was under 2 GiB. The folder-sync path never set it.
- The SQL lab's file-function denylist can no longer be bypassed. Quoting the function name (`"read_text"('/etc/passwd')`) dodged the regex, and several readers were missing from the list; the query is now normalised before matching and `read_json_objects_auto`, `read_ndjson_objects`, `sqlite_scan`, `postgres_scan`, `mysql_scan`, `st_read` and others are covered.
- Appending fractional values to an existing integer column no longer rounds them. DuckDB casts a DOUBLE into a BIGINT silently and never raises `ConversionException`, so the widen-and-retry path never fired for numeric data; the column is widened to DOUBLE before the insert.
- `.csv` files that use `;`, `|` or a tab as the delimiter keep their column names. The header row was split on a hardcoded comma while DuckDB auto-detected the real delimiter.
- A JSON file containing more than one array of records is rejected with a clear message instead of silently importing the first array and dropping the rest.
- The browser SQL result grid renders at most 1,000 rows, matching the engine. It previously built one HTML string for the whole result while the status line claimed a 1,000-row cap.
- Column names typed into the import dialog's header editor are applied in "Column headers" mode. They were discarded unless the file was imported without a header row.

### Changed
- `vendor/` ships the byte-exact upstream `sql-wasm.js` and `xlsx.full.min.js`, plus the previously missing `sql-wasm.wasm`. The bundled copies had lost a leading or trailing newline, so their SHA-384 never matched the pinned fingerprint, the browser rejected the local copy and SQL/Excel work silently fell back to the CDN. Offline use now works.
- `scripts/audit_browser_dependencies.py` hashes the bundled vendor files and fails if any stops matching a pinned fingerprint in `index.html`.
- `tests/test_regressions.py` covers each fix above.

## [0.2.0-rc.1] - 2026-10-12

This release candidate contains tested browser-app reliability fixes from the functional audit. The historical v0.1.0 archive and DOI remain unchanged.

### Fixed
- Reject malformed CSV input with an actionable error instead of silently swallowing rows.
- Show a clear error for empty files.
- Decode Windows-1252 text as a fallback when UTF-8 decoding fails.
- Allow users to select and import non-first Excel worksheets.
- Add browser-side pagination so rows after the first 150 can be reached.
- Load SQL rows in a single transaction, reducing the measured 1-million-row GROUP BY test from about 53 seconds to about 2 seconds in the audit environment.

### Verified in the audit
- CSV imports including UTF-8 BOM, accented and CJK text, malformed/empty/header-only inputs.
- Excel first-sheet and second-sheet selection.
- Sorting, filtering, pagination, profiling, tested cleaning operations, ten chart types, CSV/SVG exports, SQL queries, t-test, regression, group/pivot summaries and segment summaries.
- Responsive layouts at 390 px and 768 px.
- No JavaScript/page errors during the recorded test runs; spreadsheet cell content was escaped as text.

### Known limitations
- No undo/history for data-cleaning operations.
- Date columns are currently treated as text.
- Chart groups with all-blank values are omitted; the histogram title has a known display defect.
- SQL runs on the browser main thread and can block the UI.
- SheetJS and sql.js are loaded from public CDNs without integrity verification; offline operation is not guaranteed.
- Accessibility and dependency scans were not complete.
- Performance was measured only on narrow CSV datasets up to 1,000,000 rows. No claim is made for 1 GB files or 100 million rows.

See [the functional audit](docs/AUDIT-2026-10-12.md) for the test matrix and evidence.
