# Design and Evaluation of ReData: A Browser-First Workspace for Data Analytics

**Author:** Raghav Raman  
**ORCID:** https://orcid.org/0009-0006-6026-0674  
**Software repository:** https://github.com/theraghavraman/redata  
**Document status:** Draft; empirical evaluation pending  
**Version under study:** To be recorded from a tagged release or exact Git commit before experiments

## Abstract

ReData is a software project intended to support data exploration and analysis through a browser-first workspace, with an optional local execution engine for workloads that may exceed browser resource constraints. The repository documentation describes data ingestion, profiling, transformation, querying, visualization, selected statistical operations, and data-source connections.

This draft defines a reproducible evaluation plan for assessing analytical correctness, resource consumption, responsiveness, and behavior across supported execution modes. It does not present new experimental results. Claims about performance, scale, correctness, and compatibility must be supported by recorded tests before being stated as findings.

## 1. Scope and motivation

Data-analysis workflows commonly involve importing data, inspecting its structure, assessing quality, transforming records, querying datasets, visualizing patterns, and communicating findings. ReData aims to bring selected parts of this workflow into a single workspace.

The purpose of this report is to document the system and establish an evidence-based evaluation. A unified interface alone does not establish analytical correctness, usability, scalability, or equivalence to other products.

## 2. System description

The repository README describes two execution modes:

- **Browser-only mode:** parsing and analysis take place within the browser tab, subject to browser and device resource constraints.
- **Local-engine mode:** a local execution path uses DuckDB for supported workloads.

The README also documents data import, data exploration, profiling and quality indicators, cleaning and transformation, visualization, SQL, descriptive statistics, selected hypothesis testing and regression functions, reporting, and database or file connections.

These are repository-documented capabilities, not independent verification. Before publication, the tested source version and each evaluated feature must be confirmed against code and test results.

## 3. Claims and evidence discipline

The companion [Claims and Evidence Register](CLAIMS_AND_EVIDENCE.md) records the current documentation-level status of major project claims and the evidence required to strengthen them. It distinguishes repository-described scope from implementation-level verification, measured findings, and independent reproduction. The register is not itself evidence that a feature passes tests; it is a guard against treating intended behavior or prior README figures as established results.

## 4. Research questions

**RQ1 — Analytical correctness:** Do supported ingestion, transformation, SQL, and statistical operations produce results consistent with independent reference calculations?

**RQ2 — Resource behavior:** How do processing time, peak memory where measurable, and responsiveness change as dataset size, width, missingness, and column cardinality change?

**RQ3 — Execution modes:** For workloads supported in both modes, how do browser-only and local-engine results and resource requirements compare?

**RQ4 — Failure behavior:** Which dataset and workload characteristics cause timeouts, errors, incorrect results, or resource exhaustion?

**RQ5 — Reproducibility:** Can another person reproduce the reported results using the recorded source version, environment, data, and commands?

## 5. Evaluation design

### 5.1 Record the environment

For every run, record:

- Exact Git commit SHA or release tag.
- Operating system and version.
- CPU, installed RAM, and relevant storage details.
- Browser and version for browser-only tests.
- Python and DuckDB versions for local-engine tests.
- Dependency versions, configuration, memory limits, and thread count.
- Dataset dimensions, file size, data types, missing-value rate, and cardinality.
- Workload, warm-up procedure, repetitions, timeout, and measurement method.

Do not combine results from materially different environments without labeling the differences.

### 5.2 Dataset design

Use synthetic datasets to control row count, column count, data types, missingness, duplicate rate, and cardinality. Use only data that is licensed for reuse and safe to publish. Do not commit private, confidential, or personally identifiable data.

Preserve the data-generation script, seed, and dataset checksum where practical so the input can be recreated and identified.

### 5.3 Workloads

Evaluate only operations confirmed to exist in the tested source version:

1. Import and profile data.
2. Preview, filter, sort, and paginate records.
3. Group, aggregate, and pivot data.
4. Apply supported cleaning and formula transformations.
5. Run representative SQL queries.
6. Compute selected descriptive statistics and statistical tests.
7. Render visualizations and record query time separately from rendering time.
8. Export results and check row counts and values.
9. Test supported data-source connections separately from local-file benchmarks.

