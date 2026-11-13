#!/usr/bin/env python3
"""Sync benchmark: SQLite -> DuckDB staging through the real pipeline.

Measures the three sync modes on one generated table and checks every result
against the source, so a fast wrong answer cannot pass:

  full      first load of all rows
  append    a second run after new rows arrive (cursor = id)
  no-op     a run with nothing new
  upsert    first load, then a run after rows are changed and added
            (cursor = updated_at, key = id)

SQLite is used as the source because it needs no server, which keeps the run
reproducible anywhere. It reads through the same DB-API batch path as the
Postgres, MySQL, SQL Server and Snowflake connectors, but there is no network
in the measurement, so treat the rows/second as an upper bound for those.

    python benchmarks/run_sync_benchmark.py --rows 1000000 --output benchmarks/results/sync-1m.json
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import random
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

STATUSES = ("new", "paid", "shipped", "returned")
BASE_TIME = datetime.datetime(2026, 1, 1)


def stamp(i: int) -> str:
    """Row i was last updated i seconds after the base time, so updated_at rises with id."""
    return (BASE_TIME + datetime.timedelta(seconds=i)).isoformat(sep=" ")


def make_rows(start: int, count: int, rng: random.Random):
    for i in range(start, start + count):
        yield (i, rng.randrange(1, 50_000), round(rng.uniform(1, 5000), 2), STATUSES[i % 4],
               "note %d %s" % (i, "x" * (i % 17)), stamp(i))


def build_source(path: Path, rows: int, seed: int) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, amount REAL, status TEXT, "
                "note TEXT, updated_at TEXT)")
    con.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)", make_rows(0, rows, random.Random(seed)))
    con.commit()
    return con


def source_totals(con: sqlite3.Connection):
    count, total = con.execute("SELECT count(*), sum(amount) FROM orders").fetchone()
    return count, round(total, 2)


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def hardware() -> dict:
    """CPU model and RAM, where the OS makes them easy to read."""
    out = {"cpu_model": None, "ram_gib": None}
    try:
        if sys.platform == "darwin":
            def sysctl(name):
                return subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, check=True).stdout.strip()
            out["cpu_model"] = sysctl("machdep.cpu.brand_string")
            out["ram_gib"] = round(int(sysctl("hw.memsize")) / 2 ** 30, 1)
        elif sys.platform.startswith("linux"):
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
                if line.startswith("model name"):
                    out["cpu_model"] = line.split(":", 1)[1].strip()
                    break
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                if line.startswith("MemTotal:"):
                    out["ram_gib"] = round(int(line.split()[1]) / 2 ** 20, 1)
                    break
    except (OSError, ValueError, subprocess.CalledProcessError):
        pass
    return out


def peak_rss_mib() -> float | None:
    try:
        import resource
    except ImportError:  # Windows
        return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rows", type=int, default=1_000_000)
    parser.add_argument("--delta-percent", type=float, default=10.0, help="new rows per incremental run, as %% of --rows")
    parser.add_argument("--threads", type=int, default=2, help="DuckDB threads")
    parser.add_argument("--seed", type=int, default=20261012)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmark-results" / "sync.json")
    args = parser.parse_args()
    if args.rows < 100:
        parser.error("--rows must be at least 100")

    import duckdb
    import pyarrow

    from redata import __version__ as engine_version
    from redata.engine import Engine

    delta = max(1, int(args.rows * args.delta_percent / 100))
    changed = max(1, delta // 2)

    with tempfile.TemporaryDirectory(prefix="redata-sync-bench-") as tmp:
        temp = Path(tmp)
        started = time.perf_counter()
        src = build_source(temp / "source.db", args.rows, args.seed)
        build_seconds = time.perf_counter() - started

        engine = Engine(str(temp / "workspace"), threads=args.threads)
        pipe = engine.start_pipeline(background=False)
        conn_id = pipe.save_connection({"type": "sqlite", "name": "bench", "values": {"path": str(temp / "source.db")}})["id"]

        def stream(target: str, **settings) -> str:
            return pipe.save_stream(dict({"connection_id": conn_id, "source": "orders", "target": target}, **settings))["id"]

        def run(stream_id: str) -> dict:
            begin = time.perf_counter()
            status = pipe.run(stream_id, "benchmark")
            seconds = time.perf_counter() - begin
            record = pipe.runs(1, stream_id)[0]
            if status != "success":
                raise AssertionError("sync failed: %s" % record["message"])
            return {"seconds": round(seconds, 3), "rows_read": record["rows_read"],
                    "rows_per_second": round(record["rows_read"] / seconds) if record["rows_read"] else 0,
                    "table_rows": record["table_rows"]}

        def staged_totals(target: str):
            count, total = engine.q("SELECT count(*), sum(amount) FROM staging.%s" % target)[0]
            return count, round(total, 2)

        checks = {}
        full_id = stream("orders_full", mode="full")
        append_id = stream("orders_append", mode="append", cursor="id")
        upsert_id = stream("orders_upsert", mode="upsert", cursor="updated_at", keys="id")

        full = run(full_id)
        checks["full_matches_source"] = staged_totals("orders_full") == source_totals(src)

        append_first = run(append_id)
        upsert_first = run(upsert_id)

        # new rows arrive, and some existing rows change
        rng = random.Random(args.seed + 1)
        src.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)", make_rows(args.rows, delta, rng))
        src.execute("UPDATE orders SET amount = amount + 1, status = 'returned', updated_at = ? WHERE id < ?",
                    (stamp(args.rows + delta), changed))
        src.commit()

        append_delta = run(append_id)
        checks["append_read_only_new_rows"] = append_delta["rows_read"] == delta
        checks["append_row_count"] = append_delta["table_rows"] == args.rows + delta

        upsert_delta = run(upsert_id)
        # upsert reads cursor >= saved, so the one row holding the saved cursor value is read again
        checks["upsert_read_new_changed_and_boundary_rows"] = upsert_delta["rows_read"] == delta + changed + 1
        checks["upsert_matches_source"] = staged_totals("orders_upsert") == source_totals(src)
        checks["upsert_keys_unique"] = engine.q(
            "SELECT count(*) = count(DISTINCT id) FROM staging.orders_upsert")[0][0]

        noop = run(append_id)
        checks["noop_reads_nothing"] = noop["rows_read"] == 0

        full_again = run(full_id)
        checks["full_rerun_matches_source"] = staged_totals("orders_full") == source_totals(src)

        result = {
            "schema_version": 1,
            "benchmark_type": "ReData sync benchmark (SQLite source, local pipeline)",
            "status": "passed" if all(checks.values()) else "failed",
            "note": "Environment-specific measurement of one run per step. The source is a local SQLite file, so "
                    "there is no network time; not a capacity claim for remote databases.",
            "source_commit": git_commit(),
            "engine_version": engine_version,
            "duckdb_version": duckdb.__version__,
            "pyarrow_version": pyarrow.__version__,
            "python_version": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            **hardware(),
            "duckdb_threads": args.threads,
            "rows": args.rows,
            "columns": 6,
            "seed": args.seed,
            "delta_rows": delta,
            "changed_rows": changed,
            "source_build_seconds": round(build_seconds, 3),
            "full_first_load": full,
            "full_reload": full_again,
            "append_first_load": append_first,
            "append_incremental": append_delta,
            "append_nothing_new": noop,
            "upsert_first_load": upsert_first,
            "upsert_incremental": upsert_delta,
            "peak_rss_mib": peak_rss_mib(),
            "memory_measurement_method": "resource.getrusage(RUSAGE_SELF).ru_maxrss of the benchmark process, which "
                                         "also built the SQLite source",
            "correctness": checks,
        }
        src.close()
        engine.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
