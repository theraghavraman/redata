"""Sync behaviour: modes, saved state and schema drift.

Every test runs a real sync from a SQLite file or a folder of files into
DuckDB staging tables, with no network. The pipeline is started without its
background threads so each run happens exactly when the test asks for it.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from redata import connectors as C  # noqa: E402
from redata import pipeline as P  # noqa: E402
from redata.engine import Engine  # noqa: E402


class SyncCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="redata-sync-")
        self.root = Path(self.temp.name)
        self.workspace = str(self.root / "workspace")
        self.db_path = self.root / "shop.db"
        self.src = sqlite3.connect(self.db_path)
        self.src.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, amount, status TEXT, updated_at TEXT)")
        self.add_orders((1, 10, "new", "2026-01-01 10:00:00"),
                        (2, 20, "new", "2026-01-01 11:00:00"),
                        (3, 30, "paid", "2026-01-02 09:00:00"))
        self.open()
        self.conn_id = self.pipe.save_connection(
            {"type": "sqlite", "name": "shop", "values": {"path": str(self.db_path)}})["id"]

    def tearDown(self) -> None:
        try:
            self.src.close()
            self.engine.close()
        finally:
            self.temp.cleanup()

    def open(self) -> None:
        self.engine = Engine(self.workspace, threads=1)
        self.pipe = self.engine.start_pipeline(background=False)

    def reopen(self) -> None:
        """Stop the engine and start a new one on the same workspace."""
        self.engine.close()
        self.open()

    def add_orders(self, *rows) -> None:
        self.src.executemany("INSERT INTO orders (id, amount, status, updated_at) VALUES (?, ?, ?, ?)", rows)
        self.src.commit()

    def stream(self, **settings) -> str:
        body = {"connection_id": self.conn_id, "source": "orders", "target": "orders"}
        body.update(settings)
        return self.pipe.save_stream(body)["id"]

    def sync(self, stream_id: str) -> dict:
        self.pipe.run(stream_id, "test")
        return self.pipe.runs(1, stream_id)[0]

    def staged(self, sql: str):
        return self.engine.q(sql)

    def saved_state(self, stream_id: str) -> dict:
        """The state as written to disk, not the copy in memory."""
        cfg = json.loads((Path(self.workspace) / "connections.json").read_text(encoding="utf-8"))
        return next(s for s in cfg["streams"] if s["id"] == stream_id)["state"]


class FullSyncTests(SyncCase):
    def test_full_copies_every_row(self) -> None:
        run = self.sync(self.stream(mode="full"))
        self.assertEqual((run["status"], run["rows_read"], run["rows_written"], run["table_rows"]),
                         ("success", 3, 3, 3))
        self.assertEqual(self.staged("SELECT id, amount, status FROM staging.orders ORDER BY id"),
                         [(1, 10, "new"), (2, 20, "new"), (3, 30, "paid")])

    def test_full_picks_up_deletes_and_edits(self) -> None:
        sid = self.stream(mode="full")
        self.sync(sid)
        self.src.execute("DELETE FROM orders WHERE id = 2")
        self.src.execute("UPDATE orders SET amount = 99 WHERE id = 1")
        self.src.commit()
        run = self.sync(sid)
        self.assertEqual(run["table_rows"], 2)
        self.assertEqual(self.staged("SELECT id, amount FROM staging.orders ORDER BY id"), [(1, 99), (3, 30)])

    def test_full_with_an_empty_source_empties_the_table(self) -> None:
        sid = self.stream(mode="full")
        self.sync(sid)
        self.src.execute("DELETE FROM orders")
        self.src.commit()
        run = self.sync(sid)
        self.assertEqual((run["status"], run["table_rows"]), ("success", 0))
        self.assertEqual(run["message"], "The source returned no rows.")

    def test_full_stamps_every_row_with_a_load_time(self) -> None:
        self.sync(self.stream(mode="full"))
        self.assertEqual(self.staged("SELECT count(_redata_loaded_at) FROM staging.orders"), [(3,)])

    def test_source_can_be_a_query(self) -> None:
        sid = self.stream(mode="full", source="SELECT id, amount * 2 AS doubled FROM orders WHERE status = 'new'",
                          target="new_orders")
        self.assertEqual(self.sync(sid)["status"], "success")
        self.assertEqual(self.staged("SELECT id, doubled FROM staging.new_orders ORDER BY id"), [(1, 20), (2, 40)])


class AppendSyncTests(SyncCase):
    def test_append_reads_only_rows_past_the_cursor(self) -> None:
        sid = self.stream(mode="append", cursor="id")
        first = self.sync(sid)
        self.assertEqual((first["rows_read"], first["cursor_from"], first["cursor_to"]), (3, None, "3"))
        self.add_orders((4, 40, "new", "2026-01-03 08:00:00"), (5, 50, "new", "2026-01-03 09:00:00"))
        second = self.sync(sid)
        self.assertEqual((second["rows_read"], second["cursor_from"], second["cursor_to"], second["table_rows"]),
                         (2, "3", "5", 5))
        self.assertEqual(second["message"], "2 new rows.")

    def test_append_with_nothing_new_reads_nothing_and_keeps_the_cursor(self) -> None:
        sid = self.stream(mode="append", cursor="id")
        self.sync(sid)
        run = self.sync(sid)
        self.assertEqual((run["status"], run["rows_read"], run["message"], run["cursor_to"], run["table_rows"]),
                         ("success", 0, "No new rows.", "3", 3))

    def test_append_does_not_see_edits_behind_the_cursor(self) -> None:
        """Append trusts the cursor: a row changed without moving it is not read again."""
        sid = self.stream(mode="append", cursor="id")
        self.sync(sid)
        self.src.execute("UPDATE orders SET amount = 99 WHERE id = 1")
        self.src.commit()
        self.assertEqual(self.sync(sid)["rows_read"], 0)
        self.assertEqual(self.staged("SELECT amount FROM staging.orders WHERE id = 1"), [(10,)])

    def test_append_with_a_timestamp_cursor(self) -> None:
        sid = self.stream(mode="append", cursor="updated_at")
        self.assertEqual(self.sync(sid)["cursor_to"], "2026-01-02 09:00:00")
        self.add_orders((4, 40, "new", "2026-01-02 09:00:01"))
        run = self.sync(sid)
        self.assertEqual((run["rows_read"], run["table_rows"]), (1, 4))

    def test_incremental_modes_need_a_cursor(self) -> None:
        with self.assertRaises(P.PipelineError):
            self.stream(mode="append")

    def test_a_missing_cursor_column_fails_the_run_and_keeps_the_table(self) -> None:
        sid = self.stream(mode="append", cursor="id")
        self.sync(sid)
        self.pipe._stream(sid)["cursor"] = "no_such_column"
        self.add_orders((4, 40, "new", "2026-01-03 08:00:00"))
        run = self.sync(sid)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(self.staged("SELECT count(*) FROM staging.orders"), [(3,)])
        # nothing temporary is left behind in the staging schema
        self.assertEqual([t["table"] for t in self.pipe.staged_tables()], ["orders"])


class UpsertSyncTests(SyncCase):
    def test_upsert_replaces_changed_rows_and_adds_new_ones(self) -> None:
        sid = self.stream(mode="upsert", cursor="updated_at", keys="id")
        self.sync(sid)
        self.src.execute("UPDATE orders SET amount = 15, status = 'paid', updated_at = '2026-01-03 12:00:00' WHERE id = 1")
        self.src.commit()
        self.add_orders((4, 40, "new", "2026-01-03 13:00:00"))
        run = self.sync(sid)
        self.assertEqual((run["status"], run["table_rows"]), ("success", 4))
        self.assertEqual(self.staged("SELECT id, amount, status FROM staging.orders ORDER BY id"),
                         [(1, 15, "paid"), (2, 20, "new"), (3, 30, "paid"), (4, 40, "new")])

    def test_upsert_rereads_the_cursor_boundary_without_duplicating(self) -> None:
        """Upsert reads ``cursor >= saved`` so rows sharing the last cursor value are not missed."""
        sid = self.stream(mode="upsert", cursor="updated_at", keys="id")
        self.sync(sid)
        # a second row with the same timestamp as the saved cursor arrives late
        self.add_orders((4, 40, "new", "2026-01-02 09:00:00"))
        run = self.sync(sid)
        self.assertEqual(run["rows_read"], 2)  # the boundary row again, plus the late one
        self.assertEqual(self.staged("SELECT id FROM staging.orders ORDER BY id"), [(1,), (2,), (3,), (4,)])

    def test_upsert_is_idempotent(self) -> None:
        sid = self.stream(mode="upsert", cursor="updated_at", keys="id")
        self.sync(sid)
        before = self.staged("SELECT id, amount, status, updated_at FROM staging.orders ORDER BY id")
        for _ in range(3):
            self.assertEqual(self.sync(sid)["table_rows"], 3)
        self.assertEqual(self.staged("SELECT id, amount, status, updated_at FROM staging.orders ORDER BY id"), before)

    def test_upsert_with_a_composite_key(self) -> None:
        self.src.execute("CREATE TABLE stock (shop TEXT, sku TEXT, qty INTEGER, updated_at TEXT)")
        self.src.executemany("INSERT INTO stock VALUES (?, ?, ?, ?)",
                             [("a", "x", 1, "2026-01-01"), ("a", "y", 2, "2026-01-01"), ("b", "x", 3, "2026-01-01")])
        self.src.commit()
        sid = self.stream(mode="upsert", source="stock", target="stock", cursor="updated_at", keys="shop, sku")
        self.sync(sid)
        self.src.execute("UPDATE stock SET qty = 9, updated_at = '2026-01-02' WHERE shop = 'a' AND sku = 'x'")
        self.src.commit()
        self.sync(sid)
        self.assertEqual(self.staged("SELECT shop, sku, qty FROM staging.stock ORDER BY shop, sku"),
                         [("a", "x", 9), ("a", "y", 2), ("b", "x", 3)])

    def test_upsert_needs_keys(self) -> None:
        with self.assertRaises(P.PipelineError):
            self.stream(mode="upsert", cursor="updated_at")

    def test_upsert_with_an_unknown_key_fails_and_leaves_the_table_alone(self) -> None:
        sid = self.stream(mode="upsert", cursor="updated_at", keys="id")
        self.sync(sid)
        self.pipe._stream(sid)["keys"] = ["missing_key"]
        self.add_orders((4, 40, "new", "2026-01-05 00:00:00"))
        run = self.sync(sid)
        self.assertEqual(run["status"], "failed")
        self.assertIn("missing_key", run["message"])
        self.assertEqual(self.staged("SELECT count(*) FROM staging.orders"), [(3,)])


class SavedStateTests(SyncCase):
    def test_the_cursor_is_saved_with_its_type(self) -> None:
        sid = self.stream(mode="append", cursor="id")
        self.sync(sid)
        self.assertEqual(self.saved_state(sid)["cursor"], {"t": "int", "v": 3})

    def test_the_cursor_survives_a_restart(self) -> None:
        sid = self.stream(mode="append", cursor="id")
        self.sync(sid)
        self.reopen()
        self.add_orders((4, 40, "new", "2026-01-03 08:00:00"))
        run = self.sync(sid)
        self.assertEqual((run["rows_read"], run["cursor_from"], run["cursor_to"], run["table_rows"]), (1, "3", "4", 4))

    def test_a_failed_run_does_not_move_the_cursor(self) -> None:
        sid = self.stream(mode="append", cursor="id")
        self.sync(sid)
        self.add_orders((4, 40, "new", "2026-01-03 08:00:00"))
        os.rename(self.db_path, str(self.db_path) + ".away")
        failed = self.sync(sid)
        self.assertEqual((failed["status"], failed["cursor_to"]), ("failed", "3"))
        self.assertEqual(self.saved_state(sid)["cursor"], {"t": "int", "v": 3})
        os.rename(str(self.db_path) + ".away", self.db_path)
        self.assertEqual(self.sync(sid)["rows_read"], 1)  # the row is picked up once the source is back

    def test_reset_makes_the_next_run_read_everything(self) -> None:
        sid = self.stream(mode="upsert", cursor="updated_at", keys="id")
        self.sync(sid)
        self.pipe.reset_stream(sid)
        self.assertEqual(self.saved_state(sid), {})
        run = self.sync(sid)
        self.assertEqual((run["rows_read"], run["table_rows"]), (3, 3))

    def test_changing_the_cursor_column_clears_the_saved_state(self) -> None:
        sid = self.stream(mode="append", cursor="id")
        self.sync(sid)
        self.stream(id=sid, mode="append", cursor="updated_at")
        self.assertEqual(self.saved_state(sid), {})

    def test_changing_only_the_schedule_keeps_the_saved_state(self) -> None:
        sid = self.stream(mode="append", cursor="id")
        self.sync(sid)
        self.stream(id=sid, mode="append", cursor="id", interval=15)
        self.assertEqual(self.saved_state(sid)["cursor"], {"t": "int", "v": 3})

    def test_every_run_is_logged(self) -> None:
        sid = self.stream(mode="append", cursor="id")
        self.sync(sid)
        self.sync(sid)
        rows = self.staged("SELECT stream, mode, trigger, status, rows_read, cursor_from, cursor_to "
                           "FROM redata_ops.sync_runs ORDER BY started_at")
        self.assertEqual(rows, [("orders", "append", "test", "success", 3, None, "3"),
                                ("orders", "append", "test", "success", 0, "3", "3")])

    def test_cursor_values_round_trip_through_json(self) -> None:
        import datetime
        import decimal
        for value in (7, 2.5, "abc", decimal.Decimal("10.25"), datetime.date(2026, 1, 2),
                      datetime.datetime(2026, 1, 2, 3, 4, 5)):
            encoded = json.loads(json.dumps(C.encode_cursor(value)))
            self.assertEqual(C.decode_cursor(encoded), value)
            self.assertIs(type(C.decode_cursor(encoded)), type(value))
        self.assertIsNone(C.decode_cursor(C.encode_cursor(None)))

    def test_two_syncs_cannot_share_a_staging_table(self) -> None:
        self.stream(mode="full")
        with self.assertRaises(P.PipelineError):
            self.pipe.save_stream({"connection_id": self.conn_id, "source": "orders", "target": "orders"})

    def test_a_connection_with_syncs_cannot_be_deleted(self) -> None:
        self.stream(mode="full")
        with self.assertRaises(P.PipelineError):
            self.pipe.delete_connection(self.conn_id)


class SchemaDriftTests(SyncCase):
    """The same policy must hold between runs as between batches of one run."""

    def columns(self, table: str = "orders") -> dict:
        return {c: t for c, t in self.pipe._cols(table)}

    def test_a_new_source_column_is_added_and_old_rows_are_null(self) -> None:
        sid = self.stream(mode="append", cursor="id")
        self.sync(sid)
        self.src.execute("ALTER TABLE orders ADD COLUMN channel TEXT")
        self.src.commit()
        self.src.execute("INSERT INTO orders VALUES (4, 40, 'new', '2026-01-03 08:00:00', 'web')")
        self.src.commit()
        self.assertEqual(self.sync(sid)["status"], "success")
        self.assertEqual(self.staged("SELECT id, channel FROM staging.orders ORDER BY id"),
                         [(1, None), (2, None), (3, None), (4, "web")])

    def test_a_dropped_source_column_stays_and_is_null_in_new_rows(self) -> None:
        sid = self.stream(mode="append", cursor="id", source="SELECT id, amount, status FROM orders")
        self.sync(sid)
        self.stream(id=sid, mode="append", cursor="id", source="SELECT id, amount FROM orders WHERE id > 3")
        self.add_orders((4, 40, "new", "2026-01-03 08:00:00"))
        self.assertEqual(self.sync(sid)["status"], "success")
        self.assertEqual(self.staged("SELECT id, status FROM staging.orders ORDER BY id"),
                         [(1, "new"), (2, "new"), (3, "paid"), (4, None)])

    def test_fractions_arriving_in_a_later_run_widen_the_column(self) -> None:
        """Without widening DuckDB rounds 2.75 into the BIGINT column and reports success."""
        sid = self.stream(mode="append", cursor="id")
        self.sync(sid)
        self.assertEqual(self.columns()["amount"], "BIGINT")
        self.add_orders((4, 2.75, "new", "2026-01-03 08:00:00"))
        self.assertEqual(self.sync(sid)["status"], "success")
        self.assertEqual(self.columns()["amount"], "DOUBLE")
        self.assertEqual(self.staged("SELECT amount FROM staging.orders ORDER BY id"),
                         [(10.0,), (20.0,), (30.0,), (2.75,)])

    def test_text_arriving_in_a_number_column_in_a_later_run_widens_it_to_text(self) -> None:
        sid = self.stream(mode="append", cursor="id")
        self.sync(sid)
        self.add_orders((4, "n/a", "new", "2026-01-03 08:00:00"))
        run = self.sync(sid)
        self.assertEqual(run["status"], "success", run["message"])
        self.assertEqual(self.columns()["amount"], "VARCHAR")
        self.assertEqual(self.staged("SELECT amount FROM staging.orders ORDER BY id"),
                         [("10",), ("20",), ("30",), ("n/a",)])

    def test_upsert_handles_the_same_drift_and_keeps_keys_unique(self) -> None:
        sid = self.stream(mode="upsert", cursor="updated_at", keys="id")
        self.sync(sid)
        self.src.execute("UPDATE orders SET amount = 'n/a', updated_at = '2026-01-04 00:00:00' WHERE id = 2")
        self.src.commit()
        self.add_orders((4, 2.5, "new", "2026-01-04 00:00:01"))
        run = self.sync(sid)
        self.assertEqual(run["status"], "success", run["message"])
        self.assertEqual(self.staged("SELECT id, amount FROM staging.orders ORDER BY id"),
                         [(1, "10"), (2, "n/a"), (3, "30"), (4, "2.5")])

    def test_only_the_column_that_does_not_fit_becomes_text(self) -> None:
        sid = self.stream(mode="append", cursor="id")
        self.sync(sid)
        self.add_orders((4, "n/a", "new", "2026-01-03 08:00:00"))
        self.sync(sid)
        kinds = self.columns()
        self.assertEqual((kinds["id"], kinds["amount"], kinds["status"]), ("BIGINT", "VARCHAR", "VARCHAR"))

    def test_casts_that_would_silently_change_values_widen_instead(self) -> None:
        """DuckDB performs each of these casts on INSERT without an error."""
        import datetime
        import decimal

        import pyarrow as pa
        cases = {
            # name: (first batch, later batch, expected type, expected values)
            "ts_into_date": (pa.array([datetime.date(2026, 1, 1)]), pa.array([datetime.datetime(2026, 1, 2, 13, 45)]),
                             "TIMESTAMP", [datetime.datetime(2026, 1, 1), datetime.datetime(2026, 1, 2, 13, 45)]),
            "int_into_bool": (pa.array([True]), pa.array([5], type=pa.int64()), "BIGINT", [1, 5]),
            "big_into_int32": (pa.array([1], type=pa.int32()), pa.array([2 ** 40], type=pa.int64()), "BIGINT", [1, 2 ** 40]),
            "more_decimals": (pa.array([decimal.Decimal("1.50")]), pa.array([decimal.Decimal("2.12345")]),
                              "DECIMAL(6,5)", [decimal.Decimal("1.50000"), decimal.Decimal("2.12345")]),
            "leading_zeros": (pa.array([7], type=pa.int64()), pa.array(["007"]), "VARCHAR", ["7", "007"]),
        }
        for name, (first, later, kind, values) in cases.items():
            self.pipe._write_arrow(name, pa.table({"n": [1], "v": first}), False)
            self.pipe._write_arrow(name, pa.table({"n": [2], "v": later}), True)
            self.assertEqual(self.columns(name)["v"], kind, name)
            self.assertEqual([r[0] for r in self.staged("SELECT v FROM staging.%s ORDER BY n" % name)], values, name)

    def test_values_that_fit_do_not_change_the_column_type(self) -> None:
        import pyarrow as pa
        cases = {
            "int_into_double": (pa.array([1.5]), pa.array([7], type=pa.int64()), "DOUBLE", [1.5, 7.0]),
            "digits_into_int": (pa.array([7], type=pa.int64()), pa.array(["8"]), "BIGINT", [7, 8]),
            "small_into_big": (pa.array([2 ** 40], type=pa.int64()), pa.array([3], type=pa.int32()), "BIGINT", [2 ** 40, 3]),
        }
        for name, (first, later, kind, values) in cases.items():
            self.pipe._write_arrow(name, pa.table({"n": [1], "v": first}), False)
            self.pipe._write_arrow(name, pa.table({"n": [2], "v": later}), True)
            self.assertEqual(self.columns(name)["v"], kind, name)
            self.assertEqual([r[0] for r in self.staged("SELECT v FROM staging.%s ORDER BY n" % name)], values, name)

    def test_when_stored_values_do_not_fit_the_incoming_type_the_column_becomes_text(self) -> None:
        import pyarrow as pa
        self.pipe._write_arrow("mixed", pa.table({"n": [1], "v": [1.5]}), False)
        self.pipe._write_arrow("mixed", pa.table({"n": [2], "v": pa.array([2 ** 60 + 1], type=pa.int64())}), True)
        self.assertEqual(self.columns("mixed")["v"], "VARCHAR")
        self.assertEqual(self.staged("SELECT v FROM staging.mixed ORDER BY n"), [("1.5",), (str(2 ** 60 + 1),)])

    def test_drift_between_batches_of_one_run(self) -> None:
        import pyarrow as pa
        self.pipe._write_arrow("t", pa.table({"id": [1, 2], "v": [10, 20]}), False)
        self.pipe._write_arrow("t", pa.table({"id": [3], "v": ["x"], "extra": ["new"]}), True)
        self.assertEqual(self.staged("SELECT id, v, extra FROM staging.t ORDER BY id"),
                         [(1, "10", None), (2, "20", None), (3, "x", "new")])
        self.assertEqual(self.columns("t")["id"], "BIGINT")


class FileSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="redata-filesync-")
        self.root = Path(self.temp.name)
        self.folder = self.root / "drops"
        self.folder.mkdir()
        self.engine = Engine(str(self.root / "workspace"), threads=1)
        self.pipe = self.engine.start_pipeline(background=False)
        self.conn_id = self.pipe.save_connection(
            {"type": "files", "name": "drops", "values": {"folder": str(self.folder)}})["id"]

    def tearDown(self) -> None:
        try:
            self.engine.close()
        finally:
            self.temp.cleanup()

    def write(self, name: str, content: str, mtime: int) -> None:
        path = self.folder / name
        path.write_text(content, encoding="utf-8")
        os.utime(path, (mtime, mtime))

    def stream(self, **settings) -> str:
        body = {"connection_id": self.conn_id, "source": "*.csv", "target": "sales"}
        body.update(settings)
        return self.pipe.save_stream(body)["id"]

    def sync(self, stream_id: str) -> dict:
        self.pipe.run(stream_id, "test")
        return self.pipe.runs(1, stream_id)[0]

    def test_append_loads_only_new_files(self) -> None:
        self.write("day1.csv", "id,amount\n1,10\n2,20\n", 1_700_000_000)
        sid = self.stream(mode="append")
        self.assertEqual(self.sync(sid)["rows_read"], 2)
        self.write("day2.csv", "id,amount\n3,30\n", 1_700_000_100)
        run = self.sync(sid)
        self.assertEqual((run["rows_read"], run["table_rows"], run["message"]), (1, 3, "1 file loaded."))
        self.assertEqual(self.sync(sid)["message"], "No new files.")

    def test_a_changed_file_is_loaded_again(self) -> None:
        self.write("day1.csv", "id,amount\n1,10\n", 1_700_000_000)
        sid = self.stream(mode="upsert", keys="id")
        self.sync(sid)
        self.write("day1.csv", "id,amount\n1,11\n2,20\n", 1_700_000_500)
        run = self.sync(sid)
        self.assertEqual(run["status"], "success", run["message"])
        self.assertEqual(self.engine.q("SELECT id, amount FROM staging.sales ORDER BY id"), [(1, 11), (2, 20)])

    def test_each_row_records_its_source_file(self) -> None:
        self.write("a.csv", "id\n1\n", 1_700_000_000)
        self.write("b.csv", "id\n2\n", 1_700_000_000)
        self.sync(self.stream(mode="full"))
        self.assertEqual(self.engine.q("SELECT id, _redata_source_file FROM staging.sales ORDER BY id"),
                         [(1, "a.csv"), (2, "b.csv")])

    def test_files_with_different_columns_are_combined(self) -> None:
        self.write("a.csv", "id,amount\n1,10\n", 1_700_000_000)
        self.write("b.csv", "id,amount,channel\n2,20,web\n", 1_700_000_000)
        self.sync(self.stream(mode="full"))
        self.assertEqual(self.engine.q("SELECT id, amount, channel FROM staging.sales ORDER BY id"),
                         [(1, 10, None), (2, 20, "web")])

    def test_the_file_list_is_saved_and_reset_clears_it(self) -> None:
        self.write("a.csv", "id\n1\n", 1_700_000_000)
        sid = self.stream(mode="append")
        self.sync(sid)
        self.assertEqual(list(self.pipe._stream(sid)["state"]["files"]), ["a.csv"])
        self.pipe.reset_stream(sid)
        self.assertEqual(self.sync(sid)["rows_read"], 1)

    def test_no_matching_files_is_not_an_error(self) -> None:
        run = self.sync(self.stream(mode="full"))
        self.assertEqual((run["status"], run["message"]), ("success", "No files match *.csv."))


class SecretsTests(SyncCase):
    def test_secrets_are_stored_apart_and_never_returned(self) -> None:
        cid = self.pipe.save_connection({"type": "postgres", "name": "pg", "values": {
            "host": "db.example", "port": "5432", "database": "app", "user": "reader", "password": "s3cret"}})["id"]
        settings = (Path(self.workspace) / "connections.json").read_text(encoding="utf-8")
        self.assertNotIn("s3cret", settings)
        self.assertIn("s3cret", (Path(self.workspace) / "secrets.json").read_text(encoding="utf-8"))
        overview = json.dumps(self.pipe.overview(), default=str)
        self.assertNotIn("s3cret", overview)
        saved = next(c for c in self.pipe.overview()["connections"] if c["id"] == cid)
        self.assertEqual(saved["secretsSet"], ["password"])

    @unittest.skipIf(os.name == "nt", "POSIX file modes")
    def test_the_secrets_file_is_readable_by_the_owner_only(self) -> None:
        self.assertEqual(os.stat(Path(self.workspace) / "secrets.json").st_mode & 0o777, 0o600)

    def test_a_blank_secret_keeps_the_stored_one(self) -> None:
        cid = self.pipe.save_connection({"type": "postgres", "name": "pg", "values": {
            "host": "db.example", "port": "5432", "database": "app", "user": "reader", "password": "s3cret"}})["id"]
        self.pipe.save_connection({"id": cid, "type": "postgres", "name": "pg", "values": {"host": "db2.example", "password": ""}})
        self.assertEqual(self.pipe.secrets[cid]["password"], "s3cret")
        self.assertEqual(self.pipe._conn(cid)["params"]["host"], "db2.example")

    def test_an_env_secret_is_read_from_the_environment(self) -> None:
        cid = self.pipe.save_connection({"type": "postgres", "name": "pg", "values": {
            "host": "db.example", "port": "5432", "database": "app", "user": "reader", "password": "env:REDATA_TEST_PW"}})["id"]
        os.environ["REDATA_TEST_PW"] = "from-env"
        try:
            self.assertEqual(self.pipe._secrets_for(cid)["password"], "from-env")
        finally:
            del os.environ["REDATA_TEST_PW"]


if __name__ == "__main__":
    unittest.main()
