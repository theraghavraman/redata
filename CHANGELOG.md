# Changelog

All notable changes to ReData are documented here.

## [0.2.0] - 2026-10-12

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
