"""Regression tests for the deterministic synthetic CSV generator.

These tests validate dataset-generation artifacts only; they do not run or benchmark ReData.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPO_ROOT / "benchmarks" / "generate_dataset.py"


class DatasetGeneratorTests(unittest.TestCase):
    def run_generator(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(GENERATOR), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_shape_metadata_and_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "fixture.csv"
            result = self.run_generator(
                "--output", str(output), "--rows", "25",
                "--columns", "7", "--seed", "42",
                "--cardinality", "8", "--missing-rate", "0.2",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with output.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(len(rows), 26)  # header plus 25 data rows
            self.assertEqual(len(rows[0]), 7)
            self.assertEqual(rows[0][:5], ["id", "category", "value", "score", "event_date"])
            self.assertEqual([row[0] for row in rows[1:]], [str(i) for i in range(25)])
            self.assertTrue(all(len(row) == 7 for row in rows))

            metadata_path = Path(str(output) + ".metadata.json")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["rows"], 25)
            self.assertEqual(metadata["columns"], 7)
            self.assertEqual(metadata["seed"], 42)
            self.assertEqual(metadata["bytes"], output.stat().st_size)
            self.assertEqual(
                metadata["sha256"],
                hashlib.sha256(output.read_bytes()).hexdigest(),
            )

    def test_same_seed_produces_identical_csv_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.csv"
            second = Path(tmp) / "second.csv"
            common = ("--rows", "40", "--columns", "6", "--seed", "77",
                      "--cardinality", "10", "--missing-rate", "0.1")
            self.assertEqual(self.run_generator("--output", str(first), *common).returncode, 0)
            self.assertEqual(self.run_generator("--output", str(second), *common).returncode, 0)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_rejects_metadata_path_equal_to_csv_path_without_clobbering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "same-path.csv"
            result = self.run_generator(
                "--output", str(output), "--rows", "2", "--columns", "5",
                "--metadata", str(output),
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("metadata path must differ", result.stderr)
            self.assertFalse(output.exists())

    def test_rejects_invalid_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "invalid.csv"
            result = self.run_generator(
                "--output", str(output), "--rows", "2", "--columns", "4",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--columns must be >= 5", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
