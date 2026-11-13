"""SQL lab queries and exports."""

import os
import re
import uuid

from .sqlguard import read_only_statement
from .util import SQL_UI_ROWS, TABLE, UserError, plain, qi, safe_filename, unique_headers


class SqlLabMixin:
    # ---- SQL lab -------------------------------------------------------------------
    def _read_only_statement(self, query):
        return read_only_statement(self.con, query)

    def sql(self, query):
        stmt = self._read_only_statement(query)
        res = self.con.execute(stmt.query)
        if not res.description:
            return {"columns": [], "rows": [], "truncated": False}
        cols = unique_headers([d[0] for d in res.description], len(res.description))
        rows = res.fetchmany(SQL_UI_ROWS + 1)
        truncated = len(rows) > SQL_UI_ROWS
        rows = rows[:SQL_UI_ROWS]
        return {"columns": cols, "rows": [dict(zip(cols, [plain(v) for v in r])) for r in rows],
                "truncated": truncated}

    # ---- export -------------------------------------------------------------------------
    def export(self, kind, fmt="csv", query=None, g=None, y=None, agg="sum"):
        if kind != "sql":
            self.require_data()
        fmt = "json" if fmt == "json" else "csv"
        base = re.sub(r"\.[^.]+$", "", (self.state.get("name") or "redata").split(" · ")[0]) or "redata"
        if kind == "data":
            src = "SELECT * FROM %s ORDER BY rowid" % qi(TABLE)
            fname = "%s_export.%s" % (safe_filename(base), fmt)
        elif kind == "sql":
            stmt = self._read_only_statement(query)
            if str(stmt.type) != "StatementType.SELECT":
                raise UserError("Only SELECT results can be exported.")
            src = stmt.query.strip().rstrip(";")
            fname = "redata_sql_result.%s" % fmt
        elif kind == "aggregate":
            src = self._aggregate_export_sql(g, y, agg)
            fname = "redata_aggregate.%s" % fmt
        else:
            raise UserError("Unknown export.")
        eid = uuid.uuid4().hex
        folder = os.path.join(self.export_dir, eid)
        os.makedirs(folder)
        path = os.path.join(folder, fname)
        opts = "(FORMAT JSON, ARRAY true)" if fmt == "json" else "(HEADER, DELIMITER ',')"
        self.q("COPY (%s) TO %s %s" % (src, self._lit(path), opts))
        self.exports[eid] = path
        return {"id": eid, "file": fname, "size": os.path.getsize(path)}
