"""Column profiling: counts, distinct values, quartiles, outliers, duplicates."""

import re

from .util import EXACT_DISTINCT_LIMIT, TABLE, is_date_type, is_numeric_type, plain, qi


class ProfileMixin:
    def meta(self):
        if self.meta_cache is not None:
            return self.meta_cache
        self.require_data()
        cols = self.columns()
        n = self.row_count()
        exact = n <= EXACT_DISTINCT_LIMIT
        parts, layout = [], []
        for c, t in cols:
            id_ = qi(c)
            parts.append("count(%s)" % id_)
            parts.append(("count(DISTINCT %s)" if exact else "approx_count_distinct(%s)") % id_)
            if is_numeric_type(t):
                parts.append(
                    "avg(%s), min(%s), max(%s), stddev_samp(%s), quantile_cont(%s, [0.25, 0.5, 0.75])"
                    % (id_, id_, id_, id_, id_))
                layout.append((c, t, "num"))
            else:
                parts.append("approx_top_k(%s, 1)" % id_)
                layout.append((c, t, "cat"))
        row = self.q("SELECT %s FROM %s" % (", ".join(parts), qi(TABLE)))[0] if parts else []
        out, k = [], 0
        for c, t, kind in layout:
            nonnull, distinct = row[k], row[k + 1]
            k += 2
            info = {
                "name": c, "type": t, "numeric": kind == "num",
                "date": is_date_type(t) or bool(re.search("date|time", c, re.I)),
                "nonEmpty": nonnull, "missing": n - nonnull,
                "distinct": distinct, "distinctExact": exact,
            }
            if kind == "num":
                avg, mn, mx, sd, qs = row[k:k + 5]
                k += 5
                qs = qs or [None, None, None]
                info.update({
                    "mean": plain(avg), "min": plain(mn), "max": plain(mx),
                    "sd": plain(sd) if nonnull >= 2 else 0,
                    "q1": plain(qs[0]), "median": plain(qs[1]), "q3": plain(qs[2]),
                })
            else:
                top = row[k]
                k += 1
                info["top"] = plain(top[0]) if top else None
                info["topApprox"] = (distinct or 0) > 1000
            out.append(info)
        # approximate distinct counts are replaced by exact ones where cheap
        if not exact:
            small = [i for i in out if (i["distinct"] or 0) <= 100000]
            if small:
                res = self.q("SELECT %s FROM %s" % (
                    ", ".join("count(DISTINCT %s)" % qi(i["name"]) for i in small), qi(TABLE)))[0]
                for i, v in zip(small, res):
                    i["distinct"], i["distinctExact"] = v, True
        # exact most-frequent value wherever the column has few enough values
        modal = [i for i in out if not i["numeric"] and i["distinctExact"] and (i["distinct"] or 0) <= 100000]
        if modal:
            res = self.q("SELECT %s FROM %s" % (
                ", ".join("mode(%s)" % qi(i["name"]) for i in modal), qi(TABLE)))[0]
            for i, v in zip(modal, res):
                i["top"], i["topApprox"] = plain(v), False
        for i in out:
            if not i["numeric"] and i not in modal:
                i["topApprox"] = True
        # Tukey IQR outlier counts need the quartiles first
        nums = [i for i in out if i["numeric"] and i["q1"] is not None]
        if nums:
            exprs = []
            for i in nums:
                iqr = i["q3"] - i["q1"]
                lo, hi = i["q1"] - 1.5 * iqr, i["q3"] + 1.5 * iqr
                exprs.append("count(*) FILTER (WHERE %s < %r OR %s > %r)" % (qi(i["name"]), lo, qi(i["name"]), hi))
            res = self.q("SELECT %s FROM %s" % (", ".join(exprs), qi(TABLE)))[0]
            for i, v in zip(nums, res):
                i["outliers"] = v
        for i in out:
            if i["numeric"]:
                i.setdefault("outliers", 0)
        dups = 0
        if cols:
            distinct_rows = self.q("SELECT count(*) FROM (SELECT DISTINCT * FROM %s)" % qi(TABLE))[0][0]
            dups = n - distinct_rows
        self.meta_cache = {
            "name": self.state.get("name") or "dataset",
            "version": self.data_version,
            "updatedAt": self.state.get("updated_at"),
            "linkedStream": self.state.get("linked_stream"),
            "rows": n,
            "columns": out,
            "missingTotal": sum(i["missing"] for i in out),
            "duplicates": dups,
        }
        return self.meta_cache
