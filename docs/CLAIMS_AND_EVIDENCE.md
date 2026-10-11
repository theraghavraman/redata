# ReData Claims and Evidence Register

**Status:** Initial documentation audit; implementation-level verification and empirical evaluation are pending.  
**Audit date:** 2026-10-12  
**Repository:** https://github.com/theraghavraman/redata  
**Author:** Raghav Raman — ORCID https://orcid.org/0009-0006-6026-0674

## Purpose

This register separates (1) project scope described in the repository, (2) claims that have supporting artifacts, and (3) claims that still require execution-based evidence. It is intended to prevent documented features or historical measurements from being mistaken for independently verified results.

This is a documentation-level review of the repository's current README and research materials. It is **not** a complete source-code audit, security review, usability study, or independent reproduction.

## Claim register

| Claim area | Current basis | Permitted wording now | Evidence required for a stronger claim |
|---|---|---|---|
| Product scope | README describes a browser-first analytics workspace and optional local DuckDB engine | "ReData is designed as a browser-first data analytics workspace with an optional local execution engine." | Confirm current entry points, execution paths, and supported operations against code and smoke tests |
| Import and file formats | README lists CSV, TSV, TXT, JSON/NDJSON, XLSX/XLS and local-engine Parquet/path loading | "The README documents these import paths." | Format-by-format fixtures, malformed-input tests, row/column counts, type and date checks, and recorded results |
| Profiling, cleaning, SQL, statistics and charts | README lists these workspace features | "The project includes documented interfaces for..." | Tests comparing outputs to independent reference values, including edge cases and error behavior |
| Database and API connections | README describes local-engine connections and scheduled sync modes | "The README documents connection and sync workflows." | Integration tests against controlled fixtures or test services; tests for pagination, incremental cursors, upserts, secrets handling, retries and failure logs |
| Browser-only row capacity | README states a practical limit of up to 1,000,000 rows | Treat as a documented operating guideline, not a universal capacity guarantee | Pinned browser/device, datasets, repeat runs, memory observations, correctness checks and failure boundaries |
| Local-engine large-file capacity | README reports a 10-million-row / 723 MB CSV test | Treat as a project-reported test claim until its environment, input, exact commit and raw logs are available | Re-run on a pinned commit; publish dataset checksum, environment, commands, raw timings, memory method, correctness checks and failures |
| Performance figures | README contains historical timings; a 100,000-row CI smoke run now exercises the real local-engine HTTP API | Keep historical README figures labeled "project-reported; not independently reproduced". The 100,000-row result is an environment-specific baseline only. | Reproduce each historical workload separately and publish raw repeated observations with precise timing boundaries; scale up on controlled hardware |
| Analytical correctness | Report's RQ1 requires independent reference comparisons; no results are recorded yet | Do not claim correctness from successful rendering or execution alone | Fixed fixtures with expected outputs, independent calculations, tolerances and explicit pass/fail results |
| Comparative claims | No controlled comparison with Tableau, Power BI, or other tools is established by this report | Do not claim parity, superiority, or equivalent features | Predefined representative tasks, comparable versions/environments, clear criteria and reproducible measurements |
| Research impact | Repository and report are public artifacts; no citation or adoption evidence is established here | Describe the project and its intended contribution, not proven impact | Verifiable external citations, independent use, review, or other attributable evidence |

## Initial technical contribution statement

ReData is an open-source effort to consolidate selected data-ingestion, inspection, transformation, querying, visualization and reporting workflows in a browser-oriented workspace, with an optional local DuckDB engine for supported workloads. The project is evaluating correctness, resource behavior, responsiveness, execution-mode differences and reproducibility.

This is a scope statement, not a claim that all listed operations have passed independent tests or that ReData is equivalent or superior to commercial analytics products.


## Initial execution evidence

A bounded 100,000-row smoke benchmark passed on GitHub Actions at [run 38175393938](https://github.com/theraghavraman/redata/actions/runs/38175393938), source commit `8d73fa1ac461fe4ac06affc36bfcb26905efb7ee`. The generated CSV was 10,374,347 bytes. The run measured 272.050 ms for import plus profiling, 1.066 ms median for five SQL aggregate HTTP requests, and 2.909 ms for a five-row page request. It validated row/column counts, ID range, an independent sum check, and rejection of an unauthenticated status request. Full environment and checksum details are in the technical report's Section 6.1 and the workflow's JSON artifact.

A separate 1,000,000-row CI smoke benchmark also passed at [run 38175438341](https://github.com/theraghavraman/redata/actions/runs/38175438341), with import plus profiling measured at 1,827.525 ms, median SQL aggregate HTTP latency at 3.249 ms across five requests, and the correctness/auth checks passing. Raw observations are preserved in [the 1M JSON result](../benchmarks/results/ci-smoke-1m-32fe7af.json). Both results are environment-specific single-run baselines and do not reproduce the README's historical 10-million-row timings.

## Minimum evidence package for performance findings

For each reported workload, retain:

1. Exact Git commit SHA and clean/dirty working-tree status.
2. Operating system, CPU, installed RAM, browser/runtime and dependency versions.
3. Dataset-generation command, seed, dimensions, byte size and SHA-256 checksum.
4. Workload definition and timing boundaries.
5. Warm-up procedure and all individual repetitions, not only an average.
6. Correctness checks against a defined reference output.
7. Memory-measurement method and observed value, where reliable.
8. Errors, timeouts, crashes, retries and deviations from protocol.
9. Analysis script or explicit calculations used to summarize the observations.

Use medians and ranges for repeated timings unless a different summary is justified. Keep query time separate from parsing, profiling, rendering and export wherever possible. Do not omit failed runs.

## Publication gates

- [ ] Verify the documented feature inventory against current code.
- [ ] Add automated correctness tests for representative analytical operations.
- [ ] Run the benchmark protocol against a pinned source revision.
- [ ] Preserve raw logs and dataset sidecars.
- [ ] Resolve the dependency and bundled-asset license inventory for the intended release.
- [ ] Revise the report's results and limitations from the recorded evidence.
- [ ] Ask another person to reproduce at least the key workloads before describing them as independently reproduced.

## Related artifacts

- [Technical report draft](TECHNICAL_REPORT_DRAFT.md)
- [Benchmark protocol](BENCHMARK_PROTOCOL.md)
- [Benchmark generator and instructions](../benchmarks/README.md)
- [Third-party notices and license inventory](../THIRD_PARTY_NOTICES.md)
- [Software citation metadata](../CITATION.cff)
