"""Unit tests for the pieces the Engine is built from.

Expected values are worked out by hand or with the standard library, never by
calling the code under test a second time.
"""
from __future__ import annotations

import datetime
import decimal
import statistics
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

import duckdb  # noqa: E402

from redata import util  # noqa: E402
from redata.engine import Engine  # noqa: E402
from redata.formula import formula_to_sql  # noqa: E402
from redata.sqlguard import read_only_statement  # noqa: E402
from redata.util import UserError  # noqa: E402


class UtilTests(unittest.TestCase):
    def test_identifiers_and_literals_are_quoted(self) -> None:
        self.assertEqual(util.qi('a"b'), '"a""b"')
        self.assertEqual(util.lit("it's"), "'it''s'")

    def test_plain_makes_values_json_safe(self) -> None:
        self.assertIsNone(util.plain(float("nan")))
        self.assertIsNone(util.plain(float("inf")))
        self.assertEqual(util.plain(decimal.Decimal("1.5")), 1.5)
        self.assertEqual(util.plain(datetime.date(2026, 1, 2)), "2026-01-02")
        self.assertEqual(util.plain(b"\x01\xff"), "01ff")
        self.assertEqual(util.plain({"k": [decimal.Decimal("2"), None]}), {"k": [2.0, None]})
        self.assertIs(util.plain(True), True)

    def test_unique_headers(self) -> None:
        self.assertEqual(util.unique_headers(["a", "A", "", None, "a"], 6),
                         ["a", "A_2", "column_3", "column_4", "a_3", "column_6"])

    def test_safe_filename_drops_folders_and_odd_characters(self) -> None:
        self.assertEqual(util.safe_filename("../../etc/pass wd?.csv"), "pass wd_.csv")
        self.assertEqual(util.safe_filename(""), "dataset")
        self.assertEqual(util.safe_filename("..."), "dataset")
        self.assertEqual(len(util.safe_filename("x" * 500 + ".csv")), 120)

    def test_type_predicates(self) -> None:
        self.assertTrue(util.is_numeric_type("DECIMAL(18,3)"))
        self.assertTrue(util.is_numeric_type("bigint"))
        self.assertFalse(util.is_numeric_type("VARCHAR"))
        self.assertTrue(util.is_date_type("TIMESTAMP WITH TIME ZONE"))
        self.assertTrue(util.is_nested_type("STRUCT(a INTEGER)"))
        self.assertTrue(util.is_nested_type("INTEGER[]"))
        self.assertFalse(util.is_nested_type("INTEGER"))


class FormulaTests(unittest.TestCase):
    def evaluate(self, expression: str, row: dict):
        con = duckdb.connect()
        try:
            cols = ", ".join("%s AS %s" % (util.lit(v) if isinstance(v, str) else ("NULL" if v is None else repr(v)),
                                           util.qi(k)) for k, v in row.items())
            sql = formula_to_sql(expression, list(row))
            return con.execute("SELECT %s FROM (SELECT %s)" % (sql, cols)).fetchone()[0]
        finally:
            con.close()

    def test_precedence_and_parentheses(self) -> None:
        row = {"a": 2, "b": 3, "c": 4}
        self.assertEqual(self.evaluate("[a] + [b] * [c]", row), 14.0)
        self.assertEqual(self.evaluate("([a] + [b]) * [c]", row), 20.0)
        self.assertEqual(self.evaluate("-[a] * -[b]", row), 6.0)
        self.assertEqual(self.evaluate("[c] % [b]", row), 1.0)
        self.assertEqual(self.evaluate("1.5e1 + .5", row), 15.5)

    def test_column_names_with_spaces_and_symbols(self) -> None:
        self.assertEqual(self.evaluate("[unit price] * [qty (pcs)]", {"unit price": 2.5, "qty (pcs)": 4}), 10.0)

    def test_division_by_zero_and_text_become_null(self) -> None:
        self.assertIsNone(self.evaluate("[a] / [b]", {"a": 1, "b": 0}))
        self.assertIsNone(self.evaluate("[a] % [b]", {"a": 1, "b": 0}))
        self.assertIsNone(self.evaluate("[a] + 1", {"a": "abc"}))
        self.assertEqual(self.evaluate("[a] + 1", {"a": "41"}), 42.0)

    def test_bad_formulas_are_rejected(self) -> None:
        for expression in ("", "[missing] + 1", "[a] +", "([a] + 1", "[a] ** 2", "[a] 2", "1; DROP TABLE data",
                           "[a] + (SELECT 1)", "abs([a])"):
            with self.assertRaises(UserError, msg=expression):
                formula_to_sql(expression, ["a"])

    def test_a_column_name_cannot_inject_sql(self) -> None:
        name = 'x" FROM data; DROP TABLE data; --'
        self.assertEqual(self.evaluate("[%s] + 1" % name, {name: 1}), 2.0)


class SqlGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.con = duckdb.connect()

    def tearDown(self) -> None:
        self.con.close()

    def test_reads_are_allowed(self) -> None:
        for query in ("SELECT 1", "WITH t AS (SELECT 1 AS a) SELECT * FROM t", "EXPLAIN SELECT 1",
                      "SELECT 1; SELECT 2", "select 'read_csv is just text here'"):
            read_only_statement(self.con, query)

    def test_the_last_statement_is_the_one_returned(self) -> None:
        self.assertIn("2", read_only_statement(self.con, "SELECT 1; SELECT 2").query)

    def test_writes_and_side_effects_are_refused(self) -> None:
        for query in ("CREATE TABLE t (a INT)", "INSERT INTO t VALUES (1)", "UPDATE t SET a = 1", "DELETE FROM t",
                      "DROP TABLE t", "ATTACH 'x.db'", "COPY (SELECT 1) TO 'out.csv'", "PRAGMA database_list",
                      "SET memory_limit = '1GB'", "INSTALL httpfs", "SELECT 1; DROP TABLE t", "CALL pragma_version()",
                      "EXPORT DATABASE 'x'"):
            with self.assertRaises(UserError, msg=query):
                read_only_statement(self.con, query)

    def test_file_readers_are_refused_however_they_are_written(self) -> None:
        for query in ("SELECT * FROM read_csv('/etc/passwd')", "SELECT * FROM READ_PARQUET('x')",
                      'SELECT * FROM "read_text"(\'/etc/passwd\')', "SELECT * FROM read_json_auto ('x')",
                      "SELECT (SELECT count(*) FROM glob('/*'))", "SELECT * FROM sqlite_scan('a.db', 't')"):
            with self.assertRaises(UserError, msg=query):
                read_only_statement(self.con, query)

    def test_empty_input(self) -> None:
        for query in ("", "   ", None):
            with self.assertRaises(UserError):
                read_only_statement(self.con, query)


class EngineCase(unittest.TestCase):
    CSV = "id,team,score\n" + "".join("%d,%s,%s\n" % (i, "red" if i % 2 else "blue", v) for i, v in enumerate(
        [3, 7, 8, 5, 12, 14, 21, 13, 18, 100], start=1))
    SCORES = [3, 7, 8, 5, 12, 14, 21, 13, 18, 100]

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="redata-units-")
        self.root = Path(self.temp.name)
        self.engine = Engine(str(self.root / "workspace"), threads=1)

    def tearDown(self) -> None:
        try:
            self.engine.close()
        finally:
            self.temp.cleanup()

    def load(self, content: str | None = None, name: str = "d.csv") -> dict:
        path = self.root / name
        path.write_text(self.CSV if content is None else content, encoding="utf-8", newline="")
        return self.engine.load(self.engine.stage_path(str(path))["stage"], header=True)


