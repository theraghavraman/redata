# ReData benchmarks

This directory holds the benchmark scripts, the raw result of every recorded run, and a results page built from them.

| What | Where |
| --- | --- |
| Results, as tables | [RESULTS.md](RESULTS.md) |
| Raw result of each run (JSON) | [results/](results/) |
| Sync benchmark: full, append and upsert from SQLite into staging | `run_sync_benchmark.py` |
| Engine benchmark: CSV import, profile and SQL over the HTTP API | `run_engine_smoke.py` |
| Synthetic CSV generator | `generate_dataset.py` |
| Rebuild RESULTS.md from results/ | `summarize_results.py` |

The results are measurements of specific machines: a GitHub-hosted runner for the engine runs and one laptop for the sync runs. Each one passed its correctness checks. They are not a claim about other hardware, and they do not reproduce the older timings quoted from the v0.1.0 README. [RESULTS.md](RESULTS.md) lists what is and is not covered.

## Sync benchmark

`run_sync_benchmark.py` builds a SQLite table, then runs the real pipeline against it: a full load, an append run after new rows arrive, an append run with nothing new, and an upsert run after rows are added and changed. It fails unless row counts and `sum(amount)` match the source, append read only the new rows, and upsert left exactly one row per key.

```bash
python -m pip install .
python benchmarks/run_sync_benchmark.py --rows 1000000 --output benchmarks/results/local-sync-1m-$(git rev-parse --short HEAD).json
python benchmarks/summarize_results.py
```

Commit the code first, so the result records the commit it measured. The source is a local file, so there is no network time in the result.

## Generate a dataset

The generator uses only the Python standard library and streams rows to disk:

```bash
python benchmarks/generate_dataset.py --output /tmp/redata-100k.csv --rows 100000 --columns 10 --seed 20261012 --cardinality 1000 --missing-rate 0.01
```

For a larger workload, increase `--rows` only after confirming available disk space. Example:

```bash
python benchmarks/generate_dataset.py --output /tmp/redata-1m.csv --rows 1000000 --columns 10 --seed 20261012 --cardinality 10000 --missing-rate 0.01
```

The script writes a sidecar JSON file next to the CSV containing the parameters, file size, and SHA-256 digest. The data and metadata should be retained with each benchmark run.

## Required run records

For each test, record:

- Exact ReData Git commit SHA.
- Operating system, CPU, RAM, browser, Python, DuckDB, and dependency versions as applicable.
- Dataset sidecar JSON and checksum.
- Workload and configuration.
- Warm-up and repetition procedure.
- Duration and memory measurements, including measurement method.
- Output correctness checks, errors, timeouts, and failed runs.

See [the benchmark protocol](../docs/BENCHMARK_PROTOCOL.md).

## Important limitations

- The generator is a controlled synthetic workload, not a proxy for every Excel workbook, JSON document, or real-world CSV.
- The generator itself does not launch ReData, collect browser memory, or benchmark the local engine.
- Do not describe a dataset as successfully processed by ReData until the corresponding application run has been completed and recorded.
- Use only public or appropriately licensed datasets; never publish confidential data.

## Generator regression tests

The standard-library regression tests validate output shape, metadata/checksum consistency, same-seed CSV reproducibility, and invalid-argument safeguards. Run them from the repository root:

```bash
python -m py_compile benchmarks/generate_dataset.py tests/test_generate_dataset.py
python -m unittest discover -s tests -p "test_generate_dataset.py" -v
```

The GitHub Actions workflow at `.github/workflows/benchmark-generator-tests.yml` runs these checks on relevant pushes and pull requests. Passing these tests validates the generator artifact only; it is not a ReData application test and provides no performance result.


## Local-engine HTTP smoke benchmark

The `run_engine_smoke.py` script starts the actual ReData local engine in an isolated workspace, creates a deterministic CSV, stages and imports it through the HTTP API, checks metadata and paginated rows, runs repeated SQL aggregation queries against an independent expected sum, and verifies that an unauthenticated status request is rejected.

Run locally after installing the engine:

```bash
python -m pip install .
python benchmarks/run_engine_smoke.py --rows 100000 --columns 10 --repeats 5 --output benchmark-results/engine-smoke.json
```

The JSON output records the source commit when supplied by CI, Python/platform/DuckDB versions, dataset checksum, stage/import timings, individual SQL query timings, pagination latency, and correctness checks. GitHub Actions runs this smoke benchmark on a hosted runner and uploads the JSON as a workflow artifact. Treat those results as an environment-specific baseline; they do not independently reproduce the historical README timings or establish a universal file-size limit. Larger runs should be performed separately on a documented target machine.


## Preserved CI results

Six successful GitHub-hosted local-engine smoke runs have their raw JSON committed for long-term review. They ran before the engine moved from `http.server` to FastAPI:

- [100,000 rows](results/ci-smoke-100k-8d73fa1.json) — [workflow run](https://github.com/theraghavraman/redata/actions/runs/38175393938)
- [1,000,000 rows × 10 columns, single import](results/ci-smoke-1m-32fe7af.json) — [workflow run](https://github.com/theraghavraman/redata/actions/runs/38175438341)
- [1,000,000 rows × 10 columns, three import/profile repetitions and sampled RSS](results/ci-repeat-1m-b3714c1.json) — [workflow run](https://github.com/theraghavraman/redata/actions/runs/38175832918)
- [1,000,000 rows × 10 columns, expanded aggregate and read-only SQL checks](results/ci-repeat-1m-e92a050.json) — [workflow run](https://github.com/theraghavraman/redata/actions/runs/38175950861)
- [10,000,000 rows × 7 columns](results/ci-smoke-10m-27e1126.json) — [workflow run](https://github.com/theraghavraman/redata/actions/runs/38175528927)
- [10,000,000 rows × 10 columns](results/ci-smoke-10m-10col-efaf0aa.json) — [workflow run](https://github.com/theraghavraman/redata/actions/runs/38175634773)

These are single-run observations on a hosted runner, not a multi-machine benchmark. The 10-million-row, 10-column run matches the README's row/column counts but uses a different generated file (about 1.057 GB rather than the historical 723 MB) and different source/runtime conditions. It therefore tests that scale, not the historical timing claim. The JSON files record environment, dataset checksum, individual query timings, correctness checks, and (for the repeated 1M run) three import/profile observations plus a sampled process-RSS estimate. The workflow also uploads the same result as an artifact; GitHub artifacts are temporary, so the committed JSON is the durable record.
