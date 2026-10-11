# ReData — Analytics Workspace

**ReData is a browser-first workspace for the complete data-analysis journey:** import, inspect, profile, clean, query, summarize, visualize, test, model, and communicate.

## Open the app

The app is a static website. Open `index.html` locally or publish the repository using **GitHub Pages** (Settings → Pages → Deploy from a branch → `main` → `/ (root)`). No backend service is required for the core features.

## What is included

| Workspace | What it does |
| --- | --- |
| Overview | Live dataset summary, completeness and duplicate counts, quick links to tools |
| Import data | Local import for CSV, TSV, TXT, JSON / NDJSON and Excel XLSX/XLS; Excel worksheet picker; date-aware Excel parsing; selectable CSV / TSV / TXT encoding |
| Data explorer | Preview, search, column sorting and CSV export |
| Profile & quality | Inferred column types, missingness, distinct values, numeric ranges and completeness indicators |
| Clean & transform | Drop incomplete rows, fill missing values, remove exact duplicate rows, normalize text, remove columns |
| Visualization | Aggregated bar, line and dot-plot charts; export chart as SVG |
| SQL lab | In-memory SQLite queries against a table named `data` |
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

- Core parsing, cleaning and analysis run in the browser tab. ReData itself does not upload the selected dataset to a ReData backend.
- Excel import loads the SheetJS browser library from a public CDN. SQL loads SQL.js / WebAssembly lazily from a public CDN. Google Fonts are also remote.
- The SQL lab creates a new in-memory SQLite snapshot from the active working data each time a query runs.
- Data is held in memory for the open tab and is not automatically stored remotely.
- This static version does not replace a governed warehouse, enterprise BI system, statistical review, or a production ETL platform.

## Important analytical limitations

ReData provides practical first-pass analysis, not a guarantee that data or conclusions are correct. Review definitions, sampling, missingness, outliers, joins, units, privacy, test assumptions, and business context. The frequency-based “Segments & funnel” view is **not** an ordered conversion funnel unless your categories encode funnel stages. Welch's t-test assumes independent samples, and correlation/regression does not imply causation. Performance is browser- and memory-dependent; import is capped at 250,000 rows in this preview.

## Learning references

These are external providers; ReData is independent and is not affiliated with or endorsed by them.

- [Google Data Analytics Professional Certificate](https://www.coursera.org/professional-certificates/google-data-analytics)
- [Google Advanced Data Analytics Professional Certificate](https://www.coursera.org/professional-certificates/google-advanced-data-analytics)
- [Meta Marketing Analytics Professional Certificate](https://www.coursera.org/professional-certificates/facebook-marketing-analytics)
- [Microsoft Power BI Data Analyst](https://learn.microsoft.com/en-us/credentials/certifications/power-bi-data-analyst-associate/)
- [Microsoft Learn](https://learn.microsoft.com/en-us/training/)

## Design direction

ReData uses a warm, light analytics-workbench aesthetic: a persistent sidebar, clear quality signals, readable charts and dense-but-breathable tool panels. The product direction was also laid out in a Higgsfield canvas: [ReData — Product UI direction](https://higgsfield.ai/canvas/a2d72e11-6257-47e5-bcd4-1e3465b4b5c7).
