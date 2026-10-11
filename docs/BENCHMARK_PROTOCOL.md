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
