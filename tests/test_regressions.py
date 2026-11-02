"""Regression tests for defects fixed in this revision.

Each test here fails against the previous code and passes now. They are kept
separate from test_engine_correctness.py so the reason each case exists stays
obvious.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

import pyarrow as pa  # noqa: E402

from redata_engine import Engine, UserError  # noqa: E402
import pipeline as P  # noqa: E402


class EngineRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="redata-regression-")
        self.root = Path(self.temp.name)
        self.engine = Engine(str(self.root / "workspace"), threads=1)

    def tearDown(self) -> None:
        try:
            self.engine.con.close()
        finally:
            self.temp.cleanup()

    def write(self, name: str, content: str, encoding: str = "utf-8") -> Path:
        path = self.root / name
        path.write_text(content, encoding=encoding, newline="")
        return path

    def load(self, name: str, content: str):
        stage = self.engine.stage_path(str(self.write(name, content)))
        return self.engine.load(stage["stage"], header=True)

    # -- JSON loading no longer reserves a multi-gigabyte buffer -----------------
    def test_ndjson_loads_under_a_small_memory_limit(self) -> None:
        """maximum_object_size was 1 GiB, which made DuckDB reserve 2 GiB and fail."""
        small = Engine(str(self.root / "small-workspace"), memory_limit="256MB", threads=1)
        try:
            stage = small.stage_path(str(self.write("r.ndjson", '{"id":1,"v":4}\n{"id":2,"v":9}\n')))
            meta = small.load(stage["stage"], header=True)
            self.assertEqual(meta["rows"], 2)
            self.assertEqual(small.q('SELECT "id", "v" FROM "data" ORDER BY "id"'), [(1, 4), (2, 9)])
        finally:
            small.con.close()

    def test_json_array_of_records_is_unwrapped(self) -> None:
        meta = self.load("a.json", '[{"id":1,"v":4},{"id":2,"v":9}]')
        self.assertEqual(meta["rows"], 2)
        self.assertEqual(self.engine.q('SELECT "id" FROM "data" ORDER BY "id"'), [(1,), (2,)])

    def test_json_with_two_arrays_is_rejected_not_silently_truncated(self) -> None:
        with self.assertRaises(UserError):
            self.load("two.json", '{"a":[{"id":1}],"b":[{"id":2}]}')

    # -- SQL lab denylist cannot be dodged by quoting ---------------------------
    def test_sql_lab_blocks_quoted_file_functions(self) -> None:
        self.load("d.csv", "id,v\n1,10\n")
        for query in (
            """SELECT content FROM "read_text"('/etc/hostname')""",
            "SELECT * FROM `read_text`('/etc/hostname')",
            "SELECT * FROM read_json_objects_auto('/etc/hostname')",
            "SELECT * FROM glob('/etc/*')",
        ):
            with self.subTest(query=query):
                with self.assertRaises(UserError):
                    self.engine.sql(query)

    def test_sql_lab_still_runs_ordinary_selects(self) -> None:
        self.load("d.csv", "id,v\n1,10\n2,20\n")
        result = self.engine.sql('SELECT sum("v") AS total FROM "data"')
        self.assertEqual(result["rows"], [{"total": 30}])

    # -- header cells follow the real delimiter ---------------------------------
    def test_semicolon_csv_keeps_its_column_names(self) -> None:
        meta = self.load("semi.csv", "name;qty;price\nwidget;2;9.5\n")
        self.assertEqual([c["name"] for c in meta["columns"]], ["name", "qty", "price"])

    def test_pipe_csv_keeps_its_column_names(self) -> None:
        meta = self.load("pipe.csv", "name|qty\nwidget|2\n")
        self.assertEqual([c["name"] for c in meta["columns"]], ["name", "qty"])

    def test_comma_csv_still_works(self) -> None:
        meta = self.load("plain.csv", "name,qty\nwidget,2\n")
        self.assertEqual([c["name"] for c in meta["columns"]], ["name", "qty"])


class PipelineWideningTests(unittest.TestCase):
    """DuckDB rounds a DOUBLE into an existing integer column without raising."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="redata-pipeline-")
        self.engine = Engine(str(Path(self.temp.name) / "workspace"), threads=1)
        self.pipe = P.Pipeline(self.engine)
        self.pipe.stop.set()  # keep the worker thread from picking up work

    def tearDown(self) -> None:
        try:
            self.engine.con.close()
        finally:
            self.temp.cleanup()

    def rows(self, table: str):
        return self.engine.q("SELECT amt FROM staging.%s ORDER BY amt" % P.qi(table))

    def test_fractional_value_widens_the_column_instead_of_rounding(self) -> None:
        first = pa.table({"amt": pa.array([10, 20], type=pa.int64())})
        self.pipe._write_arrow("t", first, False)
        second = pa.table({"amt": pa.array([2.75], type=pa.float64())})
        self.pipe._write_arrow("t", second, True)
        self.assertEqual(self.rows("t"), [(2.75,), (10.0,), (20.0,)])

    def test_integer_values_do_not_force_a_widen(self) -> None:
        first = pa.table({"amt": pa.array([10], type=pa.int64())})
        self.pipe._write_arrow("t2", first, False)
        second = pa.table({"amt": pa.array([30], type=pa.int64())})
        self.pipe._write_arrow("t2", second, True)
        kind = [t for c, t in self.pipe._cols("t2") if c == "amt"][0]
        self.assertNotIn("DOUBLE", kind.upper())
        self.assertEqual(self.rows("t2"), [(10,), (30,)])


if __name__ == "__main__":
    unittest.main()