class ProfileTests(EngineCase):
    def test_numeric_profile_matches_the_standard_library(self) -> None:
        score = next(c for c in self.load()["columns"] if c["name"] == "score")
        q1, median, q3 = statistics.quantiles(self.SCORES, n=4, method="inclusive")
        self.assertEqual((score["min"], score["max"], score["missing"], score["distinct"]), (3, 100, 0, 10))
        self.assertAlmostEqual(score["mean"], statistics.mean(self.SCORES))
        self.assertAlmostEqual(score["sd"], statistics.stdev(self.SCORES))
        self.assertAlmostEqual(score["median"], median)
        self.assertAlmostEqual(score["q1"], q1)
        self.assertAlmostEqual(score["q3"], q3)
        self.assertEqual(score["outliers"], 1)  # only 100 is beyond q3 + 1.5 * IQR

    def test_text_profile_and_duplicates(self) -> None:
        meta = self.load("k,v\na,1\na,1\nb,\nb,2\n")
        k = meta["columns"][0]
        self.assertEqual((k["numeric"], k["distinct"], k["top"], k["topApprox"]), (False, 2, "a", False))
        self.assertEqual((meta["rows"], meta["duplicates"], meta["missingTotal"]), (4, 1, 1))

    def test_the_profile_is_cached_until_the_data_changes(self) -> None:
        first = self.load()
        self.assertIs(self.engine.meta(), first)
        self.engine.clean("drop_column", column="team")
        second = self.engine.meta()
        self.assertIsNot(second, first)
        self.assertEqual(second["version"], first["version"] + 1)


class AnalysisTests(EngineCase):
    def test_paging_is_stable_and_bounded(self) -> None:
        self.load()
        page = self.engine.rows(offset=8, limit=5)
        self.assertEqual(([r["id"] for r in page["rows"]], page["total"]), ([9, 10], 10))
        self.assertEqual(len(self.engine.rows(limit=100000)["rows"]), 10)
        self.assertEqual(len(self.engine.rows(limit=0)["rows"]), 10)  # 0 means the default page size

    def test_sort_puts_nulls_last_in_both_directions(self) -> None:
        self.load("id,v\n1,5\n2,\n3,9\n")
        self.assertEqual([r["id"] for r in self.engine.rows(sort="v", direction=1)["rows"]], [1, 3, 2])
        self.assertEqual([r["id"] for r in self.engine.rows(sort="v", direction=-1)["rows"]], [3, 1, 2])

    def test_search_is_case_insensitive_and_parameterised(self) -> None:
        self.load("id,name\n1,O'Brien\n2,obrien\n3,Smith\n")
        self.assertEqual(self.engine.rows(column="name", query="O'B")["total"], 1)
        self.assertEqual(self.engine.rows(column="name", query="BRIEN")["total"], 2)
        self.assertEqual(self.engine.rows(column="name", query="' OR 1=1 --")["total"], 0)

    def test_aggregations(self) -> None:
        self.load()
        red = [v for i, v in enumerate(self.SCORES, start=1) if i % 2]
        blue = [v for i, v in enumerate(self.SCORES, start=1) if not i % 2]
        for agg, fn in (("sum", sum), ("mean", statistics.mean), ("median", statistics.median), ("count", len)):
            got = {r["label"]: r["value"] for r in self.engine.aggregate("team", "score", agg)["rows"]}
            self.assertAlmostEqual(got["red"], fn(red), msg=agg)
            self.assertAlmostEqual(got["blue"], fn(blue), msg=agg)

    def test_aggregate_orders_limits_and_labels_blanks(self) -> None:
        self.load("g,v\na,1\nb,5\n,3\nc,x\n")
        rows = self.engine.aggregate("g", "v", "sum", order="asc")["rows"]
        self.assertEqual([(r["label"], r["value"]) for r in rows], [("a", 1.0), ("(blank)", 3.0), ("b", 5.0)])
        self.assertEqual(len(self.engine.aggregate("g", "v", "sum", limit=1)["rows"]), 1)
        self.assertEqual(self.engine.aggregate("g", None, "count", with_groups=True)["groups"], 4)

    def test_histogram_counts_every_value_once(self) -> None:
        self.load()
        hist = self.engine.histogram("score", bins=4)
        self.assertEqual((hist["lo"], hist["hi"], sum(hist["counts"])), (3.0, 100.0, 10))
        self.assertEqual(hist["counts"], [9, 0, 0, 1])  # the maximum lands in the last bin, not past it

    def test_histogram_of_one_distinct_value_and_of_nothing(self) -> None:
        self.load("v,t\n5,a\n5,b\n")
        self.assertEqual(self.engine.histogram("v", bins=3)["counts"], [2, 0, 0])
        self.assertEqual(self.engine.histogram("t"), {"lo": None, "hi": None, "counts": []})

    def test_box_plot(self) -> None:
        self.load()
        box = self.engine.box("score")
        q1, median, q3 = statistics.quantiles(self.SCORES, n=4, method="inclusive")
        self.assertEqual((box["n"], box["lo"], box["hi"], box["outliers"]), (10, 3.0, 100.0, [100.0]))
        self.assertAlmostEqual(box["med"], median)
        self.assertAlmostEqual(box["q1"], q1)
        self.assertAlmostEqual(box["q3"], q3)

    def test_welch_inputs(self) -> None:
        self.load()
        red = [v for i, v in enumerate(self.SCORES, start=1) if i % 2]
        out = self.engine.welch("team", "score", "red", "green")
        self.assertEqual(out["a"]["n"], 5)
        self.assertAlmostEqual(out["a"]["mean"], statistics.mean(red))
        self.assertAlmostEqual(out["a"]["var"], statistics.variance(red))
        self.assertEqual(out["b"], {"n": 0, "mean": None, "var": None})

    def test_regression_and_correlation(self) -> None:
        self.load("x,y\n1,2\n2,4.1\n3,5.9\n4,8.2\n5,\n")
        xs, ys = [1, 2, 3, 4], [2, 4.1, 5.9, 8.2]
        out = self.engine.regression("x", "y")
        self.assertEqual(out["n"], 4)  # the row with no y is left out
        self.assertAlmostEqual(out["r"], statistics.correlation(xs, ys))
        slope, intercept = statistics.linear_regression(xs, ys)
        self.assertAlmostEqual(out["slope"], slope)
        self.assertAlmostEqual(out["intercept"], intercept)

    def test_scatter_samples_but_reports_the_true_total(self) -> None:
        self.load("x,y\n" + "".join("%d,%d\n" % (i, i * 2) for i in range(500)))
        out = self.engine.scatter("x", "y", limit=50)
        self.assertEqual((len(out["pairs"]), out["total"]), (50, 500))
        self.assertTrue(all(p["y"] == p["x"] * 2 for p in out["pairs"]))

    def test_distinct_values_most_frequent_first(self) -> None:
        self.load("g\nb\na\nb\n\nc\nb\na\n")
        self.assertEqual(self.engine.distinct("g")["values"], ["b", "a", "c"])
        self.assertEqual(self.engine.distinct("g", limit=1)["values"], ["b"])


