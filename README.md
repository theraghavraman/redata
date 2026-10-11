# ReData — Analytics Workspace

**ReData is a browser-first workspace for the complete data-analysis journey:** import, inspect, profile, clean, query, summarize, visualize, test, model, and communicate.

## Open the app

The app is a static website with no backend. Open `index.html` in a modern browser, or publish the repository with **GitHub Pages**. The Pages workflow in `.github/workflows/pages.yml` runs the tests and then deploys the site on each push to `main`. Set **Settings → Pages → Build and deployment → Source** to **GitHub Actions** once.

## What is included

| Workspace | What it does |
| --- | --- |
| Overview | Live dataset summary, completeness and duplicate counts, quick links to tools |
| Import data | Local import for CSV, TSV, TXT, JSON / NDJSON and Excel XLSX/XLS. Choose the text encoding (UTF-8 or Windows-1252) and the Excel worksheet |
| Data explorer | Preview, search, column sorting and CSV export |
| Profile & quality | Inferred column types, missingness, distinct values, numeric ranges and completeness indicators |
| Clean & transform | Drop incomplete rows, fill missing values, remove exact duplicate rows, normalize text, remove columns. **Undo** the last change, **restore** the data as imported, and see a **change log** |
| Visualization | Aggregated bar, line and dot-plot charts; export chart as SVG |
| SQL lab | SQLite queries against a table named `data`. Each query runs in a transaction that is rolled back, so SQL never changes the dataset |
| Descriptive statistics | Count, mean, median, sample standard deviation, quartiles and IQR outlier screening |
| Hypothesis testing | Welch two-sample t-test with the two-sided p-value, degrees of freedom, a 95% confidence interval for the difference, and Cohen’s d |
| Correlation & regression | Pearson correlation, least-squares slope and intercept, R², and the slope’s standard error, t statistic and p-value |
| Group by & pivot | Group categorical values with sum, mean, median and counts |
| Category breakdown | Share of records in each category. This is a frequency view, not an ordered funnel |
| Formula builder | Derived numeric columns using arithmetic and `[column name]` references. Each new column is logged |
| Insights & reports | Export a Markdown analysis brief with the metric snapshot, the data preparation log, analyst notes and caveats |
| Learning roadmap | A practice sequence inspired by Google, Microsoft and Meta learning paths |

The included demonstration dataset is fictional and exists to make the interface usable immediately. Import a file to analyse your own data.

## Privacy and runtime

- Everything runs in the browser tab. ReData makes no network requests when you use it, and it does not upload your data to any server.
- The libraries and fonts are bundled in the repository, so the app works offline:
  - `vendor/xlsx/` — SheetJS 0.18.5 (Excel reading), Apache-2.0, with its licence file.
  - `vendor/sql.js/` — sql.js 1.8.0 (SQLite), MIT, with its licence file. The asm.js build is used so the app also works when opened directly from disk; it is slower than the WebAssembly build on very large imports.
  - `fonts/` — DM Sans, DM Mono and Manrope (latin subsets, SIL Open Font License 1.1), with licence files.
- The SQL lab rebuilds its in-memory SQLite snapshot only when the data has changed.
- Data is held in memory for the open tab and is not stored between visits.
- This static version does not replace a governed warehouse, enterprise BI system, statistical review, or a production ETL platform.

## Important analytical limitations

ReData provides practical first-pass analysis, not a guarantee that data or conclusions are correct. Review definitions, sampling, missingness, outliers, joins, units, privacy, test assumptions, and business context. The "Category breakdown" view is a frequency table, not an ordered conversion funnel. Welch's t-test assumes independent samples, and correlation/regression does not imply causation. Performance depends on the browser and its memory; import is capped at 250,000 rows in this preview.

## Development and tests

```bash
npm install
npm run test:unit        # statistics, parsing and formula tests (Node only)
npx playwright-core install chromium   # once, for the browser tests
npm run test:e2e         # opens index.html in headless Chromium and runs the main workflows
```

Set `CHROMIUM_PATH` to use a specific Chromium build for `test:e2e`. `npm run fixtures` regenerates the Excel fixture.

- `js/core.js` holds the pure parsing and statistics functions. It has no DOM access, so it can be tested directly.
- The reference values in `tests/core.test.mjs` were computed with SciPy 1.18.1 (`ttest_ind` with `equal_var=False`, `linregress`, `t.ppf`, `betainc`).

## Learning references

These are external providers; ReData is independent and is not affiliated with or endorsed by them.

- [Google Data Analytics Professional Certificate](https://www.coursera.org/professional-certificates/google-data-analytics)
- [Google Advanced Data Analytics Professional Certificate](https://www.coursera.org/professional-certificates/google-advanced-data-analytics)
- [Meta Marketing Analytics Professional Certificate](https://www.coursera.org/professional-certificates/facebook-marketing-analytics)
- [Microsoft Power BI Data Analyst](https://learn.microsoft.com/en-us/credentials/certifications/power-bi-data-analyst-associate/)
- [Microsoft Learn](https://learn.microsoft.com/en-us/training/)

## Design direction

ReData uses a warm, light analytics-workbench aesthetic: a persistent sidebar, clear quality signals, readable charts and dense-but-breathable tool panels. The product direction was also laid out in a Higgsfield canvas: [ReData — Product UI direction](https://higgsfield.ai/canvas/a2d72e11-6257-47e5-bcd4-1e3465b4b5c7).
