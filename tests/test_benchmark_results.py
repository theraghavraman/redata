"""The published benchmark numbers must come from committed, passing result files."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmarks" / "results"


class BenchmarkResultTests(unittest.TestCase):
    def test_results_page_matches_the_result_files(self) -> None:
        check = subprocess.run([sys.executable, str(ROOT / "benchmarks" / "summarize_results.py"), "--check"],
                               capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_every_committed_result_passed_its_checks(self) -> None:
        files = sorted(RESULTS.glob("*.json"))
        self.assertTrue(files)
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "passed", path.name)
            self.assertTrue(data["source_commit"], path.name)
            failed = [k for k, v in data["correctness"].items() if v is False]
            self.assertEqual(failed, [], path.name)

    def test_every_result_file_is_on_the_results_page(self) -> None:
        page = (ROOT / "benchmarks" / "RESULTS.md").read_text(encoding="utf-8")
        for path in RESULTS.glob("*.json"):
            self.assertIn("results/%s" % path.name, page)


if __name__ == "__main__":
    unittest.main()
