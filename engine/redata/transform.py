"""Operations that rewrite the active dataset: cleaning and derived columns."""

from .formula import formula_to_sql
from .util import TABLE, UserError, is_numeric_type, is_text_type, qi


class TransformMixin:
    # ---- changing data -----------------------------------------------------------
    def clean(self, op, **kw):
        self.require_data()
        cols = self.columns()
        if op == "drop_missing":
            before = self.row_count()
            cond = " AND ".join("%s IS NOT NULL" % qi(c) for c, _ in cols)
            self.rebuild("* EXCLUDE (__redata_rid)", "WHERE " + cond)
            return "Dropped %s rows with missing values." % format(before - self.row_count(), ",")
        if op == "fill":
            strategy = kw.get("strategy")
            marker = str(kw.get("marker") or "Unknown")
            meta = self.meta()
            missing = {i["name"]: i for i in meta["columns"]}
            select, changed = [], 0
            for c, t in cols:
                m = missing[c]["missing"]
                id_ = qi(c)
                if m and strategy == "marker":
                    if is_text_type(t):
                        select.append("COALESCE(%s, %s) AS %s" % (id_, self._lit(marker), id_))
                    else:
                        select.append("COALESCE(CAST(%s AS VARCHAR), %s) AS %s" % (id_, self._lit(marker), id_))
                    changed += m
                elif m and is_numeric_type(t) and strategy in ("zero", "mean", "median"):
                    if strategy == "zero":
                        select.append("COALESCE(%s, 0) AS %s" % (id_, id_))
                    else:
                        stat = missing[c]["mean"] if strategy == "mean" else missing[c]["median"]
                        if stat is None:
                            select.append(id_)
                            continue
                        select.append("COALESCE(CAST(%s AS DOUBLE), %r) AS %s" % (id_, float(stat), id_))
                    changed += m
                else:
                    select.append(id_)
            if changed:
                self.rebuild(", ".join(select))
            return "Filled %s missing cells. Review the changed data." % format(changed, ",")
        if op == "dedupe":
            before = self.row_count()
            part = ", ".join(qi(c) for c, _ in cols)
            self.rebuild("* EXCLUDE (__redata_rid)",
                         "QUALIFY row_number() OVER (PARTITION BY %s ORDER BY __redata_rid) = 1" % part)
            return "Removed %s exact duplicate rows." % format(before - self.row_count(), ",")
        if op == "trim":
            texts = [c for c, t in cols if is_text_type(t)]
            if not texts:
                return "Normalized 0 text cells."
            new = {c: "NULLIF(regexp_replace(trim(%s), '\\s+', ' ', 'g'), '')" % qi(c) for c in texts}
            count_expr = " + ".join("count(*) FILTER (WHERE %s IS DISTINCT FROM %s)" % (qi(c), new[c]) for c in texts)
            changes = self.q("SELECT %s FROM %s" % (count_expr, qi(TABLE)))[0][0]
            if changes:
                self.rebuild(", ".join("%s AS %s" % (new[c], qi(c)) if c in new else qi(c) for c, _ in cols))
            return "Normalized %s text cells." % format(changes, ",")
        if op == "drop_column":
            col = kw.get("column")
            self.check_col(col)
            if len(cols) <= 1:
                raise UserError("The dataset needs at least one column.")
            self.q("ALTER TABLE %s DROP COLUMN %s" % (qi(TABLE), qi(col)))
            self.changed()
            return "Removed column " + str(col)
        raise UserError("Unknown cleaning action.")

    def formula(self, name, expression):
        self.require_data()
        name = str(name or "").strip()
        if not name or not str(expression or "").strip():
            raise UserError("Enter a new column name and expression.")
        names = self.col_names()
        if name.lower() in (c.lower() for c in names):
            raise UserError("That column already exists. Choose a new name.")
        sql_expr = formula_to_sql(str(expression), names)
        self.q(
            "CREATE OR REPLACE TABLE %s AS SELECT * EXCLUDE (__redata_rid, __redata_val), "
            "CASE WHEN isfinite(__redata_val) THEN __redata_val END AS %s "
            "FROM (SELECT *, rowid AS __redata_rid, CAST(%s AS DOUBLE) AS __redata_val FROM %s) ORDER BY __redata_rid"
            % (qi(TABLE), qi(name), sql_expr, qi(TABLE)))
        self.changed()
        changed = self.q("SELECT count(%s) FROM %s" % (qi(name), qi(TABLE)))[0][0]
        return {"changed": changed, "rows": self.row_count()}
