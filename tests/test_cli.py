"""The command line: a sync configured and run end to end without the browser."""
from __future__ import annotations

import contextlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from redata import __version__, cli  # noqa: E402
from redata.engine import Engine  # noqa: E402


class CliCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="redata-cli-")
        self.root = Path(self.temp.name)
        self.workspace = str(self.root / "workspace")
        self.db = self.root / "shop.db"
        self.src = sqlite3.connect(self.db)
        self.src.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, amount INTEGER, updated_at TEXT)")
        self.src.executemany("INSERT INTO orders VALUES (?, ?, ?)",
                             [(1, 10, "2026-01-01"), (2, 20, "2026-01-02")])
        self.src.commit()

    def tearDown(self) -> None:
        self.src.close()
        self.temp.cleanup()

    def run_cli(self, *argv: str):
        """Run one command in-process; return (exit code, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv) + ["--workspace", self.workspace])
        return code, out.getvalue(), err.getvalue()

    def ok(self, *argv: str) -> str:
        code, out, err = self.run_cli(*argv)
        self.assertEqual(code, 0, err or out)
        return out

    def configure(self, mode: str = "append") -> None:
        self.ok("connection", "add", "--type", "sqlite", "--name", "shop", "--set", "path=%s" % self.db)
        extra = ["--keys", "id"] if mode == "upsert" else []
        self.ok("stream", "add", "--connection", "shop", "--source", "orders", "--mode", mode,
                "--cursor", "id", "--target", "orders", *extra)


class CliTests(CliCase):
    def test_configure_sync_and_query(self) -> None:
        self.configure()
        self.assertIn("Connected.", self.ok("connection", "test", "shop"))
        first = self.ok("sync", "orders")
        self.assertIn("success", first)
        self.assertIn("read 2", first)
        self.assertIn("cursor None -> 2", first)
        self.assertIn("staging.orders  2", " ".join(self.ok("tables").split("\n")[2].split()).replace(" 2 ", "  2 "))
        self.assertEqual(self.ok("sql", "SELECT id, amount FROM staging.orders ORDER BY id", "--format", "csv")
                         .replace("\r\n", "\n"), "id,amount\n1,10\n2,20\n")

    def test_state_carries_over_between_invocations(self) -> None:
        self.configure()
        self.ok("sync", "orders")
        self.src.execute("INSERT INTO orders VALUES (3, 30, '2026-01-03')")
        self.src.commit()
        runs = json.loads(self.ok("sync", "orders", "--json"))
        self.assertEqual((runs[0]["rows_read"], runs[0]["cursor_from"], runs[0]["cursor_to"], runs[0]["table_rows"],
                          runs[0]["trigger"]), (1, "2", "3", 3, "cli"))
        history = json.loads(self.ok("runs", "--json"))
        self.assertEqual([r["rows_read"] for r in history], [1, 2])  # newest first

    def test_sync_all_and_stream_list(self) -> None:
        self.configure()
        self.ok("stream", "add", "--connection", "shop", "--source", "SELECT id FROM orders", "--target", "ids")
        out = self.ok("sync", "--all")
        self.assertEqual(out.count("success"), 2)
        listing = self.ok("stream", "list")
        self.assertIn("orders", listing)
        self.assertIn("ids", listing)
        self.assertIn("append", listing)

    def test_a_failed_sync_exits_1_and_says_why(self) -> None:
        self.configure()
        self.src.close()
        os.remove(self.db)
        code, out, _ = self.run_cli("sync", "orders")
        self.assertEqual(code, 1)
        self.assertIn("failed", out)
        self.assertIn("No SQLite file", out)
        self.src = sqlite3.connect(self.db)

    def test_reset_then_sync_reads_everything_again(self) -> None:
        self.configure("upsert")
        self.ok("sync", "orders")
        self.ok("stream", "reset", "orders")
        run = json.loads(self.ok("sync", "orders", "--json"))[0]
        self.assertEqual((run["rows_read"], run["table_rows"]), (2, 2))

    def test_adding_the_same_name_updates_instead_of_duplicating(self) -> None:
        self.configure()
        self.configure()
        self.assertEqual(self.ok("connection", "list").count("sqlite"), 1)
        engine = Engine(self.workspace, threads=1)
        try:
            pipe = engine.start_pipeline(background=False)
            self.assertEqual((len(pipe.cfg["connections"]), len(pipe.cfg["streams"])), (1, 1))
        finally:
            engine.close()

    def test_remove_stream_and_connection(self) -> None:
        self.configure()
        self.ok("sync", "orders")
        code, _, err = self.run_cli("connection", "remove", "shop")
        self.assertEqual(code, 1)
        self.assertIn("syncs first", err)
        self.ok("stream", "remove", "orders", "--drop-table")
        self.ok("connection", "remove", "shop")
        self.assertNotIn("staging.orders", self.ok("tables"))

    def test_mistakes_exit_1_with_a_message(self) -> None:
        self.configure()
        for argv, expected in (
            (("sync", "nope"), "No sync called nope"),
            (("sync",), "Nothing to sync"),
            (("connection", "test", "nope"), "No connection called nope"),
            (("connection", "add", "--type", "sqlite", "--name", "x", "--set", "novalue"), "KEY=VALUE"),
            (("connection", "add", "--type", "sqlite", "--name", "y"), "Fill in: File path"),
            (("stream", "add", "--connection", "shop", "--source", "orders", "--mode", "upsert", "--cursor", "id"),
             "Upsert needs the key"),
            (("sql", "DROP TABLE staging.orders"), "read-only"),
        ):
            code, _, err = self.run_cli(*argv)
            self.assertEqual(code, 1, argv)
            self.assertIn(expected, err, argv)

    def test_connectors_listing(self) -> None:
        out = self.ok("connectors")
        for kind in ("postgres", "mysql", "sqlserver", "snowflake", "s3", "rest", "sqlite", "files", "http"):
            self.assertIn(kind, out)
        detail = self.ok("connectors", "postgres")
        self.assertIn("password", detail)
        self.assertIn("host", detail)

    def test_a_workspace_in_use_is_reported_not_damaged(self) -> None:
        """DuckDB locks the file per process; the second process must not clear the first one's files."""
        self.configure()
        holder = subprocess.Popen(
            [sys.executable, "-c",
             "import sys, time; sys.path.insert(0, sys.argv[1]);\n"
             "from redata.engine import Engine\n"
             "e = Engine(sys.argv[2]); open(e.stage_dir + '/keep.txt', 'w').close(); print('ready', flush=True); time.sleep(60)",
             str(ROOT / "engine"), self.workspace],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        try:
            self.assertEqual(holder.stdout.readline().strip(), "ready")
            code, _, err = self.run_cli("tables")
            self.assertEqual(code, 1)
            self.assertIn("in use by another engine", err)
            self.assertTrue((Path(self.workspace) / "stage" / "keep.txt").exists())
        finally:
            holder.kill()
            holder.wait()
            holder.stdout.close()

    def test_version_and_module_entry_point(self) -> None:
        result = subprocess.run([sys.executable, "-m", "redata", "--version"], capture_output=True, text=True,
                                env=dict(os.environ, PYTHONPATH=str(ROOT / "engine")))
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "redata " + __version__))

    def test_the_old_launcher_still_exposes_the_engine(self) -> None:
        import redata_engine
        self.assertIs(redata_engine.Engine, Engine)
        self.assertEqual(redata_engine.VERSION, __version__)

    def test_workspace_comes_from_the_environment(self) -> None:
        old = os.environ.get("REDATA_WORKSPACE")
        os.environ["REDATA_WORKSPACE"] = "/somewhere/else"
        try:
            self.assertEqual(cli.default_workspace(), "/somewhere/else")
        finally:
            if old is None:
                del os.environ["REDATA_WORKSPACE"]
            else:
                os.environ["REDATA_WORKSPACE"] = old


if __name__ == "__main__":
    unittest.main()
