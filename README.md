# ReData — Make data make sense

ReData is a browser-first analytics workspace for the data analysis lifecycle: discover, prepare, query, analyze, visualize and communicate.

## Features
- Responsive overview and a 40+ capability directory spanning spreadsheets, SQL, Python/R, BI, data engineering, statistics, governance and advanced analytics.
- CSV/TSV upload and a row/column preview with data-type heuristics.
- Data quality audit: missing-value counts, completeness, unique values and exact duplicate detection.
- Focused data cleaning: fill or drop missing values, remove exact duplicate rows, trim or lowercase text, reset to source, export cleaned CSV.
- In-browser SQLite SQL Lab using sql.js (WebAssembly) and exportable query results.
- Chart builder using Chart.js: bar, line, pie, doughnut and scatter charts; export chart as PNG.
- Descriptive numerical summaries and categorical frequency tables.
- Learning paths inspired by Google, Microsoft and Meta professional certificate curricula, with direct official learning links.
- Portfolio project briefs, local study checklist and project notes.
- No app server required for the main features. Uploaded data stays in the browser session; study progress and notes use local browser storage.

## Run locally
Open `index.html` in a modern browser. The CSV parser, SQLite WASM and chart library are loaded from jsDelivr, so core tools need an internet connection on first load. Google Fonts are optional.

## Publish with GitHub Pages
1. Open the repository's **Settings → Pages**.
2. Under **Build and deployment**, choose **Deploy from a branch**.
3. Choose branch `main` and folder `/ (root)`, then Save.
4. GitHub will show the published URL in the Pages section after its workflow completes.

This feature branch is ready for review. Merge it into `main` to use the above publishing steps against the default branch.

## Privacy and limitations
Core file parsing, profiling, cleaning, SQL, calculations and chart generation run on the client. Files are not uploaded by this page. Third-party scripts, font downloads, and external learning links still require network requests. Avoid opening sensitive datasets on an untrusted or shared device. This static version does not claim to replace full platforms such as Power BI, Tableau, Python environments or cloud warehouses; the directory links to learning resources and the browser tools cover common starter workflows.

ReData is an independent project and is not affiliated with Google, Microsoft, Meta or Coursera. Their course structures, URLs and fees may change.
