"""Shared constants and small helpers used across the engine."""

import datetime
import decimal
import math
import os
import re

TABLE = "data"
PAGE_MAX = 500
PREVIEW_ROWS = 20
SQL_UI_ROWS = 1000
EXACT_DISTINCT_LIMIT = 2_000_000
CHUNK = 1024 * 1024

NUMERIC_PREFIXES = (
    "TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UTINYINT",
    "USMALLINT", "UINTEGER", "UBIGINT", "UHUGEINT", "FLOAT", "DOUBLE",
    "DECIMAL", "REAL",
)
DATE_PREFIXES = ("DATE", "TIMESTAMP", "TIME")


class UserError(Exception):
    """An error whose message is safe and useful to show in the UI."""



def qi(name):
    """Quote an SQL identifier."""
    return '"' + str(name).replace('"', '""') + '"'


def is_numeric_type(t):
    return str(t).upper().startswith(NUMERIC_PREFIXES)


def is_date_type(t):
    return str(t).upper().startswith(DATE_PREFIXES)


def is_text_type(t):
    return str(t).upper() == "VARCHAR"


def is_nested_type(t):
    u = str(t).upper()
    return u.startswith(("STRUCT", "MAP", "UNION")) or u.endswith("]")


def plain(v):
    """Convert a DuckDB value into something json.dumps accepts."""
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, decimal.Decimal):
        f = float(v)
        return f if math.isfinite(f) else None
    if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
        return v.isoformat()
    if isinstance(v, datetime.timedelta):
        return str(v)
    if isinstance(v, (bytes, bytearray)):
        return v.hex()
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    if isinstance(v, dict):
        return {str(k): plain(x) for k, x in v.items()}
    return str(v)


def unique_headers(raw, count):
    """Same rules as the browser: blank -> column_N, duplicates -> name_2 (case-insensitive)."""
    seen, out = set(), []
    for i in range(count):
        v = raw[i] if raw and i < len(raw) and raw[i] is not None else ""
        h = str(v).strip() or "column_%d" % (i + 1)
        base, n = h, 2
        while h.lower() in seen:
            h = "%s_%d" % (base, n)
            n += 1
        seen.add(h.lower())
        out.append(h)
    return out


def safe_filename(name):
    name = os.path.basename(str(name or "dataset"))
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .") or "dataset"
    return name[:120]


def file_ext(name):
    return os.path.splitext(str(name))[1].lower().lstrip(".")


def lit(value):
    """Quote a SQL string literal."""
    return "'" + str(value).replace("'", "''") + "'"
