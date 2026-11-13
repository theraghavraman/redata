"""The engine: one DuckDB database, one active dataset, and the sync pipeline.

``Engine`` owns the DuckDB connection, the workspace folders and the saved
state. What it can do with a dataset lives in the mixins it is built from:

  ingest.IngestMixin        stage and load files
  profile.ProfileMixin      column profile (``meta``)
  analysis.AnalysisMixin    paging, aggregation, chart data, statistics
  transform.TransformMixin  cleaning and formula columns
  sqllab.SqlLabMixin        read-only SQL and exports
"""

import datetime
import json
import os
import shutil
import threading

import duckdb

from . import __version__ as VERSION
from .analysis import AnalysisMixin
from .ingest import IngestMixin
from .profile import ProfileMixin
from .sqllab import SqlLabMixin
from .transform import TransformMixin
from .util import TABLE, UserError, lit, qi


class Engine(IngestMixin, ProfileMixin, AnalysisMixin, TransformMixin, SqlLabMixin):
    _lit = staticmethod(lit)

    def __init__(self, workspace, memory_limit=None, threads=None):
        self.workspace = workspace
        self.stage_dir = os.path.join(workspace, "stage")
        self.export_dir = os.path.join(workspace, "exports")
        self.temp_dir = os.path.join(workspace, "tmp")
        for d in (workspace, self.stage_dir, self.export_dir, self.temp_dir):
            os.makedirs(d, exist_ok=True)
        self.state_path = os.path.join(workspace, "state.json")
        # Open the database first: DuckDB allows one process per file, so if
        # another engine already has this workspace the connect fails here,
        # before anything of that engine's is touched.
        self.con = duckdb.connect(os.path.join(workspace, "redata.duckdb"))
        # leftovers from an earlier run are never needed again
        for d in (self.stage_dir, self.export_dir, self.temp_dir):
            for entry in os.listdir(d):
                shutil.rmtree(os.path.join(d, entry), ignore_errors=True)
        self.con.execute("SET temp_directory = ?", [self.temp_dir])
        self.con.execute("SET preserve_insertion_order = true")
        if memory_limit:
            self.con.execute("SET memory_limit = ?", [memory_limit])
        if threads:
            self.con.execute("SET threads = %d" % int(threads))
        self.lock = threading.RLock()
        self.stages = {}
        self.exports = {}
        self.meta_cache = None
        self.data_version = 0
        self.pipeline = None
        self.state = {"name": None, "linked_stream": None, "updated_at": None}
        try:
            with open(self.state_path, "r", encoding="utf-8") as fh:
                self.state.update(json.load(fh))
        except (OSError, ValueError):
            pass
        if not self.has_data():
            self.state["name"] = None

    def start_pipeline(self, background=True):
        from .pipeline import Pipeline
        self.pipeline = Pipeline(self, background=background)
        return self.pipeline

    def close(self):
        """Stop the pipeline threads and close the database."""
        with self.lock:
            if self.pipeline is not None:
                self.pipeline.stop.set()
                for cur in (getattr(self.pipeline, "cur", None), getattr(self.pipeline, "rcur", None)):
                    try:
                        if cur is not None:
                            cur.close()
                    except Exception:
                        pass
            self.con.close()

    # ---- basics ----------------------------------------------------------
    def q(self, sql, params=None):
        return self.con.execute(sql, params or []).fetchall()

    def has_data(self):
        return bool(self.q(
            "SELECT 1 FROM information_schema.tables WHERE table_schema='main' AND table_name=?",
            [TABLE]))

    def require_data(self):
        if not self.has_data():
            raise UserError("No dataset is loaded in the local engine yet. Import a file first.")

    def columns(self):
        return [(r[0], r[1]) for r in self.q("DESCRIBE " + qi(TABLE))]

    def col_names(self):
        return [c for c, _ in self.columns()]

    def col_type(self, name):
        for c, t in self.columns():
            if c == name:
                return t
        raise UserError("Unknown column: " + str(name))

    def check_col(self, name):
        self.col_type(name)
        return qi(name)

    def row_count(self):
        return self.q("SELECT count(*) FROM " + qi(TABLE))[0][0]

    def save_state(self):
        try:
            with open(self.state_path, "w", encoding="utf-8") as fh:
                json.dump(self.state, fh)
        except OSError:
            pass

    def changed(self):
        self.meta_cache = None
        self.data_version += 1
        self.state["updated_at"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        self.save_state()

    def rebuild(self, select_list, where="", extra_from=""):
        """Rewrite the table, keeping original row order and contiguous rowids."""
        self.q(
            "CREATE OR REPLACE TABLE %s AS SELECT %s FROM (SELECT *, rowid AS __redata_rid FROM %s) %s %s ORDER BY __redata_rid"
            % (qi(TABLE), select_list, qi(TABLE), extra_from, where)
        )
        self.changed()

    # ---- status / meta -----------------------------------------------------
    def status(self):
        running = 0
        if self.pipeline:
            running = sum(1 for v in self.pipeline.status.values() if v == "running")
        return {"version": VERSION, "dataset": self.state.get("name") if self.has_data() else None,
                "dataVersion": self.data_version, "updatedAt": self.state.get("updated_at"),
                "linkedStream": self.state.get("linked_stream"), "syncsRunning": running}

    # ---- staging tables as the active dataset ---------------------------
    def open_staged(self, table, link=False):
        from .pipeline import SCHEMA
        exists = self.q("SELECT 1 FROM duckdb_tables() WHERE schema_name = ? AND table_name = ?", [SCHEMA, table])
        if not exists:
            raise UserError("No staging table called %s." % table)
        self.q("CREATE OR REPLACE TABLE %s AS SELECT * FROM %s.%s" % (qi(TABLE), SCHEMA, qi(table)))
        stream = None
        if link and self.pipeline:
            stream = next((x["id"] for x in self.pipeline.cfg["streams"] if x["target"] == table), None)
        self.state["name"] = "staging.%s" % table
        self.state["linked_stream"] = stream
        self.changed()
        return self.meta()

    def refresh_linked(self):
        from .pipeline import SCHEMA
        sid = self.state.get("linked_stream")
        if not sid or not self.pipeline:
            return
        target = next((x["target"] for x in self.pipeline.cfg["streams"] if x["id"] == sid), None)
        if not target:
            return
        with self.lock:
            self.q("CREATE OR REPLACE TABLE %s AS SELECT * FROM %s.%s" % (qi(TABLE), SCHEMA, qi(target)))
            self.changed()
            self.meta()
