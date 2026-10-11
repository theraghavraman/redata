# ReData Benchmark Protocol

**Status:** Planned protocol; no results are implied by this document.  
**Repository:** https://github.com/theraghavraman/redata  
**ORCID:** https://orcid.org/0009-0006-6026-0674

## Before testing

- [ ] Record the exact Git commit SHA and working-tree state.
- [ ] Record OS, CPU, RAM, browser, Python, DuckDB, and dependency versions.
- [ ] Confirm that the selected feature exists in the tested version.
- [ ] Prepare data-generation scripts and preserve seeds/checksums.
- [ ] Define expected outputs before timing the operation.
- [ ] Keep private or confidential data out of public artifacts.

## Workload matrix

Run only workloads supported by the tested version. Include small fixtures for correctness before scaling up.

| Workload | Input characteristics to vary | Record |
|---|---|---|
| Import and profiling | Rows, columns, types, missingness | Duration, result counts, errors, memory if measurable |
| Filter and sort | Rows, predicate selectivity, sort key | Duration, output correctness, errors |
| Grouping and aggregation | Rows, group cardinality, aggregate | Duration, group count, reference comparison |
| Transformations | Missing values, duplicates, formula cases | Duration, changed row/column counts, reference comparison |
| SQL | Query shape, input size | Duration, output correctness, errors |
| Statistics | Sample size and known fixture distributions | Result, reference calculation, assumptions |
| Visualization | Input size and chart type | Query duration and render duration separately |
| Export | Rows, columns, output format | Duration, output size, round-trip checks |

## Run log template

Create one record per run with these fields:

- Test ID
- Date and time
- Git commit SHA
- Operating system and hardware
- Browser/runtime and dependency versions
- Dataset generator, seed, dimensions, file size, checksum
- Workload and parameters
- Warm-up or cache state
- Run number
- Start/end timestamps or elapsed time
- Peak-memory method and observed value, if reliable
- Expected result and observed result
- Pass/fail and reason
- Error message, timeout, or crash details
- Notes and deviations from protocol

## Reporting rules

1. Preserve raw results; do not report only aggregated summaries.
2. State the number of repetitions and summarize variability.
3. Do not compare timings from different environments without qualification.
4. Separate parsing, profiling, computation, rendering, and export where possible.
5. Report failures and timeouts.
6. Treat any README performance figure as unverified until its source and conditions are reproducible.
7. Do not claim support for a row count or file size based on a target or a single successful run without describing the test conditions.
8. Include reference calculations for correctness; speed alone is not sufficient.

## Completion criteria

The report can move from draft to evaluated status only when the tested version, data, environment, raw observations, correctness checks, failures, and reproducibility instructions are documented. Independent reproduction should be labeled separately from the author's own test runs.


## Licensing and publication checks

- Cite the tested ReData source revision and use the repository's applicable software/documentation license notices.
- Ensure generated datasets and benchmark artifacts are safe to publish and have compatible licenses.
- For redistribution, review [Third-Party Notices](../THIRD_PARTY_NOTICES.md), resolve dependency versions, and audit transitive/native dependencies and bundled assets. The current inventory is not a complete SBOM.


## Synthetic dataset generation

Use the repository's standard-library generator to create repeatable CSV inputs:

```bash
python benchmarks/generate_dataset.py --output /tmp/redata-100k.csv --rows 100000 --columns 10 --seed 20261012 --cardinality 1000 --missing-rate 0.01
```

The generator emits a JSON sidecar with parameters, byte size, and SHA-256. Retain the CSV and sidecar for each run. See [benchmark assets and usage](../benchmarks/README.md). The generator creates inputs only; it does not run ReData or establish performance results. The companion [local-engine smoke runner](../benchmarks/run_engine_smoke.py) executes a bounded real-engine API workload and records its measurements and correctness checks. Existing CI observations are preserved in [the results directory](../benchmarks/results/).


## Local-engine smoke baseline

A bounded integration run is now available via `benchmarks/run_engine_smoke.py`. It starts the local engine, stages and imports a generated CSV, validates row/column counts and an independent aggregate result, exercises pagination, and checks authentication. GitHub Actions uploads the JSON measurements as an artifact. Record the workflow URL, commit SHA, runner and artifact before citing any numbers. This smoke test is not a substitute for the full workload matrix or a reproduction of historical 10-million-row claims.
