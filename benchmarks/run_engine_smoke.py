#!/usr/bin/env python3
"""Run a reproducible local-engine smoke benchmark and write JSON results.

This exercises the real ReData HTTP API and DuckDB engine. It is a small CI
baseline, not a universal performance claim. Run larger datasets on a recorded
machine before publishing capacity claims.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import random
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "benchmarks" / "generate_dataset.py"
ENGINE = ROOT / "engine" / "redata_engine.py"


def request(url: str, token: str | None = None, body: dict | None = None, timeout: float = 30):
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {}
    if token is not None:
        headers["X-ReData-Token"] = token
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="GET" if body is None else "POST")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read()
        content_type = response.headers.get("Content-Type", "")
    if "json" in content_type:
        return json.loads(raw.decode("utf-8"))
    return raw


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--columns", type=int, default=10)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20261012)
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmark-results" / "engine-smoke.json")
    args = parser.parse_args()
    if args.rows < 1 or args.repeats < 1:
        parser.error("--rows and --repeats must be positive")

    import duckdb

    with tempfile.TemporaryDirectory(prefix="redata-benchmark-") as tmp:
        temp = Path(tmp)
        dataset = temp / "dataset.csv"
        workspace = temp / "workspace"
        subprocess.run([
            sys.executable, str(GENERATOR), "--output", str(dataset),
            "--rows", str(args.rows), "--columns", str(args.columns),
            "--seed", str(args.seed), "--cardinality", str(max(1, min(args.rows, 1000))),
            "--missing-rate", "0",
        ], check=True, stdout=subprocess.DEVNULL)

        proc = subprocess.Popen(
            [sys.executable, str(ENGINE), "--port", str(args.port),
             "--workspace", str(workspace), "--no-browser", "--threads", "2"],
            cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True,
        )
        base_url = None
        token = None
        startup_log = ""
        try:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    startup_log = proc.stdout.read() if proc.stdout else ""
                    raise RuntimeError("ReData engine exited during startup: " + startup_log[-4000:])
                for port in range(args.port, args.port + 20):
                    candidate = f"http://127.0.0.1:{port}/"
                    try:
                        with urllib.request.urlopen(candidate, timeout=0.5) as response:
                            html = response.read().decode("utf-8", "replace")
                        match = re.search(r"window\\.REDATA_ENGINE=(\\{.*?\\});</script>", html)
                        if match:
                            config = json.loads(match.group(1))
                            base_url, token = candidate.rstrip("/"), config["token"]
                            break
                    except (OSError, urllib.error.URLError, TimeoutError):
                        continue
                if token:
                    break
                time.sleep(0.25)
            if not token or not base_url:
                raise TimeoutError("ReData engine did not become ready within 45 seconds")

            # The API must reject unauthenticated requests.
            try:
                request(base_url + "/api/status")
                raise AssertionError("Unauthenticated status request unexpectedly succeeded")
            except urllib.error.HTTPError as exc:
                if exc.code != 403:
                    raise AssertionError(f"Expected 403 without token, received {exc.code}") from exc

            status = request(base_url + "/api/status", token)
            if "version" not in status:
                raise AssertionError(f"Unexpected engine status: {status}")

            started = time.perf_counter()
            staged = request(base_url + "/api/stage_path", token, {"path": str(dataset)})
            stage_ms = (time.perf_counter() - started) * 1000
            if "stage" not in staged:
                raise AssertionError(f"Staging response has no stage id: {staged}")

            started = time.perf_counter()
            loaded = request(base_url + "/api/load", token, {"stage": staged["stage"], "header": True})
            load_ms = (time.perf_counter() - started) * 1000
            meta = loaded.get("meta") or {}
            if meta.get("rows") != args.rows:
                raise AssertionError(f"Expected {args.rows} rows after import; got {meta.get('rows')}")
            if len(meta.get("columns", [])) != args.columns:
                raise AssertionError(f"Expected {args.columns} columns; got {len(meta.get('columns', []))}")

            # Correctness oracle independent of DuckDB: the generator's value
            # column is deterministic and missing-rate is fixed at zero.
            expected_sum = math.fsum(round(((i * 7919) % 1000003) / 100.0, 4) for i in range(args.rows))
            sql = "SELECT COUNT(*) AS n, SUM(value) AS total, MIN(id) AS min_id, MAX(id) AS max_id FROM data"
            query_ms = []
            last_result = None
            for _ in range(args.repeats):
                started = time.perf_counter()
                last_result = request(base_url + "/api/sql", token, {"query": sql})
                query_ms.append((time.perf_counter() - started) * 1000)
            result_rows = last_result.get("rows", [])
            if len(result_rows) != 1:
                raise AssertionError(f"Unexpected aggregate result: {last_result}")
            row = result_rows[0]
            if int(row["n"]) != args.rows or int(row["min_id"]) != 0 or int(row["max_id"]) != args.rows - 1:
                raise AssertionError(f"Row count or id range mismatch: {row}")
            if not math.isclose(float(row["total"]), expected_sum, rel_tol=1e-10, abs_tol=1e-5):
                raise AssertionError(f"SUM(value) mismatch: expected {expected_sum}, got {row['total']}")

            page = request(base_url + "/api/rows", token, {"offset": 0, "limit": 5})
            if len(page.get("rows", [])) != 5:
                raise AssertionError(f"Expected five rows from paged API: {page}")
            if int(page["rows"][0]["id"]) != 0:
                raise AssertionError(f"Unexpected first paged row: {page['rows'][0]}")

            result = {
                "schema_version": 1,
                "benchmark_type": "ReData local-engine HTTP smoke benchmark",
                "status": "passed",
                "note": "Single-run environment-specific CI baseline; not a universal capacity claim or independent reproduction of prior README timings.",
                "source_commit": os.environ.get("GITHUB_SHA", "local-working-tree-or-unspecified"),
                "engine_version": status["version"],
                "duckdb_version": duckdb.__version__,
                "python_version": sys.version,
                "platform": platform.platform(),
                "cpu_count": os.cpu_count(),
                "rows": args.rows,
                "columns": args.columns,
                "seed": args.seed,
                "missing_rate": 0,
                "dataset_bytes": dataset.stat().st_size,
                "dataset_sha256": sha256(dataset),
                "staging_ms": round(stage_ms, 3),
                "import_and_profile_ms": round(load_ms, 3),
                "sql_query_ms": [round(x, 3) for x in query_ms],
                "sql_query_median_ms": round(sorted(query_ms)[len(query_ms) // 2], 3),
                "page_5_rows_ms": None,
                "correctness": {
                    "row_count": int(row["n"]) == args.rows,
                    "column_count": len(meta["columns"]) == args.columns,
                    "id_min_max": [int(row["min_id"]), int(row["max_id"])],
                    "sum_value_expected": expected_sum,
                    "sum_value_observed": float(row["total"]),
                    "sum_value_matches": True,
                    "page_first_id": int(page["rows"][0]["id"]),
                },
                "auth_check": "unauthenticated /api/status correctly returned HTTP 403",
                "repeats": args.repeats,
            }
            result["page_5_rows_ms"] = round((time.perf_counter() - started) * 1000, 3)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(result, indent=2))
            return 0
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            if proc.stdout:
                proc.stdout.close()


if __name__ == "__main__":
    raise SystemExit(main())