class TransformTests(EngineCase):
    def table(self):
        return self.engine.q('SELECT * FROM "data" ORDER BY rowid')

    def test_drop_missing(self) -> None:
        self.load("a,b\n1,x\n2,\n,y\n4,z\n")
        self.assertEqual(self.engine.clean("drop_missing"), "Dropped 2 rows with missing values.")
        self.assertEqual(self.table(), [(1, "x"), (4, "z")])

    def test_fill_strategies(self) -> None:
        for strategy, expected in (("zero", 0), ("mean", 4.0), ("median", 3.0)):
            self.load("a,b\n1,x\n3,y\n,z\n8,\n")
            self.assertEqual(self.engine.clean("fill", strategy=strategy), "Filled 1 missing cells. Review the changed data.")
            self.assertEqual(self.table()[2][0], expected, strategy)
            self.assertIsNone(self.table()[3][1], strategy)  # text is left alone by numeric fills

    def test_fill_with_a_marker_fills_text_and_numbers(self) -> None:
        self.load("a,b\n1,x\n,y\n2,\n")
        self.engine.clean("fill", strategy="marker", marker="n/a")
        self.assertEqual(self.table(), [("1", "x"), ("n/a", "y"), ("2", "n/a")])

    def test_dedupe_keeps_the_first_of_each_and_the_order(self) -> None:
        self.load("a,b\n2,y\n1,x\n2,y\n3,z\n1,x\n")
        self.assertEqual(self.engine.clean("dedupe"), "Removed 2 exact duplicate rows.")
        self.assertEqual(self.table(), [(2, "y"), (1, "x"), (3, "z")])

    def test_trim_collapses_inner_whitespace(self) -> None:
        self.load('a,b\n1,"x   y"\n2,"p\tq"\n3,clean\n')
        self.assertEqual(self.engine.clean("trim"), "Normalized 2 text cells.")
        self.assertEqual([r[1] for r in self.table()], ["x y", "p q", "clean"])

    def test_drop_column_and_its_limits(self) -> None:
        self.load("a,b\n1,x\n")
        self.engine.clean("drop_column", column="b")
        self.assertEqual(self.engine.col_names(), ["a"])
        with self.assertRaises(UserError):
            self.engine.clean("drop_column", column="a")  # the last column stays
        with self.assertRaises(UserError):
            self.engine.clean("drop_column", column="nope")
        with self.assertRaises(UserError):
            self.engine.clean("explode")

    def test_formula_adds_a_column_and_keeps_row_order(self) -> None:
        self.load("a,b\n3,1\n1,0\n2,2\n")
        out = self.engine.formula("ratio", "[a] / [b]")
        self.assertEqual(out, {"changed": 2, "rows": 3})
        self.assertEqual(self.table(), [(3, 1, 3.0), (1, 0, None), (2, 2, 1.0)])

    def test_formula_name_rules(self) -> None:
        self.load("a,b\n1,2\n")
        for name, expression in (("", "[a]"), ("x", ""), ("A", "[a] + 1")):
            with self.assertRaises(UserError):
                self.engine.formula(name, expression)

    def test_rewrites_keep_rowids_contiguous_for_paging(self) -> None:
        self.load("a\n" + "".join("%d\n" % i for i in range(50)))
        self.engine.q('DELETE FROM "data" WHERE a % 2 = 1')
        self.engine.rebuild("* EXCLUDE (__redata_rid)")
        self.assertEqual([r["a"] for r in self.engine.rows(offset=20, limit=3)["rows"]], [40, 42, 44])


