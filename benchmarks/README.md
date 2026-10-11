# ReData benchmark assets

This directory contains reproducible synthetic-data tooling. It does **not** contain verified performance results.

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

Run locally after installing DuckDB:

```bash
python -m pip install "duckdb>=1.1.0"
python benchmarks/run_engine_smoke.py --rows 100000 --columns 10 --repeats 5 --output benchmark-results/engine-smoke.json
```

The JSON output records the source commit when supplied by CI, Python/platform/DuckDB versions, dataset checksum, stage/import timings, individual SQL query timings, pagination latency, and correctness checks. GitHub Actions runs this smoke benchmark on a hosted runner and uploads the JSON as a workflow artifact. Treat those results as an environment-specific baseline; they do not independently reproduce the historical README timings or establish a universal file-size limit. Larger runs should be performed separately on a documented target machine.


## Preserved CI results

Two successful GitHub-hosted local-engine smoke runs have their raw JSON committed for long-term review:

- [100,000 rows](results/ci-smoke-100k-8d73fa1.json) — [workflow run](https://github.com/theraghavraman/redata/actions/runs/38175393938)
- [1,000,000 rows](results/ci-smoke-1m-32fe7af.json) — [workflow run](https://github.com/theraghavraman/redata/actions/runs/38175438341)

These are single-run observations on a hosted runner, not a multi-machine benchmark or reproduction of the README's historical 10-million-row figures. The JSON files record environment, dataset checksum, individual query timings, and correctness checks. The workflow also uploads the same result as an artifact; GitHub artifacts are temporary, so the committed JSON is the durable record.