For each workload, define expected outputs and compare them with an independent reference implementation or hand-verified small fixture.

### 5.4 Measurements

Record wall-clock duration, peak memory where a reliable measurement is available, output correctness, warnings, errors, timeouts, and crashes. Repeat timed operations and report the number of runs and a suitable summary such as median and range. Keep raw observations rather than recording only an average.

Define latency boundaries precisely. For example, distinguish file reading, parsing, profiling, query execution, rendering, and export instead of combining them into a single number.

### 5.5 Failure reporting

A failed run is a result. Record the input, configuration, observed failure, error message, and whether a retry changed the outcome. Do not omit failures from summaries or report unsupported workloads as successful.

## 6. Results

**Status: Initial bounded CI smoke run completed; full evaluation pending.** The first successful 100,000-row local-engine HTTP smoke run is recorded below and in [GitHub Actions run 38175393938](https://github.com/theraghavraman/redata/actions/runs/38175393938); its JSON is available in that run's artifact section. This is a single hosted-runner baseline, not an independent reproduction of the historical 10-million-row README timings. The broader workload matrix, repeat runs on controlled hardware, memory measurements, and independent reproduction remain pending.

| Evaluation item | Status | Evidence required |
|---|---|---|
| Import duration by dataset size | Measured only for the 100k and 1M CI smoke workloads | Multi-run measurements at target sizes on controlled hardware |
| Peak memory | Approximate sampled engine-process RSS recorded for one 1M-row run only; not a guaranteed peak | Reliable, repeated memory measurements with a stated method on a documented target machine |
| Query and transformation duration | SQL aggregate and page-request timings measured for the 100k and 1M smoke workloads only | Repeated measurements for representative query and transformation workloads |
| Analytical output correctness | Basic row/column counts, ID ranges, page contents, and one independent sum oracle passed for the smoke workloads | Broader independent fixtures for every supported operation and edge cases |
| Browser-only versus local-engine comparison | Not yet verified in this study | Equivalent supported workloads |
| Failure and timeout boundaries | Not yet verified in this study | Recorded failures and test conditions |
| Reproducibility by another operator | Not yet verified in this study | Reproduction log or independent review |

### 6.1 Initial CI local-engine smoke result

The first successful bounded smoke run used ReData commit `8d73fa1ac461fe4ac06affc36bfcb26905efb7ee` on a GitHub-hosted Linux runner. The run starts the real local engine, stages a generated CSV through its HTTP API, imports and profiles it, queries DuckDB, checks paginated rows, and confirms an unauthenticated status request receives HTTP 403.

| Measurement | Observed result |
|---|---:|
| Dataset | 100,000 rows × 10 columns |
| CSV size | 10,374,347 bytes (about 9.89 MiB) |
| Dataset SHA-256 | `9052b08359fe94a309091dbfc76328f6be9775b871507c840e15e66bef3b372a` |
| Stage local-path API | 30.936 ms |
| Import plus profiling | 272.050 ms |
| SQL aggregate query, 5 observations | 1.660, 1.177, 1.066, 1.043, 1.015 ms |
| Median SQL aggregate query | 1.066 ms |
| Five-row page API | 2.909 ms |
| Correctness | Row count, column count, ID range, first page row, and independent `SUM(value)` check passed |
| Security smoke check | Missing token rejected with HTTP 403 |

Environment: Python 3.14.8, DuckDB 1.5.6, ReData engine 1.1.0, Linux x86-64, four reported CPUs. The independently calculated expected sum was `499954165.3`; DuckDB returned `499954165.29999983`, within the script's declared floating-point tolerance.

These timings are specific to this run and measurement boundary. The SQL values include HTTP request/response overhead and are not pure DuckDB execution times. No peak-memory measurement was collected. This single 100,000-row run does not establish a 10-million-row capacity, cannot be directly compared with the historical README figures, and should not be generalized to other machines. The uploaded JSON artifact is the source of the observations; reruns and a controlled larger-dataset matrix are required before stronger conclusions.

The raw observation is preserved in [`benchmarks/results/ci-smoke-100k-8d73fa1.json`](../benchmarks/results/ci-smoke-100k-8d73fa1.json).

### 6.2 One-million-row CI smoke result

A second successful run processed 1,000,000 rows × 10 columns on the same reported GitHub-hosted runner family, using ReData commit `32fe7af4e46109b9ea5395abb0dca7318ca87456`. See [GitHub Actions run 38175438341](https://github.com/theraghavraman/redata/actions/runs/38175438341).

| Measurement | Observed result |
|---|---:|
| Dataset | 1,000,000 rows × 10 columns |
| CSV size | 104,750,872 bytes (about 99.9 MiB) |
| Dataset SHA-256 | `b228b4a2cc62504eb5a19517ce945e2d22de8d504d6714d64c25568f8009f561` |
| Stage local-path API | 44.256 ms |
| Import plus profiling | 1,827.525 ms |
| SQL aggregate query, 5 observations | 4.688, 3.476, 3.249, 3.053, 3.014 ms |
| Median SQL aggregate query | 3.249 ms |
| Five-row page API | 3.743 ms |
| Correctness | Row count, column count, ID range, first page row, and independent `SUM(value)` check passed |
| Security smoke check | Missing token rejected with HTTP 403 |

The independent expected sum was `4999995475.08`; DuckDB returned `4999995475.080004`, within the script's floating-point tolerance. The raw observation is preserved in [`benchmarks/results/ci-smoke-1m-32fe7af.json`](../benchmarks/results/ci-smoke-1m-32fe7af.json).

The 100k and 1M runs show the local-engine path completed the tested synthetic import/profile and query workload at both sizes on GitHub-hosted Linux runners. As a descriptive comparison only, row count increased 10×, import-plus-profile time increased about 6.72×, and median SQL request latency increased about 3.05×. This is not a reliable scaling law: these are single runs, exact host allocation may differ, and query timings include HTTP overhead. The results do **not** establish behavior at 10 million rows, other file formats, higher missingness/cardinality, different machines, or all ReData operations. Peak memory was not measured in those initial runs; a later 1M-row run records only an approximate sampled process RSS in Section 6.5.

These statuses do not mean a feature fails or succeeds; they mean that this report does not yet contain independently reproducible evidence for the relevant claim.

## 7. Known limitations and threats to validity

Performance depends on hardware, browser behavior, data shape, memory availability, caching, dependency versions, and workload design. A small set of workloads cannot establish universal scalability. Results from synthetic data may not generalize to real-world data.

Statistical functions must be evaluated against their assumptions and reference outputs. Correlation does not imply causation, and successful execution alone does not show that an analysis is appropriate for a particular business or research question.

The repository README contains performance figures and capacity descriptions. They are treated here as existing documentation claims, not as measurements independently reproduced by this report. Any such figures included in a final version must be traced to a specific source revision, test setup, and raw results.

## 8. Reproducibility package

Before the report is treated as a completed evaluation, publish or link:

- The exact source commit or release.
- Dataset-generation scripts and permitted test data.
- CI smoke-benchmark JSON artifact, with workflow URL, source commit and runner environment.
- Benchmark commands and configuration.
- Raw timing and resource logs.
- Analysis scripts used to summarize results.
- Expected/reference outputs and correctness checks.
- A description of failed or excluded runs.
- Dependency and environment details.

Record all changes to the protocol and explain deviations from the planned method.

## 9. Conclusion

This draft establishes a testable scope for documenting and evaluating ReData. No new performance, scalability, correctness, or independent-validation conclusions are made at this stage. Those conclusions remain pending execution of the protocol and review of the resulting evidence.

### 6.3 Ten-million-row, seven-column CI stress result

A larger smoke run passed on GitHub Actions at [run 38175528927](https://github.com/theraghavraman/redata/actions/runs/38175528927), using source commit `27e1126ad12f65ebfdb1122fd66a12f2693fa105`.

| Measurement | Observed result |
|---|---:|
| Dataset | 10,000,000 rows × 7 columns |
| CSV size | 719,145,429 bytes (about 685.7 MiB) |
| Dataset SHA-256 | `7143ef1af7b8db9877bc66f3695ecc9bbe8abc9209a352a815a993b1c4b27d22` |
| Stage local-path API | 24.510 ms |
| Import plus profiling | 8,242.526 ms |
| SQL aggregate query, 5 observations | 20.224, 14.136, 14.055, 14.608, 14.367 ms |
| Median SQL aggregate query | 14.367 ms |
| Five-row page API | 5.529 ms |
| Correctness | Row/column counts, ID range, first page row, and independent `SUM(value)` check passed |
| Security smoke check | Missing token rejected with HTTP 403 |

The independent expected sum was `49999986822.75`; DuckDB returned `49999986822.75003`, within the declared floating-point tolerance. The raw JSON is preserved in [`benchmarks/results/ci-smoke-10m-27e1126.json`](../benchmarks/results/ci-smoke-10m-27e1126.json).

This is meaningful evidence that the tested local-engine path completed this particular 10-million-row synthetic workload with seven columns on the recorded GitHub-hosted Linux runner. It does **not** reproduce the README's 10-million-row, 10-column claim: this dataset has seven columns, and its generation pattern differs from the historical input. No peak-memory measurement was collected. A separate 10-million-row, 10-column run has now passed; see Section 6.4. Its generated CSV is larger than the historical README input, and the runner, exact input, and tested source revision differ, so this is a reproduction of the row/column scale—not a reproduction of the historical timings.

### 6.4 Ten-million-row, ten-column CI stress result

The run at [GitHub Actions run 38175634773](https://github.com/theraghavraman/redata/actions/runs/38175634773) passed on commit `efaf0aad3df0be06652d42ea50dc89d6a1a6f80b`. This matches the README's stated row and column counts, but uses a newly generated deterministic dataset rather than the historical input.

| Measurement | Observed result |
|---|---:|
| Dataset | 10,000,000 rows × 10 columns |
| CSV size | 1,057,509,670 bytes (about 1.057 GB decimal) |
| Dataset SHA-256 | `233872c4ce666d82ed1645a02704522fc062dcb610cf4048495c3cff90e650e3` |
| Stage local-path API | 34.394 ms |
| Import plus profiling | 12,778.942 ms |
| SQL aggregate query, 5 observations | 32.243, 33.858, 17.859, 16.236, 23.899 ms |
| Median SQL aggregate query | 23.899 ms |
| Five-row page API | 7.203 ms |
| Correctness | Row/column counts, ID range, first page row, and independent `SUM(value)` check passed |
| Security smoke check | Missing token rejected with HTTP 403 |

The independent expected sum was `49999986822.75`; DuckDB returned `49999986822.7498`, within the declared floating-point tolerance. The raw JSON is preserved in [`benchmarks/results/ci-smoke-10m-10col-efaf0aa.json`](../benchmarks/results/ci-smoke-10m-10col-efaf0aa.json).

This run establishes that the tested code completed a deterministic 10-million-row, 10-column CSV import/profile and query smoke workload on the recorded GitHub-hosted Linux runner. It does not establish the historical README's reported 723 MB file behavior or its timings, because the generated file here is about 1.057 GB and the exact prior input, source revision, and machine conditions are unavailable. The result is one run; no peak-memory measurement was collected. The large benchmark is now configured for manual dispatch, while routine pushes run the smaller CI baseline to avoid repeatedly running expensive stress tests.

### 6.5 Repeated one-million-row run with sampled process RSS

After adding repeated import/profile measurements and an approximate RSS sampler, a further run passed at [GitHub Actions run 38175832918](https://github.com/theraghavraman/redata/actions/runs/38175832918), source commit `b3714c1a83c52609483a89fa5d70c382c77c0f3b`.

| Measurement | Observed result |
|---|---:|
| Dataset | 1,000,000 rows × 10 columns; 104,750,872 bytes |
| Stage API, three observations | 56.211, 63.417, 53.053 ms |
| Stage API median | 56.211 ms |
| Import plus profiling, three observations | 2,140.523, 2,183.861, 2,171.758 ms |
| Import plus profiling median | 2,171.758 ms |
| Sampled peak engine-process RSS | 624,344 KiB (about 609.7 MiB) |
| SQL aggregate HTTP request, five observations | 5.211, 4.286, 4.214, 5.995, 4.155 ms |
| Median SQL aggregate HTTP request | 4.286 ms |
| Five-row page request | 4.762 ms |
| Correctness and authentication checks | Passed |

The memory value is an approximate Linux process RSS sampled from `/proc/<pid>/status` every 50 ms while the engine was serving the workload. It is not DuckDB's internal allocation, total system memory, or a guaranteed peak; brief spikes may be missed. The import repetitions use the same file and engine process, so cache state may differ between repetitions. The raw JSON is preserved in [`benchmarks/results/ci-repeat-1m-b3714c1.json`](../benchmarks/results/ci-repeat-1m-b3714c1.json).

This adds repeated observations and a documented memory estimate for a 1M-row workload. It does not provide repeated 10M-row import timings or replace a controlled multi-machine study.\n\n### 6.6 Expanded one-million-row correctness run

A further CI run at [workflow run 38175950861](https://github.com/theraghavraman/redata/actions/runs/38175950861), commit `e92a050e0e4d7ffaee09ce2c2ec89c1bba5b3eab`, extended the 1M workload with an independent grouped-aggregation oracle and a read-only SQL mutation check. It passed all checks.

| Measurement | Observed result |
|---|---:|
| Import plus profiling, 3 observations | 2,223.304, 2,226.987, 2,282.200 ms |
| Import plus profiling median | 2,226.987 ms |
| Sampled engine-process RSS | 653,976 KiB (about 638.6 MiB) |
| SQL aggregate request, 5 observations | 5.185, 4.542, 4.408, 4.277, 4.322 ms |
| Median SQL aggregate request | 4.408 ms |
| Page request for 5 rows | 4.600 ms |
| Grouped aggregation | All 1,000 categories returned; category_0 sum matched independent Python calculation |
| SQL mutation protection | `DROP TABLE data` rejected; row count remained unchanged |
| API authentication | Missing token rejected with HTTP 403 |

The dataset is the same deterministic 1,000,000-row, 10-column CSV as Section 6.5 (`b228b4a2cc62504eb5a19517ce945e2d22de8d504d6714d64c25568f8009f561`). The sampled RSS is approximate Linux process RSS, not a guaranteed peak. The raw JSON is preserved in [`benchmarks/results/ci-repeat-1m-e92a050.json`](../benchmarks/results/ci-repeat-1m-e92a050.json). The repeated import observations are within a relatively narrow range on this runner, but that is not a substitute for independent reproduction or a controlled machine study.\n\n## Change history

- Initial draft: defined research questions, scope, evaluation design, evidence requirements, and unverified-result labels.
- Claims-and-evidence register added to distinguish documentation-level claims from measured and independently reproduced findings.
- Standard-library regression tests added for the synthetic dataset generator.
- Added a local-engine HTTP smoke benchmark and CI workflow; successful 100,000-row, 1,000,000-row, and 10,000,000-row (7-column) hosted-runner results are recorded in Sections 6.1–6.3, with raw JSON committed under `benchmarks/results/`. The 10M/10-column run is now recorded in Section 6.4. Repeated 1M-row runs with sampled process RSS are recorded in Sections 6.5–6.6, with expanded aggregation and SQL read-only checks in Section 6.6. These results improve the baseline but do not independently reproduce the historical README timings.


## Licensing and attribution

The original ReData software source is licensed under the MIT License in the repository-root `LICENSE`. The original prose and report materials in this directory are licensed under CC BY 4.0 unless a file states otherwise; see [LICENSE](LICENSE). Third-party software and assets retain their own licenses. The repository's [Third-Party Notices and License Inventory](../THIRD_PARTY_NOTICES.md) records the currently identified browser-loaded libraries and direct Python dependencies, including attribution notes for SheetJS Community Edition.

This inventory is not yet a complete version-resolved SBOM: dependency constraints are ranges, transitive packages may vary, and exact bundled font files must be checked for a packaged release. The report makes no claim that all dependency licensing has been legally audited. Before a release is redistributed, generate a version-resolved SBOM, verify upstream license metadata and preserve all applicable notices.


## Synthetic benchmark artifact

The repository now includes [a deterministic CSV dataset generator](../benchmarks/generate_dataset.py) and [usage instructions](../benchmarks/README.md). The generator records its parameters, output size, and SHA-256 sidecar so input data can be identified and recreated. It does not execute ReData, verify analytical outputs, or produce performance findings. Results remain pending until the documented workloads are run against a pinned source revision and their raw observations are retained.
