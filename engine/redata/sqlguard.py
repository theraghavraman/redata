"""Read-only guard for the SQL lab.

The SQL lab is a query surface over the loaded dataset and the staging
tables. It must not change data and must not read files or URLs.
"""

import re

import duckdb

from .util import UserError

# Table functions that read from the filesystem or network. The SQL lab is a
# read-only *query* surface over the loaded dataset, not a file browser, so
# these are rejected even inside an otherwise-valid SELECT (incl. CTEs/subqueries).
FILE_FUNCTIONS = (
    "read_csv", "read_csv_auto", "read_json", "read_json_auto", "read_ndjson",
    "read_ndjson_auto", "read_json_objects", "read_parquet", "parquet_scan",
    "parquet_metadata", "parquet_schema", "parquet_file_metadata",
    "parquet_kv_metadata", "read_text", "read_blob", "glob", "sniff_csv",
    "read_xlsx", "delta_scan", "iceberg_scan",
    # added: readers that were missing from the denylist entirely
    "read_json_objects_auto", "read_ndjson_objects", "read_csv_objects",
    "sqlite_scan", "sqlite_attach", "postgres_scan", "postgres_attach",
    "mysql_scan", "mysql_attach", "st_read", "read_arrow", "read_feather",
)
_FILE_FUNC_RE = re.compile(r"\b(" + "|".join(FILE_FUNCTIONS) + r")\s*\(", re.IGNORECASE)
_IDENT_QUOTES = ('"', "`", "[", "]")


def _strip_identifier_quotes(sql):
    """Drop identifier quoting so a quoted function name cannot dodge the denylist.

    DuckDB resolves "read_text"('x') to the same function as read_text('x'), but
    the regex above only matches the bare name, so quoting was a trivial bypass.
    """
    out = str(sql)
    for quote in _IDENT_QUOTES:
        if quote in out:
            out = out.replace(quote, "")
    return out


def read_only_statement(con, query):
    """Return the last statement of ``query`` after checking every statement is read-only."""
    query = str(query or "").strip()
    if not query:
        raise UserError("Enter a SQL query.")
    try:
        stmts = con.extract_statements(query)
    except duckdb.Error as e:
        raise UserError(str(e))
    if not stmts:
        raise UserError("Enter a SQL query.")
    allowed = {"StatementType.SELECT", "StatementType.EXPLAIN"}
    for s in stmts:
        if str(s.type) not in allowed:
            raise UserError(
                "The SQL lab is read-only: only SELECT-style queries run here (DESCRIBE, SUMMARIZE and EXPLAIN "
                "are fine). Use Clean & transform or Formula builder to change the data.")
        if _FILE_FUNC_RE.search(_strip_identifier_quotes(s.query)):
            raise UserError(
                "The SQL lab queries the loaded dataset only. File- or URL-reading functions "
                "(read_csv, read_parquet, read_text, glob, …) are not allowed here. "
                "Use Import data or a Connection to bring a file in.")
    return stmts[-1]
