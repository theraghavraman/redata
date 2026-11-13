"""The FastAPI app: access checks, error shapes and the routes the page uses."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from fastapi.testclient import TestClient  # noqa: E402

from redata import __version__  # noqa: E402
from redata.engine import Engine  # noqa: E402
from redata.server import create_app  # noqa: E402

PORT = 8765
TOKEN = "test-token-not-a-secret"
CSV = b"id,city,amount\n1,Pune,10\n2,Mumbai,20\n3,Pune,30\n"


class ApiCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="redata-api-")
        self.root = Path(self.temp.name)
        self.engine = Engine(str(self.root / "workspace"), threads=1)
        self.engine.start_pipeline(background=False)
        self.app = create_app(self.engine, TOKEN, PORT, ui_root=str(ROOT))
        self.client = TestClient(self.app, base_url="http://127.0.0.1:%d" % PORT)
        self.auth = {"X-ReData-Token": TOKEN}

    def tearDown(self) -> None:
        try:
            self.client.close()
            self.engine.close()
        finally:
            self.temp.cleanup()

    def post(self, path: str, body: dict | None = None):
        return self.client.post(path, json=body or {}, headers=self.auth)

    def load_csv(self, content: bytes = CSV, name: str = "sales.csv") -> dict:
        staged = self.client.post("/api/stage", params={"name": name}, content=content, headers=self.auth)
        self.assertEqual(staged.status_code, 200, staged.text)
        loaded = self.post("/api/load", {"stage": staged.json()["stage"], "header": True})
        self.assertEqual(loaded.status_code, 200, loaded.text)
        return loaded.json()["meta"]


class AccessTests(ApiCase):
    def test_api_needs_the_token(self) -> None:
        for response in (self.client.get("/api/status"), self.client.post("/api/meta", json={}),
                         self.client.post("/api/pipeline/overview", json={})):
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json(), {"error": "Missing or wrong engine token."})

    def test_a_wrong_token_is_rejected(self) -> None:
        response = self.client.get("/api/status", headers={"X-ReData-Token": TOKEN + "x"})
        self.assertEqual(response.status_code, 403)

    def test_a_non_ascii_token_is_rejected_not_an_error(self) -> None:
        response = self.client.get("/api/status", headers={"X-ReData-Token": "café".encode("latin-1")})
        self.assertEqual(response.status_code, 403)

    def test_the_token_in_the_query_string_only_works_for_downloads(self) -> None:
        self.assertEqual(self.client.get("/api/status", params={"t": TOKEN}).status_code, 403)

    def test_a_foreign_host_header_is_rejected_even_with_the_token(self) -> None:
        """DNS rebinding: another site resolves its own name to 127.0.0.1."""
        headers = dict(self.auth, Host="attacker.example")
        for response in (self.client.get("/api/status", headers=headers), self.client.get("/", headers=headers)):
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json(), {"error": "Forbidden host."})

    def test_the_same_host_on_another_port_is_rejected(self) -> None:
        response = self.client.get("/api/status", headers=dict(self.auth, Host="127.0.0.1:9999"))
        self.assertEqual(response.status_code, 403)

    def test_localhost_is_accepted(self) -> None:
        response = self.client.get("/api/status", headers=dict(self.auth, Host="localhost:%d" % PORT))
        self.assertEqual(response.status_code, 200)

    def test_every_response_carries_the_security_headers(self) -> None:
        for response in (self.client.get("/"), self.client.get("/api/status", headers=self.auth),
                         self.client.get("/api/status"), self.client.get("/nope.html")):
            self.assertEqual(response.headers["x-frame-options"], "DENY")
            self.assertEqual(response.headers["x-content-type-options"], "nosniff")
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])

    def test_a_large_json_body_is_refused(self) -> None:
        response = self.client.post("/api/sql", content=b"x" * (10 * 1024 * 1024 + 1),
                                    headers=dict(self.auth, **{"Content-Type": "application/json"}))
        self.assertEqual((response.status_code, response.json()), (400, {"error": "Request too large."}))

    def test_the_api_schema_needs_the_token_too(self) -> None:
        self.assertEqual(self.client.get("/api/openapi.json").status_code, 403)
        schema = self.client.get("/api/openapi.json", headers=self.auth).json()
        self.assertEqual(schema["info"]["version"], __version__)
        self.assertIn("/api/pipeline/save_stream", schema["paths"])
        self.assertIn("/api/rows", schema["paths"])


class StaticTests(ApiCase):
    def test_the_page_gets_the_token(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn('window.REDATA_ENGINE={"token": "%s", "version": "%s"}' % (TOKEN, __version__), response.text)

    def test_only_the_page_carries_the_token(self) -> None:
        response = self.client.get("/vendor/sql-wasm.js")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(TOKEN, response.text)

    def test_engine_source_hidden_files_and_other_types_are_not_served(self) -> None:
        for path in ("/engine/redata_engine.py", "/engine/requirements.txt", "/.gitignore", "/.git/config",
                     "/README.md", "/pyproject.toml", "/tests/test_server_api.py", "/vendor/", "/assets"):
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_path_traversal_is_not_served(self) -> None:
        for path in ("/../engine/redata_engine.py", "/assets/../../etc/passwd", "/%2e%2e/%2e%2e/etc/passwd",
                     "/assets/%2e%2e/index.html", "//etc/passwd"):
            response = self.client.get(path)
            self.assertNotIn(b"root:", response.content)
            self.assertNotIn(TOKEN.encode(), response.content if response.status_code != 200 else b"")

    def test_without_a_page_the_api_still_runs(self) -> None:
        client = TestClient(create_app(self.engine, TOKEN, PORT), base_url="http://127.0.0.1:%d" % PORT)
        root = client.get("/")
        self.assertEqual(root.status_code, 200)
        self.assertIn("text/plain", root.headers["content-type"])
        self.assertEqual(client.get("/index.html").status_code, 404)
        self.assertEqual(client.get("/api/status", headers=self.auth).status_code, 200)


class DatasetApiTests(ApiCase):
    def test_status_by_get_and_post(self) -> None:
        for response in (self.client.get("/api/status", headers=self.auth), self.post("/api/status")):
            body = response.json()
            self.assertEqual((body["version"], body["dataset"], body["syncsRunning"]), (__version__, None, 0))

    def test_upload_load_and_page(self) -> None:
        meta = self.load_csv()
        self.assertEqual((meta["name"], meta["rows"], [c["name"] for c in meta["columns"]]),
                         ("sales.csv", 3, ["id", "city", "amount"]))
        page = self.post("/api/rows", {"offset": 1, "limit": 2}).json()
        self.assertEqual((page["total"], [r["id"] for r in page["rows"]]), (3, [2, 3]))
        self.assertIn("ms", page)

    def test_rows_filter_and_sort(self) -> None:
        self.load_csv()
        page = self.post("/api/rows", {"column": "city", "query": "pune", "sort": "amount", "dir": -1}).json()
        self.assertEqual((page["total"], [r["amount"] for r in page["rows"]]), (2, [30, 10]))

    def test_an_empty_upload_is_refused(self) -> None:
        response = self.client.post("/api/stage", params={"name": "empty.csv"}, content=b"", headers=self.auth)
        self.assertEqual((response.status_code, response.json()), (400, {"error": "The selected file is empty."}))

    def test_an_unsupported_upload_is_refused_and_leaves_nothing_behind(self) -> None:
        response = self.client.post("/api/stage", params={"name": "notes.exe"}, content=b"MZ", headers=self.auth)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported file type", response.json()["error"])
        self.assertEqual(list((self.root / "workspace" / "stage").iterdir()), [])

    def test_an_upload_name_cannot_escape_the_stage_folder(self) -> None:
        response = self.client.post("/api/stage", params={"name": "../../escaped.csv"}, content=CSV, headers=self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "escaped.csv")
        self.assertFalse((self.root / "escaped.csv").exists())
        self.assertFalse((self.root / "workspace" / "escaped.csv").exists())

    def test_stage_path_load_and_discard(self) -> None:
        path = self.root / "local.csv"
        path.write_bytes(CSV)
        staged = self.post("/api/stage_path", {"path": str(path)}).json()
        self.assertEqual(staged["preview"][0], ["id", "city", "amount"])
        self.assertEqual(self.post("/api/discard", {"stage": staged["stage"]}).json()["ok"], True)
        gone = self.post("/api/load", {"stage": staged["stage"]})
        self.assertEqual(gone.status_code, 400)
        self.assertTrue(path.exists())  # a file loaded by path is never deleted

    def test_queries_before_any_data_explain_themselves(self) -> None:
        response = self.post("/api/meta")
        self.assertEqual(response.status_code, 400)
        self.assertIn("No dataset is loaded", response.json()["error"])

    def test_aggregate_and_statistics(self) -> None:
        self.load_csv()
        agg = self.post("/api/aggregate", {"g": "city", "y": "amount", "agg": "sum", "groups": True}).json()
        self.assertEqual([(r["label"], r["value"]) for r in agg["rows"]], [("Pune", 40.0), ("Mumbai", 20.0)])
        self.assertEqual(agg["groups"], 2)
        self.assertEqual(self.post("/api/distinct", {"col": "city"}).json()["values"], ["Pune", "Mumbai"])
        self.assertEqual(self.post("/api/histogram", {"col": "amount", "bins": 2}).json()["counts"], [1, 2])
        self.assertEqual(self.post("/api/box", {"col": "amount"}).json()["med"], 20.0)
        self.assertEqual(self.post("/api/scatter", {"x": "id", "y": "amount"}).json()["total"], 3)
        reg = self.post("/api/regression", {"x": "id", "y": "amount"}).json()
        self.assertAlmostEqual(reg["slope"], 10.0)
        welch = self.post("/api/welch", {"g": "city", "y": "amount", "a": "Pune", "b": "Mumbai"}).json()
        self.assertEqual((welch["a"]["n"], welch["a"]["mean"], welch["b"]["n"]), (2, 20.0, 1))

    def test_an_unknown_column_is_a_400(self) -> None:
        self.load_csv()
        response = self.post("/api/histogram", {"col": "nope"})
        self.assertEqual((response.status_code, response.json()["error"]), (400, "Unknown column: nope"))

    def test_clean_and_formula_return_the_new_profile(self) -> None:
        self.load_csv(b"id,amount\n1,10\n1,10\n2,\n")
        deduped = self.post("/api/clean", {"op": "dedupe"}).json()
        self.assertEqual((deduped["message"], deduped["meta"]["rows"]), ("Removed 1 exact duplicate rows.", 2))
        filled = self.post("/api/clean", {"op": "fill", "strategy": "zero"}).json()
        self.assertEqual(filled["meta"]["missingTotal"], 0)
        derived = self.post("/api/formula", {"name": "double", "expr": "[amount] * 2"}).json()
        self.assertEqual((derived["changed"], [c["name"] for c in derived["meta"]["columns"]][-1]), (2, "double"))

    def test_sql_is_read_only(self) -> None:
        self.load_csv()
        ok = self.post("/api/sql", {"query": "SELECT city, sum(amount) AS total FROM data GROUP BY 1 ORDER BY 1"}).json()
        self.assertEqual(ok["rows"], [{"city": "Mumbai", "total": 20}, {"city": "Pune", "total": 40}])
        for query in ("DROP TABLE data", "DELETE FROM data", "SELECT * FROM read_csv('/etc/passwd')",
                      "SELECT 1; DROP TABLE data"):
            response = self.post("/api/sql", {"query": query})
            self.assertEqual(response.status_code, 400, query)
        self.assertEqual(self.post("/api/sql", {"query": "SELECT count(*) AS n FROM data"}).json()["rows"], [{"n": 3}])

    def test_a_sql_mistake_is_reported_as_text(self) -> None:
        self.load_csv()
        response = self.post("/api/sql", {"query": "SELECT nope FROM data"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("nope", response.json()["error"])

    def test_export_and_download(self) -> None:
        self.load_csv()
        export = self.post("/api/export", {"kind": "data", "format": "csv"}).json()
        self.assertEqual(export["file"], "sales_export.csv")
        url = "/api/download/%s" % export["id"]
        self.assertEqual(self.client.get(url).status_code, 403)
        download = self.client.get(url, params={"t": TOKEN})
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content.replace(b"\r\n", b"\n"), CSV)
        self.assertIn('attachment; filename="sales_export.csv"', download.headers["content-disposition"])
        self.assertEqual(self.client.get("/api/download/unknown", params={"t": TOKEN}).status_code, 404)

    def test_export_of_a_sql_result_as_json(self) -> None:
        self.load_csv()
        export = self.post("/api/export", {"kind": "sql", "format": "json",
                                           "query": "SELECT id FROM data WHERE amount > 10 ORDER BY id"}).json()
        download = self.client.get("/api/download/%s" % export["id"], headers=self.auth)
        self.assertEqual(download.json(), [{"id": 2}, {"id": 3}])

    def test_a_malformed_body_is_a_400_with_an_error_field(self) -> None:
        for response in (
            self.client.post("/api/rows", content=b"{not json", headers=dict(self.auth, **{"Content-Type": "application/json"})),
            self.post("/api/rows", {"limit": "many"}),
            self.client.post("/api/rows", json=[1, 2], headers=self.auth),
        ):
            self.assertEqual(response.status_code, 400, response.text)
            self.assertTrue(response.json()["error"].startswith("Bad request"), response.text)

    def test_an_empty_body_uses_the_defaults(self) -> None:
        self.load_csv()
        response = self.client.post("/api/rows", headers=self.auth)
        self.assertEqual((response.status_code, response.json()["total"]), (200, 3))

    def test_unknown_routes(self) -> None:
        self.assertEqual((self.post("/api/nope").status_code, self.post("/api/nope").json()),
                         (400, {"error": "Unknown engine endpoint."}))
        self.assertEqual(self.post("/api/pipeline/nope").json(), {"error": "Unknown pipeline action."})
        missing = self.client.get("/api/nope", headers=self.auth)
        self.assertEqual((missing.status_code, missing.json()), (404, {"error": "Not found."}))
        self.assertEqual(self.client.put("/api/rows", json={}, headers=self.auth).status_code, 405)


class PipelineApiTests(ApiCase):
    def setUp(self) -> None:
        super().setUp()
        self.db = self.root / "shop.db"
        con = sqlite3.connect(self.db)
        con.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, amount INTEGER)")
        con.executemany("INSERT INTO orders VALUES (?, ?)", [(1, 10), (2, 20)])
        con.commit()
        con.close()

    def connect(self) -> str:
        saved = self.post("/api/pipeline/save_connection",
                          {"type": "sqlite", "name": "shop", "values": {"path": str(self.db)}})
        self.assertEqual(saved.status_code, 200, saved.text)
        return saved.json()["id"]

    def test_catalog_lists_the_connectors(self) -> None:
        catalog = self.post("/api/pipeline/catalog").json()["catalog"]
        self.assertEqual(sorted(catalog), ["files", "http", "mysql", "postgres", "rest", "s3", "snowflake",
                                           "sqlite", "sqlserver"])

    def test_connection_test_tables_and_columns(self) -> None:
        cid = self.connect()
        self.assertEqual(self.post("/api/pipeline/test_connection", {"id": cid}).json()["ok"], True)
        self.assertEqual(self.post("/api/pipeline/source_tables", {"id": cid}).json()["tables"], ["orders"])
        self.assertEqual(self.post("/api/pipeline/source_columns", {"id": cid, "source": "orders"}).json()["columns"],
                         ["id", "amount"])

    def test_a_pipeline_problem_is_a_400_with_its_message(self) -> None:
        response = self.post("/api/pipeline/save_stream", {"connection_id": "nope", "source": "orders"})
        self.assertEqual((response.status_code, response.json()["error"]), (400, "That connection no longer exists."))
        response = self.post("/api/pipeline/save_stream", {"connection_id": self.connect(), "source": "orders",
                                                           "mode": "append"})
        self.assertIn("cursor column", response.json()["error"])

    def test_sync_now_runs_in_the_background_and_can_be_opened(self) -> None:
        self.engine.close()
        self.engine = Engine(str(self.root / "workspace2"), threads=1)
        self.engine.start_pipeline(background=True)
        self.client = TestClient(create_app(self.engine, TOKEN, PORT), base_url="http://127.0.0.1:%d" % PORT)
        cid = self.connect()
        stream = self.post("/api/pipeline/save_stream", {"connection_id": cid, "source": "orders", "mode": "append",
                                                         "cursor": "id", "target": "orders"}).json()
        self.assertEqual(self.post("/api/pipeline/sync_now", {"id": stream["id"]}).json()["status"], "queued")
        deadline = time.time() + 20
        runs = []
        while time.time() < deadline and not runs:
            runs = self.post("/api/pipeline/runs", {"stream": stream["id"]}).json()["runs"]
            time.sleep(0.05)
        self.assertEqual([(r["status"], r["rows_read"], r["trigger"]) for r in runs], [("success", 2, "manual")])
        overview = self.post("/api/pipeline/overview").json()
        self.assertEqual(overview["staged"], [{"table": "orders", "rows": 2, "columns": 3}])
        self.assertEqual(overview["streams"][0]["cursorDisplay"], "2")
        meta = self.post("/api/open_staged", {"table": "orders", "link": True}).json()["meta"]
        self.assertEqual((meta["name"], meta["rows"], meta["linkedStream"]), ("staging.orders", 2, stream["id"]))

    def test_secrets_never_come_back(self) -> None:
        self.post("/api/pipeline/save_connection", {"type": "postgres", "name": "pg", "values": {
            "host": "db.example", "port": "5432", "database": "app", "user": "reader", "password": "s3cret"}})
        self.assertNotIn("s3cret", self.post("/api/pipeline/overview").text)


if __name__ == "__main__":
    unittest.main()
