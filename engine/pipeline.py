"""Connections, sync streams, the scheduler and the staging layer.

A *connection* is a source (a database, a folder, a bucket, an API). A
*stream* copies one table, query, file pattern or endpoint from a connection
into a DuckDB staging table, either on demand or on a schedule:

  full     replace the staging table with a fresh copy every run
  append   add only rows whose cursor column is newer than the last run
           (for files: only new or changed files)
  upsert   like append, but rows whose key already exists are replaced

Each run is logged in redata_ops.sync_runs. Connection settings live in
workspace/connections.json and secrets (passwords, tokens) in a separate
workspace/secrets.json that is readable by the owner only; neither leaves this
computer and the API never returns a secret.
"""

import datetime
import json
import os
import queue
import shutil
import threading
import time
import traceback
import uuid

import duckdb

import connectors as C

SCHEMA = "staging"
OPS = "redata_ops"
LOADED_AT = "_redata_loaded_at"
INTERVALS = [0, 5, 15, 30, 60, 180, 360, 720, 1440]


def qi(name):
    return '"' + str(name).replace('"', '""') + '"'


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


class PipelineError(Exception):
    pass


class Pipeline:
    def __init__(self, engine):
        self.engine = engine
        self.ws = engine.workspace
        self.cfg_path = os.path.join(self.ws, "connections.json")
        self.sec_path = os.path.join(self.ws, "secrets.json")
        self.cfg_lock = threading.RLock()
        self.cfg = {"connections": [], "streams": []}
        self.secrets = {}
        self._load()
        self.status = {}          # stream id -> "queued" | "running"
        self.queue = queue.Queue()
        self.stop = threading.Event()
        # one DuckDB cursor for the sync worker thread, one (behind rlock) for API reads
        self.rlock = threading.Lock()
        with engine.lock:
            self.cur = engine.con.cursor()
            self.rcur = engine.con.cursor()
            self.cur.execute("CREATE SCHEMA IF NOT EXISTS %s" % SCHEMA)
            self.cur.execute("CREATE SCHEMA IF NOT EXISTS %s" % OPS)
            self.cur.execute(
                "CREATE TABLE IF NOT EXISTS %s.sync_runs (run_id VARCHAR, stream_id VARCHAR, stream VARCHAR, "
                "connection VARCHAR, mode VARCHAR, trigger VARCHAR, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ, "
                "status VARCHAR, rows_read BIGINT, rows_written BIGINT, table_rows BIGINT, cursor_from VARCHAR, "
                "cursor_to VARCHAR, message VARCHAR)" % OPS)
        threading.Thread(target=self._worker, name="redata-sync", daemon=True).start()
        threading.Thread(target=self._scheduler, name="redata-scheduler", daemon=True).start()

    # ------------------------------------------------------------------ storage
    def _load(self):
        try:
            with open(self.cfg_path, "r", encoding="utf-8") as fh:
                self.cfg.update(json.load(fh))
        except (OSError, ValueError):
            pass
        try:
            with open(self.sec_path, "r", encoding="utf-8") as fh:
                self.secrets = json.load(fh)
        except (OSError, ValueError):
            self.secrets = {}

    def _save(self):
        with self.cfg_lock:
            tmp = self.cfg_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.cfg, fh, indent=2, default=str)
            os.replace(tmp, self.cfg_path)
            tmp = self.sec_path + ".tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.secrets, fh)
            os.replace(tmp, self.sec_path)
            try:
                os.chmod(self.sec_path, 0o600)
            except OSError:
                pass

    def _conn(self, cid):
        for c in self.cfg["connections"]:
            if c["id"] == cid:
                return c
        raise PipelineError("That connection no longer exists.")

    def _stream(self, sid):
        for s in self.cfg["streams"]:
            if s["id"] == sid:
                return s
        raise PipelineError("That sync no longer exists.")

    def _secrets_for(self, cid):
        raw = dict(self.secrets.get(cid, {}))
        # "env:NAME" keeps a secret in an environment variable instead of the file
        for k, v in list(raw.items()):
            if isinstance(v, str) and v.startswith("env:"):
                raw[k] = os.environ.get(v[4:], "")
        return raw

    def _source(self, conn):
        return C.make_source(conn["type"], conn.get("params", {}), self._secrets_for(conn["id"]), self.ws)

    # ------------------------------------------------------------- connections
    def catalog(self):
        return C.catalog()

    def overview(self):
        with self.cfg_lock:
            conns = []
            for c in self.cfg["connections"]:
                spec = C.CATALOG.get(c["type"], {})
                secret_keys = [f["key"] for f in spec.get("fields", []) if f.get("secret")]
                conns.append({
                    "id": c["id"], "name": c["name"], "type": c["type"], "typeLabel": spec.get("label", c["type"]),
                    "params": c.get("params", {}),
                    "secretsSet": [k for k in secret_keys if self.secrets.get(c["id"], {}).get(k)],
                    "lastTest": c.get("lastTest"),
                })
            streams = []
            for s in self.cfg["streams"]:
                st = dict(s)
                st["status"] = self.status.get(s["id"], "idle")
                st["cursorDisplay"] = C.display_cursor(s.get("state", {}).get("cursor"))
                state = dict(s.get("state", {}))
                state.pop("files", None)
                state["filesTracked"] = len(s.get("state", {}).get("files", {}) or {})
                st["state"] = state
                st["connectionName"] = next((c["name"] for c in self.cfg["connections"] if c["id"] == s["connection_id"]), "?")
                streams.append(st)
        runs = self.runs(30)
        return {"connections": conns, "streams": streams, "runs": runs, "intervals": INTERVALS,
                "staged": self.staged_tables(), "linked": self.engine.state.get("linked_stream")}

    def save_connection(self, body):
        kind = body.get("type")
        spec = C.CATALOG.get(kind)
        if not spec:
            raise PipelineError("Choose a connection type.")
        name = str(body.get("name") or "").strip() or spec["label"]
        values = body.get("values") or {}
        with self.cfg_lock:
            cid = body.get("id") or uuid.uuid4().hex[:10]
            existing = next((c for c in self.cfg["connections"] if c["id"] == cid), None)
            if any(c["name"].lower() == name.lower() and c["id"] != cid for c in self.cfg["connections"]):
                raise PipelineError("A connection called %s already exists." % name)
            params = dict(existing.get("params", {})) if existing else {}
            sec = dict(self.secrets.get(cid, {}))
            for f in spec["fields"]:
                k = f["key"]
                if k not in values:
                    continue
                v = values[k]
                v = v.strip() if isinstance(v, str) else v
                if f.get("secret"):
                    if v:  # a blank secret keeps the stored one
                        sec[k] = v
                else:
                    params[k] = v
            missing = [f["label"] for f in spec["fields"]
                       if f.get("required") and not f.get("secret") and not params.get(f["key"])]
            if missing:
                raise PipelineError("Fill in: " + ", ".join(missing))
            if existing:
                existing.update({"name": name, "params": params})
            else:
                self.cfg["connections"].append({"id": cid, "name": name, "type": kind, "params": params,
                                                "created": now_iso()})
            self.secrets[cid] = sec
            self._save()
        return {"id": cid}

    def delete_connection(self, cid):
        with self.cfg_lock:
            if any(s["connection_id"] == cid for s in self.cfg["streams"]):
                raise PipelineError("Delete this connection's syncs first.")
            self.cfg["connections"] = [c for c in self.cfg["connections"] if c["id"] != cid]
            self.secrets.pop(cid, None)
            self._save()
        key = os.path.join(self.ws, "keys", "%s_rsa_key.p8" % cid)
        if os.path.exists(key):
            os.remove(key)
        return {"ok": True}

    def test_connection(self, cid):
        conn = self._conn(cid)
        started = time.time()
        try:
            msg = self._source(conn).test()
            ok = True
        except C.SourceError as e:
            msg, ok = str(e), False
        except Exception as e:  # driver-specific errors
            msg, ok = "%s: %s" % (type(e).__name__, str(e).split("\n")[0]), False
        with self.cfg_lock:
            conn["lastTest"] = {"ok": ok, "message": msg, "at": now_iso(), "ms": int((time.time() - started) * 1000)}
            self._save()
        return conn["lastTest"]

    def snowflake_key(self, cid):
        conn = self._conn(cid)
        if conn["type"] != "snowflake":
            raise PipelineError("Key pairs are only for Snowflake connections.")
        path, sql = C.snowflake_keypair(self.ws, cid, conn.get("params", {}).get("user"))
        with self.cfg_lock:
            conn.setdefault("params", {})["private_key_path"] = path
            conn["params"]["auth"] = "keypair"
            self._save()
        return {"sql": sql, "path": path}

    def source_tables(self, cid):
        conn = self._conn(cid)
        try:
            return {"tables": self._source(conn).list_tables()}
        except C.SourceError as e:
            raise PipelineError(str(e))

    def source_columns(self, cid, source):
        conn = self._conn(cid)
        src = self._source(conn)
        if not hasattr(src, "columns"):
            return {"columns": []}
        try:
            return {"columns": src.columns(source)}
        except C.SourceError as e:
            raise PipelineError(str(e))
        except Exception as e:
            raise PipelineError(str(e).split("\n")[0])

    # ------------------------------------------------------------------ streams
    def save_stream(self, body):
        conn = self._conn(body.get("connection_id"))
        source = str(body.get("source") or "").strip()
        if not source:
            raise PipelineError("Choose a table, query, file pattern or endpoint to sync.")
        mode = body.get("mode") if body.get("mode") in ("full", "append", "upsert") else "full"
        cursor = str(body.get("cursor") or "").strip() or None
        keys = [k.strip() for k in str(body.get("keys") or "").split(",") if k.strip()]
        is_file = conn["type"] in ("files", "s3", "http")
        if mode in ("append", "upsert") and not cursor and not is_file:
            raise PipelineError("Incremental syncs need a cursor column, such as updated_at or an increasing id.")
        if mode == "upsert" and not keys:
            raise PipelineError("Upsert needs the key column(s) that identify a row, such as order_id.")
        if conn["type"] == "http" and mode != "full":
            mode = "full"
        interval = int(body.get("interval") or 0)
        target = C.slug(body.get("target") or "%s_%s" % (conn["name"], source.split(".")[-1].split("/")[-1].split("*")[0] or "data"))
        with self.cfg_lock:
            sid = body.get("id") or uuid.uuid4().hex[:10]
            existing = next((s for s in self.cfg["streams"] if s["id"] == sid), None)
            if any(s["target"] == target and s["id"] != sid for s in self.cfg["streams"]):
                raise PipelineError("Another sync already writes to staging.%s. Choose another table name." % target)
            rec = {"id": sid, "connection_id": conn["id"], "source": source, "target": target, "mode": mode,
                   "cursor": cursor, "keys": keys, "interval": max(0, interval), "enabled": bool(body.get("enabled", True))}
            if existing:
                reset = (existing.get("source") != source or existing.get("cursor") != cursor or existing.get("mode") != mode)
                state = {} if reset else existing.get("state", {})
                existing.clear()
                existing.update(rec, state=state)
            else:
                self.cfg["streams"].append(dict(rec, state={}, created=now_iso()))
            self._save()
        return {"id": sid, "target": target}

    def delete_stream(self, sid, drop_table=False):
        with self.cfg_lock:
            s = self._stream(sid)
            if self.status.get(sid) == "running":
                raise PipelineError("Wait for the running sync to finish.")
            self.cfg["streams"] = [x for x in self.cfg["streams"] if x["id"] != sid]
            self._save()
        if drop_table:
            with self.rlock:
                self.rcur.execute("DROP TABLE IF EXISTS %s.%s" % (SCHEMA, qi(s["target"])))
        if self.engine.state.get("linked_stream") == sid:
            self.engine.state["linked_stream"] = None
            self.engine.save_state()
        return {"ok": True}

    def reset_stream(self, sid):
        with self.cfg_lock:
            s = self._stream(sid)
            s["state"] = {}
            self._save()
        return {"ok": True}

    def enqueue(self, sid, trigger="manual"):
        self._stream(sid)
        if self.status.get(sid) in ("queued", "running"):
            return {"status": self.status[sid]}
        self.status[sid] = "queued"
        self.queue.put((sid, trigger))
        return {"status": "queued"}

    # ---------------------------------------------------------------- scheduler
    def _scheduler(self):
        while not self.stop.wait(15):
            try:
                now = time.time()
                with self.cfg_lock:
                    streams = list(self.cfg["streams"])
                for s in streams:
                    iv = int(s.get("interval") or 0)
                    if not iv or not s.get("enabled", True) or self.status.get(s["id"]):
                        continue
                    last = s.get("state", {}).get("last_started_ts") or 0
                    if now - last >= iv * 60:
                        self.enqueue(s["id"], "schedule")
            except Exception:  # never let the scheduler die
                traceback.print_exc()

    def _worker(self):
        while not self.stop.is_set():
            sid, trigger = self.queue.get()
            try:
                self.status[sid] = "running"
                self.run(sid, trigger)
            except Exception:
                traceback.print_exc()
            finally:
                self.status.pop(sid, None)

    # --------------------------------------------------------------------- runs
    def runs(self, limit=50, sid=None):
        where, params = "", []
        if sid:
            where, params = "WHERE stream_id = ?", [sid]
        with self.rlock:
            res = self.rcur.execute(
                "SELECT run_id, stream_id, stream, connection, mode, trigger, started_at, finished_at, status, rows_read, "
                "rows_written, table_rows, cursor_from, cursor_to, message FROM %s.sync_runs %s ORDER BY started_at DESC LIMIT %d"
                % (OPS, where, int(limit)), params).fetchall()
        cols = ["run_id", "stream_id", "stream", "connection", "mode", "trigger", "started_at", "finished_at", "status",
                "rows_read", "rows_written", "table_rows", "cursor_from", "cursor_to", "message"]
        out = []
        for r in res:
            d = dict(zip(cols, r))
            for k in ("started_at", "finished_at"):
                d[k] = d[k].isoformat() if d[k] else None
            out.append(d)
        return out

    def staged_tables(self):
        with self.rlock:
            res = self.rcur.execute(
                "SELECT table_name, column_count FROM duckdb_tables() WHERE schema_name = ? "
                "AND NOT starts_with(table_name, '__') ORDER BY table_name", [SCHEMA]).fetchall()
            out = []
            for name, ncols in res:
                try:
                    n = self.rcur.execute("SELECT count(*) FROM %s.%s" % (SCHEMA, qi(name))).fetchone()[0]
                except duckdb.Error:
                    n = None
                out.append({"table": name, "rows": n, "columns": ncols})
        return out

    def run(self, sid, trigger="manual"):
        with self.cfg_lock:
            s = self._stream(sid)
            conn = self._conn(s["connection_id"])
            s.setdefault("state", {})["last_started_ts"] = time.time()
            self._save()
        run_id = uuid.uuid4().hex[:12]
        started = datetime.datetime.now().astimezone()
        cursor_from = C.display_cursor(s["state"].get("cursor"))
        rec = {"read": 0, "written": 0, "table_rows": None, "cursor_to": cursor_from, "message": ""}
        status = "success"
        try:
            src = self._source(conn)
            if getattr(src, "kind", "") == "files" or conn["type"] in ("files", "s3", "http"):
                self._run_files(s, src, rec)
            else:
                self._run_rows(s, src, rec)
        except (C.SourceError, PipelineError) as e:
            status, rec["message"] = "failed", str(e)
        except duckdb.Error as e:
            status, rec["message"] = "failed", "DuckDB: " + str(e).split("\n")[0]
        except Exception as e:
            status, rec["message"] = "failed", "%s: %s" % (type(e).__name__, str(e).split("\n")[0])
            traceback.print_exc()
        finally:
            self._cleanup_temp(s)
        finished = datetime.datetime.now().astimezone()
        with self.cfg_lock:
            st = s.setdefault("state", {})
            st.update({"last_run": finished.isoformat(timespec="seconds"), "last_status": status,
                       "last_rows": rec["written"], "last_message": rec["message"],
                       "last_seconds": round((finished - started).total_seconds(), 1)})
            if status == "success":
                st["last_success"] = st["last_run"]
            self._save()
        self.cur.execute(
                "INSERT INTO %s.sync_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)" % OPS,
            [run_id, sid, s["target"], conn["name"], s["mode"], trigger, started, finished, status, rec["read"],
             rec["written"], rec["table_rows"], cursor_from, rec["cursor_to"], rec["message"][:2000]])
        if status == "success" and self.engine.state.get("linked_stream") == sid:
            try:
                self.engine.refresh_linked()
            except Exception:
                traceback.print_exc()
        return status

    # ------------------------------------------------------- loading primitives
    def _tbl(self, name):
        return "%s.%s" % (SCHEMA, qi(name))

    def _exists(self, name):
        return bool(self.cur.execute(
            "SELECT 1 FROM duckdb_tables() WHERE schema_name = ? AND table_name = ?", [SCHEMA, name]).fetchall())

    def _cols(self, name):
        return [(r[0], r[1]) for r in self.cur.execute("DESCRIBE %s" % self._tbl(name)).fetchall()]

    def _cleanup_temp(self, s):
        for prefix in ("__new_", "__inc_"):
            try:
                self.cur.execute("DROP TABLE IF EXISTS %s" % self._tbl(prefix + s["target"]))
            except duckdb.Error:
                pass

    def _write_arrow(self, table_name, arrow_tbl, created):
        """Append an Arrow table to a staging table, creating it and adding new columns as needed."""
        reg = "__redata_batch_%s" % uuid.uuid4().hex[:8]
        self.cur.register(reg, arrow_tbl)
        try:
            if not created:
                self.cur.execute("CREATE TABLE %s AS SELECT *, current_timestamp AS %s FROM %s"
                                 % (self._tbl(table_name), qi(LOADED_AT), reg))
                return
            have = {c.lower(): t for c, t in self._cols(table_name)}
            batch = [(r[0], r[1]) for r in self.cur.execute("DESCRIBE SELECT * FROM %s" % reg).fetchall()]
            for c, t in batch:
                if c.lower() not in have:
                    self.cur.execute("ALTER TABLE %s ADD COLUMN %s %s" % (self._tbl(table_name), qi(c), "VARCHAR" if t == '"NULL"' else t))
            try:
                self.cur.execute("INSERT INTO %s BY NAME SELECT *, current_timestamp AS %s FROM %s"
                                 % (self._tbl(table_name), qi(LOADED_AT), reg))
            except duckdb.ConversionException:
                # a value that does not fit the column's type: widen those columns to text and retry
                have = {c.lower(): t for c, t in self._cols(table_name)}
                for c, t in batch:
                    if have.get(c.lower()) != t and have.get(c.lower()) != "VARCHAR":
                        self.cur.execute("ALTER TABLE %s ALTER COLUMN %s TYPE VARCHAR" % (self._tbl(table_name), qi(c)))
                self.cur.execute("INSERT INTO %s BY NAME SELECT *, current_timestamp AS %s FROM %s"
                                 % (self._tbl(table_name), qi(LOADED_AT), reg))
        finally:
            self.cur.unregister(reg)

    def _max_cursor(self, table_name, col):
        names = {c.lower(): c for c, _ in self._cols(table_name)}
        real = names.get(str(col).lower())
        if not real:
            raise PipelineError("The cursor column %s is not in the data from the source." % col)
        return self.cur.execute("SELECT max(%s) FROM %s" % (qi(real), self._tbl(table_name))).fetchone()[0]

    def _swap_in(self, new, target):
        if self._exists(target):
            self.cur.execute("DROP TABLE %s" % self._tbl(target))
        self.cur.execute("ALTER TABLE %s RENAME TO %s" % (self._tbl(new), qi(target)))

    def _merge(self, s, inc):
        """Fold the batch table `inc` into the target according to the stream's mode."""
        target = s["target"]
        if not self._exists(target):
            self._swap_in(inc, target)
            return
        # new columns at the source appear in staging too
        have = {c.lower() for c, _ in self._cols(target)}
        for c, t in self._cols(inc):
            if c.lower() not in have:
                self.cur.execute("ALTER TABLE %s ADD COLUMN %s %s" % (self._tbl(target), qi(c), t))
        if s["mode"] == "upsert":
            cols = {c.lower(): c for c, _ in self._cols(inc)}
            keys = []
            for k in s["keys"]:
                if k.lower() not in cols:
                    raise PipelineError("Key column %s is not in the data from the source." % k)
                keys.append(cols[k.lower()])
            order = qi(cols.get(str(s["cursor"]).lower(), keys[0])) if s.get("cursor") else qi(keys[0])
            part = ", ".join(qi(k) for k in keys)
            self.cur.execute(
                "CREATE OR REPLACE TABLE %s AS SELECT * FROM %s QUALIFY row_number() OVER (PARTITION BY %s ORDER BY %s DESC) = 1"
                % (self._tbl(inc + "_d"), self._tbl(inc), part, order))
            cond = " AND ".join("t.%s IS NOT DISTINCT FROM d.%s" % (qi(k), qi(k)) for k in keys)
            self.cur.execute("BEGIN TRANSACTION")
            try:
                self.cur.execute("DELETE FROM %s t USING %s d WHERE %s" % (self._tbl(target), self._tbl(inc + "_d"), cond))
                self.cur.execute("INSERT INTO %s BY NAME SELECT * FROM %s" % (self._tbl(target), self._tbl(inc + "_d")))
                self.cur.execute("COMMIT")
            except Exception:
                self.cur.execute("ROLLBACK")
                raise
            finally:
                self.cur.execute("DROP TABLE IF EXISTS %s" % self._tbl(inc + "_d"))
        else:
            self.cur.execute("INSERT INTO %s BY NAME SELECT * FROM %s" % (self._tbl(target), self._tbl(inc)))
        self.cur.execute("DROP TABLE IF EXISTS %s" % self._tbl(inc))

    # ------------------------------------------------------------ row sources
    def _run_rows(self, s, src, rec):
        mode, target = s["mode"], s["target"]
        cursor_val = C.decode_cursor(s["state"].get("cursor")) if mode != "full" else None
        tmp = ("__new_" if mode == "full" else "__inc_") + target
        self.cur.execute("DROP TABLE IF EXISTS %s" % self._tbl(tmp))
        created = False
        for batch in src.read(s["source"], s.get("cursor") if mode != "full" else None, cursor_val,
                              inclusive=(mode == "upsert")):
            if batch.num_rows == 0:
                continue
            self._write_arrow(tmp, batch, created)
            created = True
            rec["read"] += batch.num_rows
        if not created:
            rec["message"] = "No new rows." if mode != "full" else "The source returned no rows."
            if mode == "full" and self._exists(target):
                self.cur.execute("DELETE FROM %s" % self._tbl(target))
            rec["table_rows"] = self._rowcount(target)
            return
        new_max = self._max_cursor(tmp, s["cursor"]) if s.get("cursor") else None
        if mode == "full":
            self._swap_in(tmp, target)
            rec["written"] = rec["read"]
        else:
            before = self._rowcount(target) or 0
            self._merge(s, tmp)
            rec["written"] = rec["read"]
            if mode == "append":
                rec["message"] = "%s new rows." % format(rec["read"], ",")
            if mode == "upsert":
                rec["message"] = "%s new, %s updated or re-checked." % (format(self._rowcount(target) - before, ","),
                                                         format(max(0, rec["read"] - (self._rowcount(target) - before)), ","))
        if new_max is not None:
            old = C.decode_cursor(s["state"].get("cursor"))
            try:
                keep = new_max if old is None or new_max > old else old
            except TypeError:
                keep = new_max
            with self.cfg_lock:
                s["state"]["cursor"] = C.encode_cursor(keep)
                self._save()
            rec["cursor_to"] = C.display_cursor(C.encode_cursor(keep))
        rec["table_rows"] = self._rowcount(target)

    def _rowcount(self, target):
        if not self._exists(target):
            return None
        return self.cur.execute("SELECT count(*) FROM %s" % self._tbl(target)).fetchone()[0]

    # ----------------------------------------------------------- file sources
    def _run_files(self, s, src, rec):
        mode, target = s["mode"], s["target"]
        done = None if mode == "full" else (s["state"].get("files") or {})
        files = src.files(s["source"], done)
        downloads = set()
        try:
            if not files:
                rec["message"] = "No new files." if mode != "full" else "No files match %s." % s["source"]
                rec["table_rows"] = self._rowcount(target)
                return
            tmp = ("__new_" if mode == "full" else "__inc_") + target
            self.cur.execute("DROP TABLE IF EXISTS %s" % self._tbl(tmp))
            created = False
            for key, path, sig in files:
                if os.sep + "downloads" + os.sep in path:
                    downloads.add(os.path.dirname(path))
                rel = self._file_relation(path)
                sql_sel = "SELECT *, %s AS _redata_source_file, current_timestamp AS %s FROM %s" % (
                    self._lit(key), qi(LOADED_AT), rel)
                if not created:
                    self.cur.execute("CREATE TABLE %s AS %s" % (self._tbl(tmp), sql_sel))
                    created = True
                else:
                    have = {c.lower() for c, _ in self._cols(tmp)}
                    for r in self.cur.execute("DESCRIBE %s" % sql_sel).fetchall():
                        c, t = r[0], r[1]
                        if c.lower() not in have:
                            self.cur.execute("ALTER TABLE %s ADD COLUMN %s %s" % (self._tbl(tmp), qi(c), t))
                    try:
                        self.cur.execute("INSERT INTO %s BY NAME %s" % (self._tbl(tmp), sql_sel))
                    except duckdb.ConversionException:
                        self.cur.execute("INSERT INTO %s BY NAME %s" % (self._tbl(tmp), sql_sel.replace(
                            rel, self._file_relation(path, all_varchar=True))))
            rec["read"] = self._rowcount(tmp) or 0
            if mode == "full":
                self._swap_in(tmp, target)
            else:
                if mode == "upsert" and not s.get("keys"):
                    raise PipelineError("Upsert needs key columns.")
                self._merge(s, tmp)
            rec["written"] = rec["read"]
            if mode != "full":
                with self.cfg_lock:
                    tracked = s["state"].setdefault("files", {})
                    for key, path, sig in files:
                        tracked[key] = sig
                    self._save()
            rec["message"] = "%d file%s loaded." % (len(files), "" if len(files) == 1 else "s")
            rec["table_rows"] = self._rowcount(target)
        finally:
            for d in downloads:
                shutil.rmtree(d, ignore_errors=True)

    @staticmethod
    def _lit(v):
        return "'" + str(v).replace("'", "''") + "'"

    def _file_relation(self, path, all_varchar=False):
        kind = C.file_kind(path)
        p = self._lit(path)
        if kind == "csv":
            opts = ["header=true", "null_padding=true"]
            if path.lower().endswith(".tsv"):
                opts.append("delim='\\t'")
            if all_varchar:
                opts.append("all_varchar=true")
            return "read_csv(%s, %s)" % (p, ", ".join(opts))
        if kind == "json":
            return "read_json_auto(%s, format='auto')" % p
        if kind == "parquet":
            return "read_parquet(%s)" % p
        if kind == "excel":
            csv_path = self.engine.excel_file_to_csv(path)
            return "read_csv(%s, header=true, null_padding=true%s)" % (self._lit(csv_path), ", all_varchar=true" if all_varchar else "")
        raise PipelineError("Unsupported file: " + path)
