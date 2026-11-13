"""Read-side queries: paging, aggregation, chart data and statistics."""

from .util import PAGE_MAX, TABLE, plain, qi


class AnalysisMixin:
    # ---- reading -----------------------------------------------------------------
    def rows(self, offset=0, limit=150, sort=None, direction=1, column=None, query=""):
        self.require_data()
        offset = max(0, int(offset or 0))
        limit = max(1, min(PAGE_MAX, int(limit or 150)))
        where, params = "", []
        if column and query:
            where = "WHERE contains(lower(CAST(%s AS VARCHAR)), lower(?))" % self.check_col(column)
            params.append(str(query))
        n = self.row_count()
        if not where and not sort:
            # rowids are kept contiguous, so a page is a direct range read
            res = self.con.execute(
                "SELECT * FROM %s WHERE rowid >= ? AND rowid < ? ORDER BY rowid" % qi(TABLE),
                [offset, offset + limit])
            total = n
        else:
            order = "rowid"
            if sort:
                order = "%s %s NULLS LAST, rowid" % (self.check_col(sort), "DESC" if int(direction or 1) < 0 else "ASC")
            res = self.con.execute(
                "SELECT * FROM %s %s ORDER BY %s LIMIT %d OFFSET %d" % (qi(TABLE), where, order, limit, offset),
                params)
            total = n if not where else None
        cols = [d[0] for d in res.description]
        data = [dict(zip(cols, [plain(v) for v in r])) for r in res.fetchall()]
        if total is None:
            total = self.q("SELECT count(*) FROM %s %s" % (qi(TABLE), where), params)[0][0]
        return {"columns": cols, "rows": data, "total": total, "offset": offset}

    @staticmethod
    def _agg_expr(agg, val):
        return {"sum": "sum(%s)", "mean": "avg(%s)", "median": "median(%s)"}.get(agg, "count(*)") % ((val,) if agg in ("sum", "mean", "median") else ())

    def aggregate(self, g, y=None, agg="sum", order="desc", limit=20, with_groups=False):
        self.require_data()
        gq = self.check_col(g)
        agg = agg if agg in ("sum", "mean", "median", "count") else "sum"
        val = "TRY_CAST(%s AS DOUBLE)" % self.check_col(y) if (y and agg != "count") else "NULL"
        value_expr = self._agg_expr(agg, "__v")
        having = "" if agg == "count" else "HAVING count(__v) > 0"
        limit = max(1, min(5000, int(limit or 20)))
        sql = ("SELECT COALESCE(CAST(%s AS VARCHAR), '(blank)') AS label, count(*) AS rows, %s AS n, %s AS value "
               "FROM (SELECT %s, %s AS __v FROM %s) GROUP BY 1 %s ORDER BY value %s NULLS LAST, label LIMIT %d") % (
            gq, "count(*)" if agg == "count" else "count(__v)", value_expr, gq, val, qi(TABLE), having,
            "ASC" if order == "asc" else "DESC", limit)
        res = self.q(sql)
        out = {"rows": [{"label": r[0], "rows": r[1], "n": r[2], "value": plain(r[3])} for r in res]}
        if with_groups:
            out["groups"] = self.q(
                "SELECT count(*) FROM (SELECT 1 FROM (SELECT %s, %s AS __v FROM %s) GROUP BY %s %s)"
                % (gq, val, qi(TABLE), gq, having))[0][0]
        return out

    def _aggregate_export_sql(self, g, y, agg):
        gq = self.check_col(g)
        agg = agg if agg in ("sum", "mean", "median", "count") else "sum"
        val = "TRY_CAST(%s AS DOUBLE)" % self.check_col(y) if (y and agg != "count") else "NULL"
        having = "" if agg == "count" else "HAVING count(__v) > 0"
        return ("SELECT COALESCE(CAST(%s AS VARCHAR), '(blank)') AS \"Group\", count(*) AS \"Rows\", %s AS \"Valid\", %s AS \"Value\" "
                "FROM (SELECT %s, %s AS __v FROM %s) GROUP BY 1 %s ORDER BY \"Value\" DESC NULLS LAST") % (
            gq, "count(*)" if agg == "count" else "count(__v)", self._agg_expr(agg, "__v"), gq, val, qi(TABLE), having)

    def histogram(self, col, bins=10):
        self.require_data()
        c = "TRY_CAST(%s AS DOUBLE)" % self.check_col(col)
        bins = max(1, min(100, int(bins or 10)))
        lo, hi, n = self.q("SELECT min(v), max(v), count(v) FROM (SELECT %s AS v FROM %s) WHERE isfinite(v)" % (c, qi(TABLE)))[0]
        if not n:
            return {"lo": None, "hi": None, "counts": []}
        width = (hi - lo) / bins or 1
        res = dict(self.q(
            "SELECT least(%d, CAST(floor((v - ?) / ?) AS BIGINT)) AS b, count(*) FROM (SELECT %s AS v FROM %s) "
            "WHERE isfinite(v) GROUP BY 1" % (bins - 1, c, qi(TABLE)), [lo, width]))
        return {"lo": lo, "hi": hi, "counts": [res.get(i, 0) for i in range(bins)]}

    def box(self, col):
        self.require_data()
        c = "TRY_CAST(%s AS DOUBLE)" % self.check_col(col)
        lo, hi, qs, n = self.q(
            "SELECT min(v), max(v), quantile_cont(v, [0.25, 0.5, 0.75]), count(v) FROM (SELECT %s AS v FROM %s) WHERE isfinite(v)"
            % (c, qi(TABLE)))[0]
        if not n:
            return {"n": 0}
        q1, med, q3 = qs
        iqr = q3 - q1
        wl, wh = max(lo, q1 - 1.5 * iqr), min(hi, q3 + 1.5 * iqr)
        outs = [r[0] for r in self.q(
            "SELECT v FROM (SELECT %s AS v FROM %s) WHERE v < ? OR v > ? ORDER BY v LIMIT 250" % (c, qi(TABLE)), [wl, wh])]
        return {"n": n, "lo": lo, "hi": hi, "q1": q1, "med": med, "q3": q3, "outliers": outs}

    def scatter(self, x, y, limit=5000):
        self.require_data()
        xq, yq = self.check_col(x), self.check_col(y)
        limit = max(10, min(20000, int(limit or 5000)))
        res = self.q(
            "SELECT x, y FROM (SELECT TRY_CAST(%s AS DOUBLE) AS x, TRY_CAST(%s AS DOUBLE) AS y FROM %s) "
            "WHERE isfinite(x) AND isfinite(y) USING SAMPLE %d ROWS" % (xq, yq, qi(TABLE), limit))
        total = self.q(
            "SELECT count(*) FROM (SELECT TRY_CAST(%s AS DOUBLE) AS x, TRY_CAST(%s AS DOUBLE) AS y FROM %s) WHERE isfinite(x) AND isfinite(y)"
            % (xq, yq, qi(TABLE)))[0][0]
        return {"pairs": [{"x": r[0], "y": r[1]} for r in res], "total": total}

    def distinct(self, col, limit=500):
        self.require_data()
        cq = self.check_col(col)
        limit = max(1, min(5000, int(limit or 500)))
        res = self.q("SELECT CAST(%s AS VARCHAR) AS v, count(*) AS c FROM %s WHERE %s IS NOT NULL GROUP BY 1 ORDER BY c DESC, v LIMIT %d"
                     % (cq, qi(TABLE), cq, limit))
        return {"values": [r[0] for r in res]}

    def welch(self, g, y, a, b):
        self.require_data()
        gq, yq = self.check_col(g), self.check_col(y)
        res = self.q(
            "SELECT k, count(v), avg(v), var_samp(v) FROM (SELECT CAST(%s AS VARCHAR) AS k, TRY_CAST(%s AS DOUBLE) AS v FROM %s) "
            "WHERE k IN (?, ?) AND isfinite(v) GROUP BY k" % (gq, yq, qi(TABLE)), [str(a), str(b)])
        d = {r[0]: {"n": r[1], "mean": r[2], "var": r[3]} for r in res}
        empty = {"n": 0, "mean": None, "var": None}
        return {"a": d.get(str(a), empty), "b": d.get(str(b), empty)}

    def regression(self, x, y):
        self.require_data()
        xq, yq = self.check_col(x), self.check_col(y)
        r = self.q(
            "SELECT regr_count(yv, xv), regr_slope(yv, xv), regr_intercept(yv, xv), corr(yv, xv), regr_sxx(yv, xv), regr_syy(yv, xv) "
            "FROM (SELECT TRY_CAST(%s AS DOUBLE) AS xv, TRY_CAST(%s AS DOUBLE) AS yv FROM %s) WHERE isfinite(xv) AND isfinite(yv)"
            % (xq, yq, qi(TABLE)))[0]
        return {"n": r[0], "slope": plain(r[1]), "intercept": plain(r[2]), "r": plain(r[3]),
                "ssx": plain(r[4]), "ssy": plain(r[5])}