class WorkspaceTests(EngineCase):
    def test_the_dataset_survives_a_restart(self) -> None:
        self.load()
        self.engine.close()
        self.engine = Engine(str(self.root / "workspace"), threads=1)
        self.assertEqual(self.engine.status()["dataset"], "d.csv")
        self.assertEqual(self.engine.meta()["rows"], 10)

    def test_leftover_stage_and_export_files_are_cleared_on_start(self) -> None:
        self.load()
        export = self.engine.export("data")
        leftover = Path(self.engine.exports[export["id"]])
        self.assertTrue(leftover.exists())
        self.engine.close()
        self.engine = Engine(str(self.root / "workspace"), threads=1)
        self.assertFalse(leftover.exists())

    def test_upload_from_a_stream(self) -> None:
        import io
        data = self.CSV.encode()
        staged = self.engine.stage_upload("up.csv", io.BytesIO(data), len(data))
        self.assertEqual(staged["preview"][0], ["id", "team", "score"])
        self.assertEqual(self.engine.load(staged["stage"])["rows"], 10)
        self.assertEqual(list(Path(self.engine.stage_dir).iterdir()), [])  # the copy is removed after loading

    def test_a_short_upload_is_refused_and_cleaned_up(self) -> None:
        import io
        with self.assertRaises(UserError):
            self.engine.stage_upload("up.csv", io.BytesIO(b"a,b\n"), 4000)
        self.assertEqual(list(Path(self.engine.stage_dir).iterdir()), [])

    def test_loading_by_path_never_deletes_the_users_file(self) -> None:
        path = self.root / "mine.csv"
        path.write_text("a\n1\n", encoding="utf-8")
        self.engine.load(self.engine.stage_path(str(path))["stage"])
        self.assertTrue(path.exists())

    def test_tsv_and_excel_sheet_choice(self) -> None:
        self.assertEqual(self.load("a\tb\n1\tx y\n", name="t.tsv")["rows"], 1)
        self.assertEqual(self.engine.q('SELECT b FROM "data"'), [("x y",)])
        import openpyxl
        book = openpyxl.Workbook()
        book.active.title = "first"
        book.active.append(["a"])
        book.active.append([1])
        second = book.create_sheet("second")
        second.append(["b", "c"])
        second.append([2, "two"])
        second.append([3, "three"])
        path = self.root / "book.xlsx"
        book.save(path)
        staged = self.engine.stage_path(str(path))
        self.assertEqual(staged["sheets"], ["first", "second"])
        self.assertEqual(self.engine.excel_preview(staged["stage"], 1)[0], ["b", "c"])
        meta = self.engine.load(staged["stage"], sheet=1)
        self.assertEqual((meta["name"], meta["rows"]), ("book.xlsx · second", 2))


if __name__ == "__main__":
    unittest.main()
