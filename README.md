# ReData — Analytics Workspace

**ReData is a browser-first workspace for the complete data-analysis journey:** import, inspect, profile, clean, query, summarize, visualize, test, model, and communicate.

## Open the app

ReData runs in two ways:

| | Browser-only | With the local engine |
| --- | --- | --- |
| How to open | Open `index.html`, or the GitHub Pages site | Run `start-engine.bat` (Windows) or `./start-engine.sh` (macOS / Linux) |
| Where the data is processed | Inside the browser tab | DuckDB on your own computer |
| Practical size | Up to 10 lakh rows (1,000,000) | Crores of rows (tested with 1 crore rows / 723 MB CSV) |
| File types | CSV, TSV, TXT, JSON / NDJSON, XLSX / XLS | Same, plus Parquet and load-by-path |
| Install | Nothing | Python 3.9+ (DuckDB is installed automatically on first run) |

GitHub Pages: Settings → Pages → Deploy from a branch → `main` → `/ (root)`.

### Large files: the local engine

The browser keeps every row as a JavaScript object, so a tab runs out of memory and freezes long before 1 crore rows. The local engine moves the data into [DuckDB](https://duckdb.org) on your machine. The page then only receives what it shows: one page of rows, one chart's totals, one table of statistics.

1. Install Python 3.9 or newer (on Windows tick **Add python.exe to PATH**).
2. Double-click `start-engine.bat` (Windows) or run `./start-engine.sh` (macOS / Linux). The first run creates `engine/.venv` and installs DuckDB; later runs start in a second.
3. Your browser opens `http://127.0.0.1:8765`. The sidebar shows **Local engine connected**.
4. Import a file, or paste its full path under **Load a file from this computer by path** (fastest for very large files; nothing is copied).

Keep the engine window open while you work, and press Ctrl+C in it to stop. The dataset stays in `engine/workspace/` and is restored next time you start the engine.

Options: `--port 9000`, `--memory-limit 6GB`, `--threads 4`, `--workspace D:\redata-work`, `--no-browser`.

Measured on a small 2-core cloud machine with a 1 crore row, 10 column CSV (a typical laptop is faster):

| Step | Time |
| --- | --- |
| Import and profile every column | ~40 s |
| Switch between any tabs | ~0.3 s |
| Page, sort or filter the data explorer | 0.4–1.7 s |
| Charts, t-test, regression, SQL | 0.3–1.5 s |
| Group by 20 lakh distinct values | ~10 s |
| Fill / dedupe / formula across all rows | 17–40 s |
| Export the full dataset to CSV | ~9 s |

## What is included

| Workspace | What it does |
| --- | --- |
| Overview | Live dataset summary, completeness and duplicate counts, quick links to tools |
| Import data | Local import for CSV, TSV, TXT, JSON / NDJSON and Excel XLSX/XLS (plus Parquet and load-by-path with the local engine) |
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
- The engine's SQL lab is read-only (SELECT, DESCRIBE, SUMMARIZE, EXPLAIN). Changes go through Clean & transform and Formula builder.
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
