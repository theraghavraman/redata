"""Small, deterministic correctness fixtures for the actual local DuckDB engine.

These are implementation tests, not performance benchmarks. Expected values are
specified independently in each fixture so successful execution alone is not
mistaken for correctness.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from redata_engine import Engine, UserError  # noqa: E402


class EngineCsvCorrectnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="redata-engine-test-")
        self.root = Path(self.temp.name)
        self.engine = Engine(str(self.root / "workspace"), threads=1)

    def tearDown(self) -> None:
        try:
            self.engine.con.close()
        finally:
            self.temp.cleanup()

    def load_csv(self, name: str, content: str):
        path = self.root / name
        path.write_text(content, encoding="utf-8", newline="")
        stage = self.engine.stage_path(str(path))
        return self.engine.load(stage["stage"], header=True)

    def test_quoted_delimiter_and_embedded_newline(self) -> None:
        meta = self.load_csv(
            "quoted.csv",
            'id,note\n1,"alpha, beta"\n2,"first line\nsecond line"\n',
        )
        rows = self.engine.q('SELECT "id", "note" FROM "data" ORDER BY "id"')
        self.assertEqual(meta["rows"], 2)
        self.assertEqual(rows, [(1, "alpha, beta"), (2, "first line\nsecond line")])

    def test_blank_and_duplicate_headers_are_normalized(self) -> None:
        meta = self.load_csv(
            "headers.csv",
            ',Name,name,Name_2\n1,first,second,third\n',
        )
        self.assertEqual(
            [column["name"] for column in meta["columns"]],
            ["column_1", "Name", "name_2", "Name_2_2"],
        )
        self.assertEqual(meta["rows"], 1)
        self.assertEqual(
            self.engine.q('SELECT * FROM "data"'),
            [(1, "first", "second", "third")],
        )

    def test_empty_cells_become_null_and_blank_rows_are_ignored(self) -> None:
        meta = self.load_csv(
            "missing.csv",
            'id,label,amount\n1,,10\n2,filled,\n,,\n',
        )
        self.assertEqual(meta["rows"], 2)
        self.assertEqual(meta["missingTotal"], 2)
        self.assertEqual(
            self.engine.q('SELECT "id", "label", "amount" FROM "data" ORDER BY "id"'),
            [(1, None, 10), (2, "filled", None)],
        )

    def test_late_mixed_type_value_is_preserved(self) -> None:
        meta = self.load_csv(
            "mixed.csv",
            "id,measurement\n1,10\n2,20\n3,not-a-number\n",
        )
        self.assertEqual(meta["rows"], 3)
        values = self.engine.q('SELECT "measurement" FROM "data" ORDER BY "id"')
        self.assertEqual([row[0] for row in values], ["10", "20", "not-a-number"])

    def test_short_rows_are_null_padded(self) -> None:
        meta = self.load_csv(
            "short.csv",
            "id,label,amount\n1,complete,7\n2,short\n",
        )
        self.assertEqual(meta["rows"], 2)
        self.assertEqual(
            self.engine.q('SELECT "id", "label", "amount" FROM "data" ORDER BY "id"'),
            [(1, "complete", 7), (2, "short", None)],
        )

    def test_all_blank_rows_are_rejected_without_replacing_loaded_data(self) -> None:
        self.load_csv("valid.csv", "id,value\n1,ok\n")
        path = self.root / "blank.csv"
        path.write_text("id,value\n,\n,,\n", encoding="utf-8")
        stage = self.engine.stage_path(str(path))
        with self.assertRaises(UserError):
            self.engine.load(stage["stage"], header=True)
        self.assertEqual(self.engine.q('SELECT * FROM "data"'), [(1, "ok")])


if __name__ == "__main__":
    unittest.main()
