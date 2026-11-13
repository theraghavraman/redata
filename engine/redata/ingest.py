"""File staging and loading: CSV/TSV, JSON/NDJSON, Excel and Parquet into DuckDB."""

import csv
import os
import shutil
import sys
import uuid

import duckdb

from .util import (CHUNK, PREVIEW_ROWS, TABLE, UserError, file_ext, is_nested_type, is_text_type, plain, qi,
                   safe_filename, unique_headers)


class IngestMixin:
    def excel_file_to_csv(self, path):
        st = {"path": path, "ext": file_ext(path)}
        return self._excel_to_csv(st, 0)

    # ---- staging ------------------------------------------------------------
    def begin_upload(self, filename):
        """Reserve a stage folder for an upload and return where to write it."""
        filename = safe_filename(filename)
        ext = file_ext(filename)
        self._check_ext(ext)
        sid = uuid.uuid4().hex
        folder = os.path.join(self.stage_dir, sid)
        os.makedirs(folder)
        return {"id": sid, "folder": folder, "path": os.path.join(folder, filename), "name": filename, "ext": ext}

    def abort_upload(self, upload):
        if upload:
            shutil.rmtree(upload["folder"], ignore_errors=True)

    def finish_upload(self, upload):
        """Register a fully written upload as a stage and return its preview."""
        with self.lock:
            return self._register_stage(upload["id"], upload["path"], upload["name"], upload["ext"],
                                        copied=True, folder=upload["folder"])

    def stage_upload(self, filename, stream, length):
        """Copy ``length`` bytes from a file-like ``stream`` into a new stage."""
        upload = self.begin_upload(filename)
        remaining = length
        with open(upload["path"], "wb") as fh:
            while remaining > 0:
                chunk = stream.read(min(CHUNK, remaining))
                if not chunk:
                    break
                fh.write(chunk)
                remaining -= len(chunk)
        if remaining > 0:
            self.abort_upload(upload)
            raise UserError("The upload was interrupted before the whole file arrived.")
        return self.finish_upload(upload)

    def stage_path(self, raw_path):
        path = os.path.abspath(os.path.expanduser(str(raw_path or "").strip().strip('"').strip("'")))
        if not raw_path or not os.path.isfile(path):
            raise UserError("No file was found at that path on this computer.")
        ext = file_ext(path)
        self._check_ext(ext)
        return self._register_stage(uuid.uuid4().hex, path, os.path.basename(path), ext, copied=False, folder=None)

    def _check_ext(self, ext):
        if ext not in ("csv", "tsv", "txt", "json", "ndjson", "jsonl", "xlsx", "xlsm", "xls", "parquet"):
            raise UserError("Unsupported file type: ." + (ext or "?") +
                            " (use CSV, TSV, TXT, JSON, NDJSON, Parquet, XLSX or XLS)")

    def _register_stage(self, sid, path, name, ext, copied, folder):
        kind = {"csv": "delimited", "tsv": "delimited", "txt": "delimited",
                "json": "json", "ndjson": "json", "jsonl": "json",
                "xlsx": "excel", "xlsm": "excel", "xls": "excel",
                "parquet": "parquet"}[ext]
        st = {"id": sid, "path": path, "name": name, "ext": ext, "kind": kind,
              "copied": copied, "folder": folder, "size": os.path.getsize(path)}
        self.stages[sid] = st
        resp = {"stage": sid, "name": name, "kind": kind, "size": st["size"], "sheets": [], "preview": None}
        if kind == "delimited":
            resp["preview"] = self._csv_preview(st)
        elif kind == "excel":
            sheets = self._excel_sheets(st)
            resp["sheets"] = sheets
            resp["preview"] = self.excel_preview(sid, 0)
        return resp

    def _stage(self, sid):
        st = self.stages.get(sid)
        if not st or not os.path.isfile(st["path"]):
            raise UserError("The selected file is no longer available. Choose it again.")
        return st

    def drop_stage(self, sid):
        st = self.stages.pop(sid, None)
        if st and st["copied"] and st["folder"]:
            shutil.rmtree(st["folder"], ignore_errors=True)

    def _csv_source(self, st, header, sample_size=None, all_varchar=False):
        opts = ["header=%s" % ("true" if header else "false"), "null_padding=true"]
        if st["ext"] == "tsv":
            opts.append("delim='\\t'")
        if st.get("parallel") is False:
            # DuckDB's parallel CSV scanner cannot combine null_padding with
            # quoted newlines. Set this only after preview detects that specific
            # compatibility error, preserving parallel imports for ordinary files.
            opts.append("parallel=false")
        if sample_size is not None:
            opts.append("sample_size=%d" % sample_size)
        if all_varchar:
            opts.append("all_varchar=true")
        return "read_csv(%s, %s)" % (self._lit(st["path"]), ", ".join(opts))

    def _delimited_headers(self, st):
        """Read original header cells before DuckDB normalizes duplicate names."""
        try:
            with open(st["path"], "r", encoding="utf-8-sig", newline="") as stream:
                sample = stream.read(65536)
                if st["ext"] == "tsv":
                    delimiter = "\t"
                else:
                    # .csv used to be hardcoded to ',', but DuckDB auto-detects the
                    # real delimiter, so a ';' or '|' file got its header row split
                    # on the wrong character and every column came out misnamed.
                    try:
                        delimiter = csv.Sniffer().sniff(
                            sample[:8192], delimiters=",\t;|"
                        ).delimiter
                    except csv.Error:
                        delimiter = ","
                stream.seek(0)
                return next(csv.reader(stream, delimiter=delimiter), [])
        except (OSError, UnicodeError, csv.Error):
            # Preserve DuckDB's normal fallback for unusual encodings/dialects.
            return None

    def _csv_preview(self, st):
        sql = "SELECT * FROM %s LIMIT %d" % (
            self._csv_source(st, False, all_varchar=True), PREVIEW_ROWS
        )
        try:
            rows = self.q(sql)
        except duckdb.Error as exc:
            message = str(exc).lower()
            if "null_padding" not in message or "quoted new lines" not in message:
                raise
            st["parallel"] = False
            sql = "SELECT * FROM %s LIMIT %d" % (
                self._csv_source(st, False, all_varchar=True), PREVIEW_ROWS
            )
            rows = self.q(sql)
        return [[plain(v) for v in r] for r in rows]

    # ---- excel ----------------------------------------------------------------
    def _excel_sheets(self, st):
        if st["ext"] == "xls":
            xlrd = self._xlrd()
            book = xlrd.open_workbook(st["path"], on_demand=True)
            return book.sheet_names()
        openpyxl = self._openpyxl()
        wb = openpyxl.load_workbook(st["path"], read_only=True, data_only=True)
        try:
            return list(wb.sheetnames)
        finally:
            wb.close()

    def _excel_rows(self, st, sheet_index):
        if st["ext"] == "xls":
            xlrd = self._xlrd()
            book = xlrd.open_workbook(st["path"], on_demand=True)
            sh = book.sheet_by_index(sheet_index)
            for r in range(sh.nrows):
                yield sh.row_values(r)
            return
        openpyxl = self._openpyxl()
        wb = openpyxl.load_workbook(st["path"], read_only=True, data_only=True)
        try:
            ws = wb.worksheets[sheet_index]
            for row in ws.iter_rows(values_only=True):
                yield row
        finally:
            wb.close()

    def excel_preview(self, sid, sheet_index):
        st = self._stage(sid)
        out = []
        for row in self._excel_rows(st, int(sheet_index or 0)):
            vals = [plain(v) for v in row]
            if any(v is not None and str(v).strip() != "" for v in vals):
                out.append(vals)
            if len(out) >= PREVIEW_ROWS:
                break
        return out

    @staticmethod
    def _openpyxl():
        try:
            import openpyxl  # noqa: F401
            return openpyxl
        except ImportError:
            raise UserError("Excel import needs the openpyxl package: python -m pip install openpyxl")

    @staticmethod
    def _xlrd():
        try:
            import xlrd  # noqa: F401
            return xlrd
        except ImportError:
            raise UserError("Old .xls files need the xlrd package: python -m pip install xlrd "
                            "(or save the sheet as .xlsx or .csv)")

    def _excel_to_csv(self, st, sheet_index):
        out_path = os.path.join(self.temp_dir, uuid.uuid4().hex + ".csv")
        with open(out_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            for row in self._excel_rows(st, sheet_index):
                w.writerow(["" if v is None else plain(v) for v in row])
        return out_path

    # ---- loading -----------------------------------------------------------------
    def load(self, sid, header=True, names=None, sheet=0):
        st = self._stage(sid)
        tmp_csv = None
        try:
            if st["kind"] == "delimited":
                source = self._pick_csv_source(st, header)
                display = st["name"]
                if header and not names:
                    names = self._delimited_headers(st)
            elif st["kind"] == "excel":
                tmp_csv = self._excel_to_csv(st, int(sheet or 0))
                fake = dict(st, path=tmp_csv, ext="csv")
                source = self._pick_csv_source(fake, header)
                sheets = self._excel_sheets(st)
                display = st["name"] + " · " + sheets[int(sheet or 0)]
            elif st["kind"] == "json":
                source = self._json_source(st)
                display = st["name"]
                names = None
            else:
                source = "read_parquet(%s)" % self._lit(st["path"])
                display = st["name"]
                names = None
            self._create_from(source, names)
        finally:
            if tmp_csv:
                try:
                    os.remove(tmp_csv)
                except OSError:
                    pass
        self.drop_stage(sid)
        self.state["name"] = display
        self.state["linked_stream"] = None
        self.save_state()
        self.changed()
        return self.meta()

    def _pick_csv_source(self, st, header):
        """DuckDB guesses column types from a sample. If a value later in the file
        does not fit the guess, the load is retried with a full-file guess, then as text."""
        return [self._csv_source(st, header),
                self._csv_source(st, header, sample_size=-1),
                self._csv_source(st, header, all_varchar=True)]

    def _json_source(self, st):
        # maximum_object_size is deliberately not set here. DuckDB reserves roughly
        # twice the requested size per thread, so the previous value of 1 GiB meant a
        # 2 GiB allocation - and an OutOfMemoryException on any machine whose DuckDB
        # memory limit is smaller than that - even for a three-line file. The
        # folder-sync path (_file_relation) has always used the default.
        src = "read_json_auto(%s, format='auto')" % self._lit(st["path"])
        try:
            desc = self.q("DESCRIBE SELECT * FROM %s" % src)
            # {"rows": [ {...}, ... ]} -> unwrap the array of objects
            if len(desc) >= 1:
                lists = [(c, t) for c, t, *_ in desc if str(t).upper().startswith("STRUCT") and str(t).endswith("[]")]
                if len(lists) > 1:
                    # Picking lists[0] here silently dropped every other field.
                    raise UserError(
                        "This JSON file contains more than one array of records (%s). "
                        "ReData cannot tell which one you meant. Import a file with a "
                        "single array, or reshape it first." % ", ".join(c for c, _ in lists))
                if lists and self.q("SELECT count(*) FROM %s" % src)[0][0] == 1:
                    c = lists[0][0]
                    return "(SELECT u.* FROM (SELECT unnest(%s) AS u FROM %s))" % (qi(c), src)
        except duckdb.Error as exc:
            raise UserError("Could not read the JSON file: %s" % str(exc).split("\n")[0])
        return src

    def _create_from(self, sources, names):
        if isinstance(sources, str):
            sources = [sources]
        last = None
        for i, source in enumerate(sources):
            try:
                return self._create_one(source, names)
            except UserError:
                raise
            except duckdb.Error as e:
                last = e
                self.q("DROP TABLE IF EXISTS __redata_load")
                if i < len(sources) - 1:
                    sys.stdout.write("  type guess did not fit every row, retrying (%s)\n" % str(e).split("\n")[0][:120])
        raise UserError("Could not read the file: %s" % str(last).split("\n")[0])

    def _create_one(self, source, names):
        desc = self.q("DESCRIBE SELECT * FROM %s" % source)
        if not desc:
            raise UserError("No columns were found in the file.")
        src_cols = [(r[0], r[1]) for r in desc]
        final = unique_headers(names if names else [c for c, _ in src_cols], len(src_cols))
        select, not_all_null = [], []
        for (c, t), alias in zip(src_cols, final):
            id_ = qi(c)
            if is_text_type(t):
                e = "NULLIF(trim(%s), '')" % id_
            elif is_nested_type(t):
                e = "CAST(to_json(%s) AS VARCHAR)" % id_
            else:
                e = id_
            select.append("%s AS %s" % (e, qi(alias)))
            not_all_null.append("%s IS NOT NULL" % e)
        sql = "CREATE OR REPLACE TABLE __redata_load AS SELECT %s FROM %s WHERE %s" % (
            ", ".join(select), source, " OR ".join(not_all_null))
        self.q(sql)
        n = self.q("SELECT count(*) FROM __redata_load")[0][0]
        if not n:
            self.q("DROP TABLE __redata_load")
            raise UserError("No data rows were found after skipping blank rows.")
        self.q("DROP TABLE IF EXISTS %s" % qi(TABLE))
        self.q("ALTER TABLE __redata_load RENAME TO %s" % qi(TABLE))
