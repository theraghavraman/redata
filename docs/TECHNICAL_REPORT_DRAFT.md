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

**Status: Pending execution and verification.**

| Evaluation item | Status | Evidence required |
|---|---|---|
| Import duration by dataset size | Not yet verified in this study | Raw timing logs and environment |
| Peak memory | Not yet verified in this study | Documented measurement method |
| Query and transformation duration | Not yet verified in this study | Repeated workload measurements |
| Analytical output correctness | Not yet verified in this study | Independent reference comparisons |
| Browser-only versus local-engine comparison | Not yet verified in this study | Equivalent supported workloads |
| Failure and timeout boundaries | Not yet verified in this study | Recorded failures and test conditions |
| Reproducibility by another operator | Not yet verified in this study | Reproduction log or independent review |

These statuses do not mean a feature fails or succeeds; they mean that this report does not yet contain independently reproducible evidence for the relevant claim.

## 7. Known limitations and threats to validity

Performance depends on hardware, browser behavior, data shape, memory availability, caching, dependency versions, and workload design. A small set of workloads cannot establish universal scalability. Results from synthetic data may not generalize to real-world data.

Statistical functions must be evaluated against their assumptions and reference outputs. Correlation does not imply causation, and successful execution alone does not show that an analysis is appropriate for a particular business or research question.

The repository README contains performance figures and capacity descriptions. They are treated here as existing documentation claims, not as measurements independently reproduced by this report. Any such figures included in a final version must be traced to a specific source revision, test setup, and raw results.

## 8. Reproducibility package

Before the report is treated as a completed evaluation, publish or link:

- The exact source commit or release.
- Dataset-generation scripts and permitted test data.
- Benchmark commands and configuration.
- Raw timing and resource logs.
- Analysis scripts used to summarize results.
- Expected/reference outputs and correctness checks.
- A description of failed or excluded runs.
- Dependency and environment details.

Record all changes to the protocol and explain deviations from the planned method.

## 9. Conclusion

This draft establishes a testable scope for documenting and evaluating ReData. No new performance, scalability, correctness, or independent-validation conclusions are made at this stage. Those conclusions remain pending execution of the protocol and review of the resulting evidence.

## Change history

- Initial draft: defined research questions, scope, evaluation design, evidence requirements, and unverified-result labels.
- Claims-and-evidence register added to distinguish documentation-level claims from measured and independently reproduced findings.
- Standard-library regression tests and a GitHub Actions workflow added for the synthetic dataset generator. These tests do not evaluate ReData application performance.


## Licensing and attribution

The original ReData software source is licensed under the MIT License in the repository-root `LICENSE`. The original prose and report materials in this directory are licensed under CC BY 4.0 unless a file states otherwise; see [LICENSE](LICENSE). Third-party software and assets retain their own licenses. The repository's [Third-Party Notices and License Inventory](../THIRD_PARTY_NOTICES.md) records the currently identified browser-loaded libraries and direct Python dependencies, including attribution notes for SheetJS Community Edition.

This inventory is not yet a complete version-resolved SBOM: dependency constraints are ranges, transitive packages may vary, and exact bundled font files must be checked for a packaged release. The report makes no claim that all dependency licensing has been legally audited. Before a release is redistributed, generate a version-resolved SBOM, verify upstream license metadata and preserve all applicable notices.


## Synthetic benchmark artifact

The repository now includes [a deterministic CSV dataset generator](../benchmarks/generate_dataset.py) and [usage instructions](../benchmarks/README.md). The generator records its parameters, output size, and SHA-256 sidecar so input data can be identified and recreated. It does not execute ReData, verify analytical outputs, or produce performance findings. Results remain pending until the documented workloads are run against a pinned source revision and their raw observations are retained.
