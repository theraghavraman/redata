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


    def stage_and_load(self, name: str, content: str):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        stage = self.engine.stage_path(str(path))
        return self.engine.load(stage["stage"], header=True)

    def test_json_array_of_records_loads_with_expected_values(self) -> None:
        meta = self.stage_and_load(
            "records.json",
            '{"rows":[{"id":1,"label":"alpha"},{"id":2,"label":"beta"}]}',
        )
        self.assertEqual(meta["rows"], 2)
        self.assertEqual(
            self.engine.q('SELECT "id", "label" FROM "data" ORDER BY "id"'),
            [(1, "alpha"), (2, "beta")],
        )

    def test_ndjson_loads_all_records(self) -> None:
        meta = self.stage_and_load(
            "records.ndjson",
            '{"id":1,"value":4}\n{"id":2,"value":9}\n{"id":3,"value":16}\n',
        )
        self.assertEqual(meta["rows"], 3)
        self.assertEqual(
            self.engine.q('SELECT sum("value"), count(*) FROM "data"'),
            [(29, 3)],
        )

    def test_parquet_import_preserves_rows_and_types(self) -> None:
        parquet = self.root / "records.parquet"
        self.engine.q(
            "COPY (SELECT * FROM (VALUES (1, 'alpha'), (2, 'beta')) "
            "AS v(id, label)) TO ? (FORMAT PARQUET)",
            [str(parquet)],
        )
        stage = self.engine.stage_path(str(parquet))
        meta = self.engine.load(stage["stage"], header=True)
        self.assertEqual(meta["rows"], 2)
        self.assertEqual(
            self.engine.q('SELECT "id", "label" FROM "data" ORDER BY "id"'),
            [(1, "alpha"), (2, "beta")],
        )

    def test_formula_and_read_only_sql_guard(self) -> None:
        self.load_csv("formula.csv", "id,value\n1,10\n2,20\n3,30\n")
        result = self.engine.formula("double_value", "[value] * 2")
        self.assertEqual(result, {"changed": 3, "rows": 3})
        self.assertEqual(
            self.engine.q('SELECT "double_value" FROM "data" ORDER BY "id"'),
            [(20.0,), (40.0,), (60.0,)],
        )
        with self.assertRaises(UserError):
            self.engine.sql("DROP TABLE data")
        self.assertEqual(self.engine.row_count(), 3)

    def test_csv_and_json_exports_round_trip(self) -> None:
        self.load_csv("export.csv", "id,label\n1,alpha\n2,beta\n")
        for fmt in ("csv", "json"):
            result = self.engine.export("data", fmt=fmt)
            output = Path(self.engine.exports[result["id"]])
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 0)
            if fmt == "json":
                import json
                parsed = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(parsed, [{"id": 1, "label": "alpha"}, {"id": 2, "label": "beta"}])
            else:
                import csv
                with output.open("r", encoding="utf-8", newline="") as stream:
                    self.assertEqual(list(csv.DictReader(stream)), [
                        {"id": "1", "label": "alpha"},
                        {"id": "2", "label": "beta"},
                    ])


    def test_fill_missing_numeric_values_uses_expected_replacement(self) -> None:
        self.load_csv("fill.csv", "id,value\n1,10\n2,\n3,30\n")
        message = self.engine.clean("fill", strategy="zero")
        self.assertIn("Filled 1 missing cells", message)
        self.assertEqual(
            self.engine.q('SELECT "id", "value" FROM "data" ORDER BY "id"'),
            [(1, 10), (2, 0), (3, 30)],
        )

    def test_group_aggregation_matches_independent_expected_totals(self) -> None:
        self.load_csv(
            "groups.csv",
            "category,amount\nA,10\nA,5\nB,7\nB,8\nC,1\n",
        )
        result = self.engine.aggregate("category", "amount", "sum", with_groups=True)
        observed = {row["label"]: row["value"] for row in result["rows"]}
        self.assertEqual(observed, {"A": 15.0, "B": 15.0, "C": 1.0})
        self.assertEqual(result["groups"], 3)

    def test_linear_regression_matches_exact_linear_fixture(self) -> None:
        self.load_csv("linear.csv", "x,y\n1,3\n2,5\n3,7\n4,9\n")
        result = self.engine.regression("x", "y")
        self.assertEqual(result["n"], 4)
        self.assertAlmostEqual(result["slope"], 2.0, places=10)
        self.assertAlmostEqual(result["intercept"], 1.0, places=10)
        self.assertAlmostEqual(result["r"], 1.0, places=10)


    def test_xlsx_import_preserves_tabular_values(self) -> None:
        from openpyxl import Workbook

        path = self.root / "workbook.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["id", "label"])
        sheet.append([1, "alpha"])
        sheet.append([2, "beta"])
        workbook.save(path)
        workbook.close()
        stage = self.engine.stage_path(str(path))
        meta = self.engine.load(stage["stage"], header=True)
        self.assertEqual(meta["rows"], 2)
        self.assertEqual(
            self.engine.q('SELECT "id", "label" FROM "data" ORDER BY "id"'),
            [(1, "alpha"), (2, "beta")],
        )

    def test_malformed_json_does_not_replace_loaded_dataset(self) -> None:
        self.load_csv("before.json.csv", "id,label\n1,retained\n")
        path = self.root / "broken.json"
        path.write_text('{"id":1,', encoding="utf-8")
        stage = self.engine.stage_path(str(path))
        with self.assertRaises(UserError):
            self.engine.load(stage["stage"], header=True)
        self.assertEqual(self.engine.q('SELECT * FROM "data"'), [(1, "retained")])


if __name__ == "__main__":
    unittest.main()
