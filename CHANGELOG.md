# Changelog

All notable changes to ReData are documented here.

## [Unreleased]

### Engine 1.2.0: package, command line, FastAPI

#### Added
- The engine is now the `redata` Python package (`engine/redata`) with a `pyproject.toml`. `python -m pip install .` installs it with the SQLite, file, URL and REST connectors; database, warehouse and S3 drivers are optional extras (`[postgres]`, `[mysql]`, `[sqlserver]`, `[snowflake]`, `[s3]`, `[all]`).
- A `redata` command that works without the browser: `serve`, `connectors`, `connection add|list|test|remove`, `stream add|list|reset|remove`, `sync`, `runs`, `tables` and `sql`. `redata sync --all` exits 1 if any sync fails, so it can run from cron.
- `benchmarks/run_sync_benchmark.py` measures full, append and upsert syncs through the real pipeline and checks each result against the source. `benchmarks/RESULTS.md` is generated from the committed result files by `benchmarks/summarize_results.py`, and a test fails if the two disagree.
- Tests for sync modes, saved state, schema drift, the HTTP API, the CLI and the engine's statistics. The engine suite grew from 27 tests to 170.

#### Changed
- The HTTP API is a FastAPI app served by Uvicorn instead of a hand-written `http.server` handler. Routes, the Host and token checks, the `{"error": ...}` shape and the response headers are unchanged, and request bodies now have typed models. The OpenAPI schema is served at `/api/openapi.json` behind the engine token. `fastapi` and `uvicorn` are new dependencies; the launch scripts install them on the next start.
- The 800-line `Engine` class is split by concern into `ingest`, `profile`, `analysis`, `transform` and `sqllab`, with `formula`, `sqlguard` and `util` as plain modules. `engine/redata_engine.py` remains as the launcher and still exports `Engine` and `UserError`.
- The README leads with sync modes, saved state and schema drift, and its performance section quotes only recorded runs.

#### Fixed
- Schema drift between two sync runs is handled the same way as drift between two batches of one run. Previously a later run that brought text into a numeric column failed the sync with a conversion error, because only the within-run path widened columns.
- Staging columns are widened before any value would be changed by a cast, not only when an insert fails. DuckDB casts on `INSERT` without an error whenever the cast cannot fail, so a timestamp arriving in a `DATE` column lost its time, a decimal with more places was rounded, an integer arriving in a `BOOLEAN` column became `true`, and between runs a fraction arriving in an integer column was rounded. The column now takes the incoming type when the stored values survive that, otherwise `VARCHAR`.
- When one column needs widening to text, only that column is changed. Every column whose type merely differed from the batch used to be turned into text along with it.
- Starting a second engine on a workspace that is already open no longer deletes the first engine's staged uploads and exports. The DuckDB file is opened, and its lock taken, before leftover folders are cleared.
- `pytz` is declared as a dependency. DuckDB needs it to return `TIMESTAMPTZ` values (the sync history and `_redata_loaded_at`), and it was only present when the Snowflake driver happened to install it.
- A static file that cannot be read returns 404 instead of an unhandled error.

### Fixes from a review of the engine and the browser app

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
