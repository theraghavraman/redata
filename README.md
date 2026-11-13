# ReData

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23314956.svg)](https://doi.org/10.5281/zenodo.23314956)

**ReData is a small data-ingestion engine with an analytics workspace on top.** The engine copies tables, queries, files and API responses into [DuckDB](https://duckdb.org) staging tables, keeps them current with incremental syncs, and remembers where each sync stopped. It runs from the command line or behind a browser page that profiles, cleans, queries and charts the data.

- **Sources:** PostgreSQL, MySQL, SQL Server, Snowflake, SQLite, local folders, S3-compatible buckets, files at a URL, and JSON REST APIs.
- **Sync modes:** full refresh, append by cursor, and upsert by key.
- **State:** each sync's cursor (or list of loaded files) is saved to disk after every successful run and survives restarts.
- **Schema drift:** new source columns are added to staging, and a column is widened before any value would be changed or rejected by its type.
- **Scheduling:** every 5 minutes to daily, with a run log you can query in SQL.
- **Interfaces:** a `redata` command, a FastAPI HTTP API, and the browser page.

Everything runs on your own computer. Nothing passes through a ReData server.

## Install and run a sync

Python 3.9 or newer.

```bash
git clone https://github.com/theraghavraman/redata.git
```

```bash
python -m pip install ./redata
```

That installs the `redata` command with the SQLite, file, URL and REST connectors. Database drivers are optional extras: `./redata[postgres]`, `[mysql]`, `[sqlserver]`, `[snowflake]`, `[s3]`, or `[all]`.

Sync a table and keep it current:

```bash
redata connection add --type postgres --name shop --set host=db.example.com --set port=5432 --set database=shop --set user=reader --set password=env:SHOP_DB_PASSWORD
```

```bash
redata stream add --connection shop --source public.orders --mode upsert --cursor updated_at --keys order_id --target orders
```

```bash
redata sync orders
```

```text
success  staging.orders  read 4  written 4  rows now 5  cursor 2026-01-01 11:00:00 -> 2026-01-02 09:00:00  2 new, 2 updated or re-checked.
```

That is the second run of a three-row table after two orders were added and one was edited: it read only what changed since the saved cursor, plus the one row sitting on the cursor.

```bash
redata sql "SELECT status, count(*) AS orders FROM staging.orders GROUP BY 1 ORDER BY 1"
```

```text
status  orders
------  ------
new     3
paid    2
```

`redata sync --all` runs every sync and exits 1 if any fails, so it works from cron. `redata runs` shows the history, `redata stream list` shows each sync's saved cursor, `redata connectors postgres` lists a connector's settings, and `redata serve` starts the engine with the browser page and the scheduler. Every command takes `--workspace`; the default is `$REDATA_WORKSPACE`, then `engine/workspace` in a checkout, then `~/.redata/workspace`. DuckDB allows one process per database file, so stop `redata serve` before running another command on the same workspace.

## Sync modes

A sync copies one table, view, `SELECT`, file pattern or API endpoint into one staging table.

| Mode | What it reads | How it writes | Use it when | What it does not do |
| --- | --- | --- | --- | --- |
| `full` | Everything, every run | Builds a new table beside the old one, then swaps it in | The source is small, has no reliable cursor, or rows are deleted | Keep history |
| `append` | Rows where `cursor > saved value` | Inserts them | Rows are only ever added, such as events or logs | See edits or deletes behind the cursor |
| `upsert` | Rows where `cursor >= saved value` | Keeps the newest row per key from the batch, then deletes and re-inserts those keys in one transaction | Rows are edited, and each edit moves a cursor such as `updated_at` | See deletes, or edits that do not move the cursor |

Upsert reads `>=` on purpose. Several rows can share the last cursor value, and one of them may be written after the sync has already passed it; reading the boundary again catches it, and the key keeps the result free of duplicates. The cost is re-reading at least one row per run.

For folders and S3, the cursor is the file: `append` and `upsert` load only files that are new or whose size or modified time has changed. A file at a URL is always a full sync. For REST APIs, the saved cursor is sent as the query parameter you name (`since_param`).

Rows from databases and APIs arrive as [Apache Arrow](https://arrow.apache.org) tables of up to 50,000 rows and are inserted into DuckDB directly from Arrow. Every staged row gets a `_redata_loaded_at` timestamp, and rows from files also get `_redata_source_file`.

## Saved state

Each sync keeps its state in `connections.json` in the workspace: the cursor value with its type (`{"t": "datetime", "v": "2026-01-02T06:33:20"}`), or for file sources the list of loaded files with each one's size and modified time.

- The state is written after the rows are in the staging table, never before. A failed run leaves the cursor where it was, drops its temporary tables, and leaves the staging table as it was.
- The cursor only moves forward. A run that reads nothing keeps it.
- It survives restarts: the next run of `redata sync`, or the next scheduled run under `redata serve`, continues from the saved value.
- `redata stream reset <name>` clears it, so the next run reads everything again. Changing a sync's source, cursor column or mode clears it too; changing only its schedule does not.
- Every run is recorded in `redata_ops.sync_runs` with its trigger, row counts, the cursor before and after, and the error message if it failed.

Two limits to know about:

- **Append is at-least-once.** If the process is killed after the rows are inserted but before the cursor is saved, the next run inserts those rows again. Upsert is not affected, because it replaces by key. Use upsert when duplicates matter.
- **Incremental syncs do not see deletes.** Run a full sync for that.

## Schema drift

Sources change. The same rules apply whether the change shows up between two batches of one run or between two runs.

| Change at the source | What happens in staging |
| --- | --- |
| A new column appears | The column is added; older rows are NULL |
| A column disappears | The column stays; newer rows are NULL |
| An integer column starts carrying fractions | The column becomes `DOUBLE` |
| A date column starts carrying times | The column becomes `TIMESTAMP` |
| Values outgrow the column (`INTEGER` to 64-bit, more decimal places) | The column takes the incoming, wider type |
| Text arrives in a numeric column | The column becomes `VARCHAR`; existing values are kept as text |
| A value that would be altered by the column's type, such as `007` into an integer column | The column becomes `VARCHAR` |
| Values of a different type that fit unchanged, such as `8` as text into an integer column | Nothing; the value is stored in the existing type |

DuckDB casts on `INSERT` without an error whenever the cast cannot fail: 2.75 into a `BIGINT` column becomes 3, and a timestamp into a `DATE` column loses its time. So the engine does not wait for an insert to fail. Before each insert it casts the incoming values to the column's type and back, and if any value comes back different, it widens the column first: to the incoming type when the stored values survive that, otherwise to `VARCHAR`. Types only widen. Nothing is narrowed, renamed or dropped automatically.

## Sources

| Connection | Works with |
| --- | --- |
| PostgreSQL | Postgres, Neon, Supabase, Aiven, AWS RDS / Aurora, Azure and Google Cloud SQL |
| MySQL / MariaDB | MySQL, MariaDB, Aiven, AWS RDS, Azure Database for MySQL, MySQL HeatWave |
| SQL Server / Azure SQL | SQL Server 2012+, Azure SQL Database (including the free offer), Managed Instance |
| Snowflake | Key-pair sign-in generated by ReData (recommended), browser SSO / MFA, or password / access token |
| SQLite | A `.db` / `.sqlite` file |
| Folder of files | CSV, TSV, JSON, NDJSON, Parquet and Excel on a local or network drive |
| Amazon S3 / S3-compatible | AWS S3, Cloudflare R2, MinIO |
| File at a URL | CSV, JSON or Parquet published over http(s) |
| REST API (JSON) | Bearer tokens, records path, next-page links, incremental `since` parameter |

`redata connectors` lists the types and `redata connectors <type>` lists the settings of one. Database connectors use each vendor's Python driver. PostgreSQL and MySQL are read through a server-side cursor, so a large table is streamed in batches instead of being held in memory.

### Connecting Snowflake (including a 30-day trial)

1. In ReData: **Connections → New connection → Snowflake**. Enter the account identifier (`ORGNAME-ACCOUNTNAME`, shown under your name → Account → View account details), user, warehouse and database.
2. Select **Generate key**. ReData creates a key pair, keeps the private key in `engine/workspace/keys/`, and shows one `ALTER USER … SET RSA_PUBLIC_KEY=…` statement.
3. Run that statement in a Snowflake worksheet (as ACCOUNTADMIN on a trial), then select **Save and test**.

Key pairs are recommended because Snowflake is ending password-only sign-ins for all users during 2026. *Externalbrowser* (SSO / MFA in your browser) and password / programmatic access token are also available.

### Where settings and secrets live

Connection settings are stored in `engine/workspace/connections.json`. Passwords, tokens and headers are stored separately in `engine/workspace/secrets.json`, readable only by your user, and generated keys in `engine/workspace/keys/`. The whole `engine/workspace/` folder is git-ignored. Neither the page nor the CLI ever gets a saved secret back; leave a secret field blank to keep the stored one. A secret can also be written as `env:VARIABLE_NAME`, which stores only the variable's name and reads the value when a sync runs.

## Scheduling and run history

Under `redata serve`, a sync can run every 5, 15 or 30 minutes, every 1, 3, 6 or 12 hours, or daily. The scheduler checks every 15 seconds, and one worker runs syncs one at a time, so two syncs never write at once and a sync that is already queued or running is not queued twice. Scheduled syncs run only while the engine is running. Without the server, schedule `redata sync --all` with cron or Task Scheduler.

In the browser page, **Analyse** makes a staging table the active dataset and keeps it live: after each successful sync the open view refreshes. Staging tables can be joined in the SQL lab as `staging.table_name`, and the history is `redata_ops.sync_runs`.

## Measured performance

These are recorded runs on two specific machines, each of which passed its correctness checks. They are not a promise about other hardware. The full tables, raw result files and caveats are in [benchmarks/RESULTS.md](benchmarks/RESULTS.md).

**Sync pipeline**, SQLite source, 6 columns, Apple M2 laptop with 8 GB, DuckDB limited to 2 threads:

| Source rows | Full load | Append: 10% new rows | Append: nothing new | Upsert: 10% new + 5% changed |
| ---: | ---: | ---: | ---: | ---: |
| 1,000,000 | 1.64 s (609,760 rows/s) | 0.21 s (473,999 rows/s) | 0.003 s | 0.36 s (412,558 rows/s) |
| 10,000,000 | 16.59 s (602,835 rows/s) | 1.80 s (556,532 rows/s) | 0.007 s | 4.36 s (343,744 rows/s) |

The source is a local file, so there is no network time; for a remote database read the rate as an upper bound. Each run checked row counts and `sum(amount)` against the source, that append read only the new rows, and that upsert left one row per key.

**CSV import and query over the HTTP API**, GitHub-hosted runner with 4 vCPUs, DuckDB limited to 2 threads:

| Rows | Columns | CSV size | Import + full column profile | SQL aggregate |
| ---: | ---: | ---: | ---: | ---: |
| 1,000,000 | 10 | 105 MB | 2.17 s (median of 3) | 4.3 ms |
| 10,000,000 | 10 | 1.06 GB | 12.78 s (single run) | 23.9 ms |

These HTTP runs were recorded before the server moved from `http.server` to FastAPI and have not been repeated since.

## How the engine is built

The engine is the `redata` package in [`engine/redata`](engine/redata).

| Module | What it holds |
| --- | --- |
| `connectors.py` | One class per source; the catalog of settings; typed cursor encoding |
| `pipeline.py` | Sync modes, saved state, schema drift, the worker queue, the scheduler, the run log |
| `engine.py` | The DuckDB workspace and the active dataset; composed from the five modules below |
| `ingest.py`, `profile.py`, `analysis.py`, `transform.py`, `sqllab.py` | File loading; column profiling; paging, aggregation and statistics; cleaning and formulas; read-only SQL and exports |
| `sqlguard.py`, `formula.py` | The read-only SQL check; the formula parser |
| `server.py` | The FastAPI app: typed request models, Host and token checks, security headers |
| `cli.py` | The `redata` command |

The HTTP API listens on `127.0.0.1` only, rejects any request whose `Host` header is not the loopback address it is serving, and requires a random per-run token on every `/api/` call. Its OpenAPI schema is at `/api/openapi.json`, behind the same token.

## Tests

```bash
python -m pip install "./redata[test]"
```

```bash
python -m pytest redata/tests
```

The suite runs real syncs from SQLite files and folders into DuckDB with no network, and covers each sync mode, the saved state across restarts and failures, every schema-drift rule above, the HTTP API including its access checks, the CLI end to end, and the statistics against Python's `statistics` module. CI runs it on pull requests and on pushes to `main`.

## The browser workspace

The page is a workspace for the rest of the analysis: import, inspect, profile, clean, query, summarize, visualize, test and report. It works on its own in a browser tab for smaller files, and on top of the engine for large files and synced tables.

### Opening the page

ReData runs in two ways:

| | Browser-only | With the local engine |
| --- | --- | --- |
| How to open | Open `index.html`, or the GitHub Pages site | Run `start-engine.bat` (Windows) or `./start-engine.sh` (macOS / Linux) |
| Where the data is processed | Inside the browser tab | DuckDB on your own computer |
| Practical size | Up to 10 lakh rows (1,000,000) | Large files; a 1 crore row, 1.06 GB CSV imported and profiled in 12.8 s on a 4-vCPU CI runner ([results](benchmarks/RESULTS.md)) |
| File types | CSV, TSV, TXT, JSON / NDJSON, XLSX / XLS | Same, plus Parquet and load-by-path |
| Install | Nothing | Python 3.9+ (the engine's packages are installed automatically on first run) |

GitHub Pages: Settings → Pages → Deploy from a branch → `main` → `/ (root)`.

### Large files: the local engine

The browser keeps every row as a JavaScript object, so a tab runs out of memory and freezes long before 1 crore rows. The local engine moves the data into [DuckDB](https://duckdb.org) on your machine. The page then only receives what it shows: one page of rows, one chart's totals, one table of statistics.

1. Install Python 3.9 or newer (on Windows tick **Add python.exe to PATH**).
2. Double-click `start-engine.bat` (Windows) or run `./start-engine.sh` (macOS / Linux). The first run creates `engine/.venv` and installs the engine's packages; later runs start in a second.
3. Your browser opens `http://127.0.0.1:8765`. The sidebar shows **Local engine connected**.
4. Import a file, or paste its full path under **Load a file from this computer by path** (fastest for very large files; nothing is copied).

Keep the engine window open while you work, and press Ctrl+C in it to stop. The dataset stays in `engine/workspace/` and is restored next time you start the engine.

The first run also installs the database drivers used by Connections; the launcher reinstalls automatically whenever `engine/requirements.txt` changes.

Options: `--port 9000`, `--memory-limit 6GB`, `--threads 4`, `--workspace D:\redata-work`, `--no-browser`. The launch scripts run `redata serve`, so the same options work there.

Measured import and query times for the engine are in [Measured performance](#measured-performance). The timings below were recorded in the v0.1.0 README on a 2-core cloud machine with a 1 crore row, 10 column CSV. That file and machine are no longer available, so they have not been reproduced; treat them as project-reported.

| Step | Project-reported time |
| --- | --- |
| Import and profile every column | ~40 s |
| Switch between any tabs | ~0.3 s |
| Page, sort or filter the data explorer | 0.4–1.7 s |
| Charts, t-test, regression, SQL | 0.3–1.5 s |
| Group by 20 lakh distinct values | ~10 s |
| Fill / dedupe / formula across all rows | 17–40 s |
| Export the full dataset to CSV | ~9 s |

### What the page includes

| Workspace | What it does |
| --- | --- |
| Overview | Live dataset summary, completeness and duplicate counts, quick links to tools |
| Import data | Local import for CSV, TSV, TXT, JSON / NDJSON and Excel XLSX/XLS (plus Parquet and load-by-path with the local engine) |
| Connections | Scheduled full, append and upsert syncs from databases, Snowflake, files, S3, URLs and REST APIs into staging tables (local engine) |
| Data explorer | Preview, search, column sorting and CSV export |
| Profile & quality | Inferred column types, missingness, distinct values, numeric ranges and completeness indicators |
| Clean & transform | Drop incomplete rows, fill missing values, remove exact duplicate rows, normalize text, remove columns |
| Visualization | Aggregated bar, line and dot-plot charts; export chart as SVG |
| SQL lab | Queries against a table named `data`: in-browser SQLite, or read-only DuckDB on the full dataset with the local engine |
| Descriptive statistics | Count, mean, median, sample standard deviation, quartiles and IQR outlier screening |
| Hypothesis testing | Welch two-sample t-test with two-sided p-value and degrees of freedom |
| Correlation & regression | Pearson correlation, simple OLS slope/intercept and R² |
| Group by & pivot | Group categorical values with sum, mean, median and counts |
| Segments & funnel | Frequency and share breakdown by a categorical field |
| Formula builder | Derived numeric columns using arithmetic and `[column name]` references |
| Insights & reports | Export a Markdown analysis brief with metric snapshot, analyst notes and caveats |
| Learning roadmap | A practice sequence inspired by Google, Microsoft and Meta learning paths |

The included demonstration dataset is fictional and exists to make the interface usable immediately. Import a file to analyse your own data.

## Privacy and runtime

- Browser-only mode: parsing, cleaning and analysis run in the browser tab. ReData does not upload the dataset anywhere.
- Local engine: the data goes from the page to the engine on the same computer (`127.0.0.1`) and stays there. The engine only listens on the loopback address and checks the Host header. Every request needs a random token that the engine only gives to the ReData page it serves, so other websites cannot read your data through it.
- With Connections, the engine connects from your computer straight to the sources you configure (your database, Snowflake, S3, an API). Nothing passes through a ReData server.
- The engine's SQL lab is read-only (SELECT, DESCRIBE, SUMMARIZE, EXPLAIN). Changes go through Clean & transform and Formula builder.
- See [SECURITY.md](SECURITY.md) for the local-engine threat boundaries and vulnerability-reporting process.
- Browser-only mode loads SheetJS (Excel) and SQL.js (SQL lab) from public CDNs. Google Fonts are also remote. The engine needs no internet after its first-run install.

## Important analytical limitations

ReData provides practical first-pass analysis, not a guarantee that data or conclusions are correct. Review definitions, sampling, missingness, outliers, joins, units, privacy, test assumptions, and business context. The frequency-based “Segments & funnel” view is **not** an ordered conversion funnel unless your categories encode funnel stages. Welch's t-test assumes independent samples, and correlation/regression does not imply causation. Browser-only mode is capped at 10 lakh rows; use the local engine for larger data. On data above 20 lakh rows, the engine shows distinct counts for very high-cardinality columns (such as IDs) as estimates, marked with ≈. The scatter plot draws a random sample of 5,000 points, while correlation and regression use every row.

## Learning references

These are external providers; ReData is independent and is not affiliated with or endorsed by them.

- [Google Data Analytics Professional Certificate](https://www.coursera.org/professional-certificates/google-data-analytics)
- [Google Advanced Data Analytics Professional Certificate](https://www.coursera.org/professional-certificates/google-advanced-data-analytics)
- [Meta Marketing Analytics Professional Certificate](https://www.coursera.org/professional-certificates/facebook-marketing-analytics)
- [Microsoft Power BI Data Analyst](https://learn.microsoft.com/en-us/credentials/certifications/power-bi-data-analyst/)
- [Microsoft Learn](https://learn.microsoft.com/en-us/training/)

## Design direction

ReData uses a warm, light analytics-workbench aesthetic: a persistent sidebar, clear quality signals, readable charts and dense-but-breathable tool panels. The product direction was also laid out in a Higgsfield canvas: [ReData — Product UI direction](https://higgsfield.ai/canvas/a2d72e11-6257-47e5-bcd4-1e3465b4b5c7).


## Research and reproducibility

- [Technical report draft](docs/TECHNICAL_REPORT_DRAFT.md) — system scope and planned evaluation.
- [Claims and evidence register](docs/CLAIMS_AND_EVIDENCE.md) — distinguishes documented capabilities, project-reported figures, and claims that still require testing.
- [Benchmark protocol](docs/BENCHMARK_PROTOCOL.md) — repeatable test plan and evidence requirements.
- [Benchmark results](benchmarks/RESULTS.md) — every recorded run, generated from the raw result files in `benchmarks/results/`.
- [Sync benchmark](benchmarks/run_sync_benchmark.py) — full, append and upsert syncs through the real pipeline, each checked against the source.
- [Local-engine smoke benchmark](benchmarks/run_engine_smoke.py) — exercises the actual local-engine HTTP API, validates basic outputs, and records environment-specific timings.
- [Citation metadata](CITATION.cff) — software citation details, validated by the citation-metadata CI workflow.
- [Release and DOI readiness](docs/RELEASE_READINESS.md) — release gates, required human review, and the Zenodo archival sequence.
- [Release notes template](docs/RELEASE_NOTES_TEMPLATE.md) — evidence-first release notes with explicit limitations and DOI placeholders.


## Citing ReData

**Archived release:** ReData v0.1.0 — Analytics Workspace  
**DOI:** [10.5281/zenodo.23314956](https://doi.org/10.5281/zenodo.23314956)  
**Version record:** [Zenodo record](https://zenodo.org/records/23314956)  
**Source repository:** [theraghavraman/redata](https://github.com/theraghavraman/redata)

The DOI identifies the archived v0.1.0 release, which predates the `redata` package and command line. For citation, prefer the DOI for the exact archived version you used; use the repository link for the development version.


## Licensing and third-party notices

- Original ReData software source is licensed under the MIT License; see [LICENSE](LICENSE).
- Original documentation and report prose under `docs/` are licensed under [CC BY 4.0](docs/LICENSE), unless a file states otherwise.
- Third-party libraries and assets retain their own terms. See [Third-Party Notices and License Inventory](THIRD_PARTY_NOTICES.md) for the direct dependencies and browser-loaded assets identified so far.
- [Dependency, License, and SBOM Audit](docs/DEPENDENCY_AUDIT.md) — how to reproduce the automated Python dependency audit and interpret its evidence.
- The third-party inventory is an initial direct-dependency review, not a complete transitive-dependency SBOM. Before redistributing a packaged build, verify the exact resolved dependency versions and all bundled asset notices.
