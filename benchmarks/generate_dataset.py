#!/usr/bin/env python3
"""Generate deterministic synthetic CSV data for ReData benchmark experiments.

This script uses only the Python standard library. It streams rows to disk and
writes a JSON sidecar containing the dataset parameters, byte size, and SHA-256.
It does not run ReData or measure application performance.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from pathlib import Path


GENERATOR_VERSION = "1.0.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="Output CSV path")
    parser.add_argument("--rows", required=True, type=int, help="Number of data rows")
    parser.add_argument("--columns", type=int, default=10, help="Total columns (minimum 5; default: 10)")
    parser.add_argument("--seed", type=int, default=20261012, help="Deterministic PRNG seed")
    parser.add_argument("--cardinality", type=int, default=1000, help="Number of category values")
    parser.add_argument("--missing-rate", type=float, default=0.0, help="Missing-value probability for nullable fields, from 0 to 1")
    parser.add_argument("--metadata", type=Path, help="Metadata JSON path (default: <output>.metadata.json)")
    args = parser.parse_args()

    if args.rows < 0:
        parser.error("--rows must be >= 0")
    if args.columns < 5:
        parser.error("--columns must be >= 5")
    if args.cardinality < 1:
        parser.error("--cardinality must be >= 1")
    if not 0.0 <= args.missing_rate <= 1.0:
        parser.error("--missing-rate must be between 0 and 1")
    return args


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    metadata_path = args.metadata or Path(str(args.output) + ".metadata.json")
    rng = random.Random(args.seed)

    headers = ["id", "category", "value", "score", "event_date"]
    headers.extend(f"extra_{index}" for index in range(6, args.columns + 1))

    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(headers)
        for row_id in range(args.rows):
            category = f"category_{row_id % args.cardinality}"
            value = round(((row_id * 7919) % 1000003) / 100.0, 4)
            score = round(rng.random() * 100.0, 6)
            event_date = f"2020-01-{(row_id % 28) + 1:02d}"
            values: list[object] = [row_id, category, value, score, event_date]
            for column_index in range(6, args.columns + 1):
                values.append(round(rng.uniform(-1000.0, 1000.0), 6))

            # Keep the primary key and category intact; inject missing values
            # into non-key fields according to the configured deterministic rate.
            for cell_index in range(2, len(values)):
                if rng.random() < args.missing_rate:
                    values[cell_index] = ""

            writer.writerow(values)

    metadata = {
        "generator": "ReData synthetic CSV generator",
        "generator_version": GENERATOR_VERSION,
        "output_file": args.output.name,
        "rows": args.rows,
        "columns": args.columns,
        "seed": args.seed,
        "category_cardinality": min(args.cardinality, args.rows) if args.rows else 0,
        "requested_cardinality": args.cardinality,
        "missing_rate": args.missing_rate,
        "bytes": args.output.stat().st_size,
        "sha256": sha256_file(args.output),
        "notes": [
            "Synthetic data only; not representative of every real-world dataset.",
            "Generation metadata does not constitute a ReData performance result.",
            "Record the tested ReData commit and machine environment separately.",
        ],
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
